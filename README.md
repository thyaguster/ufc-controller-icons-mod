# Parsectagon — UFC Controller Icons Mod

[![Discord](https://img.shields.io/badge/Discord-Join%20Community-5865F2?logo=discord&logoColor=white)](https://discord.gg/a84pBw2Ff)
[![Games](https://img.shields.io/badge/Supported-UFC%202%20%7C%203%20%7C%204%20%7C%205%20%7C%206-e63946)](#supported-games)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A standalone, 100% reversible controller & keyboard button prompt installer for **EA Sports UFC 2, UFC 3, UFC 4, UFC 5, and UFC 6** on PC emulation (**SacredFire** & **Kyty**).

## Features

- **5 Supported Games:** Auto-detects **UFC 2** (`CUSA01968`), **UFC 3** (`CUSA06534`), **UFC 4** (`CUSA14209`), **UFC 5** (`PPSA03541`), and **UFC 6** (`PPSA23566`) — or browse to any custom install folder.
- **4 Icon Families with Live Previews & Mix-and-Match `MENUS` / `MOVES` Presets:**
  - **Xbox:** Authentic KLPS EA Xbox One icons (`White`, `Outline`, `Color` menus × `Ring`, `Disc`, `White` moves) + **Kenney** flat vector Xbox icons.
  - **PlayStation:** `Stock` (100% clean restore), `PS4` (authentic colored EA PS4 buttons for UFC 5 & UFC 6), `Kenney White`, and `Kenney Color`.
  - **Nintendo Switch (Kenney):** Physical Switch layout (`B / A / Y / X`, `L / R / ZL / ZR`, `+ / -`, `Home`) in `Solid` or `Outline`.
  - **Keyboard (Kenney):** Crisp double-resolution Kenney keycaps that dynamically match your exact bindings, with a collapsible 3-column remapper for **SacredFire** (`bbport.ini`) and **Kyty** (`UFC6.ini`).
- **One-Click Multi-Game Install:** Toggle **Apply to all detected UFC games** to patch your entire library at once.
- **Icon Gallery:** Click **All Icons** to preview every bundled icon pack side-by-side.
- **100% Reversible & Safe:** Automatic verified backups before any write. Select **PlayStation (`Stock` / `Stock`) → Restore PlayStation** anytime to return to untouched game files.

## Download & Usage

1. Download **`UFC_Controller_Icons_Mod.exe`** from the [Latest Release](https://github.com/thyaguster/ufc-controller-icons-mod/releases/latest).
2. Close any running UFC game or emulator.
3. Run `UFC_Controller_Icons_Mod.exe`, select your game (or click **Browse Folder...**), pick your `MENUS` / `MOVES` presets, and click **Install**.

## Building from Source

Requires **Python 3.11+**, **Pillow**, and **PyInstaller**:

```powershell
pip install pillow pyinstaller
.\build-standalone-icons-installer.ps1
```

The standalone executable is written to `dist\UFC_Controller_Icons_Mod.exe`.

## Credits & Licenses

- **KLPS** — Authentic EA Sports UFC 2/3 & UFC 4 Xbox One GNF button icon packs.
- **Kenney ([kenney.nl](https://kenney.nl))** — Input Prompts v1.5 (Keyboard & Mouse, Xbox Series, PlayStation Series, Nintendo Switch), licensed under **CC0 1.0 Universal**.
- **Barlow Condensed** — SIL Open Font License.
- **Parsectagon / Portheon / SacredFire / Kyty Community** — [Join the Discord](https://discord.gg/a84pBw2Ff).
- All original game assets remain the property of EA Sports. This tool patches only the user's own local game installation with verified backups.
