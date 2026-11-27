"""Shared Kenney gamepad (Xbox / PlayStation / Switch) + EA PS4 icon helper."""
from __future__ import annotations

import io
from pathlib import Path
import sys
import zipfile

_ZIP_CACHE: dict[str, bytes] | None = None


def _load_zip() -> dict[str, bytes]:
    global _ZIP_CACHE
    if _ZIP_CACHE is not None:
        return _ZIP_CACHE
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "kenney_gamepad_prompts.zip")
    here = Path(__file__).resolve()
    for base in here.parents:
        candidates.append(base / "installer" / "kenney_gamepad_prompts.zip")
        candidates.append(base / "ufc4" / "src" / "kenney_gamepad_prompts.zip")
    for cand in candidates:
        if cand.is_file():
            with zipfile.ZipFile(cand) as zf:
                _ZIP_CACHE = {n: zf.read(n) for n in zf.namelist() if n.endswith(".png")}
                return _ZIP_CACHE
    _ZIP_CACHE = {}
    return _ZIP_CACHE


def _open_cropped(name: str):
    from PIL import Image
    data = _load_zip().get(name)
    if not data:
        return None
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    bb = im.getchannel("A").point(lambda v: 255 if v > 15 else 0).getbbox()
    return im.crop(bb) if bb else im


