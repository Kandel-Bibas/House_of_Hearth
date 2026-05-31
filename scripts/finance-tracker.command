#!/bin/bash
# macOS double-clickable launcher for House of Hearth.
# Symlink this onto your Desktop, e.g.:
#   ln -s "$(pwd)/scripts/finance-tracker.command" ~/Desktop/

set -e

# Resolve this script's real location (it may be symlinked to the Desktop),
# then derive the project root as its parent directory.
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
PROJECT="$(cd -P "$(dirname "$SOURCE")/.." && pwd)"

cd "$PROJECT"
echo "House of Hearth — starting..."
exec make dev
