import os
import time
import glob
import shutil
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from google.cloud import storage
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# インフラ設定
PROJECT_ID = os.getenv("PROJECT_ID", "")
BUCKET_NAME = os.getenv("BUCKET_NAME", "")
ENEOS_USERNAME = os.getenv("ENEOS_USERNAME", "")
ENEOS_PASSWORD = os.getenv("ENEOS_PASSWORD", "")

# ダウンロード先の一時ディレクトリ（絶対パスで指定すること）
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.abspath(os.path.join(os.getcwd(), "tmp_downloads"))


def _chrome_for_testing_roots() -> list[str]:
    roots: list[str] = []
    if home := os.getenv("HOME"):
        roots.append(os.path.join(home, ".local/share/chrome-for-testing"))
    roots.append(os.path.expanduser("~/.local/share/chrome-for-testing"))
    roots.append(os.path.join(_PROJECT_DIR, ".chrome"))
    return list(dict.fromkeys(roots))


def _find_chrome_for_testing() -> str | None:
    for cft_root in _chrome_for_testing_roots():
        if not os.path.isdir(cft_root):
            continue
        for ver in sorted(os.listdir(cft_root), reverse=True):
            candidate = os.path.join(cft_root, ver, "chrome-linux64", "chrome")
            if os.path.isfile(candidate):
                return candidate
    return None


def _resolve_chrome_binary() -> str:
    """システムまたはローカルの Chrome for Testing バイナリを解決する。"""
    if env_path := os.getenv("CHROME_BINARY"):
        if os.path.isfile(env_path):
            return env_path
        raise FileNotFoundError(f"CHROME_BINARY が見つかりません: {env_path}")

    for name in ("google-chrome-stable", "google-chrome", "chromium-browser", "chromium"):
        if path := shutil.which(name):
            return path

    if candidate := _find_chrome_for_testing():
        return candidate

    raise FileNotFoundError(
        "Chrome が見つかりません。google-chrome をインストールするか、"
        "Chrome for Testing を ~/.local/share/chrome-for-testing/ に配置し、"
        "または CHROME_BINARY 環境変数でパスを指定してください。"
    )


def _usage_list_button_label(dt: datetime) -> str:
    return f"{dt.year}年{dt.month}月{dt.day}日分使用量一覧"


def _navigate_to_usage_date(driver: webdriver.Chrome, wait: WebDriverWait, target: datetime) -> None:
    """使用量ページで表示日を target（JST の日付）に合わせる。"""
    target_label = _usage_list_button_label(target)
    wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "//button[contains(normalize-space(.), '分使用量一覧')]")
        )
    )

    for _ in range(31):
        labels = [
            b.text.strip()
            for b in driver.find_elements(
                By.XPATH, "//button[contains(normalize-space(.), '分使用量一覧')]"
            )
        ]
        if any(target_label in label for label in labels):
            logger.info(f"表示日を合わせました: {target_label}")
            return
        prev_btn = driver.find_element(By.XPATH, "//button[normalize-space(.)='前日']")
        _safe_click(driver, prev_btn)
        time.sleep(0.5)

    raise TimeoutError(f"使用量ページで対象日に遷移できませんでした: {target_label}")


def _safe_click(driver: webdriver.Chrome, element) -> None:
    """固定ヘッダー等による click intercepted を避けてクリックする。"""
    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
        element,
    )
    time.sleep(0.5)
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)


def setup_driver() -> webdriver.Chrome:
    """ヘッドレスChromeのセットアップ（ダウンロードの許可設定を含む）"""
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("window-size=1920x1080")

    # ヘッドレスモードでファイルの自動ダウンロードを許可
    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)
    options.binary_location = _resolve_chrome_binary()

    # Selenium Manager が binary_location の Chrome に一致する ChromeDriver を自動解決する
    driver = webdriver.Chrome(options=options)
    return driver


def scrape_and_upload():
    driver = None
    try:
        driver = setup_driver()
        wait = WebDriverWait(driver, 15)

        logger.info("ENEOSマイページにアクセスします...")
        driver.get("https://service.ouchi-eneos.jp/mypage/#/login/enter")

        # 1. ログイン処理
        wait.until(EC.presence_of_element_located((By.ID, "accountAuthenticationInfo"))).send_keys(ENEOS_USERNAME)
        driver.find_element(By.XPATH, "//*[@id='content']/div/div/div/div[2]/button").click()

        wait.until(EC.presence_of_element_located((By.ID, "ocYPswrd"))).send_keys(ENEOS_PASSWORD)
        driver.find_element(By.XPATH, "//*[@id='content']/div/div/div/div[1]/button").click()

        # ログイン完了（マイページ描画）を待機
        wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(text(), '原田　遼汰さま')]")))
        logger.info("ログイン成功。使用量ページへ遷移します。")

        # 2. 使用量ページへ遷移
        usage_nav = wait.until(EC.presence_of_element_located(
            (By.XPATH, "//app-header/header/nav/div[2]/ul/li[3]/button/div[1]")))
        _safe_click(driver, usage_nav)
        logger.info("使用量ページへ遷移しました。")

        JST = timezone(timedelta(hours=9))
        target_date = datetime.now(JST) - timedelta(days=1)
        logger.info(
            f"取得対象日（日本時間の一日前）: "
            f"{target_date.year}年{target_date.month}月{target_date.day}日"
        )

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "button.cmn_svg-download")))
        _navigate_to_usage_date(driver, wait, target_date)

        # CSV ダウンロード
        download_btn = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "button.cmn_svg-download"))
        )
        _safe_click(driver, download_btn)
        logger.info("ダウンロードボタンをクリックしました。ファイルの保存を待機します。")

        # 3. ローカルへのファイル保存を監視（ポーリング）
        downloaded_file = None
        for _ in range(15):
            time.sleep(1)
            files = glob.glob(os.path.join(DOWNLOAD_DIR, "*.csv"))
            # ダウンロード中のテンポラリファイル（.crdownload等）を除外
            valid_files = [f for f in files if not f.endswith(".crdownload")]
            if valid_files:
                # 最新のファイルを取得
                downloaded_file = max(valid_files, key=os.path.getctime)
                break

        if not downloaded_file:
            raise TimeoutError("CSVファイルのダウンロードが時間内に完了しませんでした。")

        filename = os.path.basename(downloaded_file)
        logger.info(f"ダウンロード完了: {filename}。GCSへのアップロードを開始します。")

        # 4. GCSへのアップロード
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)

        # DLしたCSVを読み込んでアップロード
        blob.upload_from_filename(downloaded_file, content_type="text/csv")
        logger.info(f"GCS (gs://{BUCKET_NAME}/{filename}) へのアップロードが完了しました。")

        # 5. ローカルの掃除
        os.remove(downloaded_file)

    except Exception as e:
        logger.error(f"スクレイピング処理中にエラーが発生しました: {e}")
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    scrape_and_upload()
