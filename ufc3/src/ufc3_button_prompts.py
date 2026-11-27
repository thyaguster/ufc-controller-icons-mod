"""Reversible PS / Xbox / Keyboard button-prompt patcher for UFC 3 v1.14 (CUSA06534)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile
import zlib

_REPO_UFC4_SRC = Path(__file__).resolve().parents[2] / "ufc4" / "src"
for _p in (str(_REPO_UFC4_SRC), str(_REPO_UFC4_SRC / "ufc4_keyboard")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from keyboard_art import FONT, descriptor, pillow, render as render_keycap  # noqa: E402
from keyboard_bindings import load_bbport  # noqa: E402
from keyboard_flash import records, skip_matrix, skip_rect  # noqa: E402
from patcher_core import swf_symbols, swf_tags  # noqa: E402
from ufc4_gnf_codec import dimensions, replace_image  # noqa: E402

SWF_PREFIX = "ufc3_buttonart_"
GNF_PREFIX = "ufc3_direct_icons_"
STYLES = ("ps", "xbox", "keyboard")

_NON_BUTTON_GNFS = frozenset({
    "black_large/blurred_strip.gnf",
    "box_art.gnf",
    "careehubmainicon.gnf",
    "controller.gnf",
    "controller_swatch.gnf",
    "controller_white.gnf",
})


def parse_eb03_toc(archive: Path) -> list[tuple[str, int, int]]:
    """Parse an EA EB\\x00\\x03 .big archive TOC into (full_path, offset, size)."""
    with archive.open("rb") as stream:
        hdr = stream.read(20)
        magic, count, _, name_off, dir_hint = struct.unpack(">4sIIII", hdr)
        if magic != b"EB\x00\x03":
            raise ValueError(f"Unsupported .big archive header in {archive.name}: {magic!r}")
        # Read enough of the header + TOC + string tables (capped at 4 MB).
        stream.seek(0)
        toc_bytes = stream.read(min(archive.stat().st_size, max(dir_hint + 0x40000, 0x200000)))

    entries = []
    for i in range(count):
        off16, _, size, _ = struct.unpack_from(">IIII", toc_bytes, 0x30 + i * 16)
        entries.append((off16 * 16, size))

    # Detect filename record stride (2-byte big-endian dir_idx + null-padded filename).
    stride = None
    for cand in range(48, 80):
        if name_off + 2 * cand >= len(toc_bytes):
            break
        ok = True
        for k in range(min(count, 8)):
            p = name_off + k * cand
            d = struct.unpack_from(">H", toc_bytes, p)[0]
            if d > 4096 or toc_bytes[p + 2] < 32:
                ok = False
                break
        if ok:
            stride = cand
            break
    if stride is None:
        raise ValueError(f"Could not detect filename stride in {archive.name}")

    dir_start = toc_bytes.find(b"samplegame/ui\x00", name_off)
    if dir_start < 0:
        pos = name_off + count * stride
        while pos < len(toc_bytes) and toc_bytes[pos] == 0:
            pos += 1
        dir_start = pos

    dirs: list[str] = []
    pos = dir_start
    while pos + 0x6C <= len(toc_bytes) and toc_bytes[pos] != 0:
        dirs.append(toc_bytes[pos:pos + 0x6C].split(b"\x00", 1)[0].decode("ascii", "replace"))
        pos += 0x6C

    result: list[tuple[str, int, int]] = []
    for i in range(count):
        p = name_off + i * stride
        d_idx = struct.unpack_from(">H", toc_bytes, p)[0]
        fname = toc_bytes[p + 2:p + stride].split(b"\x00", 1)[0].decode("ascii", "replace")
        dname = dirs[d_idx] if d_idx < len(dirs) else ""
        full = f"{dname}/{fname}" if dname else fname
        result.append((full, entries[i][0], entries[i][1]))
    return result


def _decompress_cws(raw: bytes) -> bytearray:
    if len(raw) < 8 or raw[:3] != b"CWS":
        raise ValueError("Expected compressed CWS SWF")
    return bytearray(b"FWS" + raw[3:8] + zlib.decompress(raw[8:]))


def _recompress_cws(plain: bytes, header8: bytes, target_size: int) -> bytes:
    compressed = b"CWS" + header8[3:8] + zlib.compress(plain[8:], 9)
    if len(compressed) > target_size:
        raise ValueError(f"Patched SWF ({len(compressed)}) exceeds allocation ({target_size})")
    return compressed + b"\x00" * (target_size - len(compressed))


def _swf_defs(plain: bytes) -> dict[int, tuple[int, int, int]]:
    return {
        struct.unpack_from("<H", plain, pos)[0]: (kind, pos, size)
        for kind, pos, size in swf_tags(plain)
        if kind in (2, 22, 32, 39, 20, 36)
    }


def _bitmap_for_sprite(plain: bytes, defs: dict[int, tuple[int, int, int]], cid: int) -> int:
    kind, pos, size = defs[cid]
    if kind != 39:
        raise ValueError(f"Expected sprite tag 39 for cid {cid}, got {kind}")
    chars = [
        struct.unpack_from("<H", plain, p + 3)[0]
        for tag, p, _, _ in records(plain, pos + 4, pos + size)
        if tag == 26
    ]
    if len(chars) != 1:
        raise ValueError(f"Unexpected sprite child count ({len(chars)}) for cid {cid}")
    skind, sp, _ = defs[chars[0]]
    if skind != 2:
        raise ValueError(f"Expected DefineShape tag 2 for cid {chars[0]}, got {skind}")
    p = skip_rect(plain, sp + 2)
    cnt = plain[p]
    p += 1
    if cnt == 255:
        cnt = struct.unpack_from("<H", plain, p)[0]
        p += 2
    bitmaps = []
    for _ in range(cnt):
        fk = plain[p]
        p += 1
        if fk not in (0x40, 0x41, 0x42, 0x43):
            raise ValueError(f"Unexpected shape fill kind {fk:#x}")
        bmp = struct.unpack_from("<H", plain, p)[0]
        p = skip_matrix(plain, p + 2)
        # UFC 3 shapes include a dummy fill (cid 3) before the real DefineBitsLossless2 tag.
        if bmp != 65535 and bmp in defs and defs[bmp][0] in (20, 36):
            bitmaps.append(bmp)
    if len(set(bitmaps)) != 1:
        raise ValueError(f"Unexpected bitmap count {bitmaps} in shape {chars[0]}")
    return bitmaps[0]


def _bitmap_rgba(plain: bytes, pos: int, size: int):
    Image, _, _ = pillow()
    if plain[pos + 2] != 5:
        raise ValueError("Expected format-5 ARGB Flash bitmap")
    w, h = struct.unpack_from("<HH", plain, pos + 3)
    argb = zlib.decompress(plain[pos + 7:pos + size])
    if len(argb) != w * h * 4:
        raise ValueError("Unexpected Flash bitmap decompressed size")
    rgba = bytearray(len(argb))
    for i in range(0, len(argb), 4):
        a, r, g, b = argb[i:i + 4]
        rgba[i:i + 4] = (
            min(255, round(r * 255 / a)) if a else 0,
            min(255, round(g * 255 / a)) if a else 0,
            min(255, round(b * 255 / a)) if a else 0,
            a,
        )
    return Image.frombytes("RGBA", (w, h), bytes(rgba))


def _write_bitmap(plain: bytearray, pos: int, size: int, image) -> None:
    w, h = struct.unpack_from("<HH", plain, pos + 3)
    if image.size != (w, h):
        raise ValueError("Flash bitmap dimensions changed")
    rgba = image.tobytes()
    argb = bytearray(len(rgba))
    for i in range(0, len(rgba), 4):
        r, g, b, a = rgba[i:i + 4]
        argb[i:i + 4] = (a, (r * a + 127) // 255, (g * a + 127) // 255, (b * a + 127) // 255)
    comp = zlib.compress(argb, 9)
    if len(comp) > size - 7:
        raise ValueError("Patched Flash bitmap exceeds existing tag allocation")
    plain[pos + 7:pos + size] = comp + b"\x00" * (size - 7 - len(comp))


def build_swf_xbox(original: bytes) -> bytes:
    """Swap PS/Xbox button symbols and fit Menu/View glyphs into Start/Select slots."""
    plain = _decompress_cws(original)
    sym_tags = [(pos, size) for kind, pos, size in swf_tags(plain) if kind == 76]
    if len(sym_tags) != 1:
        raise ValueError(f"Expected 1 SymbolClass tag in tin.swf, found {len(sym_tags)}")
    sym_pos, sym_size = sym_tags[0]
    count = struct.unpack_from("<H", plain, sym_pos)[0]
    cursor = sym_pos + 2
    names: dict[str, tuple[int, int]] = {}
    for _ in range(count):
        cid = struct.unpack_from("<H", plain, cursor)[0]
        cid_off = cursor
        cursor += 2
        end = plain.index(0, cursor, sym_pos + sym_size)
        name = plain[cursor:end].decode("latin1")
        cursor = end + 1
        names[name] = (cid_off, cid)

    swaps = 0
    for name, (ps_off, ps_cid) in names.items():
        if "_ps_" not in name or "Btn_start_ps_" in name or "Btn_select_ps_" in name:
            continue
        other = names.get(name.replace("_ps_", "_xb_"))
        if other is None:
            continue
        xb_off, xb_cid = other
        struct.pack_into("<H", plain, ps_off, xb_cid)
        struct.pack_into("<H", plain, xb_off, ps_cid)
        swaps += 1
    if swaps < 4:
        raise ValueError(f"Too few PS<->Xbox symbol pairs in tin.swf ({swaps})")

    defs = _swf_defs(plain)
    Image, _, _ = pillow()
    footer_pairs = (
        ("parts.buttons.Btn_start_xb_mc", "parts.buttons.Btn_start_ps_mc"),
        ("parts.buttons.Btn_start_xb_highLight_mc", "parts.buttons.Btn_start_ps_highLight_mc"),
        ("parts.buttons.Btn_select_xb_mc", "parts.buttons.Btn_select_ps_mc"),
        ("parts.buttons.Btn_select_xb_highLight_mc", "parts.buttons.Btn_select_ps_highLight_mc"),
    )
    for src_name, dst_name in footer_pairs:
        if src_name not in names or dst_name not in names:
            continue
        _, src_pos, src_sz = defs[_bitmap_for_sprite(plain, defs, names[src_name][1])]
        _, dst_pos, dst_sz = defs[_bitmap_for_sprite(plain, defs, names[dst_name][1])]
        src_img = _bitmap_rgba(plain, src_pos, src_sz)
        w, h = struct.unpack_from("<HH", plain, dst_pos + 3)
        glyph_sz = min(20 if "Btn_select_" in dst_name else h - 2, h - 2, src_img.width, src_img.height)
        glyph = src_img.resize((glyph_sz, glyph_sz), Image.Resampling.LANCZOS)
        if "Btn_select_" in dst_name:
            levels_c, levels_a = (8, 8) if "highLight" in dst_name else (16, 16)
            q = lambda ch, n: ch.point(lambda v: round(v * (n - 1) / 255) * 255 // (n - 1))
            r, g, b, a = glyph.split()
            glyph = Image.merge("RGBA", (q(r, levels_c), q(g, levels_c), q(b, levels_c), q(a, levels_a)))
        canvas = Image.new("RGBA", (w, h))
        canvas.alpha_composite(glyph, (w - glyph_sz, (h - glyph_sz) // 2))
        _write_bitmap(plain, dst_pos, dst_sz, canvas)

    return _recompress_cws(plain, original[:8], len(original))


def build_swf_gamepad(original: bytes, family: str = "xbox", menus_preset: str = "white") -> bytes:
    """Build tin.swf / samplefedata.swf for Xbox (KLPS/Kenney), PS (Stock/PS4/Kenney), or Switch."""
    if family == "xbox" and menus_preset == "white":
        return build_swf_xbox(original)
    if family == "ps" and menus_preset == "stock":
        return original
    from gamepad_presets import gamepad_icon, fit_rgba_image
    Image, _, _ = pillow()

    def write_bmp(plain_b: bytearray, pos: int, size: int, fitted) -> None:
        for levels in (None, 32, 16, 8, 4):
            cand_im = fitted
            if levels is not None:
                q = lambda ch: ch.point(lambda v: round(v * (levels - 1) / 255) * 255 // (levels - 1))
                r, g, b, a = cand_im.split()
                cand_im = Image.merge("RGBA", (q(r), q(g), q(b), q(a)))
            rgba = cand_im.tobytes()
            argb = bytearray(len(rgba))
            for i in range(0, len(rgba), 4):
                r, g, b, a = rgba[i:i + 4]
                argb[i:i + 4] = (a, (r * a + 127) // 255, (g * a + 127) // 255, (b * a + 127) // 255)
            comp = zlib.compress(argb, 9)
            if len(comp) <= size - 7:
                plain_b[pos + 7:pos + size] = comp + b"\x00" * (size - 7 - len(comp))
                return

    if family == "xbox" and menus_preset in ("colored", "outline"):
        base_swf = build_swf_xbox(original)
        plain = _decompress_cws(base_swf)
        defs = _swf_defs(plain)
        from ufc4_direct_icons import _decode_bc7_gnf_rgba
        klps = _load_klps_xbox_gnfs()
        done_bmp = set()
        for name, cid, _ in swf_symbols(plain):
            if not name.startswith("parts.buttons.Btn_ue_digital_") or "_ps_" not in name:
                continue
            stem = name.removeprefix("parts.buttons.Btn_").split("_ps_", 1)[0]
            base = stem.removeprefix("ue_")
            gnf_k = f"{base}.gnf" if menus_preset == "colored" else f"{stem}.gnf"
            if gnf_k not in klps:
                continue
            im = _decode_bc7_gnf_rgba(klps[gnf_k])
            bb = im.getchannel("A").point(lambda v: 255 if v > 15 else 0).getbbox()
            if bb:
                im = im.crop(bb)
            try:
                bmp = _bitmap_for_sprite(plain, defs, cid)
                if bmp in done_bmp:
                    continue
                done_bmp.add(bmp)
                _, pos, size = defs[bmp]
                if plain[pos + 2] != 5:
                    continue
                w, h = struct.unpack_from("<HH", plain, pos + 3)
                write_bmp(plain, pos, size, fit_rgba_image(im, w, h))
            except Exception:
                continue
    else:
        plain = _decompress_cws(original)
        defs = _swf_defs(plain)
        done_bmp = set()
        for name, cid, _ in swf_symbols(plain):
            if not name.startswith("parts.buttons.Btn_") or "_ps_" not in name:
                continue
            stem = name.removeprefix("parts.buttons.Btn_").split("_ps_", 1)[0]
            is_face = stem.removeprefix("ue_") in ("digital_one", "digital_two", "digital_three", "digital_four")
            if family == "switch":
                variant = "outline" if menus_preset == "outline" else "solid"
            elif family == "ps" and menus_preset == "ps4_color":
                if not is_face:
                    continue
                variant = "ps4_ea"
            elif family == "ps" and menus_preset == "kenney_color":
                variant = "kenney_color" if is_face else "kenney_white"
            else:
                variant = "kenney_white"
            im = gamepad_icon(family, stem, variant)
            if im is None:
                continue
            try:
                bmp = _bitmap_for_sprite(plain, defs, cid)
                if bmp in done_bmp:
                    continue
                done_bmp.add(bmp)
                _, pos, size = defs[bmp]
                if plain[pos + 2] != 5:
                    continue
                w, h = struct.unpack_from("<HH", plain, pos + 3)
                write_bmp(plain, pos, size, fit_rgba_image(im, w, h))
            except Exception:
                continue
    try:
        return _recompress_cws(plain, original[:8], len(original))
    except ValueError:
        return build_swf_xbox(original) if family == "xbox" else original


def build_swf_keyboard(original: bytes, bindings_path: Path | None) -> bytes:
    """Render monochrome keyboard keycaps into UFC 3's tin.swf button bitmaps."""
    plain = _decompress_cws(original)
    defs = _swf_defs(plain)
    mapping: dict[int, tuple[dict, str]] = {}
    for name, cid, _ in swf_symbols(plain):
        if not name.startswith("parts.buttons."):
            continue
        desc = descriptor(name.removeprefix("parts."))
        if not desc:
            continue
        bmp = _bitmap_for_sprite(plain, defs, cid)
        state = "pressed" if "highlight" in name.lower() else "normal"
        if bmp in mapping:
            prev_desc, prev_state = mapping[bmp]
            if prev_desc != desc:
                raise ValueError(f"Shared bitmap {bmp} has conflicting button meanings")
            if prev_state != state:
                state = "normal"
        mapping[bmp] = (desc, state)
    if not mapping:
        raise ValueError("No button bitmaps found in UFC 3 tin.swf")

    bindings = load_bbport(bindings_path)
    for kind, pos, size in swf_tags(plain):
        if kind != 36 or size < 7:
            continue
        cid = struct.unpack_from("<H", plain, pos)[0]
        if cid not in mapping:
            continue
        desc, state = mapping[cid]
        w, h = struct.unpack_from("<HH", plain, pos + 3)
        rgba = render_keycap(w, h, desc, bindings, state)
        comp = None
        for alpha_levels, shades in (
            (8, (36, 107, 179, 250)),
            (4, (36, 107, 179, 250)),
            (2, (36, 107, 179, 250)),
            (2, (36, 250)),
        ):
            px = bytearray(len(rgba))
            for i in range(0, len(rgba), 4):
                gray = min(shades, key=lambda c: abs(c - rgba[i]))
                alpha = round(round(rgba[i + 3] * (alpha_levels - 1) / 255) * 255 / (alpha_levels - 1))
                val = (gray * alpha + 127) // 255
                px[i:i + 4] = bytes((alpha, val, val, val))
            cand = zlib.compress(px, 9)
            if len(cand) <= size - 7:
                comp = cand
                break
        if comp is None:
            raise ValueError(f"Keycap bitmap {cid} ({w}x{h}) exceeded Flash allocation ({size - 7})")
        plain[pos + 7:pos + size] = comp + b"\x00" * (size - 7 - len(comp))

    return _recompress_cws(plain, original[:8], len(original))


