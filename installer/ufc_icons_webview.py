"""Parsectagon — UFC Controller Icons Mod (Edge WebView2 Edition)."""
from __future__ import annotations

import argparse
import base64
import ctypes
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import urllib.request
import webbrowser
import zipfile

import webview

APP_VERSION = "1.0.0"
GITHUB_RELEASES_API = "https://api.github.com/repos/thyaguster/ufc-controller-icons-mod/releases/latest"
GITHUB_RELEASES_PAGE = "https://github.com/thyaguster/ufc-controller-icons-mod/releases/latest"


def _parse_semver(tag: str) -> tuple[int, ...]:
    nums = []
    for part in str(tag or "").strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        nums.append(int(digits) if digits else 0)
    return tuple(nums or [0])

_MEIPASS = Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "_MEIPASS", None) else None
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent

for _p in (
    _MEIPASS,
    _HERE,
    _REPO / "ufc3" / "src",
    _REPO / "ufc4" / "src",
    _REPO / "ufc4" / "src" / "ufc4_keyboard",
    _REPO / "vendor" / "xbox-icons",
):
    if _p and _p.exists() and str(_p) not in sys.path:
        sys.path.append(str(_p))

# Reuse all verified game-detection, binding, prefs, and patching logic from ufc_icons_installer
import ufc_icons_installer as core_ui  # noqa: E402
from gamepad_presets import gamepad_icon  # noqa: E402
from ufc4_direct_icons import _decode_bc7_gnf_rgba  # noqa: E402

JS_KEY_MAP = {
    "Enter": "Return", " ": "Space", "Escape": "Escape", "Tab": "Tab",
    "Backspace": "Backspace", "CapsLock": "CapsLock",
    "ShiftLeft": "Left Shift", "ShiftRight": "Right Shift",
    "ControlLeft": "Left Ctrl", "ControlRight": "Right Ctrl",
    "AltLeft": "Left Alt", "AltRight": "Right Alt",
    "ArrowUp": "Up", "ArrowDown": "Down", "ArrowLeft": "Left", "ArrowRight": "Right",
    "PageUp": "PageUp", "PageDown": "PageDown",
}