def _pair(left_name: str, right_name: str):
    from PIL import Image
    l_im = _open_cropped(left_name)
    r_im = _open_cropped(right_name)
    if not l_im or not r_im:
        return None
    gap = max(4, round(min(l_im.height, r_im.height) * 0.14))
    h = max(l_im.height, r_im.height)
    out = Image.new("RGBA", (l_im.width + gap + r_im.width, h), (0, 0, 0, 0))
    out.alpha_composite(l_im, (0, (h - l_im.height) // 2))
    out.alpha_composite(r_im, (l_im.width + gap, (h - r_im.height) // 2))
    return out


def gamepad_icon(family: str, stem: str, variant: str):
    """Return a cropped PIL RGBA icon for (family, stem, variant) or None."""
    stem = stem.removeprefix("ue_").replace("_hold_skip_widget", "").removesuffix("_hold")

    if family == "ps" and variant == "ps4_ea":
        # Authentic UFC 4 colored PS4 icons
        if stem in ("digital_one", "digital_two", "digital_three", "digital_four"):
            return _open_cropped(f"ps4_ea/{stem}.png")
        return None

    if family == "ps":
        color = variant == "kenney_color"
        outline = variant == "kenney_outline"
        suf = "_outline" if outline else ""
        if stem == "digital_one":
            return _open_cropped(f"playstation_button_{'color_' if color else ''}cross{suf}.png")
        if stem == "digital_two":
            return _open_cropped(f"playstation_button_{'color_' if color else ''}circle{suf}.png")
        if stem == "digital_three":
            return _open_cropped(f"playstation_button_{'color_' if color else ''}triangle{suf}.png")
        if stem == "digital_four":
            return _open_cropped(f"playstation_button_{'color_' if color else ''}square{suf}.png")
        if stem == "left_bumper":
            return _open_cropped(f"playstation_trigger_l1{suf}.png")
        if stem == "right_bumper":
            return _open_cropped(f"playstation_trigger_r1{suf}.png")
        if stem == "left_trigger":
            return _open_cropped(f"playstation_trigger_l2{suf}.png")
        if stem == "right_trigger":
            return _open_cropped(f"playstation_trigger_r2{suf}.png")
        if stem == "left_right_bumper":
            return _pair(f"playstation_trigger_l1{suf}.png", f"playstation_trigger_r1{suf}.png")
        if stem == "left_right_trigger":
            return _pair(f"playstation_trigger_l2{suf}.png", f"playstation_trigger_r2{suf}.png")
        if stem == "start":
            return _open_cropped(f"playstation4_button_options{suf}.png")
        if stem == "select":
            return _open_cropped(f"playstation4_touchpad{suf}.png")
        if stem == "las_c":
            return _open_cropped(f"playstation_button_l3{suf}.png")
        if stem == "ras_c":
            return _open_cropped(f"playstation_button_r3{suf}.png")
        return None

    if family == "xbox":
        color = variant in ("kenney_color", "kenney")
        outline = variant == "kenney_outline"
        suf = "_outline" if outline else ""
        if stem == "digital_one":
            return _open_cropped(f"xbox_button_{'color_' if color else ''}a{suf}.png")
        if stem == "digital_two":
            return _open_cropped(f"xbox_button_{'color_' if color else ''}b{suf}.png")
        if stem == "digital_three":
            return _open_cropped(f"xbox_button_{'color_' if color else ''}y{suf}.png")
        if stem == "digital_four":
            return _open_cropped(f"xbox_button_{'color_' if color else ''}x{suf}.png")
        if stem == "left_bumper":
            return _open_cropped(f"xbox_lb{suf}.png")
        if stem == "right_bumper":
            return _open_cropped(f"xbox_rb{suf}.png")
        if stem == "left_trigger":
            return _open_cropped(f"xbox_lt{suf}.png")
        if stem == "right_trigger":
            return _open_cropped(f"xbox_rt{suf}.png")
        if stem == "left_right_bumper":
            return _pair(f"xbox_lb{suf}.png", f"xbox_rb{suf}.png")
        if stem == "left_right_trigger":
            return _pair(f"xbox_lt{suf}.png", f"xbox_rt{suf}.png")
        if stem == "start":
            return _open_cropped(f"xbox_button_menu{suf}.png")
        if stem == "select":
            return _open_cropped(f"xbox_button_view{suf}.png")
        if stem == "guide":
            return _open_cropped(f"xbox_guide{suf}.png")
        if stem == "las_c":
            return _open_cropped(f"xbox_ls{suf}.png")
        if stem == "ras_c":
            return _open_cropped(f"xbox_rs{suf}.png")
        return None

    if family == "switch":
        suf = "_outline" if variant == "outline" else ""
        # Physical Switch layout: bottom=B, right=A, top=X, left=Y
        if stem == "digital_one":
            return _open_cropped(f"switch_button_b{suf}.png")
        if stem == "digital_two":
            return _open_cropped(f"switch_button_a{suf}.png")
        if stem == "digital_three":
            return _open_cropped(f"switch_button_x{suf}.png")
        if stem == "digital_four":
            return _open_cropped(f"switch_button_y{suf}.png")
        if stem == "left_bumper":
            return _open_cropped(f"switch_button_l{suf}.png")
        if stem == "right_bumper":
            return _open_cropped(f"switch_button_r{suf}.png")
        if stem == "left_trigger":
            return _open_cropped(f"switch_button_zl{suf}.png")
        if stem == "right_trigger":
            return _open_cropped(f"switch_button_zr{suf}.png")
        if stem == "left_right_bumper":
            return _pair(f"switch_button_l{suf}.png", f"switch_button_r{suf}.png")
        if stem == "left_right_trigger":
            return _pair(f"switch_button_zl{suf}.png", f"switch_button_zr{suf}.png")
        if stem == "start":
            return _open_cropped(f"switch_button_plus{suf}.png")
        if stem == "select":
            return _open_cropped(f"switch_button_minus{suf}.png")
        if stem == "guide":
            return _open_cropped(f"switch_button_home{suf}.png")
        if stem == "las_c":
            return _open_cropped("switch_stick_l_press.png")
        if stem == "ras_c":
            return _open_cropped("switch_stick_r_press.png")
        return None

    return None


def fit_rgba_image(im, width: int, height: int):
    """Aspect-fit a cropped PIL RGBA image centered inside (width, height)."""
    from PIL import Image
    pad = 2 if min(width, height) <= 32 else 0
    tw_max = max(1, width - pad)
    th_max = max(1, height - pad)
    sc = min(tw_max / im.width, th_max / im.height)
    tw, th = max(1, round(im.width * sc)), max(1, round(im.height * sc))
    fitted = im.resize((tw, th), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.alpha_composite(fitted, ((width - tw) // 2, (height - th) // 2))
    return canvas
