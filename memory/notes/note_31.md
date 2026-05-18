# Daily: 2026-05-14

- **Tags**: daily-memory
- **Created**: 2026-05-18T17:50:57Z
- **Importance**: 1

# Memory - 2026-05-14

## Summary
Installed and configured Pi coding agent (v0.74.0) with opencode-go provider.

## What We Did

### 1. Installed Pi Coding Agent
- Installed via `npm install -g @earendil-works/pi-coding-agent` (210 packages, 21s)
- Binary: `~/.npm-global/bin/pi` (already in PATH from previous setup)

### 2. Configured Authentication
- **Provider:** opencode-go
- **Key storage:** `~/.pi/opencode-key` (chmod 600, 68 bytes) — user wrote the key themselves
- **auth.json:** References key via `!cat ~/.pi/opencode-key` — key never stored in config, read at runtime
- Pi supports key resolution from shell commands, env vars, or literal values

### 3. Default Settings
- Created `~/.pi/agent/settings.json` with:
  - `defaultProvider: "opencode-go"`
  - `defaultModel: "deepseek-v4-flash"`
  - Theme: dark

### 4. Verified
- `pi --list-models` → 12 models available ✅
- `pi -p "Say hello in one word"` → "Hello" ✅

### Pi Key Facts
- **Docs:** https://pi.dev/docs/latest
- **Config di
