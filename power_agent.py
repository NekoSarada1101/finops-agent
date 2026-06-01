import logging
import subprocess
import time

from finops_common.cpu import estimate_cpu_power_from_util
from finops_common.report import report_metrics as send_power_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CPU_NAME = "Intel Core i5-11400F"
RAPL_PATH = "/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj"
CPU_IDLE_POWER_W = 10.0
CPU_MAX_POWER_W = 65.0


def get_cpu_power() -> tuple[str, float]:
    """
    Linux環境においてIntel RAPLからの物理電力取得を試み、
    失敗した場合は使用率に基づく論理推論へフォールバックする
    """
    try:
        with open(RAPL_PATH, "r") as f:
            energy1 = int(f.read().strip())

        time.sleep(1.0)  # 1秒間のエネルギー消費を測定

        with open(RAPL_PATH, "r") as f:
            energy2 = int(f.read().strip())

        # 1秒間の差分(マイクロジュール)を1,000,000で割り、ワット(W)に変換
        power_w = (energy2 - energy1) / 1_000_000.0

        if power_w >= 0:
            logger.info(f"Intel RAPL 物理計測: {power_w:.1f} W")
            return CPU_NAME, round(power_w, 2)

    except PermissionError:
        logger.warning("RAPLへのアクセス権限がありません。推論モードへ移行します。")
    except FileNotFoundError:
        logger.warning("RAPLインターフェースが存在しません。推論モードへ移行します。")
    except Exception as e:
        logger.warning(f"RAPL計測エラー: {e}。推論モードへ移行します。")

    return estimate_cpu_power_from_util(
        CPU_NAME,
        CPU_IDLE_POWER_W,
        CPU_MAX_POWER_W,
        fallback_idle=CPU_IDLE_POWER_W,
    )


def get_gpu_power() -> list[dict]:
    """nvidia-smiからGPUの消費電力と使用率を取得し、NAの場合は論理推論する"""
    try:
        cmd = [
            "nvidia-smi",
            "--query-gpu=index,name,power.draw,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]
        result = subprocess.check_output(cmd, encoding="utf-8", text=True)

        gpus = []
        for line in result.strip().split("\n"):
            if not line:
                continue

            parts = [p.strip() for p in line.split(",")]
            if len(parts) != 4:
                continue

            idx_str, name, power_str, util_str = parts
            idx = int(idx_str)

            try:
                utilization = float(util_str)
            except ValueError:
                utilization = 100.0

            try:
                power = float(power_str)
            except ValueError:
                if "1650" in name:
                    # GTX 1650: アイドル10W, 最大75Wとして使用率から推論
                    power = 10.0 + (65.0 * (utilization / 100.0))
                    logger.warning(
                        f"GPU {idx} ({name}) の電力(NA)を使用率 {utilization}% から "
                        f"{power:.1f} W と推論しました。"
                    )
                else:
                    logger.warning(f"GPU {idx} ({name}) の電力が取得不可。推論せず NULL 相当で記録します。")
                    power = None

            gpus.append({
                "gpu_index": idx,
                "gpu_name": name,
                "power_draw_w": round(power, 2) if power is not None else None,
            })
        return gpus
    except FileNotFoundError:
        logger.error("nvidia-smi が見つかりません。")
        return []
    except Exception as e:
        logger.error(f"GPU電力取得エラー: {e}")
        return []


def main() -> None:
    cpu_name, cpu_power_w = get_cpu_power()
    gpus = get_gpu_power()
    send_power_metrics(cpu_name, cpu_power_w, gpus)


if __name__ == "__main__":
    main()
