#!/usr/bin/env bash
# Update the QuenchQuest API on the server from GitHub. Run as the `ubuntu` user:
#
#   bash /var/www/quenchquest-api/deploy/deploy-api.sh
#
# It only touches QuenchQuest: pulls the code, installs requirements, migrates
# (manage.py runs as the qqapi user, which owns .env and the static/media folders),
# collects static files and gracefully reloads quenchquest-api (no dropped requests).
set -euo pipefail

APP="/var/www/quenchquest-api"
SERVICE="quenchquest-api"
HEALTH_URL="http://127.0.0.1:8081/api/website/settings/"

cd "$APP"
echo "→ Pulling the latest code"
git pull --ff-only

echo "→ Installing requirements"
.venv/bin/pip install --quiet -r requirements.txt

echo "→ Checking settings"
sudo -u qqapi .venv/bin/python manage.py check

echo "→ Migrating the database"
sudo -u qqapi .venv/bin/python manage.py migrate --noinput

echo "→ Collecting static files"
sudo -u qqapi .venv/bin/python manage.py collectstatic --noinput --verbosity 0

echo "→ Reloading $SERVICE (graceful)"
sudo systemctl reload "$SERVICE"

for _ in $(seq 1 20); do
  if curl -fsS -o /dev/null --max-time 5 "$HEALTH_URL"; then
    echo "✓ API is up: $(git log -1 --format='%h %s')"
    exit 0
  fi
  sleep 1
done
echo "✗ API isn't answering. Logs: journalctl -u $SERVICE -n 100" >&2
exit 1
