#!/usr/bin/env bash
# Development only: open a plugin route in Game Mode (optional) and take a screenshot of the handheld.
# Usage: scripts/dev/ui-shot.sh deck@<host> [route] [out.png] [scroll-to-bottom:0|1]
#   e.g. scripts/dev/ui-shot.sh deck@10.10.10.21 /wow-addons/get out/get.png 1
set -euo pipefail
HOST="${1:?usage: ui-shot.sh user@host [route] [out.png] [scroll]}"
ROUTE="${2:-}"; OUT="${3:-out/ui-shot.png}"; SCROLL="${4:-0}"
DIR="$(cd "$(dirname "$0")" && pwd)"
scp -q "$DIR/cdp.py" "$HOST:/tmp/wa-cdp.py"
ssh "$HOST" "ROUTE='$ROUTE' SCROLL='$SCROLL' bash -s" <<'REMOTE'
set -e
if [ -n "$ROUTE" ]; then
  python3 /tmp/wa-cdp.py SharedJSContext "DFL.Navigation.Navigate('/library/home'); new Promise(r => setTimeout(() => { DFL.Navigation.Navigate('$ROUTE'); r('ok'); }, 900))" >/dev/null
  sleep 2.5
fi
if [ "$SCROLL" = "1" ]; then
  python3 /tmp/wa-cdp.py "Big-Picture-Modus" '(() => { const c = [...document.querySelectorAll("div[style*=\"overflow-y\"]")].pop(); if (c) c.scrollTo(0, c.scrollHeight); return !!c; })()' >/dev/null
  sleep 1
fi
rm -f /tmp/wa-shot.png
gamescopectl screenshot /tmp/wa-shot.png >/dev/null 2>&1
for i in $(seq 1 10); do [ -s /tmp/wa-shot.png ] && break; sleep 0.5; done
REMOTE
mkdir -p "$(dirname "$OUT")"
scp -q "$HOST:/tmp/wa-shot.png" "$OUT"
echo "saved $OUT"
