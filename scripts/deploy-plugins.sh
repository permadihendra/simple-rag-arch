#!/usr/bin/env bash
# deploy-plugins.sh — Install RAG memory plugins to platform directories
# Usage: ./deploy-plugins.sh [--dry-run]

set -e

DRY_RUN=false
[ "$1" = "--dry-run" ] && DRY_RUN=true

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PI_EXT_DIR="$HOME/.pi/agent/extensions/rag-memory"
OC_PLUGIN_DIR="$HOME/.openclaw/extensions/rag-memory"

echo "🧠 Deploying RAG Memory Plugins"
echo "   Project: $PROJECT_DIR"
echo ""

# ── Pi Code Extension ──────────────────────────────────────────────

echo "── Pi Code Extension ──"
echo "   Source: $PROJECT_DIR/plugins/pi-code/rag-memory/"
echo "   Target: $PI_EXT_DIR"

if [ "$DRY_RUN" = true ]; then
  echo "   [dry-run] Would copy to $PI_EXT_DIR"
else
  mkdir -p "$HOME/.pi/agent/extensions"
  # Remove old if exists, then copy
  rm -rf "$PI_EXT_DIR"
  cp -r "$PROJECT_DIR/plugins/pi-code/rag-memory" "$PI_EXT_DIR"
  echo "   ✅ Installed ($(find "$PI_EXT_DIR" -type f | wc -l) files)"
fi

echo ""

# ── OpenClaw Plugin ────────────────────────────────────────────────

echo "── OpenClaw Plugin ──"
echo "   Source: $PROJECT_DIR/plugins/openclaw/rag-memory/"
echo "   Target: $OC_PLUGIN_DIR"

if [ "$DRY_RUN" = true ]; then
  echo "   [dry-run] Would copy to $OC_PLUGIN_DIR"
else
  mkdir -p "$HOME/.openclaw/extensions"
  rm -rf "$OC_PLUGIN_DIR"
  cp -r "$PROJECT_DIR/plugins/openclaw/rag-memory" "$OC_PLUGIN_DIR"
  echo "   ✅ Installed ($(find "$OC_PLUGIN_DIR" -type f | wc -l) files)"

  # Refresh OpenClaw plugin registry so it picks up changes
  if command -v openclaw &>/dev/null; then
    echo "   🔄 Refreshing plugin registry..."
    openclaw plugins registry --refresh 2>&1 | tail -1
  fi
fi

echo ""
echo "✅ Done. Restart pi or run /reload to pick up extension changes."
echo "   OpenClaw changes are live after registry refresh."
