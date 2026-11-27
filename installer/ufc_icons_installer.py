"""Standalone UFC 3 / UFC 4 / UFC 6 Xbox & Keyboard Button Icons Installer + Key Remapper."""
from __future__ import annotations

import io
import os
from pathlib import Path
import queue
import sys
import threading
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    tk = None
    filedialog = messagebox = ttk = None
import webbrowser
import zipfile

_MEIPASS = Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "_MEIPASS", None) else None
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent

for _p in (
    _MEIPASS,
    _REPO / "ufc3" / "src",
    _REPO / "ufc4" / "src",
    _REPO / "ufc4" / "src" / "ufc4_keyboard",
    _REPO / "vendor" / "xbox-icons",
):
    if _p and _p.exists() and str(_p) not in sys.path:
        sys.path.append(str(_p))

ACTION_ROWS = [
    ("Cross", "A / Cross", "cross"),
    ("Circle", "B / Circle", "circle"),
    ("Square", "X / Square", "square"),
    ("Triangle", "Y / Triangle", "triangle"),
    ("L1", "LB / L1", "l1"),
    ("R1", "RB / R1", "r1"),
    ("L2", "LT / L2", "l2"),
    ("R2", "RT / R2", "r2"),
    ("L3", "L3 Click", "l3"),
    ("R3", "R3 Click", "r3"),
    ("Options", "Menu / Opt", "options"),
    ("TouchPad", "View / Pad", "touchpad"),
    ("Up", "D-Up", "up"),
    ("Down", "D-Down", "down"),
    ("Left", "D-Left", "left"),
    ("Right", "D-Right", "right"),
    ("LeftStickUp", "LS Up", "move_up"),
    ("LeftStickDown", "LS Down", "move_down"),
    ("LeftStickLeft", "LS Left", "move_left"),
    ("LeftStickRight", "LS Right", "move_right"),
    ("RightStickUp", "RS Up", "look_up"),
    ("RightStickDown", "RS Down", "look_down"),
    ("RightStickLeft", "RS Left", "look_left"),
    ("RightStickRight", "RS Right", "look_right"),
]

SACREDFIRE_DEFAULTS = {
    "Cross": "Space", "Circle": "Left Shift", "Square": "E", "Triangle": "Q",
    "L1": "1", "R1": "3", "L2": "R", "R2": "F", "L3": "Z", "R3": "C",
    "Options": "Return", "TouchPad": "Tab", "TouchPadRight": "Backspace",
    "Up": "I", "Down": "K", "Left": "J", "Right": "L",
    "LeftStickUp": "W", "LeftStickDown": "S", "LeftStickLeft": "A", "LeftStickRight": "D",
    "RightStickUp": "Up", "RightStickDown": "Down", "RightStickLeft": "Left", "RightStickRight": "Right",
}

UFC6_DEFAULTS = {
    "Cross": "J", "Circle": "L", "Square": "K", "Triangle": "I",
    "L1": "Q", "R1": "E", "L2": "Z", "R2": "C", "L3": "Left Shift", "R3": "Left Ctrl",
    "Options": "Return", "TouchPad": "Tab", "TouchPadRight": "Backspace",
    "Up": "Up", "Down": "Down", "Left": "Left", "Right": "Right",
    "LeftStickUp": "W", "LeftStickDown": "S", "LeftStickLeft": "A", "LeftStickRight": "D",
    "RightStickUp": "T", "RightStickDown": "G", "RightStickLeft": "F", "RightStickRight": "H",
}

TK_KEY_MAP = {
    "Return": "Return", "space": "Space", "Escape": "Escape", "Tab": "Tab",
    "BackSpace": "Backspace", "Caps_Lock": "CapsLock",
    "Shift_L": "Left Shift", "Shift_R": "Right Shift",
    "Control_L": "Left Ctrl", "Control_R": "Right Ctrl",
    "Alt_L": "Left Alt", "Alt_R": "Right Alt",
    "Up": "Up", "Down": "Down", "Left": "Left", "Right": "Right",
    "Prior": "PageUp", "Next": "PageDown",
}

SHORT_DISPLAY = {
    "Space": "SPACE", "Left Shift": "L-SHIFT", "Right Shift": "R-SHIFT",
    "Left Ctrl": "L-CTRL", "Right Ctrl": "R-CTRL", "Left Alt": "L-ALT",
    "Right Alt": "R-ALT", "Return": "ENTER", "Backspace": "BKSP",
    "Tab": "TAB", "Escape": "ESC", "Up": "↑", "Down": "↓", "Left": "←", "Right": "→",
}

KNOWN_PATHS = [
    ("UFC2", Path(r"E:\Jogos\UFC 2 v1.13\CUSA01968")),
    ("UFC3", Path(r"E:\Jogos\UFC 3 v1.14\CUSA06534")),
    ("UFC4", Path(r"E:\Jogos\UFC 4 v28.00\CUSA14209")),
    ("UFC5", Path(r"E:\Jogos\UFC 5 v01.031\PPSA03541")),
    ("UFC6", Path(r"E:\Jogos\UFC 6 v01.006\PPSA23566-app0-files")),
]


def detect_game(folder: Path) -> tuple[str | None, Path | None]:
    """Return ('UFC2'|'UFC3'|'UFC4'|'UFC5'|'UFC6', resolved_root) for a selected folder."""
    if not folder.exists():
        return None, None
    if (folder / "eboot.bin").is_file() and ((folder / "Data").is_dir() or (folder / "data").is_dir() or (folder / "sce_sys").is_dir()):
        if not (folder / "databigs").is_dir():
            pj = folder / "sce_sys" / "param.json"
            if pj.is_file():
                try:
                    tid = json.loads(pj.read_text(encoding="utf-8-sig")).get("titleId", "")
                    if tid == "PPSA03541":
                        return "UFC5", folder
                except Exception:
                    pass
            if "ppsa03541" in str(folder).lower() or "ufc 5" in str(folder).lower():
                return "UFC5", folder
            return "UFC6", folder
    if (folder / "PPSA03541").is_dir():
        return "UFC5", folder / "PPSA03541"
    if (folder / "PPSA23566-app0-files").is_dir():
        return "UFC6", folder / "PPSA23566-app0-files"
    db = folder if folder.name.lower() == "databigs" else (folder / "databigs")
    if not db.is_dir():
        for sub in ("CUSA14209", "CUSA06534", "CUSA01968"):
            cand = folder / sub / "databigs"
            if cand.is_dir():
                db = cand
                break
    if db.is_dir() and (db / "inxp_ui_40.big").is_file():
        ui_big = db / "inxp_ui_40.big"
        if (db / "00index.csv").is_file() or (db / "inxp_ui_40.manifest.csv").is_file():
            return "UFC4", db
        if ui_big.stat().st_size > 0x0f66a200 + 8:
            with ui_big.open("rb") as f:
                f.seek(0x0f66a200)
                if f.read(3) == b"CWS":
                    return "UFC4", db
        if "cusa01968" in str(db).lower() or "ufc 2" in str(db).lower() or (db / "game_ui_200.big").is_file():
            return "UFC2", db
        return "UFC3", db
    return None, None


def bbport_path(game: str) -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    folder = {"UFC2": "UFC2Native", "UFC3": "UFC3Native"}.get(game, "UFC4Native")
    return local / folder / "bbport.ini"


def load_bbport_dict(path: Path) -> dict[str, str]:
    controls = SACREDFIRE_DEFAULTS.copy()
    if not path.is_file():
        return controls
    action_map = {act: ctrl for ctrl, _, act in ACTION_ROWS}
    action_map["touchpad_right"] = "TouchPadRight"
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        if not raw.startswith("key.") or "=" not in raw:
            continue
        action, value = raw.split("=", 1)
        ctrl = action_map.get(action[4:].strip().lower())
        first_key = value.split(",", 1)[0].strip()
        if ctrl and first_key:
            controls[ctrl] = first_key
    return controls