def _img_to_data_uri(im) -> str:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _render_strip_uri(icons: list, width: int = 216, height: int = 30, cell_w: int = 30, gap: int = 4) -> str:
    from PIL import Image
    strip = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if icons:
        n = len(icons)
        slot_h = height - 4
        total_w = n * cell_w + (n - 1) * gap
        start_x = max(0, (width - total_w) // 2)
        for idx, im in enumerate(icons):
            sc = min(cell_w / im.width, slot_h / im.height)
            r = im.resize((max(1, round(im.width * sc)), max(1, round(im.height * sc))), Image.Resampling.LANCZOS)
            cx = start_x + idx * (cell_w + gap) + (cell_w - r.width) // 2
            cy = (height - r.height) // 2
            strip.alpha_composite(r, (cx, cy))
    return _img_to_data_uri(strip)


def _grab_gnf(zp: Path | None, pref: str, keys: tuple[str, ...]) -> list:
    out = []
    if zp and zp.is_file():
        with zipfile.ZipFile(zp) as z:
            names = set(z.namelist())
            for k in keys:
                full = f"{pref}{k}.gnf"
                if full in names:
                    im = _decode_bc7_gnf_rgba(z.read(full))
                    bb = im.getchannel("A").point(lambda v: 255 if v > 15 else 0).getbbox()
                    out.append(im.crop(bb) if bb else im)
    return out


def _stock_ps_glyphs(colored: bool) -> list:
    from PIL import Image, ImageDraw
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


class BridgeAPI:
    def __init__(self, initial_game: str | None = None, initial_folder: str | None = None) -> None:
        self._window: webview.Window | None = None
        self._game: str | None = None
        self._target: Path | None = None
        self._controls: dict[str, str] = core_ui.SACREDFIRE_DEFAULTS.copy()
        self._prefs: dict = core_ui.load_prefs()
        self._presets: dict[str, dict[str, str]] = {
            "xbox": {"menus": "white", "moves": "ring"},
            "ps": {"menus": "stock", "moves": "stock"},
            "switch": {"menus": "solid", "moves": "solid"},
        }
        self._busy = False
        self._pending_update: dict | None = None
        self._z23_p = next((p for p in (_MEIPASS / "ufc23_xbox_gnf.zip" if _MEIPASS else None, _REPO / "ufc3" / "src" / "ufc23_xbox_gnf.zip") if p and p.is_file()), None)
        self._z4_p = next((p for p in (_MEIPASS / "ufc4_xbox_gnf.zip" if _MEIPASS else None, _REPO / "ufc4" / "src" / "ufc4_xbox_gnf.zip") if p and p.is_file()), None)
        self._kz_p = next((p for p in (
            _MEIPASS / "ufc4_keyboard" / "keyboard-art" / "kenney_kb_prompts.zip" if _MEIPASS else None,
            _REPO / "ufc4" / "src" / "ufc4_keyboard" / "keyboard-art" / "kenney_kb_prompts.zip",
        ) if p and p.is_file()), None)
        loaded = False
        if initial_folder:
            fp = Path(initial_folder)
            if fp.exists():
                loaded = self._load_folder(fp)
        if not loaded and initial_game:
            g_id = initial_game.strip().upper().replace(" ", "")
            gp = self._known_game_path(g_id)
            if gp and gp.exists():
                loaded = self._load_folder(gp)
        if not loaded:
            self._auto_guess()

    def _known_game_path(self, game_id: str) -> Path | None:
        saved = self._prefs.get("paths", {}).get(game_id)
        if saved and Path(saved).exists():
            return Path(saved)
        for g, p in core_ui.KNOWN_PATHS:
            if g == game_id and p.exists():
                return p
        return None

    def _auto_guess(self) -> None:
        for g, _ in core_ui.KNOWN_PATHS:
            p = self._known_game_path(g)
            if p and p.exists():
                self._load_folder(p)
                return

    def _load_folder(self, folder: Path) -> bool:
        game, resolved = core_ui.detect_game(folder)
        if not game or not resolved:
            return False
        self._game, self._target = game, resolved
        self._prefs.setdefault("paths", {})[game] = str(resolved)
        core_ui.save_prefs(self._prefs)
        self._controls = core_ui.load_bbport_dict(core_ui.bbport_path(game)) if game in ("UFC2", "UFC3", "UFC4") else core_ui.load_kyty_dict(resolved)
        saved_p = self._prefs.get("presets", {}).get(game)
        if saved_p:
            for s in ("xbox", "ps", "switch"):
                if s in saved_p:
                    self._presets[s].update(saved_p[s])
        else:
            self._presets["xbox"]["menus"] = "white"
            self._presets["xbox"]["moves"] = "disc" if game in ("UFC5", "UFC6") else "ring"
            self._presets["ps"] = {"menus": "stock", "moves": "stock"}
            self._presets["switch"] = {"menus": "solid", "moves": "solid"}
        return True

    def _build_previews(self) -> dict:
        from PIL import Image
        g = self._game or "UFC4"
        p23 = "samplegame/ui/kettle_assets/skins/buttons/ps3/"
        p4 = "samplegame/ui/kettle_assets/skins/buttons/ps/"
        zp, pref = (self._z23_p, p23) if g in ("UFC2", "UFC3") else (self._z4_p, p4)

        # Xbox
        xm, xv = self._presets["xbox"]["menus"], self._presets["xbox"]["moves"]
        if xm == "kenney":
            xb_m = [im for s in ("digital_one", "digital_two", "digital_four", "digital_three", "left_bumper", "right_bumper") if (im := gamepad_icon("xbox", s, "kenney_white")) is not None]
        else:
            mf = ("ue_digital_one", "ue_digital_two", "ue_digital_four", "ue_digital_three") if xm == "outline" else (("digital_one", "digital_two", "digital_four", "digital_three") if xm == "colored" else ("white/digital_one", "white/digital_two", "white/digital_four", "white/digital_three"))
            xb_m = _grab_gnf(zp, pref, mf + ("left_bumper", "right_bumper"))
        if xv == "kenney":
            xb_v = [im for s in ("digital_one", "digital_two", "digital_four", "digital_three", "left_trigger", "right_trigger") if (im := gamepad_icon("xbox", s, "kenney_color")) is not None]
        else:
            vf = _grab_gnf(self._z23_p, p23, ("black_large/digital_one", "black_large/digital_two", "black_large/digital_four", "black_large/digital_three")) if xv == "disc" else _grab_gnf(zp, pref, ("white/digital_one", "white/digital_two", "white/digital_four", "white/digital_three") if xv == "white" else ("digital_one", "digital_two", "digital_four", "digital_three"))
            xb_v = vf + _grab_gnf(zp, pref, ("left_trigger", "right_trigger"))

        # PlayStation
        pm, pv = self._presets["ps"]["menus"], self._presets["ps"]["moves"]
        if pm == "kenney":
            ps_m = [im for s in ("digital_one", "digital_two", "digital_four", "digital_three", "left_bumper", "right_bumper") if (im := gamepad_icon("ps", s, "kenney_white")) is not None]
        elif pm == "kenney_color":
            ps_m = [im for s in ("digital_one", "digital_two", "digital_four", "digital_three") if (im := gamepad_icon("ps", s, "kenney_color")) is not None] + [im for s in ("left_bumper", "right_bumper") if (im := gamepad_icon("ps", s, "kenney_white")) is not None]
        elif pm == "ps4_color":
            ps_m = [im for s in ("digital_one", "digital_two", "digital_four", "digital_three") if (im := gamepad_icon("ps", s, "ps4_ea")) is not None] or _stock_ps_glyphs(True)
        else:
            ps_m = _stock_ps_glyphs(False)

        if pv == "kenney":
            ps_v = [im for s in ("digital_one", "digital_two", "digital_four", "digital_three", "left_trigger", "right_trigger") if (im := gamepad_icon("ps", s, "kenney_color")) is not None]
        elif pv == "ps4_color":
            ps_v = [im for s in ("digital_one", "digital_two", "digital_four", "digital_three") if (im := gamepad_icon("ps", s, "ps4_ea")) is not None] or _stock_ps_glyphs(True)
        else:
            ps_v = _stock_ps_glyphs(g not in ("UFC5", "UFC6"))

        # Switch
        sm, sv = self._presets["switch"]["menus"], self._presets["switch"]["moves"]
        sw_m = [im for s in ("digital_one", "digital_two", "digital_four", "digital_three", "left_bumper", "right_bumper") if (im := gamepad_icon("switch", s, sm)) is not None]
        sw_v = [im for s in ("digital_one", "digital_two", "digital_four", "digital_three", "left_trigger", "right_trigger") if (im := gamepad_icon("switch", s, sv)) is not None]

        # Keyboard (live from self._controls)
        kb_m, kb_v = [], []
        if self._kz_p:
            with zipfile.ZipFile(self._kz_p) as z:
                avail = set(z.namelist())
                for ctrl in ("Cross", "Circle", "Options", "TouchPad", "L1", "R1"):
                    k = core_ui._key_to_kenney_png(self._controls.get(ctrl, ""), avail)
                    if k:
                        im = Image.open(io.BytesIO(z.read(k))).convert("RGBA")
                        bb = im.getchannel("A").point(lambda v: 255 if v > 15 else 0).getbbox()
                        kb_m.append(im.crop(bb) if bb else im)
                for ctrl in ("LeftStickUp", "LeftStickLeft", "LeftStickDown", "LeftStickRight", "L2", "R2"):
                    k = core_ui._key_to_kenney_png(self._controls.get(ctrl, ""), avail)
                    if k:
                        im = Image.open(io.BytesIO(z.read(k))).convert("RGBA")
                        bb = im.getchannel("A").point(lambda v: 255 if v > 15 else 0).getbbox()
                        kb_v.append(im.crop(bb) if bb else im)

        return {
            "xbox": {"m": _render_strip_uri(xb_m), "v": _render_strip_uri(xb_v)},
            "ps": {"m": _render_strip_uri(ps_m), "v": _render_strip_uri(ps_v)},
            "switch": {"m": _render_strip_uri(sw_m), "v": _render_strip_uri(sw_v)},
            "keyboard": {"m": _render_strip_uri(kb_m), "v": _render_strip_uri(kb_v)},
        }

    def get_state(self) -> dict:
        installed = core_ui.detect_installed_pack(self._game, self._target, self._prefs) if (self._game and self._target) else ""
        games = [{"id": g, "label": f"UFC {g[3:]}", "exists": self._known_game_path(g) is not None} for g, _ in core_ui.KNOWN_PATHS]
        nice_g = f"UFC {self._game[3:]}" if (self._game and self._game.startswith("UFC")) else (self._game or "")
        return {
            "game": self._game,
            "nice_game": nice_g,
            "target": str(self._target) if self._target else "",
            "installed": installed,
            "games": games,
            "presets": self._presets,
            "controls": {k: core_ui.SHORT_DISPLAY.get(v, v.upper()) for k, v in self._controls.items()},
            "previews": self._build_previews(),
            "busy": self._busy,
        }

    def select_game(self, game_id: str) -> dict:
        p = self._known_game_path(game_id)
        if p and p.exists():
            self._load_folder(p)
            return self.get_state()
        return self.browse_folder()

    def browse_folder(self) -> dict:
        if self._window:
            res = self._window.create_file_dialog(webview.FileDialog.FOLDER)
            if res and len(res) > 0:
                chosen = Path(res[0])
                if not self._load_folder(chosen):
                    self._window.evaluate_js(f"window.onLog({json.dumps(f'Unrecognized UFC folder: {chosen}')})")
        return self.get_state()

    def set_preset(self, style: str, kind: str, val: str) -> dict:
        self._presets[style][kind] = val
        if self._game:
            self._prefs.setdefault("presets", {})[self._game] = {s: dict(v) for s, v in self._presets.items()}
            core_ui.save_prefs(self._prefs)
        return self.get_state()

    def set_key(self, ctrl: str, code: str, key: str) -> dict:
        mapped = JS_KEY_MAP.get(code) or JS_KEY_MAP.get(key)
        if not mapped:
            if len(key) == 1 and key.isalnum():
                mapped = key.upper()
            elif key.startswith("F") and key[1:].isdigit():
                mapped = key.upper()
            else:
                mapped = key
        self._controls[ctrl] = mapped
        return self.get_state()

    def reset_keys(self) -> dict:
        self._controls = (core_ui.UFC6_DEFAULTS if self._game in ("UFC5", "UFC6") else core_ui.SACREDFIRE_DEFAULTS).copy()
        return self.get_state()

    def open_url(self, url: str) -> None:
        webbrowser.open(url)

    def check_update(self) -> None:
        def _worker() -> None:
            try:
                req = urllib.request.Request(
                    GITHUB_RELEASES_API,
                    headers={"Accept": "application/vnd.github+json", "User-Agent": f"UFC-Controller-Icons-Mod/{APP_VERSION}"},
                )
                with urllib.request.urlopen(req, timeout=4) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))
                tag = str(data.get("tag_name") or "").strip()
                if not tag or _parse_semver(tag) <= _parse_semver(APP_VERSION):
                    return
                dl_url = ""
                for a in data.get("assets") or []:
                    if str(a.get("name", "")).lower() == "ufc_controller_icons_mod.exe":
                        dl_url = str(a.get("browser_download_url") or "")
                        break
                self._pending_update = {"tag": tag, "url": dl_url, "page": str(data.get("html_url") or GITHUB_RELEASES_PAGE)}
                if self._window:
                    self._window.evaluate_js(f"window.onUpdateAvailable({json.dumps(tag)})")
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def apply_update(self) -> dict:
        upd = self._pending_update
        if not upd:
            return {"ok": False, "message": "No update available."}
        if not getattr(sys, "frozen", False) or not upd.get("url"):
            webbrowser.open(upd.get("page") or GITHUB_RELEASES_PAGE)
            return {"ok": True, "message": "Opened release page."}
        exe_path = Path(sys.executable).resolve()
        new_path = exe_path.with_suffix(".exe.new")

        def _worker() -> None:
            try:
                if self._window:
                    self._window.evaluate_js(f"window.onLog({json.dumps('Downloading update ' + upd['tag'] + '...')})")
                req = urllib.request.Request(upd["url"], headers={"User-Agent": f"UFC-Controller-Icons-Mod/{APP_VERSION}"})
                with urllib.request.urlopen(req, timeout=60) as resp, open(new_path, "wb") as out:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        out.write(chunk)
                if new_path.stat().st_size < 1_000_000 or new_path.read_bytes()[:2] != b"MZ":
                    new_path.unlink(missing_ok=True)
                    raise RuntimeError("Downloaded update file was invalid.")
                bat = exe_path.with_suffix(".update.cmd")
                args_str = " ".join(f'"{a}"' for a in sys.argv[1:])
                bat.write_text(
                    "@echo off\r\n"
                    f"set TARGET={exe_path}\r\n"
                    f"set NEW={new_path}\r\n"
                    ":retry\r\n"
                    "timeout /t 1 /nobreak >nul\r\n"
                    "move /y \"%NEW%\" \"%TARGET%\" >nul 2>&1\r\n"
                    "if errorlevel 1 goto retry\r\n"
                    f"start \"\" \"%TARGET%\" {args_str}\r\n"
                    "del \"%~f0\" >nul 2>&1\r\n",
                    encoding="utf-8",
                )
                subprocess.Popen(
                    ["cmd", "/c", str(bat)],
                    creationflags=0x08000000 | 0x00000008,  # CREATE_NO_WINDOW | DETACHED_PROCESS
                    close_fds=True,
                )
                if self._window:
                    self._window.destroy()
            except Exception as exc:
                if self._window:
                    self._window.evaluate_js(f"window.onLog({json.dumps('Update failed: ' + str(exc))})")

        threading.Thread(target=_worker, daemon=True).start()
        return {"ok": True}

    def resize_height(self, content_h: int) -> None:
        if not self._window:
            return
        max_h = 880
        try:
            sh = ctypes.windll.user32.GetSystemMetrics(1)
            if sh > 500:
                max_h = sh - 80
        except Exception:
            pass
        want_h = min(max_h, max(470, int(content_h) + 38))
        self._window.resize(self._window.width, want_h)

    def set_modal_expanded(self, expanded: bool) -> None:
        if not self._window:
            return
        if os.name == "nt":
            try:
                user32 = ctypes.windll.user32
                hwnd = user32.FindWindowW(None, self._window.title)
                if hwnd:
                    class _RECT(ctypes.Structure):
                        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
                    if expanded:
                        cur = _RECT()
                        if user32.GetWindowRect(hwnd, ctypes.byref(cur)):
                            self._pre_expand = (cur.left, cur.top, cur.right - cur.left, cur.bottom - cur.top)
                        rc = _RECT()
                        if user32.SystemParametersInfoW(48, 0, ctypes.byref(rc), 0):
                            wa_w = rc.right - rc.left
                            wa_h = rc.bottom - rc.top
                            cur_w = (cur.right - cur.left) if getattr(self, "_pre_expand", None) else 980
                            w = min(wa_w - 60, max(cur_w, 1120))
                            h = max(620, wa_h - 40)
                            x = rc.left + max(0, (wa_w - w) // 2)
                            y = rc.top + max(0, (wa_h - h) // 2)
                            user32.SetWindowPos(hwnd, 0, x, y, w, h, 0x0004)  # SWP_NOZORDER
                            return
                    else:
                        prev = getattr(self, "_pre_expand", None)
                        if prev:
                            px, py, pw, ph = prev
                            user32.SetWindowPos(hwnd, 0, px, py, pw, ph, 0x0004)
                            self._pre_expand = None
                            return
            except Exception:
                pass
        if expanded:
            self._pre_expand_wh = (self._window.width, self._window.height)
            self._window.resize(1120, 860)
        else:
            prev = getattr(self, "_pre_expand_wh", None)
            if prev:
                self._window.resize(prev[0], prev[1])
                self._pre_expand_wh = None

    def get_all_icons(self) -> list[dict]:
        from PIL import Image
        p23 = "samplegame/ui/kettle_assets/skins/buttons/ps3/"
        p4 = "samplegame/ui/kettle_assets/skins/buttons/ps/"
        all_s = ("digital_one", "digital_two", "digital_four", "digital_three", "left_bumper", "right_bumper", "left_trigger", "right_trigger", "start", "select", "guide")

        def strip(icons):
            if not icons:
                return ""
            w = len(icons) * 37 + 8
            return _render_strip_uri(icons, width=w, height=34, cell_w=32, gap=5)

        sections = [
            {
                "title": "Xbox — KLPS (Authentic EA UFC 2/3 & UFC 4)",
                "rows": [
                    ("MENUS · White (UFC 4/5/6)", strip(_grab_gnf(self._z4_p, p4, ("white/digital_one", "white/digital_two", "white/digital_four", "white/digital_three", "left_bumper", "right_bumper", "left_trigger", "right_trigger", "start", "select", "guide")))),
                    ("MENUS · White (UFC 2/3)", strip(_grab_gnf(self._z23_p, p23, ("white/digital_one", "white/digital_two", "white/digital_four", "white/digital_three", "left_bumper", "right_bumper", "left_trigger", "right_trigger", "start", "select", "guide")))),
                    ("MENUS · Outline", strip(_grab_gnf(self._z4_p, p4, ("ue_digital_one", "ue_digital_two", "ue_digital_four", "ue_digital_three", "left_bumper", "right_bumper")))),
                    ("MOVES · Color Ring (UFC 4)", strip(_grab_gnf(self._z4_p, p4, ("digital_one", "digital_two", "digital_four", "digital_three", "left_trigger", "right_trigger", "left_right_bumper", "left_right_trigger")))),
                    ("MOVES · Color Ring (UFC 2/3)", strip(_grab_gnf(self._z23_p, p23, ("digital_one", "digital_two", "digital_four", "digital_three", "left_trigger", "right_trigger")))),
                    ("MOVES · Dark Disc", strip(_grab_gnf(self._z23_p, p23, ("black_large/digital_one", "black_large/digital_two", "black_large/digital_four", "black_large/digital_three")) + _grab_gnf(self._z4_p, p4, ("left_trigger", "right_trigger")))),
                ],
            },
            {
                "title": "Xbox — Kenney (Flat Vector)",
                "rows": [
                    ("MENUS · Kenney White", strip([im for s in all_s + ("las_c", "ras_c") if (im := gamepad_icon("xbox", s, "kenney_white")) is not None])),
                    ("MOVES · Kenney Color", strip([im for s in all_s + ("las_c", "ras_c") if (im := gamepad_icon("xbox", s, "kenney_color")) is not None])),
                ],
            },
            {
                "title": "PlayStation — EA PS4 & Kenney",
                "rows": [
                    ("EA PS4 · Colored", strip([im for s in ("digital_one", "digital_two", "digital_four", "digital_three") if (im := gamepad_icon("ps", s, "ps4_ea")) is not None])),
                    ("Kenney · White", strip([im for s in all_s + ("las_c", "ras_c") if (im := gamepad_icon("ps", s, "kenney_white")) is not None])),
                    ("Kenney · Color", strip([im for s in all_s + ("las_c", "ras_c") if (im := gamepad_icon("ps", s, "kenney_color")) is not None])),
                ],
            },
            {
                "title": "Nintendo Switch — Kenney",
                "rows": [
                    ("Solid (B/A/Y/X · L/R/ZL/ZR)", strip([im for s in all_s + ("las_c", "ras_c") if (im := gamepad_icon("switch", s, "solid")) is not None])),
                    ("Outline", strip([im for s in all_s if (im := gamepad_icon("switch", s, "outline")) is not None])),
                ],
            },
        ]
        if self._kz_p:
            with zipfile.ZipFile(self._kz_p) as z:
                avail = set(z.namelist())
                def kb_list(ctrls):
                    out = []
                    for c in ctrls:
                        k = core_ui._key_to_kenney_png(self._controls.get(c, ""), avail)
                        if k:
                            im = Image.open(io.BytesIO(z.read(k))).convert("RGBA")
                            bb = im.getchannel("A").point(lambda v: 255 if v > 15 else 0).getbbox()
                            out.append(im.crop(bb) if bb else im)
                    return out
                sections.append({
                    "title": f"Keyboard — Kenney (Active {self._game or 'Default'} Bindings)",
                    "rows": [
                        ("Face & System", strip(kb_list(("Cross", "Circle", "Square", "Triangle", "Options", "TouchPad", "L1", "R1", "L2", "R2", "L3", "R3")))),
                        ("Sticks & D-Pad", strip(kb_list(("LeftStickUp", "LeftStickLeft", "LeftStickDown", "LeftStickRight", "Up", "Left", "Down", "Right", "RightStickUp", "RightStickLeft", "RightStickDown", "RightStickRight")))),
                    ],
                })
        return sections

    def install(self, style: str, apply_all: bool) -> dict:
        if self._busy:
            return {"ok": False, "message": "Busy..."}
        if not self._game or not self._target:
            return {"ok": False, "message": "Select a UFC game first."}
        self._busy = True
        game, target, controls = self._game, self._target, dict(self._controls)
        p = self._presets.get(style, {"menus": "white", "moves": "ring"})
        pm, pv = p["menus"], p["moves"]

        def _push_log(msg: str) -> None:
            if self._window:
                self._window.evaluate_js(f"window.onLog({json.dumps(str(msg))})")

        def worker() -> None:
            try:
                targets: list[tuple[str, Path]] = []
                if apply_all:
                    seen = set()
                    for g_id, _ in core_ui.KNOWN_PATHS:
                        cand = self._known_game_path(g_id)
                        if cand and cand.exists():
                            g, r = core_ui.detect_game(cand)
                            if g and r and g not in seen:
                                targets.append((g, r))
                                seen.add(g)
                    if game and target and game not in seen:
                        targets.append((game, target))
                else:
                    targets.append((game, target))

                if style == "keyboard":
                    lbl = "Keyboard (Kenney)"
                elif style == "ps" and pm == "stock" and pv == "stock":
                    lbl = "PlayStation (Stock)"
                else:
                    lbl = f"{ {'xbox':'Xbox','ps':'PlayStation','switch':'Switch'}.get(style, style.title()) } ({pm.title()}/{pv.title()})"

                results = []
                for g, r in targets:
                    _push_log(f"Applying {lbl} to {g}...")
                    c_for_g = controls if g == game else (core_ui.load_bbport_dict(core_ui.bbport_path(g)) if g in ("UFC2", "UFC3", "UFC4") else core_ui.load_kyty_dict(r))
                    res = core_ui.apply_game_icons(g, r, style, c_for_g, _push_log, menus_preset=pm, moves_preset=pv)
                    results.append(f"{g}: {res}")
                    self._prefs.setdefault("installed", {})[g] = lbl
                core_ui.save_prefs(self._prefs)
                final = "\n".join(results) if len(results) > 1 else results[0]
                self._busy = False
                if self._window:
                    self._window.evaluate_js(f"window.onInstallDone(true, {json.dumps(final)}, {json.dumps(self.get_state())})")
            except Exception as exc:
                self._busy = False
                if self._window:
                    self._window.evaluate_js(f"window.onInstallDone(false, {json.dumps(str(exc))}, {json.dumps(self.get_state())})")

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<style>
  :root {
    --bg: #0f1117; --card: #171a23; --sub: #12151e; --tile: #202534; --border: #2a3042;
    --fg: #f1f4f9; --muted: #8b94a7; --red: #e63946; --green: #229659; --blue: #3b6ef0;
    --switch: #c82b40; --discord: #5865F2;
  }
  * { box-sizing: border-box; user-select: none; }
  html, body { margin: 0; padding: 0; background: var(--bg); color: var(--fg); font-family: "Segoe UI", system-ui, sans-serif; font-size: 13px; overflow-x: hidden; }
  ::-webkit-scrollbar { width: 8px; height: 8px; }
  ::-webkit-scrollbar-track { background: var(--sub); }
  ::-webkit-scrollbar-thumb { background: #31384c; border-radius: 99px; }
  ::-webkit-scrollbar-thumb:hover { background: #4a5472; }

  .app { padding: 16px 20px 14px; display: flex; flex-direction: column; gap: 12px; }
  .hdr { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .brand-wrap { display: flex; flex-direction: column; gap: 3px; }
  .brand-row { display: flex; align-items: center; gap: 10px; }
  .badge { background: linear-gradient(135deg, #e63946, #c92434); color: #fff; font-weight: 800; font-size: 10px; letter-spacing: .08em; padding: 3px 8px; border-radius: 5px; border: 0; cursor: pointer; box-shadow: 0 2px 10px rgba(230,57,70,.35); transition: .15s; }
  .badge:hover { filter: brightness(1.12); transform: translateY(-1px); }
  h1 { margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -.01em; }
  .sub { color: var(--muted); font-size: 12px; }

  .hdr-btns { display: flex; align-items: center; gap: 6px; }
  .hbtn { background: var(--tile); color: var(--fg); border: 1px solid var(--border); border-radius: 7px; padding: 6px 11px; font-size: 11.5px; font-weight: 600; cursor: pointer; transition: .15s; }
  .hbtn:hover { background: #2a3145; border-color: #3d4660; transform: translateY(-1px); }
  .hbtn.icons { color: #6be675; }
  .hbtn.help { color: #8ad8ff; }
  .hbtn.gh { background: #21262d; }
  .hbtn.dc { background: var(--discord); border-color: #6c78ff; color: #fff; }
  .hbtn.dc:hover { background: #4956e8; }

  .bar { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 11px 14px; display: flex; flex-direction: column; gap: 8px; }
  .bar-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .games { display: flex; align-items: center; gap: 6px; }
  .games .lbl { color: var(--muted); font-weight: 600; font-size: 12px; margin-right: 4px; }
  .gpill { background: var(--tile); color: var(--fg); border: 1px solid transparent; border-radius: 7px; padding: 5px 12px; font-size: 12px; font-weight: 700; cursor: pointer; transition: .15s; }
  .gpill:hover { background: #2b3246; }
  .gpill.missing { opacity: .55; border: 1px dashed #3d4660; }
  .gpill.missing:hover { opacity: 1; }
  .gpill.active { background: var(--red); color: #fff; opacity: 1; border-color: transparent; box-shadow: 0 2px 10px rgba(230,57,70,.35); }
  .bar-right { display: flex; align-items: center; gap: 12px; }
  .chk { display: flex; align-items: center; gap: 6px; color: var(--fg); font-size: 12px; cursor: pointer; }
  .chk input { accent-color: var(--red); width: 14px; height: 14px; cursor: pointer; }
  .bar-bot { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .detect { color: #6be675; font-size: 12px; font-family: "Consolas", monospace; }
  .inst-badge { background: rgba(138,216,255,.12); color: #8ad8ff; border: 1px solid rgba(138,216,255,.25); border-radius: 99px; padding: 2px 10px; font-size: 11px; font-weight: 700; }

  .cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 11px; padding: 12px; display: flex; flex-direction: column; gap: 8px; transition: border-color .15s; }
  .card:hover { border-color: #3c4560; }
  .card-title { text-align: center; font-size: 14px; font-weight: 700; }
  .prow { display: flex; align-items: center; justify-content: space-between; min-height: 24px; }
  .prow.center { justify-content: center; }
  .plbl { color: var(--muted); font-size: 10px; font-weight: 700; letter-spacing: .06em; }

  .seg { display: inline-flex; background: #0e1017; border: 1px solid #282e40; border-radius: 6px; padding: 2px; gap: 2px; }
  .seg button { background: transparent; color: var(--muted); border: 0; border-radius: 4px; padding: 2px 6px; font-size: 10px; font-weight: 700; cursor: pointer; transition: .12s; }
  .seg button:hover { color: var(--fg); }
  .seg button.on-xbox { background: var(--green); color: #fff; }
  .seg button.on-ps { background: var(--blue); color: #fff; }
  .seg button.on-switch { background: var(--switch); color: #fff; }

  .strip-box { display: flex; justify-content: center; align-items: center; height: 32px; }
  .strip-box img { max-width: 100%; height: 30px; image-rendering: auto; }

  .act-btn { margin-top: auto; width: 100%; border: 0; border-radius: 8px; padding: 9px 10px; font-size: 12.5px; font-weight: 700; color: #fff; cursor: pointer; transition: .15s; }
  .act-btn:hover { filter: brightness(1.1); transform: translateY(-1px); }
  .act-btn:disabled { opacity: .5; cursor: not-allowed; transform: none; }
  .act-btn.xbox { background: linear-gradient(135deg, #27a261, #1e7f4b); }
  .act-btn.ps-stock { background: #2a3040; border: 1px solid #3a4258; }
  .act-btn.ps-custom { background: linear-gradient(135deg, #4376f5, #2f5bd4); }
  .act-btn.switch { background: linear-gradient(135deg, #d12e45, #a91f33); }
  .act-btn.kb { background: linear-gradient(135deg, #e63946, #c62735); }

  .drawer-toggle { background: var(--card); border: 1px solid var(--border); border-radius: 9px; padding: 9px 14px; color: var(--fg); font-weight: 700; font-size: 12px; text-align: left; cursor: pointer; display: flex; align-items: center; justify-content: space-between; }
  .drawer-toggle:hover { background: #1d212d; }
  .drawer { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 12px; display: none; flex-direction: column; gap: 10px; }
  .drawer.open { display: flex; }
  .drawer-top { display: flex; align-items: center; justify-content: space-between; font-size: 11.5px; color: var(--muted); }
  .kgrid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
  .kcol { background: var(--sub); border: 1px solid #242a3a; border-radius: 8px; padding: 10px; display: flex; flex-direction: column; gap: 6px; }
  .ksec { color: var(--muted); font-size: 10px; font-weight: 700; letter-spacing: .06em; margin-top: 4px; }
  .ksec:first-child { margin-top: 0; }
  .krow { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .krow .kname { display: flex; align-items: center; gap: 6px; font-size: 12px; }
  .dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
  .ktile { background: var(--tile); border: 1px solid var(--border); border-radius: 6px; color: var(--fg); font-size: 11px; font-weight: 700; min-width: 74px; padding: 4px 8px; text-align: center; cursor: pointer; transition: .12s; }
  .ktile:hover { border-color: #586588; }
  .ktile.cap { background: #4a1d24; border-color: var(--red); color: #fff; }
  .tcluster { display: grid; grid-template-columns: repeat(3, 66px); gap: 4px; justify-content: center; margin: 2px 0; }
  .tkey { background: var(--tile); border: 1px solid var(--border); border-radius: 6px; padding: 3px 4px; text-align: center; cursor: pointer; }
  .tkey:hover { border-color: #586588; }
  .tkey.cap { background: #4a1d24; border-color: var(--red); }
  .tkey .tsub { font-size: 8.5px; color: var(--muted); font-weight: 700; }
  .tkey .tval { font-size: 11px; font-weight: 700; }

  .status { background: #0a0c11; border-top: 1px solid #1f2433; padding: 7px 14px; font-family: "Consolas", monospace; font-size: 11.5px; color: #b5bfd3; position: fixed; left: 0; right: 0; bottom: 0; }
  .spacer { height: 28px; }

  /* Modal Overlay */
  .modal-bg { position: fixed; inset: 0; background: rgba(5,7,11,.75); backdrop-filter: blur(4px); display: none; align-items: center; justify-content: center; z-index: 50; padding: 20px; }
  .modal-bg.open { display: flex; }
  .modal-bg.expanded { padding: 8px; }
  .modal { background: var(--bg); border: 1px solid var(--border); border-radius: 12px; width: 100%; max-width: 820px; max-height: 86vh; display: flex; flex-direction: column; box-shadow: 0 20px 60px rgba(0,0,0,.6); }
  .modal.expanded { max-width: 100%; max-height: 100%; height: 100%; }
  .modal-hdr { padding: 14px 18px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }
  .modal-hdr h2 { margin: 0; font-size: 15px; }
  .modal-actions { display: flex; gap: 8px; align-items: center; }
  .modal-body { padding: 14px 18px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
  .msec { background: var(--card); border: 1px solid var(--border); border-radius: 9px; padding: 10px 14px; display: flex; flex-direction: column; gap: 6px; }
  .msec h3 { margin: 0 0 2px; font-size: 12px; color: #8ad8ff; }
  .msec p { margin: 0; font-size: 12px; color: #d6dceb; line-height: 1.5; white-space: pre-line; }
  .irow { display: flex; align-items: center; gap: 12px; }
  .irow span { width: 175px; flex-shrink: 0; font-size: 11px; font-weight: 700; color: var(--muted); }
  .irow img { height: 32px; }
</style>
</head>
<body>
<div class="app">
  <div class="hdr">
    <div class="brand-wrap">
      <div class="brand-row">
        <button class="badge" title="Visit parsectagon.cc" onclick="api().open_url('https://parsectagon.cc')">PARSECTAGON</button>
        <h1>UFC Controller Icons Mod</h1>
      </div>
      <div class="sub">Choose your game and icon pack below. Customize keyboard bindings anytime if needed.</div>
    </div>
    <div class="hdr-btns">
      <button class="hbtn" id="upd-btn" style="display:none;background:#1a3d2a;border-color:#2ea05f;color:#7df2a8;" onclick="doUpdate()">Update</button>
      <button class="hbtn icons" onclick="openIcons()">All Icons</button>
      <button class="hbtn help" onclick="openHelp()">? Help</button>
      <button class="hbtn" onclick="openCredits()">Credits</button>
      <button class="hbtn gh" onclick="api().open_url('https://github.com/thyaguster/ufc-controller-icons-mod')">GitHub</button>
      <button class="hbtn dc" onclick="api().open_url('https://discord.gg/a84pBw2Ff')">Discord</button>
    </div>
  </div>

  <div class="bar">
    <div class="bar-top">
      <div class="games">
        <span class="lbl">Game:</span>
        <div id="game-pills" style="display:flex;gap:6px;"></div>
      </div>
      <div class="bar-right">
        <label class="chk"><input type="checkbox" id="apply-all" /> Apply to all detected UFC games</label>
        <button class="hbtn" onclick="browse()">Browse Folder...</button>
      </div>
    </div>
    <div class="bar-bot">
      <div class="detect" id="detect-lbl">Detecting games...</div>
      <div class="inst-badge" id="inst-badge"></div>
    </div>
  </div>

  <div class="cards" id="cards"></div>

  <button class="drawer-toggle" id="drawer-btn" onclick="toggleDrawer()">
    <span>▸ &nbsp;Customize Keyboard Mapping (Optional)</span>
    <span style="color:var(--muted);font-weight:500;font-size:11px;">SacredFire (bbport.ini) &amp; Kyty (UFC6.ini)</span>
  </button>
  <div class="drawer" id="drawer">
    <div class="drawer-top">
      <span>Click any binding below, then press a new key (Esc cancels). Live preview updates automatically.</span>
      <button class="hbtn" onclick="resetKeys()">Reset Defaults</button>
    </div>
    <div class="kgrid" id="kgrid"></div>
  </div>

  <div class="spacer"></div>
</div>
<div class="status" id="status">Ready.</div>

<div class="modal-bg" id="modal-bg" onclick="if(event.target===this)closeModal()">
  <div class="modal" id="modal-box">
    <div class="modal-hdr">
      <h2 id="modal-title">Modal</h2>
      <div class="modal-actions">
        <button class="hbtn" id="modal-expand-btn" style="display:none" onclick="toggleModalExpand()">⤢ Expand</button>
        <button class="hbtn" onclick="closeModal()">Close</button>
      </div>
    </div>
    <div class="modal-body" id="modal-body"></div>
  </div>
</div>

<script>
const api = () => window.pywebview.api;
let S = null;
let capturing = null;
let drawerOpen = false;

const MENU_OPTS = {
  xbox: [["white","White"],["outline","Outl"],["colored","Color"],["kenney","Ken"]],
  ps: [["stock","Stock"],["ps4_color","PS4"],["kenney","Ken"],["kenney_color","KenC"]],
  switch: [["solid","Solid"],["outline","Outline"]],
};
const MOVE_OPTS = {
  xbox: [["ring","Ring"],["disc","Disc"],["white","White"],["kenney","Ken"]],
  ps: [["stock","Stock"],["ps4_color","PS4"],["kenney","Kenney"]],
  switch: [["solid","Solid"],["outline","Outline"]],
};

function render(st) {
  S = st;
  const gp = document.getElementById("game-pills");
  gp.innerHTML = st.games.map(g =>
    `<button class="gpill ${st.game===g.id?'active':''} ${!g.exists?'missing':''}" title="${g.exists ? 'Select ' + g.label : 'Click to locate ' + g.label + ' folder...'}" onclick="pickGame('${g.id}')">${g.label}${g.exists?'':' +'}</button>`
  ).join("");
  const dl = document.getElementById("detect-lbl");
  if (st.game) {
    dl.textContent = `Detected ${st.nice_game}:  ${st.target}`;
    dl.style.color = "#6be675";
  } else {
    dl.textContent = "No UFC game detected automatically — click Browse Folder... or any game button to locate it.";
    dl.style.color = "#f5b841";
  }
  const ib = document.getElementById("inst-badge");
  ib.textContent = st.installed ? `Installed: ${st.installed}` : "";
  ib.style.display = st.installed ? "" : "none";

  const psStock = st.presets.ps.menus === "stock" && st.presets.ps.moves === "stock";
  const cardDefs = [
    { id:"xbox", title:"Xbox", btn:"Install Xbox Icons", bcls:"xbox" },
    { id:"ps", title:"PlayStation", btn: psStock ? "Restore PlayStation" : "Install PS Icons", bcls: psStock ? "ps-stock" : "ps-custom" },
    { id:"switch", title:"Switch (Kenney)", btn:"Install Switch Icons", bcls:"switch" },
    { id:"keyboard", title:"Keyboard (Kenney)", btn:"Save Keys & Install", bcls:"kb" },
  ];
  document.getElementById("cards").innerHTML = cardDefs.map(c => {
    const mOpts = MENU_OPTS[c.id], vOpts = MOVE_OPTS[c.id];
    const mkSeg = (kind, opts) => opts ? `<div class="seg">${opts.map(([v,t]) =>
      `<button class="${st.presets[c.id][kind]===v?'on-'+c.id:''}" onclick="setPreset('${c.id}','${kind}','${v}')">${t}</button>`
    ).join("")}</div>` : "";
    return `<div class="card">
      <div class="card-title">${c.title}</div>
      <div class="prow ${mOpts?'':'center'}"><span class="plbl">MENUS</span>${mkSeg('menus', mOpts)}</div>
      <div class="strip-box"><img src="${st.previews[c.id].m}" /></div>
      <div class="prow ${vOpts?'':'center'}"><span class="plbl">MOVES</span>${mkSeg('moves', vOpts)}</div>
      <div class="strip-box"><img src="${st.previews[c.id].v}" /></div>
      <button class="act-btn ${c.bcls}" ${st.busy?'disabled':''} onclick="doInstall('${c.id}')">${c.btn}</button>
    </div>`;
  }).join("");
  renderKeymap();
}

function renderKeymap() {
  if (!S) return;
  const c = S.controls;
  const tKey = (ctrl, sub) => `<div class="tkey ${capturing===ctrl?'cap':''}" onclick="startCap('${ctrl}')">
    <div class="tsub">${sub}</div><div class="tval">${capturing===ctrl?'PRESS...':(c[ctrl]||'-')}</div></div>`;
  const row = (ctrl, lbl, dot) => `<div class="krow">
    <span class="kname"><span class="dot" style="background:${dot}"></span>${lbl}</span>
    <button class="ktile ${capturing===ctrl?'cap':''}" onclick="startCap('${ctrl}')">${capturing===ctrl?'PRESS...':(c[ctrl]||'-')}</button>
  </div>`;
  document.getElementById("kgrid").innerHTML = `
    <div class="kcol">
      <div class="ksec">LEFT STICK (MOVE)</div>
      <div class="tcluster"><div></div>${tKey('LeftStickUp','UP')}<div></div>${tKey('LeftStickLeft','LEFT')}${tKey('LeftStickDown','DOWN')}${tKey('LeftStickRight','RIGHT')}</div>
      ${row('L3','L3 Click','#8b94a7')}
      <div class="ksec">D-PAD</div>
      <div class="tcluster"><div></div>${tKey('Up','UP')}<div></div>${tKey('Left','LEFT')}${tKey('Down','DOWN')}${tKey('Right','RIGHT')}</div>
    </div>
    <div class="kcol">
      <div class="ksec">TRIGGERS &amp; BUMPERS</div>
      ${row('L2','LT / L2','#8b94a7')}${row('L1','LB / L1','#8b94a7')}${row('R1','RB / R1','#8b94a7')}${row('R2','RT / R2','#8b94a7')}
      <div class="ksec">SYSTEM</div>
      ${row('TouchPad','View / TouchPad','#8b94a7')}${row('Options','Menu / Options','#8b94a7')}
    </div>
    <div class="kcol">
      <div class="ksec">FACE BUTTONS</div>
      ${row('Cross','A / Cross','#4cd964')}${row('Circle','B / Circle','#f05454')}${row('Square','X / Square','#3b9eff')}${row('Triangle','Y / Triangle','#eab81c')}
      <div class="ksec">RIGHT STICK (HEAD / GRAPPLE)</div>
      <div class="tcluster"><div></div>${tKey('RightStickUp','UP')}<div></div>${tKey('RightStickLeft','LEFT')}${tKey('RightStickDown','DOWN')}${tKey('RightStickRight','RIGHT')}</div>
      ${row('R3','R3 Click','#8b94a7')}
    </div>`;
}

async function pickGame(id) { render(await api().select_game(id)); setStatus(`Loaded ${id} bindings.`); }
async function browse() { render(await api().browse_folder()); }
async function setPreset(s, k, v) { render(await api().set_preset(s, k, v)); }
async function resetKeys() { capturing = null; render(await api().reset_keys()); setStatus("Reset keyboard bindings to defaults."); }
function startCap(ctrl) { capturing = ctrl; renderKeymap(); setStatus(`Press any key to bind ${ctrl} (Escape cancels)...`); }
function fitWindow() {
  requestAnimationFrame(() => {
    const h = document.querySelector(".app").offsetHeight + 24;
    api().resize_height(h);
  });
}
function toggleDrawer() {
  drawerOpen = !drawerOpen;
  document.getElementById("drawer").classList.toggle("open", drawerOpen);
  document.getElementById("drawer-btn").firstElementChild.innerHTML = drawerOpen ? "▾ &nbsp;Hide Keyboard Mapping" : "▸ &nbsp;Customize Keyboard Mapping (Optional)";
  fitWindow();
}
async function doInstall(style) {
  const all = document.getElementById("apply-all").checked;
  setStatus(`Applying ${style.toUpperCase()}...`);
  const r = await api().install(style, all);
  if (!r.ok) setStatus(r.message);
}
window.onLog = (m) => setStatus(m);
window.onInstallDone = (ok, msg, st) => { render(st); setStatus(ok ? msg.split('\n')[0] : `ERROR: ${msg}`); alert((ok ? "Done:\n\n" : "Error:\n\n") + msg); };
function setStatus(m) { document.getElementById("status").textContent = m; }

document.addEventListener("keydown", async (e) => {
  if (e.key === "Escape") {
    if (capturing) { capturing = null; renderKeymap(); setStatus("Remap cancelled."); return; }
    closeModal();
    return;
  }
  if (!capturing) return;
  e.preventDefault();
  const ctrl = capturing; capturing = null;
  render(await api().set_key(ctrl, e.code, e.key));
  setStatus(`Mapped ${ctrl} -> ${S.controls[ctrl]}`);
});

let modalExpanded = false;
function showModal(title, html, expandable = false) {
  modalExpanded = false;
  document.getElementById("modal-bg").classList.remove("expanded");
  document.getElementById("modal-box").classList.remove("expanded");
  const eb = document.getElementById("modal-expand-btn");
  eb.style.display = expandable ? "" : "none";
  eb.textContent = "⤢ Expand";
  document.getElementById("modal-title").textContent = title;
  document.getElementById("modal-body").innerHTML = html;
  document.getElementById("modal-bg").classList.add("open");
}
async function toggleModalExpand() {
  modalExpanded = !modalExpanded;
  document.getElementById("modal-bg").classList.toggle("expanded", modalExpanded);
  document.getElementById("modal-box").classList.toggle("expanded", modalExpanded);
  document.getElementById("modal-expand-btn").textContent = modalExpanded ? "⤡ Restore" : "⤢ Expand";
  await api().set_modal_expanded(modalExpanded);
}
async function closeModal() {
  document.getElementById("modal-bg").classList.remove("open", "expanded");
  document.getElementById("modal-box").classList.remove("expanded");
  if (modalExpanded) {
    modalExpanded = false;
    await api().set_modal_expanded(false);
    fitWindow();
  }
}

async function openIcons() {
  showModal("All Available Button Icons", "<div class='sub'>Rendering icon sets...</div>", true);
  const secs = await api().get_all_icons();
  document.getElementById("modal-body").innerHTML = secs.map(s =>
    `<div class="msec"><h3>${s.title}</h3>${s.rows.map(([l,u]) =>
      `<div class="irow"><span>${l}</span>${u ? `<img src="${u}"/>` : ''}</div>`).join("")}</div>`
  ).join("");
}
function openHelp() {
  showModal("Help & Tips", [
    ["1. Quick Start", "Pick UFC 2, UFC 3, UFC 4, UFC 5, or UFC 6 at the top (or click Browse Folder...). Choose your MENUS and MOVES presets on any card, preview them live, and click Install. Enable 'Apply to all detected UFC games' to patch all detected games in one click."],
    ["2. MENUS vs MOVES", "MENUS controls bottom-bar footer prompts, tab switches, and menu buttons. MOVES controls the controls screen, move list, in-fight hints, and tutorials."],
    ["3. Icon Pack Presets", "• Xbox: KLPS authentic EA Xbox One icons (White / Outline / Color menus × Ring / Disc / White moves) plus Kenney flat vector icons.\n• PlayStation: Stock restores 100% untouched original game files. PS4 brings classic colored X/O/Square/Triangle icons to UFC 5 & UFC 6. Kenney applies Kenney PlayStation icons.\n• Switch (Kenney): Nintendo Switch physical layout (B/A/Y/X, L/R/ZL/ZR, +/-) in Solid or Outline.\n• Keyboard (Kenney): Crisp double-res Kenney keycaps matched to your live bindings."],
    ["4. Safety & Backups", "Always close the game before installing or restoring. Original game data is backed up automatically. To revert anytime, select PlayStation (Stock / Stock) and click Restore PlayStation."],
  ].map(([h,t]) => `<div class="msec"><h3>${h}</h3><p>${t}</p></div>`).join(""));
}
function openCredits() {
  showModal("Credits & Acknowledgments", [
    ["KLPS Xbox Icon Packs", "Authentic EA Sports UFC 2/3 and UFC 4 Xbox One GNF button icon packs."],
    ["Kenney — Input Prompts v1.5 (CC0 1.0)", "Keyboard & Mouse, Xbox Series, PlayStation Series, and Nintendo Switch double-resolution prompt icons by Kenney (kenney.nl)."],
    ["Typography", "Barlow Condensed Bold (SIL Open Font License)."],
    ["Community & Ecosystem", "Built for the Parsectagon / Portheon / SacredFire / Kyty UFC emulation community."],
  ].map(([h,t]) => `<div class="msec"><h3>${h}</h3><p>${t}</p></div>`).join(""));
}

window.onUpdateAvailable = (tag) => {
  const b = document.getElementById("upd-btn");
  b.textContent = `↑ Update ${tag}`;
  b.style.display = "";
};
async function doUpdate() {
  const b = document.getElementById("upd-btn");
  b.disabled = true;
  b.textContent = "Updating...";
  await api().apply_update();
}

window.addEventListener("pywebviewready", async () => {
  render(await api().get_state());
  fitWindow();
  setStatus("Ready.");
  api().check_update();
});
</script>
</body>
</html>
"""


def _apply_dark_titlebar_hwnd(title: str) -> None:
    if os.name != "nt":
        return
    try:
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if not hwnd:
            return
        dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
        val = ctypes.c_int(1)
        dwm(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
        cap = ctypes.c_int(0x0017110F)  # #0f1117
        dwm(hwnd, 35, ctypes.byref(cap), ctypes.sizeof(cap))
        bdr = ctypes.c_int(0x004639E6)  # #e63946 Parsectagon red border
        dwm(hwnd, 34, ctypes.byref(bdr), ctypes.sizeof(bdr))
        txt = ctypes.c_int(0x00F9F4F1)
        dwm(hwnd, 36, ctypes.byref(txt), ctypes.sizeof(txt))
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--game", default=None)
    parser.add_argument("--folder", default=None)
    args, _ = parser.parse_known_args()

    title = "Parsectagon — UFC Controller Icons Mod"
    api = BridgeAPI(initial_game=args.game, initial_folder=args.folder)
    win = webview.create_window(
        title,
        html=HTML,
        js_api=api,
        width=980,
        height=495,
        min_size=(920, 450),
        background_color="#0f1117",
    )
    api._window = win
    ico = next((p for p in (_MEIPASS / "overlay.ico" if _MEIPASS else None, _HERE / "assets" / "overlay.ico") if p and p.is_file()), None)

    def on_shown() -> None:
        _apply_dark_titlebar_hwnd(title)

    win.events.shown += on_shown
    webview.start(gui="edgechromium", icon=str(ico) if ico else None)


if __name__ == "__main__":
    main()
