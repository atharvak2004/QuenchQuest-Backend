#!/usr/bin/env bash
# Build and deploy the QuenchQuest website from GitHub, on this server. Run as `ubuntu`:
#
#   bash /var/www/quenchquest-api/deploy/deploy-web.sh
#
# Uses the website repo's own deploy/build-release.sh and qq-deploy (deploy-release.sh).
# - Node 22 comes from /opt/node22, so the system Node (other apps) is never touched.
# - The build runs at the lowest CPU and disk priority with a memory cap, so other
#   apps on the server stay responsive while it runs.
set -euo pipefail

SRC="/var/www/quenchquest-web-src"
NODE_DIR="/opt/node22"
WEB_PORT="3100"
BUILD_MEMORY_MB="${BUILD_MEMORY_MB:-1024}"

export PATH="$NODE_DIR/bin:$PATH"
[[ -x "$NODE_DIR/bin/node" ]] || { echo "✗ $NODE_DIR/bin/node not found (see DEPLOYMENT.md, Node 22)." >&2; exit 1; }

FREE_MB="$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)"
SWAP_MB="$(awk '/SwapFree/ {print int($2/1024)}' /proc/meminfo)"
if (( FREE_MB + SWAP_MB < BUILD_MEMORY_MB + 300 )); then
  echo "✗ Only ${FREE_MB} MB RAM + ${SWAP_MB} MB swap free; the build needs about $((BUILD_MEMORY_MB + 300)) MB." >&2
  echo "  Add swap (DEPLOYMENT.md step 5.2) so the build can't squeeze other apps." >&2
  exit 1
fi

cd "$SRC"
echo "→ Pulling the latest website code"
git pull --ff-only

echo "→ Building at low priority (node $(node -v), memory cap ${BUILD_MEMORY_MB} MB)"
NODE_OPTIONS="--max-old-space-size=${BUILD_MEMORY_MB}" nice -n 19 ionice -c3 bash deploy/build-release.sh

ARCHIVE="$(ls -1t release/quenchquest-web-*.tar.gz | head -1)"
echo "→ Deploying $ARCHIVE on port $WEB_PORT"
sudo PORT="$WEB_PORT" /usr/local/bin/qq-deploy "$ARCHIVE"

# Keep the 3 newest archives in the checkout (qq-deploy keeps its own 5 releases)
ls -1t release/quenchquest-web-*.tar.gz | tail -n +4 | xargs -r rm -f
