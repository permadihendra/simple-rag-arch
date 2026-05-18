# Daily: 2026-05-17

- **Tags**: daily-memory
- **Created**: 2026-05-18T17:50:57Z
- **Importance**: 1

# 2026-05-17

## Created TUI User Message Right-Align Plugin

Created a plugin to right-align user messages in OpenClaw TUI.

**Problem:** User messages and assistant messages look the same (left-aligned), hard to distinguish in long conversations.

**Solution:** Bundle patching approach:
- `patch.cjs` — patches `theme.userText` in `tui-L4ke40-x.js` to calculate terminal width and add left padding (pushing user text to right)
- `swap.sh` — friendly CLI: `./swap.sh on` / `./swap.sh off` / `./swap.sh status`
- Plugin stores config (`rightMargin`), patcher does the actual work
- Backup of original file saved automatically

**Key lesson:** TUI renders locally, so hooks won't work. Need direct bundle patching.
**Another lesson:** Plugin system blocks `child_process.execSync` — patch scripts must be run manually.

## Edgy — Default Agent

Renamed agent from "linux-admin" to **"Edgy"** 🦞 — the best agent of the edgies world.

**Changes made:**
- Set `default: true` on linux-admin agent entry

