import logging

import psutil

logger = logging.getLogger(__name__)


def estimate_cpu_power_from_util(
    cpu_name: str,
    idle_power: float,
    max_power: float,
    *,
    fallback_idle: float | None = None,
) -> tuple[str, float]:
    """CPU 使用率から消費電力(W)を線形補間で推論する。"""
    safe_idle = fallback_idle if fallback_idle is not None else idle_power
    try:
        cpu_util = psutil.cpu_percent(interval=1.0)
        power_w = idle_power + ((max_power - idle_power) * (cpu_util / 100.0))
        logger.info(f"CPU使用率: {cpu_util}% -> 推論電力: {power_w:.1f} W")
        return cpu_name, round(power_w, 2)
    except Exception as e:
        logger.error(f"CPU電力推論エラー: {e}")
        return cpu_name, safe_idle
