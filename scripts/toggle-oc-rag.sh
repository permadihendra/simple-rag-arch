#!/usr/bin/env bash
# toggle-oc-rag.sh — Enable/disable the OpenClaw RAG memory plugin
# Usage: ./toggle-oc-rag.sh [on|off|status]

case "${1:-status}" in
  on|enable)
    echo "🔧 Enabling OpenClaw RAG plugin..."
    openclaw plugins enable rag-memory 2>&1
    echo "✅ OpenClaw RAG plugin enabled"
    ;;
  off|disable)
    echo "🔧 Disabling OpenClaw RAG plugin..."
    openclaw plugins disable rag-memory 2>&1
    echo "✅ OpenClaw RAG plugin disabled"
    ;;
  status)
    openclaw plugins inspect rag-memory 2>&1 | grep -E "^(Status|id)" || echo "📕 OpenClaw RAG plugin: NOT FOUND"
    ;;
  *)
    echo "Usage: $0 [on|off|status]"
    exit 1
    ;;
esac
