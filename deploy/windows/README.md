# メイン PC（Windows）— 電力エージェント

## セットアップ

1. リポジトリをクローンし、仮想環境を作成する。
2. `pip install -r requirements.txt`
3. `credentials.json` と `.env` を配置する（`.env.example` を参照）。
4. `.env` に **メイン PC 用**の `UPTIME_KUMA_PUSH_URL` を設定する。

## タスクスケジューラ

- **プログラム**: `venv\Scripts\python.exe`
- **引数**: `power_agent_win.py` のフルパス
- **開始**: リポジトリのルート（`finops-agent`）

`power_agent.py` は Linux（サブ PC）用です。Windows では `power_agent_win.py` を実行してください。
