import logging
import socket
from datetime import datetime, timezone

import requests
from google.cloud import bigquery

from finops_common.config import FULL_TABLE_ID, PROJECT_ID, UPTIME_KUMA_PUSH_URL

logger = logging.getLogger(__name__)


def _gpu_power_total(gpus: list[dict]) -> float:
    total = 0.0
    for gpu in gpus:
        power = gpu.get("power_draw_w")
        if power is not None:
            total += power
    return total


def report_metrics(
    cpu_name: str,
    cpu_power_w: float | None,
    gpus: list[dict],
) -> None:
    """計測済みメトリクスを BigQuery に送信し、成功時は Uptime Kuma に通知する。"""
    hostname = socket.gethostname()

    if cpu_power_w is None:
        logger.warning(f"[{hostname}] CPU メトリクス取得失敗。送信をスキップします。")
        return

    total_gpu_power = _gpu_power_total(gpus)
    total_system_power = cpu_power_w + total_gpu_power

    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hostname": hostname,
        "cpu_name": cpu_name,
        "cpu_power_w": cpu_power_w,
        "gpus": gpus,
        "total_power_w": round(total_system_power, 2),
    }

    try:
        client = bigquery.Client(project=PROJECT_ID)
        errors = client.insert_rows_json(FULL_TABLE_ID, [row])

        if errors:
            logger.error(f"[{hostname}] BigQueryインサートエラー: {errors}")
            return

        logger.info(
            f"[{hostname}] FinOpsメトリクス送信成功: "
            f"合計 {total_system_power:.1f} W (CPU: {cpu_power_w}W / GPU: {total_gpu_power}W)"
        )

        if not UPTIME_KUMA_PUSH_URL:
            logger.debug("UPTIME_KUMA_PUSH_URL 未設定のため Uptime Kuma 通知をスキップします。")
            return

        try:
            requests.get(UPTIME_KUMA_PUSH_URL, timeout=10)
            logger.info("Uptime Kuma へハートビートを送信しました。")
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"Uptime Kuma への通知に失敗しましたが、BigQueryへの送信は完了しています: {e}"
            )
    except Exception as e:
        logger.error(f"BigQueryへの通信処理で例外発生: {e}")
