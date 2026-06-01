import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
DATASET_ID = os.getenv("BQ_DATASET_ID", "")
TABLE_ID = os.getenv("BQ_POWER_TABLE_ID", "")
FULL_TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"
UPTIME_KUMA_PUSH_URL = os.getenv("UPTIME_KUMA_PUSH_URL", "")
