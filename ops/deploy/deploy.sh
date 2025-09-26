
---

## ops/deploy/deploy.sh
```bash
#!/usr/bin/env bash
# Simple pull-and-restart script for the VM (run as the service user or via sudo)

set -euo pipefail

REPO_DIR="/home/your-ubuntu-user/ninjaone-ai-agent"  # <<< EDIT
SERVICE_NAME="ninja-agent"                            # <<< matches systemd unit
PYTHON_BIN="$REPO_DIR/.venv/bin/python"
PIP_BIN="$REPO_DIR/.venv/bin/pip"

cd "$REPO_DIR"
echo "[deploy] pulling latest..."
git pull --ff-only

echo "[deploy] installing deps..."
$PIP_BIN install -r requirements.txt

echo "[deploy] DB migrate/init if needed..."
$PYTHON_BIN - <<'PY'
from storage import init_db
init_db()
print("DB ready.")
PY

echo "[deploy] restarting service..."
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
echo "[deploy] done."
