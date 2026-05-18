#!/usr/bin/env bash
# toggle-pi-rag.sh — Enable/disable the Pi Code RAG memory extension
# Usage: ./toggle-pi-rag.sh [on|off|status]

EXT_DIR="$HOME/.pi/agent/extensions/rag-memory"
EXT_DISABLED="$HOME/.pi/agent/extensions/rag-memory.disabled"

case "${1:-status}" in
  on|enable)
    if [ -d "$EXT_DISABLED" ]; then
      mv "$EXT_DISABLED" "$EXT_DIR"
      echo "✅ Pi RAG extension enabled"
      echo "   Restart pi or run /reload to apply"
    elif [ -d "$EXT_DIR" ]; then
      echo "ℹ️  Pi RAG extension already enabled"
    else
      echo "❌ Extension not found at $EXT_DIR or $EXT_DISABLED"
      exit 1
    fi
    ;;
  off|disable)
    if [ -d "$EXT_DIR" ]; then
      mv "$EXT_DIR" "$EXT_DISABLED"
      echo "✅ Pi RAG extension disabled"
      echo "   Restart pi or run /reload to apply"
    elif [ -d "$EXT_DISABLED" ]; then
      echo "ℹ️  Pi RAG extension already disabled"
    else
      echo "❌ Extension not found"
      exit 1
    fi
    ;;
  status)
    if [ -d "$EXT_DIR" ]; then
      echo "📗 Pi RAG extension: ENABLED"
      ls -la "$EXT_DIR"/*.ts 2>/dev/null
    elif [ -d "$EXT_DISABLED" ]; then
      echo "📕 Pi RAG extension: DISABLED"
    else
      echo "❌ Pi RAG extension: NOT INSTALLED"
    fi
    ;;
  *)
    echo "Usage: $0 [on|off|status]"
    exit 1
    ;;
esac
