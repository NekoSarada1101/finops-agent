import logging
import subprocess

from finops_common.cpu import estimate_cpu_power_from_util
from finops_common.report import report_metrics as send_power_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CPU_NAME = "AMD Ryzen 7 9700X"
CPU_IDLE_POWER_W = 15.0
CPU_MAX_POWER_W = 88.0


def get_cpu_power() -> tuple[str, float]:
    """Windows環境のCPU使用率を計測し、Ryzen 7 9700Xの特性から消費電力(W)を推論する"""
    return estimate_cpu_power_from_util(
        CPU_NAME,
        CPU_IDLE_POWER_W,
        CPU_MAX_POWER_W,
        fallback_idle=CPU_IDLE_POWER_W,
    )


def get_gpu_power() -> list[dict]:
    """nvidia-smiからGPUの消費電力を取得"""
    try:
        cmd = ["nvidia-smi", "--query-gpu=index,name,power.draw", "--format=csv,noheader,nounits"]
        result = subprocess.check_output(cmd, encoding="utf-8", text=True)

        gpus = []
        for line in result.strip().split("\n"):
            if not line:
                continue
            idx, name, power = map(str.strip, line.split(","))
            gpus.append({
                "gpu_index": int(idx),
                "gpu_name": name,
                "power_draw_w": float(power),
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