def _extract_xbox_glyphs(ps_swf: bytes) -> dict[str, object]:
    plain = _decompress_cws(ps_swf)
    defs = _swf_defs(plain)
    out = {}
    stems = {
        "digital_one", "digital_two", "digital_three", "digital_four",
        "left_bumper", "right_bumper", "left_trigger", "right_trigger",
        "left_right_bumper", "left_right_trigger", "start", "select", "guide",
        "las_c", "ras_c",
    }
    for name, cid, _ in swf_symbols(plain):
        if not name.startswith("parts.buttons.Btn_") or "_xb_" not in name:
            continue
        stem = name.removeprefix("parts.buttons.Btn_").split("_xb_", 1)[0].removeprefix("ue_")
        if stem not in stems:
            continue
        state = "hold" if "highLight" in name else "normal"
        _, bp, bs = defs[_bitmap_for_sprite(plain, defs, cid)]
        out[f"{stem}:{state}"] = _bitmap_rgba(plain, bp, bs)
    return out


def _render_clean_inline_tb(width: int, height: int, stem: str) -> bytes:
    """Render crisp, artifact-free inline Xbox LT/RT/LB/RB glyphs."""
    Image, ImageDraw, ImageFont = pillow()
    scale = 4
    im = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    is_trig = stem.endswith("trigger")
    is_right = stem.startswith("right_")
    if is_trig:
        pts = [(0.16, 0.16), (0.76, 0.16), (0.84, 0.24), (0.84, 0.72), (0.70, 0.86), (0.16, 0.86)]
        lbl = "RT" if is_right else "LT"
    else:
        pts = [(0.10, 0.42), (0.24, 0.20), (0.82, 0.20), (0.90, 0.30), (0.90, 0.80), (0.10, 0.80)]
        lbl = "RB" if is_right else "LB"
    if is_right:
        pts = [(1.0 - x, y) for x, y in pts]
    draw.polygon([(x * width * scale, y * height * scale) for x, y in pts], fill=(246, 246, 246, 255))
    font = ImageFont.truetype(str(FONT), round(height * 0.44 * scale))
    cy = 0.50 if is_trig else 0.52
    draw.text((width * 0.50 * scale, height * cy * scale), lbl, fill=(32, 32, 32, 255), font=font, anchor="mm")
    return im.resize((width, height), Image.Resampling.LANCZOS).tobytes()


