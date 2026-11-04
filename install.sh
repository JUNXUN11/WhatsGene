#!/usr/bin/env bash
# WhatsGene installer (macOS and Linux): pastes the tool onto this machine
# and starts it. Re-running updates the checkout and restarts.
#   curl -fsSL https://raw.githubusercontent.com/JUNXUN11/WhatsGene/main/install.sh | bash
# Override with WHATSGENE_DIR / WHATSGENE_REPO_URL if you keep a fork.
# Everything sits inside main(), called on the last line, so a download
# cut off halfway runs nothing instead of half a script.
set -euo pipefail

main() {
  local dir="${WHATSGENE_DIR:-$HOME/WhatsGene}"
  local repo="${WHATSGENE_REPO_URL:-https://github.com/JUNXUN11/WhatsGene.git}"

  local missing="" tool
  for tool in git python3 node npm; do
    command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"
  done
  if [ -n "$missing" ]; then
    echo "WhatsGene needs these programs first:$missing" >&2
    install_hint
    exit 1
  fi

  local too_old=""
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 12))' \
    || too_old="$too_old Python 3.12+ (found $(python3 --version 2>&1))"
  local node_major
  node_major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
  [ "$node_major" -ge 20 ] 2>/dev/null \
    || too_old="$too_old Node.js 20+ (found $(node --version 2>&1))"
  if [ -n "$too_old" ]; then
    echo "WhatsGene needs newer versions of:$too_old" >&2
    install_hint
    exit 1
  fi

  if [ -d "$dir/.git" ]; then
    echo "==> WhatsGene already at $dir; updating"
    git -C "$dir" pull --ff-only
  else
    echo "==> Downloading WhatsGene to $dir"
    git clone "$repo" "$dir"
  fi

  echo "==> Starting WhatsGene (first run builds the website)"
  cd "$dir" && exec ./start
}

install_hint() {
  echo "  Mac:     xcode-select --install, then: brew install git node python blast" >&2
  echo "  Ubuntu:  sudo apt-get install -y git python3 python3-venv nodejs npm ncbi-blast+" >&2
  echo "           (if apt's Node is older than 20, get Node from https://nodejs.org)" >&2
}

main "$@"
