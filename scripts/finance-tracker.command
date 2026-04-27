#!/bin/bash
# macOS double-clickable launcher for Finance Tracker.
# Symlinked to ~/Desktop/Finance Tracker.command.

set -e
PROJECT="/Users/bibas/personal/finance-tracker"

cd "$PROJECT"
echo "Finance Tracker — starting..."
exec make dev