def _render_clean_inline_abxy(width: int, height: int, stem: str) -> bytes:
    """Render crisp, artifact-free inline Xbox A/B/X/Y circular glyphs."""
    Image, ImageDraw, ImageFont = pillow()
    scale = 4
    im = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    lbl = {"digital_one": "A", "digital_two": "B", "digital_three": "Y", "digital_four": "X"}[stem]
    d = min(width, height) * 0.76 * scale
    cx, cy = width * 0.5 * scale, height * 0.5 * scale
    draw.ellipse((cx - d / 2, cy - d / 2, cx + d / 2, cy + d / 2), fill=(246, 246, 246, 255))
    font = ImageFont.truetype(str(FONT), round(d * 0.62))
    draw.text((cx, cy), lbl, fill=(32, 32, 32, 255), font=font, anchor="mm")
    return im.resize((width, height), Image.Resampling.LANCZOS).tobytes()


def _render_xbox_gnf(glyphs: dict[str, object], width: int, height: int, rel: str) -> bytes | None:
    stem = rel.rsplit("/", 1)[-1].removesuffix(".gnf").removeprefix("ue_")
    state = "hold" if stem.endswith("_hold") else "normal"
    stem = stem.removesuffix("_hold")
    if not rel.startswith(("ground_game_hud/", "text_ground_game_hud/", "ue_")):
        if stem in {"left_trigger", "right_trigger", "left_bumper", "right_bumper"}:
            return _render_clean_inline_tb(width, height, stem)
        if stem in {"digital_one", "digital_two", "digital_three", "digital_four"}:
            return _render_clean_inline_abxy(width, height, stem)
    stock = glyphs.get(f"{stem}:{state}") or glyphs.get(f"{stem}:normal")
    if stock is None:
        return None
    Image, ImageDraw, _ = pillow()
    scale = 0.72 * min(width / stock.width, height / stock.height)
    sz = (max(1, round(stock.width * scale)), max(1, round(stock.height * scale)))
    fitted = stock.resize(sz, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (width, height))
    canvas.alpha_composite(fitted, ((width - sz[0]) // 2, (height - sz[1]) // 2))
    result = bytearray(canvas.tobytes())
    return bytes(result)


def _load_klps_xbox_gnfs() -> dict[str, bytes]:
    """Load authentic Xbox One GNF textures from ufc23_xbox_gnf.zip if available."""
    candidates = [Path(__file__).with_name("ufc23_xbox_gnf.zip")]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.insert(0, Path(meipass) / "ufc23_xbox_gnf.zip")
    for base in Path(__file__).resolve().parents:
        candidates.append(base / "KLPS_UFC2-3-4_Xbox_Icons_Pack" / "src" / "ufc23_xbox_gnf.zip")
        candidates.append(base / "KLPS_UFC2-3_Xbox_Icons_Pack" / "KLPS_UFC2-3_Xbox_Icons_Pack" / "src" / "ufc23_xbox_gnf.zip")
    for zp in candidates:
        if zp.is_file():
            with zipfile.ZipFile(zp) as z:
                return {
                    n.split("skins/buttons/ps3/", 1)[1]: z.read(n)
                    for n in z.namelist()
                    if "skins/buttons/ps3/" in n and n.endswith(".gnf")
                }
    return {}


def prepare(databigs_dir: Path, output: Path, bindings_path: Path | None = None,
            xbox_menus: str = "white", xbox_moves: str = "ring", gamepad_family: str = "xbox") -> dict[str, int]:
    """Prepare PS, Xbox, and Keyboard button assets for UFC 3 without altering unknown data."""
    patch_big = databigs_dir / "patch_inxp900.big"
    ui_big = databigs_dir / "inxp_ui_40.big"
    if not patch_big.is_file() or not ui_big.is_file():
        raise FileNotFoundError(f"Expected patch_inxp900.big and inxp_ui_40.big in {databigs_dir}")

    output.mkdir(parents=True, exist_ok=True)

    # 1. Flash tin.swf & samplefedata.swf in patch_inxp900.big and inxp_ui_40.big
    swf_meta_list = []
    primary_ps_swf = None
    for big_path in (patch_big, ui_big):
        swf_entries = [
            (n, off, sz) for n, off, sz in parse_eb03_toc(big_path)
            if (n.rsplit("/", 1)[-1] in ("tin.swf", "samplefedata.swf")) and sz > 1024 * 1024
        ]
        for swf_name, tin_off, tin_sz in swf_entries:
            with big_path.open("rb") as f:
                f.seek(tin_off)
                current_swf = f.read(tin_sz)

            swf_stem = swf_name.rsplit("/", 1)[-1].removesuffix(".swf")
            tag = f"{big_path.stem}_{swf_stem}"
            ps_swf_file = output / f"{SWF_PREFIX}{tag}_ps.bin"
            if ps_swf_file.exists():
                ps_swf = ps_swf_file.read_bytes()
                old_variants = {
                    (output / f"{SWF_PREFIX}{tag}_{s}.bin").read_bytes()
                    for s in STYLES
                    if (output / f"{SWF_PREFIX}{tag}_{s}.bin").exists()
                }
                if current_swf not in old_variants:
                    raise ValueError(f"{big_path.name} {swf_stem}.swf changed externally; refusing to overwrite")
            else:
                ps_swf = current_swf

            xbox_swf = build_swf_gamepad(ps_swf, gamepad_family, xbox_menus)
            kb_swf = build_swf_keyboard(ps_swf, bindings_path)
            if ps_swf_file.exists() and current_swf != ps_swf:
                for s_name, blob in (("xbox", xbox_swf), ("keyboard", kb_swf)):
                    old_p = output / f"{SWF_PREFIX}{tag}_{s_name}.bin"
                    if old_p.exists() and current_swf == old_p.read_bytes():
                        with big_path.open("r+b") as f:
                            f.seek(tin_off)
                            f.write(blob)
                        break

            for s_name, blob in (("ps", ps_swf), ("xbox", xbox_swf), ("keyboard", kb_swf)):
                (output / f"{SWF_PREFIX}{tag}_{s_name}.bin").write_bytes(blob)
            swf_meta_list.append({
                "archive": big_path.name,
                "tag": tag,
                "offset": tin_off,
                "size": tin_sz,
                "ps_sha256": hashlib.sha256(ps_swf).hexdigest(),
            })
            if primary_ps_swf is None:
                primary_ps_swf = ps_swf

    if not swf_meta_list or primary_ps_swf is None:
        raise ValueError("No main tin.swf found in UFC 3 databigs")
    (output / f"{SWF_PREFIX}meta.json").write_text(
        json.dumps({"swfs": swf_meta_list}, indent=2), encoding="utf-8"
    )

    # 2. Direct BC7 GNF textures in inxp_ui_40.big
    map_file = output / f"{GNF_PREFIX}map.json"
    ps_gnf_file = output / f"{GNF_PREFIX}ps.bin"
    if map_file.exists() and ps_gnf_file.exists():
        metadata = json.loads(map_file.read_text(encoding="utf-8"))
        prior_blobs = {
            s: (output / f"{GNF_PREFIX}{s}.bin").read_bytes()
            for s in STYLES
            if (output / f"{GNF_PREFIX}{s}.bin").exists()
        }
        ps_gnf_blob = prior_blobs["ps"]
    else:
        unique: dict[tuple[int, int], str] = {}
        for full, off, sz in parse_eb03_toc(ui_big):
            if "skins/buttons/ps3/" not in full or not full.endswith(".gnf"):
                continue
            rel = full.split("skins/buttons/ps3/", 1)[1]
            if rel in _NON_BUTTON_GNFS or not descriptor(rel.removesuffix(".gnf")):
                continue
            unique.setdefault((off, sz), rel)
        metadata = []
        ps_buf = bytearray()
        with ui_big.open("rb") as f:
            for (off, sz), rel in sorted(unique.items()):
                f.seek(off)
                raw = f.read(sz)
                if raw[:4] != b"GNF ":
                    continue  # Skip chunkzip-compressed large digits
                dimensions(raw)  # Validate BC7 fmt=41
                metadata.append({"name": rel, "offset": off, "size": sz})
                ps_buf += raw
        ps_gnf_blob = bytes(ps_buf)
        prior_blobs = None

    bindings = load_bbport(bindings_path)
    glyphs = _extract_xbox_glyphs(primary_ps_swf)
    klps_gnfs = _load_klps_xbox_gnfs()
    gnf_blobs = {s: bytearray() for s in STYLES}
    cursor = 0
    for row in metadata:
        rel, sz = row["name"], row["size"]
        orig = ps_gnf_blob[cursor:cursor + sz]
        w, h = dimensions(orig)
        desc = descriptor(rel.removesuffix(".gnf"))
        kb_gnf = replace_image(orig, render_keycap(w, h, desc, bindings), separate_alpha=True)
        ground_stick = rel in ("text_ground_game_hud/las.gnf", "text_ground_game_hud/ras.gnf")
        stem = rel.rsplit("/", 1)[-1].removesuffix(".gnf").removesuffix("_hold").removeprefix("ue_")
        is_face = stem in ("digital_one", "digital_two", "digital_three", "digital_four")
        is_menu = rel.startswith(("white/", "ue_"))
        from gamepad_presets import gamepad_icon, fit_rgba_image
        kenney_im = None
        custom_tex = None
        if gamepad_family == "switch":
            var = "outline" if (xbox_menus if is_menu else xbox_moves) == "outline" else "solid"
            kenney_im = None if ground_stick else gamepad_icon("switch", stem, var)
        elif gamepad_family == "ps":
            if not ground_stick:
                if is_face and not is_menu and xbox_moves == "kenney":
                    kenney_im = gamepad_icon("ps", stem, "kenney_color")
                elif is_face and is_menu and xbox_menus == "ps4_color":
                    kenney_im = gamepad_icon("ps", stem, "ps4_ea")
                elif is_face and is_menu and xbox_menus == "kenney_color":
                    kenney_im = gamepad_icon("ps", stem, "kenney_color")
                elif is_menu and xbox_menus in ("kenney", "kenney_color"):
                    kenney_im = gamepad_icon("ps", stem, "kenney_white")
                elif not is_face and (xbox_menus in ("kenney", "kenney_color") or xbox_moves == "kenney"):
                    kenney_im = gamepad_icon("ps", stem, "kenney_white")
        elif not ground_stick and klps_gnfs:
            if is_face and is_menu and xbox_menus == "kenney":
                kenney_im = gamepad_icon("xbox", stem, "kenney_white")
            elif is_face and not is_menu and xbox_moves == "kenney":
                kenney_im = gamepad_icon("xbox", stem, "kenney_color")
            elif not is_face and xbox_menus == "kenney":
                kenney_im = gamepad_icon("xbox", stem, "kenney_white")
            elif is_face and is_menu and xbox_menus != "white":
                custom_tex = klps_gnfs.get(f"ue_{stem}.gnf") if xbox_menus == "outline" else klps_gnfs.get(f"{stem}.gnf")
            elif is_face and not is_menu and xbox_moves != "ring":
                if xbox_moves == "disc":
                    custom_tex = klps_gnfs.get(f"black_large/{stem}.gnf")
                elif xbox_moves == "white":
                    custom_tex = klps_gnfs.get(f"white/{stem}.gnf")
        klps_match = (
            klps_gnfs.get(rel)
            or klps_gnfs.get(f"white/{rel}")
            or klps_gnfs.get(rel.removeprefix("white/"))
        )
        if gamepad_family in ("switch", "ps"):
            xb_gnf = replace_image(orig, fit_rgba_image(kenney_im, w, h).tobytes(), separate_alpha=True) if kenney_im else orig
        elif kenney_im is not None:
            xb_gnf = replace_image(orig, fit_rgba_image(kenney_im, w, h).tobytes(), separate_alpha=True)
        elif custom_tex is not None:
            from ufc4_direct_icons import _fit_gnf_rgba
            xb_gnf = replace_image(orig, _fit_gnf_rgba(custom_tex, w, h), separate_alpha=True)
        elif not ground_stick and klps_match and len(klps_match) == sz and dimensions(klps_match) == (w, h):
            xb_gnf = orig[:256] + klps_match[256:]
        else:
            xb_rgba = None if ground_stick else _render_xbox_gnf(glyphs, w, h, rel)
            sep_alpha = not rel.startswith(("ground_game_hud/", "text_ground_game_hud/", "ue_")) and rel.rsplit("/", 1)[-1] in {
                "left_trigger.gnf", "right_trigger.gnf", "left_bumper.gnf", "right_bumper.gnf",
                "digital_one.gnf", "digital_two.gnf", "digital_three.gnf", "digital_four.gnf",
                "las_c.gnf", "ras_c.gnf",
            }
            xb_gnf = replace_image(orig, xb_rgba, separate_alpha=sep_alpha) if xb_rgba else orig
        for s_name, var in (("ps", orig), ("xbox", xb_gnf), ("keyboard", kb_gnf)):
            if len(var) != sz:
                raise ValueError(f"GNF size mismatch for {rel}")
            gnf_blobs[s_name] += var
        cursor += sz

    if prior_blobs:
        cursor = 0
        with ui_big.open("r+b") as f:
            for row in metadata:
                sz = row["size"]
                f.seek(row["offset"])
                cur = f.read(sz)
                for s_name, prior_b in prior_blobs.items():
                    if cur == prior_b[cursor:cursor + sz]:
                        f.seek(row["offset"])
                        f.write(gnf_blobs[s_name][cursor:cursor + sz])
                        break
                cursor += sz

    for s_name, blob in gnf_blobs.items():
        (output / f"{GNF_PREFIX}{s_name}.bin").write_bytes(bytes(blob))
    map_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {"swf_bytes": sum(m["size"] for m in swf_meta_list), "gnf_count": len(metadata)}


def set_style(databigs_dir: Path, output: Path, style: str) -> None:
    """Apply 'ps', 'xbox', or 'keyboard' button prompts to UFC 3 databigs."""
    if style not in STYLES:
        raise ValueError(f"Style must be one of {STYLES}, got {style!r}")
    ui_big = databigs_dir / "inxp_ui_40.big"

    swf_meta = json.loads((output / f"{SWF_PREFIX}meta.json").read_text(encoding="utf-8"))
    for entry in swf_meta["swfs"]:
        swf_blob = (output / f"{SWF_PREFIX}{entry['tag']}_{style}.bin").read_bytes()
        if len(swf_blob) != entry["size"]:
            raise ValueError(f"Prepared SWF asset size mismatch for {entry['archive']}")
        with (databigs_dir / entry["archive"]).open("r+b") as f:
            f.seek(entry["offset"])
            f.write(swf_blob)

    gnf_meta = json.loads((output / f"{GNF_PREFIX}map.json").read_text(encoding="utf-8"))
    gnf_blob = (output / f"{GNF_PREFIX}{style}.bin").read_bytes()
    if len(gnf_blob) != sum(row["size"] for row in gnf_meta):
        raise ValueError("Prepared GNF asset size mismatch")
    cursor = 0
    with ui_big.open("r+b") as f:
        for row in gnf_meta:
            sz = row["size"]
            f.seek(row["offset"])
            f.write(gnf_blob[cursor:cursor + sz])
            cursor += sz


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="UFC 3 Xbox & Keyboard button-prompt patcher")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_prep = sub.add_parser("prepare")
    p_prep.add_argument("--databigs", type=Path, required=True)
    p_prep.add_argument("--output", type=Path, required=True)
    p_prep.add_argument("--bindings", type=Path, default=None)

    p_set = sub.add_parser("set")
    p_set.add_argument("--databigs", type=Path, required=True)
    p_set.add_argument("--output", type=Path, required=True)
    p_set.add_argument("--style", choices=STYLES, required=True)

    args = parser.parse_args(argv)
    if args.cmd == "prepare":
        info = prepare(args.databigs, args.output, args.bindings)
        print(f"Prepared UFC 3 button prompts: tin.swf={info['swf_bytes']} bytes, gnf={info['gnf_count']} textures")
    elif args.cmd == "set":
        set_style(args.databigs, args.output, args.style)
        print(f"Applied UFC 3 button prompt style: {args.style}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