def save_bbport_dict(path: Path, controls: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ctrl_to_act = {ctrl: act for ctrl, _, act in ACTION_ROWS}
    existing = path.read_text(encoding="utf-8-sig").splitlines() if path.is_file() else []
    seen = set()
    out = []
    for line in existing:
        if line.startswith("key.") and "=" in line:
            act = line.split("=", 1)[0][4:].strip().lower()
            matching = [c for c, a in ctrl_to_act.items() if a == act]
            if matching:
                c = matching[0]
                rest = line.split("=", 1)[1].split(",", 1)
                suffix = f",{rest[1]}" if len(rest) > 1 else ""
                out.append(f"key.{act}={controls.get(c, SACREDFIRE_DEFAULTS[c])}{suffix}")
                seen.add(act)
                continue
        out.append(line)
    for ctrl, _, act in ACTION_ROWS:
        if act not in seen:
            out.append(f"key.{act}={controls.get(ctrl, SACREDFIRE_DEFAULTS[ctrl])}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def kyty_ini_path(target: Path | None) -> Path | None:
    cands = []
    if target:
        cands.extend([target / "UFC6.ini", target.parent / "UFC6.ini"])
    cands.append(Path(r"E:\Jogos\PORTHEON\games\UFC6\UFC6.ini"))
    local = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    cands.append(local / "PORTHEON" / "UFC6.ini")
    for p in cands:
        if p.is_file():
            return p
    return None


def load_kyty_dict(target: Path | None) -> dict[str, str]:
    controls = UFC6_DEFAULTS.copy()
    ini_p = kyty_ini_path(target)
    json_p = (target / ".ufc6-input-bindings.json") if target else None
    vendor_dir = _MEIPASS if (_MEIPASS and (_MEIPASS / "profiles").is_dir()) else (_REPO / "vendor" / "xbox-icons")
    if str(vendor_dir) not in sys.path or sys.path[0] != str(vendor_dir):
        sys.path.insert(0, str(vendor_dir))
    sys.modules.pop("keyboard_bindings", None)
    for src in (ini_p, json_p):
        if src and src.is_file():
            try:
                import keyboard_bindings as kb6
                loaded = kb6.load(src)
                controls.update(loaded.controls)
                return controls
            except Exception:
                pass
    return controls


def save_kyty_ini(ini_p: Path, controls: dict[str, str]) -> None:
    raw = ini_p.read_bytes()
    enc = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    text = raw.decode(enc, errors="replace")
    keymap_val = ";".join(f"{k}={v}" for k, v in controls.items() if v)
    lines = text.splitlines()
    out = []
    in_ufc6 = False
    wrote = False
    for line in lines:
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            if in_ufc6 and not wrote:
                out.append(f"keymap={keymap_val}")
                wrote = True
            in_ufc6 = (s.lower() == "[ufc6]")
            out.append(line)
            continue
        if in_ufc6 and s.lower().startswith("keymap="):
            out.append(f"keymap={keymap_val}")
            wrote = True
            continue
        out.append(line)
    if in_ufc6 and not wrote:
        out.append(f"keymap={keymap_val}")
        wrote = True
    if not wrote:
        out.extend(["", "[UFC6]", f"keymap={keymap_val}"])
    ini_p.write_bytes(("\r\n".join(out) + "\r\n").encode("utf-16" if enc == "utf-16" else "utf-8"))


def _asset_cache_dir(game: str) -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    d = local / "UFCButtonIconsInstaller" / game.lower()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _prefs_path() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    d = local / "UFCButtonIconsInstaller"
    d.mkdir(parents=True, exist_ok=True)
    return d / "prefs.json"


def load_prefs() -> dict:
    p = _prefs_path()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_prefs(prefs: dict) -> None:
    try:
        _prefs_path().write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    except Exception:
        pass


def detect_installed_pack(game: str, target: Path, prefs: dict) -> str:
    """Detect the currently installed icon pack for the given game folder."""
    recorded = prefs.get("installed", {}).get(game)
    if game in ("UFC5", "UFC6"):
        st = target / ".ufc6-input-icons-state.json"
        if st.is_file():
            try:
                mode = json.loads(st.read_text(encoding="utf-8")).get("current", {}).get("mode", "")
                if mode == "playstation":
                    return "PlayStation (Stock)"
                if mode == "keyboard":
                    return "Keyboard (Kenney)"
                if recorded and mode in ("xbox", "switch", "ps_custom"):
                    return recorded
                if mode:
                    return mode.replace("_", " ").title()
            except Exception:
                pass
        return recorded or "PlayStation (Stock)"
    if game == "UFC4":
        try:
            import hashlib
            from ufc4_icon_art import ART_OFFSET, ART_SIZE, ORIGINAL_SHA256
            arc = target / "inxp_ui_40.big"
            if arc.is_file():
                with arc.open("rb") as f:
                    f.seek(ART_OFFSET)
                    cur = f.read(ART_SIZE)
                if hashlib.sha256(cur).hexdigest() == ORIGINAL_SHA256:
                    # Could still have custom PS GNF if recorded
                    if recorded and recorded.startswith("PlayStation ("):
                        return recorded
                    return "PlayStation (Stock)"
                cache = _asset_cache_dir("UFC4")
                kb_f = cache / "ufc4_buttonart_keyboard.bin"
                if kb_f.is_file() and cur == kb_f.read_bytes():
                    return "Keyboard (Kenney)"
                return recorded or "Xbox / Custom"
        except Exception:
            pass
        return recorded or "Unknown"
    if game == "UFC2":
        try:
            cache = _asset_cache_dir("UFC2")
            bk = cache / "ufc2_backup.json"
            ui_big = target / "inxp_ui_40.big"
            if bk.is_file() and ui_big.is_file():
                orig_sz = json.loads(bk.read_text(encoding="utf-8")).get("orig_file_size")
                if orig_sz and ui_big.stat().st_size != orig_sz:
                    return recorded or "Xbox / Custom"
                if orig_sz and ui_big.stat().st_size == orig_sz and (not recorded or recorded == "PlayStation (Stock)"):
                    return "PlayStation (Stock)"
        except Exception:
            pass
        return recorded or "PlayStation (Stock)"
    if game == "UFC3":
        try:
            cache = _asset_cache_dir("UFC3")
            meta_p = cache / "ufc3_direct_icons_map.json"
            ui_big = target / "inxp_ui_40.big"
            if meta_p.is_file() and ui_big.is_file():
                meta = json.loads(meta_p.read_text(encoding="utf-8"))
                if meta:
                    row = meta[0]
                    with ui_big.open("rb") as f:
                        f.seek(row["offset"])
                        cur = f.read(row["size"])
                    for s, label in (("ps", "PlayStation (Stock)"), ("keyboard", "Keyboard (Kenney)"), ("xbox", recorded or "Xbox / Custom")):
                        bf = cache / f"ufc3_direct_icons_{s}.bin"
                        if bf.is_file() and bf.read_bytes()[:row["size"]] == cur:
                            return label
        except Exception:
            pass
        return recorded or "PlayStation (Stock)"
    return "Unknown"


_KENNEY_KEY_MAP = {
    "SPACE": "keyboard_space_icon.png",
    "ENTER": "keyboard_return.png",
    "RETURN": "keyboard_return.png",
    "TAB": "keyboard_tab_icon.png",
    "LSHIFT": "keyboard_shift_icon.png",
    "RSHIFT": "keyboard_shift_icon.png",
    "LEFTSHIFT": "keyboard_shift_icon.png",
    "RIGHTSHIFT": "keyboard_shift_icon.png",
    "L_SHIFT": "keyboard_shift_icon.png",
    "R_SHIFT": "keyboard_shift_icon.png",
    "SHIFT": "keyboard_shift_icon.png",
    "LCTRL": "keyboard_ctrl.png",
    "RCTRL": "keyboard_ctrl.png",
    "LEFTCTRL": "keyboard_ctrl.png",
    "RIGHTCTRL": "keyboard_ctrl.png",
    "L_CTRL": "keyboard_ctrl.png",
    "R_CTRL": "keyboard_ctrl.png",
    "CTRL": "keyboard_ctrl.png",
    "LALT": "keyboard_alt.png",
    "RALT": "keyboard_alt.png",
    "LEFTALT": "keyboard_alt.png",
    "RIGHTALT": "keyboard_alt.png",
    "ALT": "keyboard_alt.png",
    "BACKSPACE": "keyboard_backspace_icon.png",
    "ESCAPE": "keyboard_escape.png",
    "ESC": "keyboard_escape.png",
    "UP": "keyboard_arrow_up.png",
    "DOWN": "keyboard_arrow_down.png",
    "LEFT": "keyboard_arrow_left.png",
    "RIGHT": "keyboard_arrow_right.png",
    "MINUS": "keyboard_minus.png",
    "EQUAL": "keyboard_equals.png",
    "EQUALS": "keyboard_equals.png",
    "COMMA": "keyboard_comma.png",
    "PERIOD": "keyboard_period.png",
    "SLASH": "keyboard_slash_forward.png",
    "BACKSLASH": "keyboard_slash_back.png",
    "SEMICOLON": "keyboard_semicolon.png",
    "APOSTROPHE": "keyboard_apostrophe.png",
    "LBRACKET": "keyboard_bracket_open.png",
    "RBRACKET": "keyboard_bracket_close.png",
}


def _key_to_kenney_png(key_name: str, available: set[str]) -> str | None:
    k = (key_name or "").strip().upper().replace(" ", "")
    if not k:
        return None
    if k in _KENNEY_KEY_MAP and _KENNEY_KEY_MAP[k] in available:
        return _KENNEY_KEY_MAP[k]
    cand = f"keyboard_{k.lower()}.png"
    if cand in available:
        return cand
    return None


def apply_game_icons(game: str, target: Path, style: str, controls: dict[str, str], log,
                     menus_preset: str = "white", moves_preset: str = "ring") -> str:
    """Apply 'xbox', 'ps', 'switch', or 'keyboard' to UFC 2, UFC 3, UFC 4, or UFC 6."""
    is_ps_stock = (style == "ps" and menus_preset == "stock" and moves_preset == "stock")
    if game == "UFC2":
        bpath = bbport_path("UFC2")
        if style == "keyboard":
            save_bbport_dict(bpath, controls)
            log(f"Saved remapped keys to {bpath}")
        from ufc2_button_prompts import apply_ufc2
        cache = _asset_cache_dir("UFC2")
        log("Patching UFC 2 chunkzip GNF button prompts...")
        count = apply_ufc2(target, cache, style, bpath if bpath.is_file() else None,
                           menus_preset=menus_preset, moves_preset=moves_preset)
        return f"UFC 2 icons set to {style.upper()} ({count} GNF textures)!"
    if game == "UFC3":
        bpath = bbport_path("UFC3")
        if style == "keyboard":
            save_bbport_dict(bpath, controls)
            log(f"Saved remapped keys to {bpath}")
        from ufc3_button_prompts import prepare as u3_prepare, set_style as u3_set
        cache = _asset_cache_dir("UFC3")
        log("Preparing UFC 3 button prompts (SWF + GNF)...")
        fam = "switch" if style == "switch" else ("ps" if style == "ps" else "xbox")
        info = u3_prepare(target, cache, bpath if bpath.is_file() else None,
                          xbox_menus=menus_preset, xbox_moves=moves_preset, gamepad_family=fam)
        log(f"Prepared UFC 3: {info['gnf_count']} GNF textures.")
        target_slot = "ps" if is_ps_stock else ("keyboard" if style == "keyboard" else "xbox")
        u3_set(target, cache, target_slot)
        return f"UFC 3 icons set to {style.upper()}!"

    if game == "UFC4":
        bpath = bbport_path("UFC4")
        if style == "keyboard":
            save_bbport_dict(bpath, controls)
            log(f"Saved remapped keys to {bpath}")
        from ufc4_icon_art import prepare as u4_prep_swf, set_style as u4_set_swf
        from ufc4_direct_icons import prepare as u4_prep_gnf, set_style as u4_set_gnf
        archive = target / "inxp_ui_40.big"
        manifest = target / "00index.csv"
        if not manifest.is_file():
            manifest = target / "inxp_ui_40.manifest.csv"
        cache = _asset_cache_dir("UFC4")
        fam = "switch" if style == "switch" else ("ps" if style == "ps" else "xbox")
        log("Preparing UFC 4 Flash button art...")
        u4_prep_swf(archive, cache, bpath if bpath.is_file() else None,
                    gamepad_family=fam, menus_preset=menus_preset)
        log("Preparing UFC 4 GNF prompt textures...")
        count = u4_prep_gnf(archive, manifest, cache, bpath if bpath.is_file() else None,
                            xbox_menus=menus_preset, xbox_moves=moves_preset, gamepad_family=fam)
        log(f"Prepared UFC 4: {count} direct icon textures.")
        gnf_slot = "ps" if is_ps_stock else ("keyboard" if style == "keyboard" else "xbox")
        swf_slot = gnf_slot
        u4_set_gnf(archive, cache, gnf_slot)
        u4_set_swf(archive, cache, swf_slot)
        return f"UFC 4 icons set to {style.upper()}!"

    if game in ("UFC5", "UFC6"):
        vendor_dir = _MEIPASS if (_MEIPASS and (_MEIPASS / "profiles").is_dir()) else (_REPO / "vendor" / "xbox-icons")
        if str(vendor_dir) not in sys.path or sys.path[0] != str(vendor_dir):
            sys.path.insert(0, str(vendor_dir))
        for mod in ("keyboard_bindings", "keyboard_art", "keyboard_flash", "patcher_core", "input_icons"):
            sys.modules.pop(mod, None)
        import input_icons as ii
        import keyboard_bindings as kb6

        if game == "UFC5":
            profile = ii.load_profile(vendor_dir, "PPSA03541-01.031.000.json", "PPSA03541-01.031.000-keyboard.json")
        else:
            profile = ii.load_profile(vendor_dir)
        if is_ps_stock:
            u6_style = "playstation"
        elif style == "ps":
            u6_style = "ps_custom"
        else:
            u6_style = style
        bindings = kb6.defaults()
        if style == "keyboard":
            full = dict(kb6.DEFAULTS)
            full.update(controls)
            bindings = kb6.from_controls(full)
            try:
                kb6.save(target / ".ufc6-input-bindings.json", bindings)
                ini_p = kyty_ini_path(target)
                if ini_p:
                    save_kyty_ini(ini_p, full)
                    log(f"Saved Kyty keymap to {ini_p}")
                else:
                    log("Saved UFC 6 keyboard bindings JSON.")
            except Exception as exc:
                log(f"Note: could not save Kyty keymap ({exc}); applying icons with custom keys.")
        return ii.run("install" if u6_style != "playstation" else "restore", target, profile,
                      log=log, style=u6_style, bindings=bindings,
                      xbox_menus=menus_preset, xbox_moves=moves_preset)

    raise ValueError(f"Unsupported game: {game}")


def _apply_dark_titlebar(win: tk.Misc) -> None:
    """Enable Windows 10/11 dark titlebar matching #12141a."""
    if os.name != "nt":
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
        val = ctypes.c_int(1)
        dwm(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))  # DWMWA_USE_IMMERSIVE_DARK_MODE
        cap = ctypes.c_int(0x001A1412)  # COLORREF 0x00BBGGRR for #12141a
        dwm(hwnd, 35, ctypes.byref(cap), ctypes.sizeof(cap))  # DWMWA_CAPTION_COLOR
        txt = ctypes.c_int(0x00F9F4F1)  # #f1f4f9
        dwm(hwnd, 36, ctypes.byref(txt), ctypes.sizeof(txt))  # DWMWA_TEXT_COLOR
    except Exception:
        pass


class InstallerApp(tk.Tk if tk else object):
    BG = "#12141a"
    CARD = "#1b1e27"
    SUBCARD = "#161922"
    TILE = "#232836"
    TILE_BORDER = "#32384a"
    ACCENT = "#e63946"
    GREEN = "#2e8b57"
    FG = "#f1f4f9"
    MUTED = "#8d95a6"

    def __init__(self) -> None:
        super().__init__()
        self.title("Parsectagon — UFC Controller Icons Mod")
        self.geometry("1020x450")
        self.minsize(960, 440)
        self.configure(bg=self.BG)
        self._ico_path = next((p for p in (
            _MEIPASS / "overlay.ico" if _MEIPASS else None,
            _HERE / "assets" / "overlay.ico",
        ) if p and p.is_file()), None)
        if self._ico_path:
            try:
                self.iconbitmap(str(self._ico_path))
            except Exception:
                pass

        self.game: str | None = None
        self.target: Path | None = None
        self.controls: dict[str, str] = SACREDFIRE_DEFAULTS.copy()
        self.capturing_ctrl: str | None = None
        self.keymap_visible = False
        self.tile_widgets: dict[str, tuple[tk.Frame, tk.Label, tk.Label]] = {}
        self.game_pills: dict[str, tk.Button] = {}
        self.preview_labels: dict[str, tuple[tk.Label, tk.Label]] = {}
        self._preview_refs: dict[str, tuple[object, object]] = {}
        self.presets: dict[str, dict[str, str]] = {
            "xbox": {"menus": "white", "moves": "ring"},
            "ps": {"menus": "stock", "moves": "stock"},
            "switch": {"menus": "solid", "moves": "solid"},
        }
        self.prefs: dict = load_prefs()
        self.apply_all_var = tk.BooleanVar(value=False)
        self.preset_pills: dict[tuple[str, str, str], tk.Button] = {}
        self.log_q: queue.Queue[str] = queue.Queue()
        self.busy = False

        self._build_ui()
        _apply_dark_titlebar(self)
        self._auto_guess_folder()
        self.update_idletasks()
        self.geometry(f"1020x{max(450, self.winfo_reqheight() + 8)}")
        self.bind_all("<KeyPress>", self._on_key_capture)
        self.after(100, self._drain_log)

    def _build_ui(self) -> None:
        # Header
        hdr = tk.Frame(self, bg=self.BG)
        hdr.pack(fill="x", padx=20, pady=(14, 6))
        hdr_top = tk.Frame(hdr, bg=self.BG)
        hdr_top.pack(fill="x")
        brand = tk.Frame(hdr_top, bg=self.BG)
        brand.pack(side="left")
        tk.Button(brand, text="PARSECTAGON", command=lambda: webbrowser.open("https://parsectagon.cc"), font=("Segoe UI", 8, "bold"), bg=self.ACCENT, fg="#ffffff", relief="flat", bd=0, padx=7, pady=2, cursor="hand2").pack(side="left", padx=(0, 10), pady=(3, 0))
        tk.Label(brand, text="UFC Controller Icons Mod", font=("Segoe UI", 16, "bold"), bg=self.BG, fg=self.FG).pack(side="left")
        tk.Button(hdr_top, text="Discord", command=lambda: webbrowser.open("https://discord.gg/a84pBw2Ff"), bg="#5865F2", fg="#ffffff", relief="flat", font=("Segoe UI", 8, "bold"), padx=10, pady=4, cursor="hand2").pack(side="right", padx=(6, 0))
        tk.Button(hdr_top, text="GitHub", command=lambda: webbrowser.open("https://github.com/thyaguster/ufc-controller-icons-mod"), bg="#24292f", fg=self.FG, relief="flat", font=("Segoe UI", 8, "bold"), padx=10, pady=4, cursor="hand2").pack(side="right", padx=(6, 0))
        tk.Button(hdr_top, text="Credits", command=self._show_credits, bg=self.TILE, fg=self.FG, relief="flat", font=("Segoe UI", 8, "bold"), padx=9, pady=4, cursor="hand2").pack(side="right", padx=(6, 0))
        tk.Button(hdr_top, text="? Help", command=self._show_help, bg=self.TILE, fg="#8ad8ff", relief="flat", font=("Segoe UI", 8, "bold"), padx=9, pady=4, cursor="hand2").pack(side="right", padx=(6, 0))
        tk.Button(hdr_top, text="All Icons", command=self._show_all_icons, bg=self.TILE, fg="#6be675", relief="flat", font=("Segoe UI", 8, "bold"), padx=9, pady=4, cursor="hand2").pack(side="right")
        tk.Label(hdr, text="Choose your game and icon pack below. Customize keyboard bindings anytime if needed.", font=("Segoe UI", 9), bg=self.BG, fg=self.MUTED).pack(anchor="w", pady=(2, 0))

        # Game selection bar
        bar = tk.Frame(self, bg=self.CARD, highlightbackground=self.TILE_BORDER, highlightthickness=1)
        bar.pack(fill="x", padx=20, pady=6)
        pill_row = tk.Frame(bar, bg=self.CARD)
        pill_row.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(pill_row, text="Game:", bg=self.CARD, fg=self.MUTED, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
        for gname, gpath in KNOWN_PATHS:
            label = f"UFC {gname[3:]}" if gname.startswith("UFC") else gname
            b = tk.Button(
                pill_row, text=label, width=8, relief="flat", cursor="hand2",
                font=("Segoe UI", 9, "bold"), bg=self.TILE, fg=self.FG,
                command=lambda p=gpath: self._set_folder(p),
            )
            b.pack(side="left", padx=4)
            self.game_pills[gname] = b
        tk.Button(pill_row, text="Browse Folder...", command=self._browse, bg="#2c3140", fg=self.FG, relief="flat", font=("Segoe UI", 9), padx=10, pady=2, cursor="hand2").pack(side="right")
        tk.Checkbutton(
            pill_row, text="Apply to all detected UFC games", variable=self.apply_all_var,
            bg=self.CARD, fg=self.FG, selectcolor=self.TILE, activebackground=self.CARD,
            activeforeground=self.FG, font=("Segoe UI", 8), cursor="hand2",
        ).pack(side="right", padx=(0, 12))

        path_row = tk.Frame(bar, bg=self.CARD)
        path_row.pack(fill="x", padx=12, pady=(2, 10))
        self.detect_lbl = tk.Label(path_row, text="Select a UFC 3, UFC 4, or UFC 6 folder.", bg=self.CARD, fg="#f5b841", font=("Segoe UI", 9))
        self.detect_lbl.pack(side="left")
        self.installed_badge = tk.Label(path_row, text="", bg=self.TILE, fg="#8ad8ff", font=("Segoe UI", 8, "bold"), padx=8, pady=2)
        self.installed_badge.pack(side="right")

        # Icon Pack Cards (4 cards flush with top/bottom bars at 20px outer margin)
        cards = tk.Frame(self, bg=self.BG)
        cards.pack(fill="x", padx=16, pady=(6, 6))
        cards.columnconfigure((0, 1, 2, 3), weight=1, uniform="cards")
        self.btn_xbox = self._make_pack_card(cards, 0, "Xbox", "Install Xbox Icons", "xbox", self.GREEN)
        self.btn_ps = self._make_pack_card(cards, 1, "PlayStation", "Restore PlayStation", "ps", "#2b3040")
        self.btn_switch = self._make_pack_card(cards, 2, "Switch (Kenney)", "Install Switch Icons", "switch", "#b8293d")
        self.btn_kb = self._make_pack_card(cards, 3, "Keyboard (Kenney)", "Save Keys & Install", "keyboard", self.ACCENT)

        # Collapsible Keymap Toggle Bar
        toggle_bar = tk.Frame(self, bg=self.BG)
        toggle_bar.pack(fill="x", padx=20, pady=(4, 4))
        self.toggle_btn = tk.Button(
            toggle_bar, text="▸  Customize Keyboard Mapping (Optional)",
            command=self._toggle_keymap, bg=self.CARD, fg=self.FG,
            relief="flat", font=("Segoe UI", 9, "bold"), anchor="w", padx=12, pady=7, cursor="hand2"
        )
        self.toggle_btn.pack(fill="x")

        # Collapsible Keymap Drawer (hidden by default)
        self.keymap_frame = tk.Frame(self, bg=self.CARD, highlightbackground=self.TILE_BORDER, highlightthickness=1)
        self._build_keymap_drawer(self.keymap_frame)

        # Compact status bar
        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(self, textvariable=self.status_var, bg="#0d0f14", fg="#b8c1d1", font=("Consolas", 9), anchor="w", padx=12, pady=6).pack(fill="x", side="bottom")

    def _render_strip(self, icons: list, width: int = 212, height: int = 28):
        from PIL import Image, ImageTk
        strip = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        if icons:
            n = len(icons)
            cell_w = 30
            gap = 4
            slot_h = height - 4
            total_w = n * cell_w + (n - 1) * gap
            start_x = max(0, (width - total_w) // 2)
            for idx, im in enumerate(icons):
                sc = min(cell_w / im.width, slot_h / im.height)
                r = im.resize((max(1, round(im.width * sc)), max(1, round(im.height * sc))), Image.Resampling.LANCZOS)
                cx = start_x + idx * (cell_w + gap) + (cell_w - r.width) // 2
                cy = (height - r.height) // 2
                strip.alpha_composite(r, (cx, cy))
        photo = ImageTk.PhotoImage(strip)
        return photo

    def _make_pack_previews(self, style: str, game: str | None = None):
        from PIL import Image, ImageDraw
        from gamepad_presets import gamepad_icon
        menus_icons, moves_icons = [], []
        g = game or "UFC4"
        if style == "xbox":
            from ufc4_direct_icons import _decode_bc7_gnf_rgba
            z23_p = next((p for p in (_MEIPASS / "ufc23_xbox_gnf.zip" if _MEIPASS else None, _REPO / "ufc3" / "src" / "ufc23_xbox_gnf.zip") if p and p.is_file()), None)
            z4_p = next((p for p in (_MEIPASS / "ufc4_xbox_gnf.zip" if _MEIPASS else None, _REPO / "ufc4" / "src" / "ufc4_xbox_gnf.zip") if p and p.is_file()), None)

            def grab(zp, prefix, keys):
                out = []
                if zp:
                    with zipfile.ZipFile(zp) as z:
                        for k in keys:
                            full = f"{prefix}{k}.gnf"
                            if full in z.namelist():
                                im = _decode_bc7_gnf_rgba(z.read(full))
                                bb = im.getchannel("A").point(lambda v: 255 if v > 15 else 0).getbbox()
                                out.append(im.crop(bb) if bb else im)
                return out

            p23 = "samplegame/ui/kettle_assets/skins/buttons/ps3/"
            p4 = "samplegame/ui/kettle_assets/skins/buttons/ps/"
            zp, pref = (z23_p, p23) if g in ("UFC2", "UFC3") else (z4_p, p4)
            xm = self.presets["xbox"]["menus"]
            xv = self.presets["xbox"]["moves"]
            if xm == "kenney":
                menus_icons = [im for s in ("digital_one", "digital_two", "digital_four", "digital_three", "left_bumper", "right_bumper")
                               if (im := gamepad_icon("xbox", s, "kenney_white")) is not None]
            else:
                if xm == "outline":
                    m_face = ("ue_digital_one", "ue_digital_two", "ue_digital_four", "ue_digital_three")
                elif xm == "colored":
                    m_face = ("digital_one", "digital_two", "digital_four", "digital_three")
                else:
                    m_face = ("white/digital_one", "white/digital_two", "white/digital_four", "white/digital_three")
                menus_icons = grab(zp, pref, m_face + ("left_bumper", "right_bumper"))

            if xv == "kenney":
                moves_icons = [im for s in ("digital_one", "digital_two", "digital_four", "digital_three", "left_trigger", "right_trigger")
                               if (im := gamepad_icon("xbox", s, "kenney_color")) is not None]
            else:
                if xv == "disc":
                    v_face = grab(z23_p, p23, ("black_large/digital_one", "black_large/digital_two", "black_large/digital_four", "black_large/digital_three"))
                elif xv == "white":
                    v_face = grab(zp, pref, ("white/digital_one", "white/digital_two", "white/digital_four", "white/digital_three"))
                else:
                    v_face = grab(zp, pref, ("digital_one", "digital_two", "digital_four", "digital_three"))
                moves_icons = v_face + grab(zp, pref, ("left_trigger", "right_trigger"))
        elif style == "switch":
            sm = self.presets["switch"]["menus"]
            sv = self.presets["switch"]["moves"]
            menus_icons = [im for s in ("digital_one", "digital_two", "digital_four", "digital_three", "left_bumper", "right_bumper")
                           if (im := gamepad_icon("switch", s, sm)) is not None]
            moves_icons = [im for s in ("digital_one", "digital_two", "digital_four", "digital_three", "left_trigger", "right_trigger")
                           if (im := gamepad_icon("switch", s, sv)) is not None]
        elif style == "keyboard":
            kz_p = next((p for p in (
                _MEIPASS / "ufc4_keyboard" / "keyboard-art" / "kenney_kb_prompts.zip" if _MEIPASS else None,
                _REPO / "ufc4" / "src" / "ufc4_keyboard" / "keyboard-art" / "kenney_kb_prompts.zip",
            ) if p and p.is_file()), None)
            if kz_p:
                with zipfile.ZipFile(kz_p) as z:
                    avail = set(z.namelist())
                    menu_ctrls = ("Cross", "Circle", "Options", "TouchPad", "L1", "R1")
                    move_ctrls = ("LeftStickUp", "LeftStickLeft", "LeftStickDown", "LeftStickRight", "L2", "R2")
                    for ctrl in menu_ctrls:
                        k = _key_to_kenney_png(self.controls.get(ctrl, ""), avail)
                        if k:
                            im = Image.open(io.BytesIO(z.read(k))).convert("RGBA")
                            bb = im.getchannel("A").point(lambda v: 255 if v > 15 else 0).getbbox()
                            menus_icons.append(im.crop(bb) if bb else im)
                    for ctrl in move_ctrls:
                        k = _key_to_kenney_png(self.controls.get(ctrl, ""), avail)
                        if k:
                            im = Image.open(io.BytesIO(z.read(k))).convert("RGBA")
                            bb = im.getchannel("A").point(lambda v: 255 if v > 15 else 0).getbbox()
                            moves_icons.append(im.crop(bb) if bb else im)
        else:
            # PlayStation: Stock / PS4 Color / Kenney
            pm = self.presets["ps"]["menus"]
            pv = self.presets["ps"]["moves"]

            def stock_ps_glyphs(colored: bool):
                out = []
                for kind, col in (("x", (88, 155, 255, 255)), ("o", (245, 92, 114, 255)), ("sq", (230, 130, 210, 255)), ("tri", (64, 214, 180, 255))):
                    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
                    d = ImageDraw.Draw(im)
                    if colored:
                        d.ellipse((4, 4, 59, 59), fill=(24, 28, 36, 255), outline=col, width=4)
                        ink = col
                    else:
                        d.ellipse((4, 4, 59, 59), fill=(242, 245, 250, 255))
                        ink = (28, 32, 40, 255)
                    if kind == "x":
                        d.line((20, 20, 44, 44), fill=ink, width=5)
                        d.line((44, 20, 20, 44), fill=ink, width=5)
                    elif kind == "o":
                        d.ellipse((19, 19, 45, 45), outline=ink, width=5)
                    elif kind == "sq":
                        d.rectangle((20, 20, 44, 44), outline=ink, width=5)
                    else:
                        d.polygon([(32, 17), (46, 44), (18, 44)], outline=ink, width=4)
                    out.append(im)
                return out

            if pm == "kenney":
                menus_icons = [im for s in ("digital_one", "digital_two", "digital_four", "digital_three", "left_bumper", "right_bumper")
                               if (im := gamepad_icon("ps", s, "kenney_white")) is not None]
            elif pm == "kenney_color":
                menus_icons = [im for s in ("digital_one", "digital_two", "digital_four", "digital_three")
                               if (im := gamepad_icon("ps", s, "kenney_color")) is not None] + [
                               im for s in ("left_bumper", "right_bumper")
                               if (im := gamepad_icon("ps", s, "kenney_white")) is not None]
            elif pm == "ps4_color":
                menus_icons = [im for s in ("digital_one", "digital_two", "digital_four", "digital_three")
                               if (im := gamepad_icon("ps", s, "ps4_ea")) is not None] or stock_ps_glyphs(colored=True)
            else:
                menus_icons = stock_ps_glyphs(colored=False)

            if pv == "kenney":
                moves_icons = [im for s in ("digital_one", "digital_two", "digital_four", "digital_three", "left_trigger", "right_trigger")
                               if (im := gamepad_icon("ps", s, "kenney_color")) is not None]
            elif pv == "ps4_color":
                moves_icons = [im for s in ("digital_one", "digital_two", "digital_four", "digital_three")
                               if (im := gamepad_icon("ps", s, "ps4_ea")) is not None] or stock_ps_glyphs(colored=True)
            else:
                moves_icons = stock_ps_glyphs(colored=(g not in ("UFC5", "UFC6")))
        return self._render_strip(menus_icons), self._render_strip(moves_icons)

    def _refresh_previews(self) -> None:
        for style, (lbl_m, lbl_v) in self.preview_labels.items():
            try:
                p_m, p_v = self._make_pack_previews(style, self.game)
                self._preview_refs[style] = (p_m, p_v)
                lbl_m.config(image=p_m)
                lbl_v.config(image=p_v)
            except Exception:
                pass

    def _set_preset(self, style: str, kind: str, val: str) -> None:
        self.presets[style][kind] = val
        if self.game:
            self.prefs.setdefault("presets", {})[self.game] = {
                s: dict(v) for s, v in self.presets.items()
            }
            save_prefs(self.prefs)
        self._refresh_preset_pills()
        self._refresh_previews()

    def _refresh_preset_pills(self) -> None:
        colors = {"xbox": self.GREEN, "ps": "#3867d6", "switch": "#b8293d"}
        track_bg = "#111319"
        for (style, kind, val), b in self.preset_pills.items():
            active = self.presets[style][kind] == val
            b.config(bg=colors[style] if active else track_bg, fg="#ffffff" if active else self.MUTED)
        if hasattr(self, "btn_ps"):
            ps_stock = self.presets["ps"]["menus"] == "stock" and self.presets["ps"]["moves"] == "stock"
            self.btn_ps.config(
                text="Restore PlayStation" if ps_stock else "Install PS Icons",
                bg="#2b3040" if ps_stock else "#3867d6",
            )

    def _make_pack_card(self, parent: tk.Widget, col: int, title: str, btn_text: str, style: str, color: str) -> tk.Button:
        card = tk.Frame(parent, bg=self.CARD, highlightbackground=self.TILE_BORDER, highlightthickness=1)
        card.grid(row=0, column=col, padx=4, sticky="nsew")
        tk.Label(card, text=title, bg=self.CARD, fg=self.FG, font=("Segoe UI", 10, "bold")).pack(pady=(10, 6))

        menu_opts = {
            "xbox": (("white", "White"), ("outline", "Outl"), ("colored", "Color"), ("kenney", "Ken")),
            "ps": (("stock", "Stock"), ("ps4_color", "PS4"), ("kenney", "Ken"), ("kenney_color", "KenC")),
            "switch": (("solid", "Solid"), ("outline", "Outline")),
        }.get(style)
        move_opts = {
            "xbox": (("ring", "Ring"), ("disc", "Disc"), ("white", "White"), ("kenney", "Ken")),
            "ps": (("stock", "Stock"), ("ps4_color", "PS4"), ("kenney", "Kenney")),
            "switch": (("solid", "Solid"), ("outline", "Outline")),
        }.get(style)

        track_bg = "#111319"
        def add_row(label_text: str, kind: str, opts):
            row = tk.Frame(card, bg=self.CARD, height=24)
            row.pack_propagate(False)
            row.pack(fill="x", padx=8)
            tk.Label(row, text=label_text, bg=self.CARD, fg=self.MUTED, font=("Segoe UI", 7, "bold")).pack(side="left" if opts else "top", expand=not opts)
            if opts:
                track = tk.Frame(row, bg=track_bg, highlightbackground="#2b3142", highlightthickness=1, padx=2, pady=2)
                track.pack(side="right")
                for val, txt in opts:
                    pb = tk.Label(track, text=txt, bg=track_bg, fg=self.MUTED, font=("Segoe UI", 7, "bold"),
                                  padx=5, pady=1, cursor="hand2")
                    pb.pack(side="left", padx=1)
                    pb.bind("<Button-1>", lambda _e, s=style, k=kind, v=val: self._set_preset(s, k, v))
                    pb.bind("<Enter>", lambda _e, w=pb, s=style, k=kind, v=val: w.config(fg=self.FG) if self.presets[s][k] != v else None)
                    pb.bind("<Leave>", lambda _e, w=pb, s=style, k=kind, v=val: w.config(fg=self.MUTED) if self.presets[s][k] != v else None)
                    self.preset_pills[(style, kind, val)] = pb

        add_row("MENUS", "menus", menu_opts)
        lbl_m = tk.Label(card, bg=self.CARD)
        lbl_m.pack(pady=(2, 6))

        add_row("MOVES", "moves", move_opts)
        lbl_v = tk.Label(card, bg=self.CARD)
        lbl_v.pack(pady=(2, 8))

        self.preview_labels[style] = (lbl_m, lbl_v)
        btn = tk.Button(card, text=btn_text, command=lambda s=style: self._start(s), bg=color, fg=self.FG, font=("Segoe UI", 9, "bold"), relief="flat", pady=8, cursor="hand2")
        btn.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        self._refresh_preset_pills()
        return btn

    def _build_keymap_drawer(self, parent: tk.Frame) -> None:
        top = tk.Frame(parent, bg=self.CARD)
        top.pack(fill="x", padx=14, pady=(10, 6))
        tk.Label(top, text="Click any binding below, then press a new key (Esc cancels). Applies to SacredFire (bbport.ini) & Kyty (UFC6.ini).", bg=self.CARD, fg=self.MUTED, font=("Segoe UI", 8)).pack(side="left")
        tk.Button(top, text="Reset Defaults", command=self._reset_defaults, bg="#2c3140", fg=self.FG, relief="flat", font=("Segoe UI", 8, "bold"), padx=10, pady=3, cursor="hand2").pack(side="right")

        cols = tk.Frame(parent, bg=self.CARD)
        cols.pack(fill="both", expand=True, padx=10, pady=(2, 12))
        cols.columnconfigure((0, 1, 2), weight=1)

        # Col 0: Movement (Left Stick + D-Pad)
        c0 = tk.Frame(cols, bg=self.SUBCARD, highlightbackground="#282d3b", highlightthickness=1)
        c0.grid(row=0, column=0, padx=5, sticky="nsew")
        self._group_header(c0, "LEFT STICK (MOVE)")
        self._build_t_cluster(c0, "LeftStickUp", "LeftStickLeft", "LeftStickDown", "LeftStickRight", "L3")
        self._group_header(c0, "D-PAD")
        self._build_t_cluster(c0, "Up", "Left", "Down", "Right", None)

        # Col 1: Shoulders, Triggers & System
        c1 = tk.Frame(cols, bg=self.SUBCARD, highlightbackground="#282d3b", highlightthickness=1)
        c1.grid(row=0, column=1, padx=5, sticky="nsew")
        self._group_header(c1, "TRIGGERS & BUMPERS")
        for ctrl, name in (("L2", "LT / L2"), ("L1", "LB / L1"), ("R1", "RB / R1"), ("R2", "RT / R2")):
            self._make_list_row(c1, ctrl, name, "#9aa5bc")
        self._group_header(c1, "SYSTEM")
        for ctrl, name in (("TouchPad", "View / TouchPad"), ("Options", "Menu / Options")):
            self._make_list_row(c1, ctrl, name, "#9aa5bc")

        # Col 2: Face Buttons + Right Stick
        c2 = tk.Frame(cols, bg=self.SUBCARD, highlightbackground="#282d3b", highlightthickness=1)
        c2.grid(row=0, column=2, padx=5, sticky="nsew")
        self._group_header(c2, "FACE BUTTONS")
        for ctrl, name, col in (
            ("Cross", "A / Cross", "#4cd964"),
            ("Circle", "B / Circle", "#f05454"),
            ("Square", "X / Square", "#3b9eff"),
            ("Triangle", "Y / Triangle", "#eab81c"),
        ):
            self._make_list_row(c2, ctrl, name, col)
        self._group_header(c2, "RIGHT STICK (HEAD / GRAPPLE)")
        self._build_t_cluster(c2, "RightStickUp", "RightStickLeft", "RightStickDown", "RightStickRight", "R3")

    def _group_header(self, parent: tk.Widget, text: str) -> None:
        tk.Label(parent, text=text, bg=self.SUBCARD, fg=self.MUTED, font=("Segoe UI", 8, "bold"), anchor="w").pack(fill="x", padx=10, pady=(8, 4))

    def _make_list_row(self, parent: tk.Widget, ctrl: str, title: str, accent: str) -> None:
        row = tk.Frame(parent, bg=self.SUBCARD)
        row.pack(fill="x", padx=10, pady=2)
        tk.Label(row, text="●", bg=self.SUBCARD, fg=accent, font=("Segoe UI", 8)).pack(side="left", padx=(0, 5))
        tk.Label(row, text=title, bg=self.SUBCARD, fg=self.FG, font=("Segoe UI", 9), anchor="w").pack(side="left", fill="x", expand=True)
        pill = tk.Frame(row, bg=self.TILE, highlightbackground=self.TILE_BORDER, highlightthickness=1, width=78, height=24, cursor="hand2")
        pill.pack_propagate(False)
        pill.pack(side="right")
        lbl = tk.Label(pill, text=self._fmt(self.controls.get(ctrl, "-")), bg=self.TILE, fg=self.FG, font=("Segoe UI", 8, "bold"), cursor="hand2")
        lbl.pack(expand=True)
        for wdg in (pill, lbl):
            wdg.bind("<Button-1>", lambda _e, k=ctrl: self._begin_capture(k))
        self.tile_widgets[ctrl] = (pill, lbl, lbl)

    def _build_t_cluster(self, parent: tk.Widget, up: str, left: str, down: str, right: str, click: str | None) -> None:
        grid = tk.Frame(parent, bg=self.SUBCARD)
        grid.pack(padx=10, pady=(0, 4))
        self._make_small_key(grid, up, "UP").grid(row=0, column=1, padx=2, pady=2)
        self._make_small_key(grid, left, "LEFT").grid(row=1, column=0, padx=2, pady=2)
        self._make_small_key(grid, down, "DOWN").grid(row=1, column=1, padx=2, pady=2)
        self._make_small_key(grid, right, "RIGHT").grid(row=1, column=2, padx=2, pady=2)
        if click:
            self._make_list_row(parent, click, f"{click} Click", "#9aa5bc")

    def _make_small_key(self, parent: tk.Widget, ctrl: str, sub: str) -> tk.Frame:
        f = tk.Frame(parent, bg=self.TILE, highlightbackground=self.TILE_BORDER, highlightthickness=1, width=68, height=34, cursor="hand2")
        f.pack_propagate(False)
        l1 = tk.Label(f, text=sub, bg=self.TILE, fg=self.MUTED, font=("Segoe UI", 6, "bold"), cursor="hand2")
        l1.pack(pady=(2, 0))
        l2 = tk.Label(f, text=self._fmt(self.controls.get(ctrl, "-")), bg=self.TILE, fg=self.FG, font=("Segoe UI", 8, "bold"), cursor="hand2")
        l2.pack(pady=(0, 2))
        for wdg in (f, l1, l2):
            wdg.bind("<Button-1>", lambda _e, k=ctrl: self._begin_capture(k))
        self.tile_widgets[ctrl] = (f, l1, l2)
        return f

    def _toggle_keymap(self) -> None:
        self.keymap_visible = not self.keymap_visible
        if self.keymap_visible:
            self.toggle_btn.config(text="▾  Hide Keyboard Mapping")
            self.keymap_frame.pack(fill="both", expand=True, padx=20, pady=(0, 8))
        else:
            self.toggle_btn.config(text="▸  Customize Keyboard Mapping (Optional)")
            self.keymap_frame.pack_forget()
        self.update_idletasks()
        max_h = max(500, self.winfo_screenheight() - 80)
        want_h = min(max_h, max(450, self.winfo_reqheight() + 12))
        self.geometry(f"1020x{want_h}")

    def _fmt(self, key: str) -> str:
        return SHORT_DISPLAY.get(key, key.upper())

    def _auto_guess_folder(self) -> None:
        for _, cand in KNOWN_PATHS:
            if cand.exists():
                self._set_folder(cand)
                return

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(title="Select UFC 3, UFC 4, or UFC 6 game folder")
        if chosen:
            self._set_folder(Path(chosen))

    def _set_folder(self, folder: Path) -> None:
        game, resolved = detect_game(folder)
        self.game, self.target = game, resolved
        for gname, pill in self.game_pills.items():
            pill.config(bg=self.ACCENT if gname == game else self.TILE)
        if not game:
            self.detect_lbl.config(text=f"Unrecognized folder: {folder}", fg="#ff6b6b")
            return
        nice_g = f"UFC {game[3:]}" if game.startswith("UFC") else game
        self.detect_lbl.config(text=f"Detected {nice_g}:  {resolved}", fg="#6be675")
        self.controls = load_bbport_dict(bbport_path(game)) if game in ("UFC2", "UFC3", "UFC4") else load_kyty_dict(resolved)
        self.capturing_ctrl = None
        saved_p = self.prefs.get("presets", {}).get(game)
        if saved_p:
            for s in ("xbox", "ps", "switch"):
                if s in saved_p:
                    self.presets[s].update(saved_p[s])
        else:
            self.presets["xbox"]["menus"] = "white"
            self.presets["xbox"]["moves"] = "disc" if game in ("UFC5", "UFC6") else "ring"
            self.presets["ps"]["menus"] = "stock"
            self.presets["ps"]["moves"] = "stock"
            self.presets["switch"]["menus"] = "solid"
            self.presets["switch"]["moves"] = "solid"
        self._refresh_preset_pills()
        self._refresh_tiles()
        self._refresh_previews()
        self._refresh_installed_badge()
        engine = "SacredFire (bbport.ini)" if game in ("UFC2", "UFC3", "UFC4") else "Kyty (UFC6.ini)"
        self.status_var.set(f"Loaded {game} bindings [{engine}].")

    def _refresh_installed_badge(self) -> None:
        if not self.game or not self.target:
            self.installed_badge.config(text="")
            return
        cur = detect_installed_pack(self.game, self.target, self.prefs)
        self.installed_badge.config(text=f"Installed: {cur}")

    def _refresh_tiles(self) -> None:
        for ctrl, (f, l1, l2) in self.tile_widgets.items():
            active = ctrl == self.capturing_ctrl
            bg = "#471e24" if active else self.TILE
            bd = self.ACCENT if active else self.TILE_BORDER
            f.config(bg=bg, highlightbackground=bd)
            l1.config(bg=bg)
            l2.config(bg=bg, text="PRESS..." if active else self._fmt(self.controls.get(ctrl, "-")))

    def _begin_capture(self, ctrl: str) -> None:
        if self.busy:
            return
        self.capturing_ctrl = ctrl
        self._refresh_tiles()
        self.status_var.set(f"Press any key to bind {ctrl} (or Escape to cancel)...")

    def _on_key_capture(self, event: tk.Event) -> None:
        if not self.capturing_ctrl:
            return
        ks = event.keysym
        if ks == "Escape":
            self.capturing_ctrl = None
            self._refresh_tiles()
            self.status_var.set("Remap cancelled.")
            return
        mapped = TK_KEY_MAP.get(ks)
        if not mapped:
            if len(ks) == 1 and ks.isalnum():
                mapped = ks.upper()
            elif ks.startswith("F") and ks[1:].isdigit():
                mapped = ks.upper()
            else:
                mapped = ks
        self.controls[self.capturing_ctrl] = mapped
        self.status_var.set(f"Mapped {self.capturing_ctrl} -> {mapped}")
        self.capturing_ctrl = None
        self._refresh_tiles()
        self._refresh_previews()

    def _reset_defaults(self) -> None:
        self.controls = (UFC6_DEFAULTS if self.game in ("UFC5", "UFC6") else SACREDFIRE_DEFAULTS).copy()
        self.capturing_ctrl = None
        self._refresh_tiles()
        self._refresh_previews()
        self.status_var.set("Reset keyboard bindings to defaults.")

    def _log(self, msg: str) -> None:
        self.log_q.put(str(msg))

    def _drain_log(self) -> None:
        while True:
            try:
                msg = self.log_q.get_nowait()
            except queue.Empty:
                break
            self.status_var.set(msg)
        self.after(100, self._drain_log)

    def _start(self, style: str) -> None:
        if self.busy:
            return
        if not self.game or not self.target:
            messagebox.showerror("Game Not Selected", "Select UFC 3, UFC 4, or UFC 6 first.")
            return
        self.busy = True
        for b in (self.btn_xbox, self.btn_ps, self.btn_switch, self.btn_kb):
            b.config(state="disabled")
        game, target, controls = self.game, self.target, dict(self.controls)
        p = self.presets.get(style, {"menus": "white", "moves": "ring"})
        pm, pv = p["menus"], p["moves"]
        apply_all = bool(self.apply_all_var.get())

        def _label_for() -> str:
            if style == "keyboard":
                return "Keyboard (Kenney)"
            if style == "ps" and pm == "stock" and pv == "stock":
                return "PlayStation (Stock)"
            name_map = {"xbox": "Xbox", "ps": "PlayStation", "switch": "Switch"}
            return f"{name_map.get(style, style.title())} ({pm.title()}/{pv.title()})"

        def worker() -> None:
            try:
                targets: list[tuple[str, Path]] = []
                if apply_all:
                    seen = set()
                    for _, cand in KNOWN_PATHS:
                        if cand.exists():
                            g, r = detect_game(cand)
                            if g and r and g not in seen:
                                targets.append((g, r))
                                seen.add(g)
                    if game and target and game not in seen:
                        targets.append((game, target))
                else:
                    targets.append((game, target))

                results = []
                lbl = _label_for()
                for g, r in targets:
                    self._log(f"Applying {lbl} to {g}...")
                    c_for_g = controls if g == game else (load_bbport_dict(bbport_path(g)) if g in ("UFC2", "UFC3", "UFC4") else load_kyty_dict(r))
                    res = apply_game_icons(g, r, style, c_for_g, self._log, menus_preset=pm, moves_preset=pv)
                    results.append(f"{g}: {res}")
                    self.prefs.setdefault("installed", {})[g] = lbl
                save_prefs(self.prefs)
                final_msg = "\n".join(results) if len(results) > 1 else results[0]
                self._log(results[-1])
                self.after(0, self._refresh_installed_badge)
                self.after(0, lambda m=final_msg: messagebox.showinfo("Done", m))
            except Exception as exc:
                self._log(f"ERROR: {exc}")
                self.after(0, lambda e=exc: messagebox.showerror("Error", str(e)))
            finally:
                def unlock() -> None:
                    self.busy = False
                    for b in (self.btn_xbox, self.btn_ps, self.btn_switch, self.btn_kb):
                        b.config(state="normal")
                self.after(0, unlock)

        threading.Thread(target=worker, daemon=True).start()


    def _show_all_icons(self) -> None:
        from PIL import Image, ImageTk
        from gamepad_presets import gamepad_icon
        from ufc4_direct_icons import _decode_bc7_gnf_rgba

        win = tk.Toplevel(self)
        win.title("All Available Button Icons")
        win.configure(bg=self.BG)
        if self._ico_path:
            try:
                win.iconbitmap(str(self._ico_path))
            except Exception:
                pass
        _apply_dark_titlebar(win)
        win.transient(self)
        win.grab_set()
        w_win, h_win = 820, 620

        hdr = tk.Frame(win, bg=self.BG)
        hdr.pack(fill="x", padx=20, pady=(14, 6))
        tk.Label(hdr, text="All Available Button Icons", bg=self.BG, fg=self.FG, font=("Segoe UI", 14, "bold")).pack(side="left")
        tk.Label(hdr, text="Live rendered from bundled KLPS, EA PS4 & Kenney packs", bg=self.BG, fg=self.MUTED, font=("Segoe UI", 8)).pack(side="right", pady=(6, 0))

        wrap = tk.Frame(win, bg=self.BG)
        wrap.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        st = ttk.Style(win)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.layout("Dark.Vertical.TScrollbar", [
            ("Vertical.Scrollbar.trough", {
                "sticky": "ns",
                "children": [("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})],
            })
        ])
        st.configure(
            "Dark.Vertical.TScrollbar",
            gripcount=0,
            background="#32384a",
            darkcolor="#32384a",
            lightcolor="#32384a",
            troughcolor="#161922",
            bordercolor="#161922",
            arrowcolor="#161922",
            relief="flat",
            width=10,
        )
        st.map("Dark.Vertical.TScrollbar", background=[("active", "#4d5672"), ("pressed", "#637094")])

        canvas = tk.Canvas(wrap, bg=self.BG, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview, style="Dark.Vertical.TScrollbar")
        inner = tk.Frame(canvas, bg=self.BG)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw", width=w_win - 54)
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y", padx=(4, 0))
        win.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        refs = []
        win._img_refs = refs  # keep PhotoImage refs alive

        z23_p = next((p for p in (_MEIPASS / "ufc23_xbox_gnf.zip" if _MEIPASS else None, _REPO / "ufc3" / "src" / "ufc23_xbox_gnf.zip") if p and p.is_file()), None)
        z4_p = next((p for p in (_MEIPASS / "ufc4_xbox_gnf.zip" if _MEIPASS else None, _REPO / "ufc4" / "src" / "ufc4_xbox_gnf.zip") if p and p.is_file()), None)
        kz_p = next((p for p in (
            _MEIPASS / "ufc4_keyboard" / "keyboard-art" / "kenney_kb_prompts.zip" if _MEIPASS else None,
            _REPO / "ufc4" / "src" / "ufc4_keyboard" / "keyboard-art" / "kenney_kb_prompts.zip",
        ) if p and p.is_file()), None)

        def grab_gnf(zp, pref, keys):
            out = []
            if zp:
                with zipfile.ZipFile(zp) as z:
                    for k in keys:
                        full = f"{pref}{k}.gnf"
                        if full in z.namelist():
                            im = _decode_bc7_gnf_rgba(z.read(full))
                            bb = im.getchannel("A").point(lambda v: 255 if v > 15 else 0).getbbox()
                            out.append(im.crop(bb) if bb else im)
            return out

        def make_row_img(icons: list, cell_w: int = 32, height: int = 32, gap: int = 5):
            if not icons:
                return None
            total_w = len(icons) * cell_w + (len(icons) - 1) * gap + 8
            strip = Image.new("RGBA", (total_w, height), (0, 0, 0, 0))
            slot_h = height - 6
            for idx, im in enumerate(icons):
                sc = min(cell_w / im.width, slot_h / im.height)
                r = im.resize((max(1, round(im.width * sc)), max(1, round(im.height * sc))), Image.Resampling.LANCZOS)
                cx = 4 + idx * (cell_w + gap) + (cell_w - r.width) // 2
                cy = (height - r.height) // 2
                strip.alpha_composite(r, (cx, cy))
            ph = ImageTk.PhotoImage(strip)
            refs.append(ph)
            return ph

        def add_section(title: str, rows: list[tuple[str, list]]):
            box = tk.Frame(inner, bg=self.CARD, highlightbackground=self.TILE_BORDER, highlightthickness=1)
            box.pack(fill="x", pady=(0, 10))
            tk.Label(box, text=title, bg=self.CARD, fg="#8ad8ff", font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=12, pady=(8, 4))
            for label, icons in rows:
                r = tk.Frame(box, bg=self.CARD)
                r.pack(fill="x", padx=12, pady=(2, 6))
                tk.Label(r, text=label, bg=self.CARD, fg=self.MUTED, font=("Segoe UI", 8, "bold"), width=22, anchor="w").pack(side="left")
                ph = make_row_img(icons)
                if ph:
                    tk.Label(r, image=ph, bg=self.CARD, anchor="w").pack(side="left")

        p23 = "samplegame/ui/kettle_assets/skins/buttons/ps3/"
        p4 = "samplegame/ui/kettle_assets/skins/buttons/ps/"
        all_stems = ("digital_one", "digital_two", "digital_four", "digital_three", "left_bumper", "right_bumper", "left_trigger", "right_trigger", "start", "select", "guide")

        add_section("Xbox — KLPS (Authentic EA UFC 2/3 & UFC 4)", [
            ("MENUS · White (UFC 4/5/6)", grab_gnf(z4_p, p4, ("white/digital_one", "white/digital_two", "white/digital_four", "white/digital_three", "left_bumper", "right_bumper", "left_trigger", "right_trigger", "start", "select", "guide"))),
            ("MENUS · White (UFC 2/3)", grab_gnf(z23_p, p23, ("white/digital_one", "white/digital_two", "white/digital_four", "white/digital_three", "left_bumper", "right_bumper", "left_trigger", "right_trigger", "start", "select", "guide"))),
            ("MENUS · Outline", grab_gnf(z4_p, p4, ("ue_digital_one", "ue_digital_two", "ue_digital_four", "ue_digital_three", "left_bumper", "right_bumper"))),
            ("MOVES · Color Ring (UFC 4)", grab_gnf(z4_p, p4, ("digital_one", "digital_two", "digital_four", "digital_three", "left_trigger", "right_trigger", "left_right_bumper", "left_right_trigger"))),
            ("MOVES · Color Ring (UFC 2/3)", grab_gnf(z23_p, p23, ("digital_one", "digital_two", "digital_four", "digital_three", "left_trigger", "right_trigger"))),
            ("MOVES · Dark Disc", grab_gnf(z23_p, p23, ("black_large/digital_one", "black_large/digital_two", "black_large/digital_four", "black_large/digital_three")) + grab_gnf(z4_p, p4, ("left_trigger", "right_trigger"))),
        ])

        add_section("Xbox — Kenney (Flat Vector)", [
            ("MENUS · Kenney White", [im for s in all_stems + ("las_c", "ras_c") if (im := gamepad_icon("xbox", s, "kenney_white")) is not None]),
            ("MOVES · Kenney Color", [im for s in all_stems + ("las_c", "ras_c") if (im := gamepad_icon("xbox", s, "kenney_color")) is not None]),
        ])

        add_section("PlayStation — EA PS4 & Kenney", [
            ("EA PS4 · Colored", [im for s in ("digital_one", "digital_two", "digital_four", "digital_three") if (im := gamepad_icon("ps", s, "ps4_ea")) is not None]),
            ("Kenney · White", [im for s in all_stems + ("las_c", "ras_c") if (im := gamepad_icon("ps", s, "kenney_white")) is not None]),
            ("Kenney · Color", [im for s in all_stems + ("las_c", "ras_c") if (im := gamepad_icon("ps", s, "kenney_color")) is not None]),
        ])

        add_section("Nintendo Switch — Kenney", [
            ("Solid (B/A/Y/X · L/R/ZL/ZR)", [im for s in all_stems + ("las_c", "ras_c") if (im := gamepad_icon("switch", s, "solid")) is not None]),
            ("Outline", [im for s in all_stems if (im := gamepad_icon("switch", s, "outline")) is not None]),
        ])

        if kz_p:
            with zipfile.ZipFile(kz_p) as z:
                avail = set(z.namelist())
                def kb_list(ctrls):
                    out = []
                    for c in ctrls:
                        k = _key_to_kenney_png(self.controls.get(c, ""), avail)
                        if k:
                            im = Image.open(io.BytesIO(z.read(k))).convert("RGBA")
                            bb = im.getchannel("A").point(lambda v: 255 if v > 15 else 0).getbbox()
                            out.append(im.crop(bb) if bb else im)
                    return out
                add_section(f"Keyboard — Kenney (Active {self.game or 'Default'} Bindings)", [
                    ("Face & System", kb_list(("Cross", "Circle", "Square", "Triangle", "Options", "TouchPad", "L1", "R1", "L2", "R2", "L3", "R3"))),
                    ("Sticks & D-Pad", kb_list(("LeftStickUp", "LeftStickLeft", "LeftStickDown", "LeftStickRight", "Up", "Left", "Down", "Right", "RightStickUp", "RightStickLeft", "RightStickDown", "RightStickRight"))),
                ])

        foot = tk.Frame(win, bg=self.BG)
        foot.pack(fill="x", padx=20, pady=(0, 14))
        tk.Button(foot, text="Close", command=win.destroy, bg=self.TILE, fg=self.FG, relief="flat", font=("Segoe UI", 9, "bold"), padx=18, pady=5, cursor="hand2").pack(side="right")
        win.bind("<Escape>", lambda _e: win.destroy())
        x = self.winfo_rootx() + max(0, (self.winfo_width() - w_win) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - h_win) // 2)
        win.geometry(f"{w_win}x{h_win}+{x}+{y}")

    def _open_info_dialog(self, title: str, sections: list[tuple[str, str]], width: int = 620) -> None:
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=self.BG)
        if self._ico_path:
            try:
                win.iconbitmap(str(self._ico_path))
            except Exception:
                pass
        _apply_dark_titlebar(win)
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)

        hdr = tk.Frame(win, bg=self.BG)
        hdr.pack(fill="x", padx=20, pady=(16, 8))
        tk.Label(hdr, text=title, bg=self.BG, fg=self.FG, font=("Segoe UI", 14, "bold")).pack(anchor="w")

        body = tk.Frame(win, bg=self.CARD, highlightbackground=self.TILE_BORDER, highlightthickness=1)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        for heading, text in sections:
            tk.Label(body, text=heading, bg=self.CARD, fg="#8ad8ff", font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=14, pady=(10, 2))
            tk.Label(body, text=text, bg=self.CARD, fg=self.FG, font=("Segoe UI", 9), justify="left", anchor="w", wraplength=width - 76).pack(fill="x", padx=14, pady=(0, 4))
        tk.Frame(body, bg=self.CARD, height=8).pack()

        foot = tk.Frame(win, bg=self.BG)
        foot.pack(fill="x", padx=20, pady=(0, 14))
        tk.Button(foot, text="Close", command=win.destroy, bg=self.TILE, fg=self.FG, relief="flat", font=("Segoe UI", 9, "bold"), padx=18, pady=5, cursor="hand2").pack(side="right")
        win.bind("<Escape>", lambda _e: win.destroy())
        win.update_idletasks()
        h = win.winfo_reqheight()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - width) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - h) // 2)
        win.geometry(f"{width}x{h}+{x}+{y}")

    def _show_help(self) -> None:
        self._open_info_dialog("Help & Tips", [
            ("1. Quick Start",
             "Pick UFC 2, UFC 3, UFC 4, UFC 5, or UFC 6 at the top (or click Browse Folder... to locate a custom install). "
             "Choose your MENUS and MOVES presets on any card, preview them live, and click Install. "
             "Enable 'Apply to all detected UFC games' to patch all detected games in one click."),
            ("2. MENUS vs MOVES",
             "MENUS controls bottom-bar footer prompts, tab switches, and menu buttons. "
             "MOVES controls the controls screen, move list, in-fight hints, and tutorials."),
            ("3. Icon Pack Presets",
             "• Xbox: KLPS authentic EA Xbox One icons (White / Outline / Color menus × Ring / Disc / White moves) plus Kenney flat vector icons.\n"
             "• PlayStation: Stock restores 100% untouched original game files. PS4 brings classic colored X/O/Square/Triangle moves to UFC 6 (PS5). Kenney applies Kenney PlayStation icons.\n"
             "• Switch (Kenney): Nintendo Switch physical layout (B/A/Y/X, L/R/ZL/ZR, +/-) in Solid or Outline style.\n"
             "• Keyboard (Kenney): Crisp double-res Kenney keycaps matched to your actual bindings."),
            ("4. Keyboard Mapping (SacredFire & Kyty)",
             "Open 'Customize Keyboard Mapping' to rebind any control (click a key tile, press the new key, Esc cancels). "
             "The Keyboard preview updates live as you remap. Changes save automatically to bbport.ini (UFC 3/4) or UFC6.ini (UFC 6)."),
            ("5. Safety & Restoring Stock Files",
             "Always close the game before installing or restoring icons. Original game data is backed up automatically "
             "(in %LOCALAPPDATA%\\UFCButtonIconsInstaller for UFC 3/4, and .ufc6-input-icons-backup.bin for UFC 6). "
             "To revert anytime, select PlayStation (Stock / Stock) and click Restore PlayStation."),
        ], width=640)

    def _show_credits(self) -> None:
        self._open_info_dialog("Credits & Acknowledgments", [
            ("KLPS Xbox Icon Packs",
             "Authentic EA Sports UFC 2/3 and UFC 4 Xbox One GNF button icon packs (ufc23_xbox_gnf.zip & ufc4_xbox_gnf.zip), "
             "providing native EA Xbox typography, rings, dark discs, and bumper/trigger artwork."),
            ("Kenney — Input Prompts v1.5 (CC0 1.0)",
             "Keyboard & Mouse, Xbox Series, PlayStation Series, and Nintendo Switch double-resolution prompt icons by Kenney (kenney.nl), "
             "licensed under Creative Commons Zero (CC0 1.0 Universal)."),
            ("Typography",
             "Barlow Condensed Bold (SIL Open Font License) used for crisp fallback and keycap label rendering."),
            ("EA Sports UFC 3 / 4 / 6 Assets",
             "All original PlayStation and Xbox game archives remain the property of EA Sports. "
             "This installer patches only the user's own local game files reversibly with verified backups."),
            ("Community & Ecosystem",
             "Built for the UFC 3 / 4 / 6 PC emulation & overlay community (SacredFire, Kyty, Portheon, and Parsectagon)."),
        ], width=580)

    def _open_dummy_anchor(self) -> None:
        pass


if __name__ == "__main__":
    InstallerApp().mainloop()
