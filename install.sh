#!/usr/bin/env bash
# WhatsGene installer (macOS and Linux): pastes the tool onto this machine
# and starts it. Re-running updates the checkout and restarts.
#   curl -fsSL https://raw.githubusercontent.com/JUNXUN11/WhatsGene/main/install.sh | bash
# Override with WHATSGENE_DIR / WHATSGENE_REPO_URL if you keep a fork.
set -euo pipefail

DIR="${WHATSGENE_DIR:-$HOME/WhatsGene}"
REPO="${WHATSGENE_REPO_URL:-https://github.com/JUNXUN11/WhatsGene.git}"

missing=""
for tool in git python3 npm; do
  command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"
done
if [ -n "$missing" ]; then
  echo "WhatsGene needs these programs first:$missing" >&2
  echo "  Mac:     install Xcode Command Line Tools, then Node.js 20+," >&2
  echo "           then: brew install node python ncbi-blast  (or blast via brew install blast)" >&2
  echo "  Ubuntu:  sudo apt-get install -y git python3 python3-venv nodejs npm ncbi-blast+" >&2
  exit 1
fi

if [ -d "$DIR/.git" ]; then
  echo "==> WhatsGene already at $DIR; updating"
  git -C "$DIR" pull --ff-only
else
  echo "==> Downloading WhatsGene to $DIR"
  git clone "$REPO" "$DIR"
fi

echo "==> Starting WhatsGene (first run builds the website and prints a login password)"
cd "$DIR" && exec ./start
