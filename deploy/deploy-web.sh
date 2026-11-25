#!/usr/bin/env bash
# Build and deploy the QuenchQuest website from GitHub, on this server. Run as `ubuntu`:
#
#   bash /var/www/quenchquest-api/deploy/deploy-web.sh
#
# Uses the website repo's own deploy/build-release.sh and qq-deploy (deploy-release.sh).
# - Node 22 comes from /opt/node22, so the system Node (other apps) is never touched.
# - The build runs in its own systemd scope with a hard memory limit, a CPU cap and
#   the lowest I/O weight. When it needs more memory it swaps out ITS OWN pages, never
#   other apps' (e.g. Kavya), and if it still runs out only the build is stopped.
set -euo pipefail

SRC="/var/www/quenchquest-web-src"
NODE_DIR="/opt/node22"
WEB_PORT="3100"
BUILD_MEMORY_MAX="${BUILD_MEMORY_MAX:-700M}"    # RAM the build may use; the rest goes to swap
BUILD_HEAP_MB="${BUILD_HEAP_MB:-1024}"          # Node heap cap (can exceed RAM cap: it swaps)
BUILD_CPU="${BUILD_CPU:-60%}"                   # of one core; leaves CPU for other apps

[[ -x "$NODE_DIR/bin/node" ]] || { echo "✗ $NODE_DIR/bin/node not found (see DEPLOYMENT.md, Node 22)." >&2; exit 1; }

SWAP_MB="$(awk '/SwapFree/ {print int($2/1024)}' /proc/meminfo)"
if (( SWAP_MB < 1200 )); then
  echo "✗ Only ${SWAP_MB} MB swap free; the capped build needs about 1.2 GB of swap to spill into." >&2
  echo "  Add swap (DEPLOYMENT.md step 5.2) first." >&2
  exit 1
fi

cd "$SRC"
echo "→ Pulling the latest website code"
git pull --ff-only

echo "→ Building in a capped scope (RAM ${BUILD_MEMORY_MAX}, CPU ${BUILD_CPU}, lowest I/O priority)."
echo "  On a small server this can take 10–20 minutes; other apps keep running normally."
sudo systemd-run --scope --quiet --unit="quenchquest-web-build-$(date +%s)" \
  -p MemoryMax="$BUILD_MEMORY_MAX" -p MemorySwapMax=2G -p CPUQuota="$BUILD_CPU" -p IOWeight=10 \
  sudo -u "$(id -un)" env \
    "PATH=$NODE_DIR/bin:/usr/local/bin:/usr/bin:/bin" \
    "HOME=$HOME" \
    "NODE_OPTIONS=--max-old-space-size=${BUILD_HEAP_MB}" \
    "NEXT_TELEMETRY_DISABLED=1" \
    nice -n 19 bash deploy/build-release.sh

ARCHIVE="$(ls -1t release/quenchquest-web-*.tar.gz | head -1)"
echo "→ Deploying $ARCHIVE on port $WEB_PORT"
sudo env PORT="$WEB_PORT" /usr/local/bin/qq-deploy "$ARCHIVE"

# Keep the 3 newest archives in the checkout (qq-deploy keeps its own 5 releases)
ls -1t release/quenchquest-web-*.tar.gz | tail -n +4 | xargs -r rm -f
