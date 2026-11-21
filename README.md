# Codex Desktop Slash (`/`) Skills Patch (macOS)

English | [简体中文](./README.zh-CN.md)

Restore `/` slash-menu skill invocation in Codex Desktop (`ChatGPT.app`, tested on `26.1117.31558` for Apple Silicon macOS) while keeping all built-in slash commands and the `$` skill picker intact.

## What changed in Codex Desktop 26.1117.31558

In version `26.1117.31558`, typing `/` in the Codex composer only shows built-in slash commands (plus the `plan` skill), while all other enabled skills moved to `$`. This patch registers every enabled workspace skill back into the `/` slash command menu.

## Features

- Typing `/` in the Codex composer displays all built-in slash commands followed by a `Skills` section with every enabled skill.
- Typing `/skill-name` filters by both display title and raw skill name. Pressing Enter or clicking a match replaces `/...` inline with the native `$skill` mention chip.
- Enables `/` skill invocation across the Codex workspace composer, general Work composer, and browser skills.
- Uses APFS copy-on-write staging and atomic directory swap so an untouched official backup is saved automatically and you can run it safely without corrupting an active session.
- Zero third-party Python dependencies (macOS built-in `python3` and `codesign` only).

## Requirements

- macOS (Apple Silicon) with Codex Desktop installed at `/Applications/ChatGPT.app` (or `/Applications/Codex.app`).
- `python3` and `codesign` (Xcode Command Line Tools, installable via `xcode-select --install`).
- Optional `node` binary for automatic `node --check` syntax verification before repacking.

## Quick Start

```bash
git clone https://github.com/vanch007/codex-slash-skills-patch.git
cd codex-slash-skills-patch

# 1. Check current app status
python3 codex-slash-skills-patch.py status

# 2. Dry run (read-only check, verifies target chunks and JS syntax)
python3 codex-slash-skills-patch.py apply --dry-run

# 3. Back up original app and apply the patch
python3 codex-slash-skills-patch.py apply
```

After `apply` finishes, **quit ChatGPT/Codex completely (`Cmd+Q`) and reopen it**.

### Restore the Original App

```bash
python3 codex-slash-skills-patch.py restore
```

Quit (`Cmd+Q`) and reopen the app to return to the untouched Apple-signed bundle.

## CLI Options

| Option | Default | Description |
| :--- | :--- | :--- |
| `--app` | `/Applications/ChatGPT.app` | Target `.app` bundle path |
| `--backup-dir` | `~/.codex-slash-patch/backups` | Directory where original app backups are stored |
| `--sign` | `auto` | Code signing identity (`auto`, `-` for ad-hoc, or a certificate name / SHA-1) |
| `--dry-run` | off | Available on `apply` to verify chunk matching and syntax without writing files |
| `--backup` | latest matching version | Available on `restore` to specify an explicit backup `.app` path |

`--sign auto` picks an available local `Apple Development` or `Developer ID Application` certificate when present and falls back to ad-hoc signing (`-`) otherwise. Pass `--sign -` to force ad-hoc signing.

## How It Works

1. Dynamically locates the three webview async JS chunks inside `Contents/Resources/app.asar` using stable string anchors.
2. Adds a `Skills` slash-command registrar (`id_slash_skills`) to the Codex composer chunk and adds `"/"` plus `onSelectFromInlineSlash` to the Work composer and Browser Skills chunks.
3. Appends the patched JS files to `app.asar`, recalculates per-file and archive-header SHA-256 hashes, updates `Contents/Info.plist`, and flips the Electron embedded ASAR integrity fuse bit in `Codex Framework`.
4. Re-signs the helpers, `Codex Framework.framework`, and main `.app` bundle with a single consistent identity, verifies with `codesign --verify --verbose=2`, and swaps the bundle atomically.

## Notes

- **Keychain prompt on first relaunch**
  Because the code-signing identity changes, macOS may ask once for permission to access `Codex Safe Storage` in Keychain. Click **Always Allow** to keep your existing session. Using a local Apple Development certificate keeps this grant persistent across relaunches.
- **Restricted entitlements**
  Local re-signing strips Apple-team-restricted entitlements (push notifications, associated domains, official app groups). Core Codex chat, local workspaces, skills, MCP tools, and plugins continue working normally.
- **App updates**
  Official auto-updates replace `ChatGPT.app` and remove the patch. Run `python3 codex-slash-skills-patch.py apply --dry-run` after an update to check whether the new build is still compatible.

## License

MIT
