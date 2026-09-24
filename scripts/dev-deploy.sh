#!/usr/bin/env bash
# Build, copy to the handheld and restart Decky Loader.
# Usage: scripts/dev-deploy.sh deck@<host>   (key auth and passwordless sudo required)
set -euo pipefail
HOST="${1:?usage: dev-deploy.sh user@host}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
NAME="WoW Addons"
export PATH="/opt/homebrew/bin:$PATH"
pnpm build >/dev/null
rm -rf out/deploy; mkdir -p "out/deploy/$NAME/dist"
cp plugin.json package.json main.py decky.pyi LICENSE README.md minisign.pub "out/deploy/$NAME/" 2>/dev/null || true
cp dist/index.js "out/deploy/$NAME/dist/"
cp -R py_modules "out/deploy/$NAME/py_modules"
find "out/deploy/$NAME" -name "__pycache__" -type d -prune -exec rm -rf {} +
ssh "$HOST" 'rm -rf /tmp/wow-addons-deploy && mkdir -p /tmp/wow-addons-deploy'
COPYFILE_DISABLE=1 tar -C out/deploy --exclude "._*" --exclude ".DS_Store" -cf - "$NAME" | ssh "$HOST" 'tar -C /tmp/wow-addons-deploy -xf -'
ssh "$HOST" 'set -e; sudo -n rm -rf "$HOME/homebrew/plugins/WoW Addons"; sudo -n mv "/tmp/wow-addons-deploy/WoW Addons" "$HOME/homebrew/plugins/WoW Addons"; sudo -n chown -R deck:deck "$HOME/homebrew/plugins/WoW Addons"; sudo -n systemctl restart plugin_loader; echo "deployed, plugin_loader restarted"'
