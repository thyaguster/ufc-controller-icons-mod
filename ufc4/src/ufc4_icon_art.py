"""Prepare reversible UFC 4 button art from the user's own game archive.

The game SWF contains PlayStation and Xbox artwork. Xbox mode switches symbol
IDs; keyboard mode replaces the existing bitmaps with rendered keycaps. Both
variants preserve the archive slot size.
"""

import argparse
import hashlib
import pathlib
import struct
import sys
import zlib

ART_OFFSET = 0xF66A200
ART_SIZE = 88036
TAIL_OFFSET = 84758
TAIL_END = 88034
SYMBOL_OFFSET = 154522
SYMBOL_SIZE = 3322
ORIGINAL_SHA256 = "f3d69e4ec09c88b869686724674096a0eae95af18104c67b21c52e0767cc4de3"


def _flash_helpers():
    keyboard = pathlib.Path(__file__).with_name("ufc4_keyboard")
    if str(keyboard) not in sys.path:
        sys.path.insert(0, str(keyboard))
    from keyboard_art import pillow
    from keyboard_flash import bitmap_for_shape, records
    from patcher_core import swf_symbols, swf_tags
    return pillow, bitmap_for_shape, records, swf_symbols, swf_tags


def _bitmap_for_symbol(plain: bytes, symbol_name: str) -> tuple[int, int]:
    _, bitmap_for_shape, records, swf_symbols, swf_tags = _flash_helpers()
    definitions = {struct.unpack_from("<H", plain, pos)[0]: (kind, pos, size)
                   for kind, pos, size in swf_tags(plain)
                   if kind in (2, 22, 32, 39, 20, 36)}
    symbols = {name: cid for name, cid, _ in swf_symbols(plain)}
    cid = symbols.get(symbol_name)
    if cid not in definitions:
        raise ValueError(f"UFC 4 footer symbol is missing: {symbol_name}")
    kind, pos, size = definitions[cid]
    if kind != 39:
        raise ValueError(f"Unexpected UFC 4 footer symbol: {symbol_name}")
    children = [struct.unpack_from("<H", plain, at + 3)[0]
                for tag, at, _, _ in records(plain, pos + 4, pos + size)
                if tag == 26]
    if len(children) != 1 or children[0] not in definitions:
        raise ValueError(f"Unexpected UFC 4 footer sprite: {symbol_name}")
    _, shape_pos, shape_size = definitions[children[0]]
    bitmap = bitmap_for_shape(plain, shape_pos, shape_size)
    if bitmap not in definitions or definitions[bitmap][0] != 36:
        raise ValueError(f"Unexpected UFC 4 footer bitmap: {symbol_name}")
    return definitions[bitmap][1:]


def _bitmap_rgba(plain: bytes, pos: int, size: int):
    pillow, _, _, _, _ = _flash_helpers()
    Image, _, _ = pillow()
    if plain[pos + 2] != 5:
        raise ValueError("Unexpected UFC 4 footer bitmap format")
    width, height = struct.unpack_from("<HH", plain, pos + 3)
    argb = zlib.decompress(plain[pos + 7:pos + size])
    if len(argb) != width * height * 4:
        raise ValueError("Unexpected UFC 4 footer bitmap size")
    rgba = bytearray(len(argb))
    for at in range(0, len(argb), 4):
        alpha, red, green, blue = argb[at:at + 4]
        rgba[at:at + 4] = (
            min(255, round(red * 255 / alpha)) if alpha else 0,
            min(255, round(green * 255 / alpha)) if alpha else 0,
            min(255, round(blue * 255 / alpha)) if alpha else 0,
            alpha,
        )
    return Image.frombytes("RGBA", (width, height), bytes(rgba))


def _write_bitmap(plain: bytearray, pos: int, size: int, image) -> None:
    width, height = struct.unpack_from("<HH", plain, pos + 3)
    if image.size != (width, height):
        raise ValueError("UFC 4 footer bitmap dimensions changed")
    rgba = image.tobytes()
    argb = bytearray(len(rgba))
    for at in range(0, len(rgba), 4):
        red, green, blue, alpha = rgba[at:at + 4]
        argb[at:at + 4] = (
            alpha,
            (red * alpha + 127) // 255,
            (green * alpha + 127) // 255,
            (blue * alpha + 127) // 255,
        )
    compressed = zlib.compress(argb, 9)
    if len(compressed) > size - 7:
        raise ValueError("Xbox footer Menu glyph exceeds its Flash allocation")
    plain[pos + 7:pos + size] = compressed + b"\0" * (size - 7 - len(compressed))


def _patch_footer_buttons(plain: bytearray, include_select: bool = True,
                          smooth_select: bool = True) -> None:
    pillow, _, _, _, _ = _flash_helpers()
    Image, _, _ = pillow()
    pairs = [
        ("buttons.Btn_start_xb_mc", "buttons.Btn_start_ps_mc"),
        ("buttons.Btn_start_xb_highLight_mc", "buttons.Btn_start_ps_highLight_mc"),
    ]
    if include_select:
        pairs.extend((
            ("buttons.Btn_select_xb_mc", "buttons.Btn_select_ps_mc"),
            ("buttons.Btn_select_xb_highLight_mc", "buttons.Btn_select_ps_highLight_mc"),
        ))
    for source_name, target_name in pairs:
        source_pos, source_size = _bitmap_for_symbol(plain, source_name)
        target_pos, target_size = _bitmap_for_symbol(plain, target_name)
        source = _bitmap_rgba(plain, source_pos, source_size)
        width, height = struct.unpack_from("<HH", plain, target_pos + 3)
        glyph_size = min(20, height - 2, source.width, source.height) if "Btn_select_" in target_name and smooth_select else min(height - 2, source.width, source.height)
        glyph = source.resize((glyph_size, glyph_size), Image.Resampling.LANCZOS)
        if "Btn_select_" in target_name:
            # The Select bitmap has a much smaller compressed Flash allocation.
            # Retain graded edges; the old binary mask looked visibly jagged.
            if smooth_select:
                color_levels, alpha_levels = (8, 8) if "highLight" in target_name else (16, 16)
                def levels(channel, count):
                    return channel.point(lambda value: round(value * (count - 1) / 255) * 255 // (count - 1))
                red, green, blue, alpha = glyph.split()
                glyph = Image.merge("RGBA", (levels(red, color_levels),
                                             levels(green, color_levels),
                                             levels(blue, color_levels),
                                             levels(alpha, alpha_levels)))
            else:
                alpha = glyph.getchannel("A").point(lambda value: 255 if value >= 96 else 0)
                light = glyph.getchannel("R").point(lambda value: 255 if value >= 128 else 0)
                glyph = Image.merge("RGBA", (light, light, light, alpha))
        canvas = Image.new("RGBA", (width, height))
        canvas.alpha_composite(glyph, (width - glyph_size, (height - glyph_size) // 2))
        _write_bitmap(plain, target_pos, target_size, canvas)


def keyboard_art(original: bytes, bindings_path: pathlib.Path | None = None) -> bytes:
    """Use the overlay's existing keycap renderer inside UFC 4's Flash bitmaps."""
    sys.path.insert(0, str(pathlib.Path(__file__).with_name("ufc4_keyboard")))
    from keyboard_bindings import load_bbport
    from keyboard_flash import decode_swf, library_map, patch

    if hashlib.sha256(original).hexdigest() != ORIGINAL_SHA256:
        raise ValueError("Keyboard artwork requires the supported original UFC 4 archive")
    size = len(original)
    frame = (size & 0xffffff).to_bytes(4, "big") + bytes((0, (size >> 16) & 15)) + (size & 0xffff).to_bytes(2, "big")
    mapped = library_map(decode_swf(original))
    if len(mapped) != 93:
        raise ValueError("UFC 4 keyboard bitmap inventory changed")
    result = patch(frame + original, load_bbport(bindings_path), len(mapped))[8:]
    if len(result) != ART_SIZE or result[:8] != original[:8]:
        raise ValueError("Keyboard button-art patch failed verification")
    return result


def legacy_xbox_art(original: bytes) -> bytes:
    """Return the earlier symbol-swap-only Xbox variant."""
    if len(original) != ART_SIZE or original[:3] != b"CWS":
        raise ValueError("UFC 4 button art does not match the supported version")
    data = bytearray(zlib.decompress(original[8:]))
    symbols = data[SYMBOL_OFFSET:SYMBOL_OFFSET + SYMBOL_SIZE]
    count = int.from_bytes(symbols[:2], "little")
    position = 2
    names = {}
    for _ in range(count):
        cid = int.from_bytes(symbols[position:position + 2], "little")
        cid_offset = SYMBOL_OFFSET + position
        position += 2
        end = symbols.index(0, position)
        name = symbols[position:end].decode("latin1")
        position = end + 1
        names[name] = (cid_offset, cid)
    swaps = 0
    for name, (ps_offset, ps_cid) in names.items():
        if "_ps_" not in name:
            continue
        other = names.get(name.replace("_ps_", "_xb_"))
        if other is None:
            continue
        xb_offset, xb_cid = other
        data[ps_offset:ps_offset + 2] = xb_cid.to_bytes(2, "little")
        data[xb_offset:xb_offset + 2] = ps_cid.to_bytes(2, "little")
        swaps += 1
    if swaps < 4:
        raise ValueError("Xbox artwork mappings were not found")
    tail = (pathlib.Path(__file__).with_name("ufc4_buttonart_xbox_tail.bin")).read_bytes()
    if len(tail) != TAIL_END - TAIL_OFFSET:
        raise ValueError("Xbox button-art patch is incomplete")
    result = original[:TAIL_OFFSET] + tail + original[TAIL_END:]
    if zlib.decompress(result[8:]) != data:
        raise ValueError("Xbox button-art patch failed verification")
    return result


def _write_bitmap_fit(plain: bytearray, pos: int, size: int, image) -> None:
    """Write an RGBA image into a Flash tag 36 slot, quantizing alpha/RGB only if needed to fit."""
    w, h = struct.unpack_from("<HH", plain, pos + 3)
    if image.size != (w, h):
        image = image.resize((w, h), _flash_helpers()[0]()[0].Resampling.LANCZOS)
    for levels in (None, 32, 16, 8, 4):
        im = image
        if levels is not None:
            q = lambda ch: ch.point(lambda v: round(v * (levels - 1) / 255) * 255 // (levels - 1))
            r, g, b, a = im.split()
            im = im.merge if False else type(im).merge if False else _flash_helpers()[0]()[0].merge("RGBA", (q(r), q(g), q(b), q(a)))
        rgba = im.tobytes()
        argb = bytearray(len(rgba))
        for at in range(0, len(rgba), 4):
            r, g, b, a = rgba[at:at + 4]
            argb[at:at + 4] = (a, (r * a + 127) // 255, (g * a + 127) // 255, (b * a + 127) // 255)
        comp = zlib.compress(argb, 9)
        if len(comp) <= size - 7:
            plain[pos + 7:pos + size] = comp + b"\0" * (size - 7 - len(comp))
            return
    raise ValueError(f"Bitmap ({w}x{h}) exceeds Flash allocation ({size - 7})")


def _render_colored_xbox_btn(width: int, height: int, stem: str):
    """Render a native 4x supersampled colored Xbox A/B/X/Y ring at exact slot size."""
    from ufc4_keyboard.keyboard_art import FONT, pillow
    Image, ImageDraw, ImageFont = pillow()
    colors = {
        "ue_digital_one":   ("A", (56, 184, 68, 255)),
        "ue_digital_two":   ("B", (216, 56, 56, 255)),
        "ue_digital_three": ("Y", (234, 184, 28, 255)),
        "ue_digital_four":  ("X", (46, 139, 230, 255)),
    }
    lbl, col = colors[stem]
    scale = 4
    im = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    d = (min(width, height) - 2) * scale
    cx, cy = width * 0.5 * scale, height * 0.5 * scale
    ring_w = max(2, round(min(width, height) * 0.095 * scale))
    draw.ellipse((cx - d / 2, cy - d / 2, cx + d / 2, cy + d / 2), fill=(18, 20, 24, 255), outline=col, width=ring_w)
    font = ImageFont.truetype(str(FONT), round(d * 0.58))
    draw.text((cx, cy), lbl, fill=col, font=font, anchor="mm")
    return im.resize((width, height), Image.Resampling.LANCZOS)


def _patch_klps_xbox_buttons(plain: bytearray) -> None:
    """Replace UFC 4's stock Xbox SWF bitmaps with the white KLPS UFC 2/3 Xbox GNF art."""
    import zipfile
    zp = None
    for base in pathlib.Path(__file__).resolve().parents:
        cand = base / "KLPS_UFC2-3_Xbox_Icons_Pack" / "KLPS_UFC2-3_Xbox_Icons_Pack" / "src" / "ufc23_xbox_gnf.zip"
        if cand.is_file():
            zp = cand
            break
    if zp is None:
        return
    from ufc4_direct_icons import _decode_bc7_gnf_rgba
    with zipfile.ZipFile(zp) as z:
        klps = {
            n.split("skins/buttons/ps3/", 1)[1]: z.read(n)
            for n in z.namelist()
            if "skins/buttons/ps3/" in n and n.endswith(".gnf")
        }
    mapping = {
        "ue_digital_one": "white/digital_one.gnf",
        "ue_digital_two": "white/digital_two.gnf",
        "ue_digital_three": "white/digital_three.gnf",
        "ue_digital_four": "white/digital_four.gnf",
        "left_bumper": "left_bumper.gnf",
        "right_bumper": "right_bumper.gnf",
        "left_trigger": "left_trigger.gnf",
        "right_trigger": "right_trigger.gnf",
        "guide": "guide.gnf",
    }
    for stem, gnf_name in mapping.items():
        if gnf_name not in klps:
            continue
        src_im = _decode_bc7_gnf_rgba(klps[gnf_name])
        if stem.startswith("ue_digital_"):
            bb = src_im.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
            if bb:
                src_im = src_im.crop(bb)
        for suf in ("_ps_mc", "_ps_highLight_mc"):
            sym = f"buttons.Btn_{stem}{suf}"
            pos, size = _bitmap_for_symbol(plain, sym)
            _write_bitmap_fit(plain, pos, size, src_im)

    Image, _, _ = _flash_helpers()[0]()
    for stem, gnf_name in (("start", "start.gnf"), ("select", "select.gnf")):
        if gnf_name not in klps:
            continue
        src_im = _decode_bc7_gnf_rgba(klps[gnf_name])
        bb = src_im.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
        if bb:
            src_im = src_im.crop(bb)
        for suf in ("_ps_mc", "_ps_highLight_mc"):
            sym = f"buttons.Btn_{stem}{suf}"
            pos, size = _bitmap_for_symbol(plain, sym)
            w, h = struct.unpack_from("<HH", plain, pos + 3)
            glyph_sz = min(20, h - 2) if stem == "select" else h - 2
            glyph = src_im.resize((glyph_sz, glyph_sz), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (w, h))
            canvas.alpha_composite(glyph, (w - glyph_sz, (h - glyph_sz) // 2))
            _write_bitmap_fit(plain, pos, size, canvas)


def xbox_art(original: bytes, include_select: bool = True,
             smooth_select: bool = True, use_klps: bool = True) -> bytes:
    """Build Xbox mappings with footer glyphs that cannot cover their labels."""
    if len(original) != ART_SIZE or original[:3] != b"CWS":
        raise ValueError("UFC 4 button art does not match the supported version")
    data = bytearray(zlib.decompress(original[8:]))
    symbols = data[SYMBOL_OFFSET:SYMBOL_OFFSET + SYMBOL_SIZE]
    count = int.from_bytes(symbols[:2], "little")
    position = 2
    names = {}
    for _ in range(count):
        cid = int.from_bytes(symbols[position:position + 2], "little")
        cid_offset = SYMBOL_OFFSET + position
        position += 2
        end = symbols.index(0, position)
        name = symbols[position:end].decode("latin1")
        position = end + 1
        names[name] = (cid_offset, cid)
    swaps = 0
    for name, (ps_offset, ps_cid) in names.items():
        if "_ps_" not in name or "Btn_start_ps_" in name or (include_select and "Btn_select_ps_" in name):
            continue
        other = names.get(name.replace("_ps_", "_xb_"))
        if other is None:
            continue
        xb_offset, xb_cid = other
        data[ps_offset:ps_offset + 2] = xb_cid.to_bytes(2, "little")
        data[xb_offset:xb_offset + 2] = ps_cid.to_bytes(2, "little")
        swaps += 1
    if swaps < 4:
        raise ValueError("Xbox artwork mappings were not found")
    plain = bytearray(original[:8]) + data
    _patch_footer_buttons(plain, include_select, smooth_select)
    compressed = original[:8] + zlib.compress(plain[8:], 9)
    if len(compressed) > ART_SIZE:
        raise ValueError("Xbox button-art patch exceeds the UFC 4 allocation")
    result = compressed + b"\0" * (ART_SIZE - len(compressed))
    if zlib.decompress(result[8:]) != plain[8:]:
        raise ValueError("Xbox button-art patch failed verification")
    return result


def gamepad_swf_art(original: bytes, family: str = "xbox", menus_preset: str = "white") -> bytes:
    """Build Flash buttonart.swf for Xbox (KLPS/Kenney), PlayStation (Stock/PS4/Kenney), or Switch."""
    if family == "xbox" and menus_preset == "white":
        return xbox_art(original)
    if family == "ps" and menus_preset == "stock":
        return original
    from gamepad_presets import gamepad_icon, fit_rgba_image
    _, _, _, swf_symbols, _ = _flash_helpers()

    if family == "xbox" and menus_preset in ("colored", "outline"):
        base_swf = xbox_art(original)
        plain = bytearray(base_swf[:8]) + bytearray(zlib.decompress(base_swf[8:]))
        from ufc4_direct_icons import _load_klps_ufc4_xbox_gnf, _decode_bc7_gnf_rgba
        klps = _load_klps_ufc4_xbox_gnf()
        done_pos = set()
        for name, _, _ in swf_symbols(plain):
            if not name.startswith("buttons.Btn_ue_digital_") or "_ps_" not in name:
                continue
            stem = name.removeprefix("buttons.Btn_").split("_ps_", 1)[0]
            base = stem.removeprefix("ue_")
            gnf_k = f"{base}.gnf" if menus_preset == "colored" else f"{stem}.gnf"
            if gnf_k not in klps:
                continue
            im = _decode_bc7_gnf_rgba(klps[gnf_k])
            bb = im.getchannel("A").point(lambda v: 255 if v > 15 else 0).getbbox()
            if bb:
                im = im.crop(bb)
            try:
                pos, size = _bitmap_for_symbol(plain, name)
                if pos in done_pos:
                    continue
                done_pos.add(pos)
                w, h = struct.unpack_from("<HH", plain, pos + 3)
                _write_bitmap_fit(plain, pos, size, fit_rgba_image(im, w, h))
            except Exception:
                continue
    else:
        plain = bytearray(original[:8]) + bytearray(zlib.decompress(original[8:]))
        done_pos = set()
        for name, _, _ in swf_symbols(plain):
            if not name.startswith("buttons.Btn_") or "_ps_" not in name:
                continue
            stem = name.removeprefix("buttons.Btn_").split("_ps_", 1)[0]
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
                pos, size = _bitmap_for_symbol(plain, name)
                if pos in done_pos:
                    continue
                done_pos.add(pos)
                w, h = struct.unpack_from("<HH", plain, pos + 3)
                _write_bitmap_fit(plain, pos, size, fit_rgba_image(im, w, h))
            except Exception:
                continue

    compressed = original[:8] + zlib.compress(plain[8:], 9)
    if len(compressed) > ART_SIZE:
        return xbox_art(original) if family == "xbox" else original
    result = compressed + b"\0" * (ART_SIZE - len(compressed))
    if zlib.decompress(result[8:]) != plain[8:]:
        raise ValueError("Gamepad button-art patch failed verification")
    return result


def prepare(archive: pathlib.Path, output: pathlib.Path,
            bindings_path: pathlib.Path | None = None,
            gamepad_family: str = "xbox", menus_preset: str = "white") -> None:
    with archive.open("rb") as stream:
        stream.seek(ART_OFFSET)
        current = stream.read(ART_SIZE)
    ps_file = output / "ufc4_buttonart_ps.bin"
    xbox_file = output / "ufc4_buttonart_xbox.bin"
    keyboard_file = output / "ufc4_buttonart_keyboard.bin"
    if ps_file.exists() and xbox_file.exists():
        original, previous_xbox = ps_file.read_bytes(), xbox_file.read_bytes()
        legacy_xbox = legacy_xbox_art(original)
        xbox = gamepad_swf_art(original, gamepad_family, menus_preset)
        prior_xbox = xbox_art(original, include_select=False, use_klps=False)
        prior_binary_select = xbox_art(original, smooth_select=False, use_klps=False)
        prior_stock_xbox = xbox_art(original, use_klps=False)
        if hashlib.sha256(original).hexdigest() != ORIGINAL_SHA256:
            raise ValueError("Prepared button artwork failed validation")
        previous_keyboard = keyboard_file.read_bytes() if keyboard_file.exists() else None
        keyboard = keyboard_art(original, bindings_path)
        if current not in (original, legacy_xbox, prior_xbox, prior_binary_select, prior_stock_xbox, previous_xbox, xbox, keyboard, previous_keyboard):
            raise ValueError("Archive button art changed; refusing to overwrite it")
        output.mkdir(parents=True, exist_ok=True)
        xbox_file.write_bytes(xbox)
        keyboard_file.write_bytes(keyboard)
        desired = None
        if current == previous_xbox and current != xbox:
            desired = xbox
        elif previous_keyboard is not None and current == previous_keyboard and current != keyboard:
            desired = keyboard
        if desired is not None:
            with archive.open("r+b") as stream:
                stream.seek(ART_OFFSET)
                stream.write(desired)
                stream.flush()
        (output / "ufc4_buttonart_archive.txt").write_text(str(archive.resolve()), encoding="utf-8")
        return
    original = current
    if hashlib.sha256(original).hexdigest() != ORIGINAL_SHA256:
        raise ValueError("UFC 4 archive version is not supported for button icons")
    xbox = gamepad_swf_art(original, gamepad_family, menus_preset)
    keyboard = keyboard_art(original, bindings_path)
    output.mkdir(parents=True, exist_ok=True)
    ps_file.write_bytes(original)
    xbox_file.write_bytes(xbox)
    keyboard_file.write_bytes(keyboard)
    (output / "ufc4_buttonart_archive.txt").write_text(str(archive.resolve()), encoding="utf-8")


def set_style(archive: pathlib.Path, output: pathlib.Path, style: str) -> None:
    original = (output / "ufc4_buttonart_ps.bin").read_bytes()
    xbox = (output / "ufc4_buttonart_xbox.bin").read_bytes()
    keyboard = (output / "ufc4_buttonart_keyboard.bin").read_bytes()
    desired = {"ps": original, "xbox": xbox, "keyboard": keyboard}[style]
    with archive.open("r+b") as stream:
        stream.seek(ART_OFFSET)
        current = stream.read(ART_SIZE)
        if current not in (original, xbox, keyboard):
            raise ValueError("Archive button art changed; refusing to overwrite it")
        if current == desired:
            return
        stream.seek(ART_OFFSET)
        stream.write(desired)
        stream.flush()
        stream.seek(ART_OFFSET)
        if stream.read(ART_SIZE) != desired:
            raise IOError("Button art verification failed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "set"))
    parser.add_argument("--archive", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--style", choices=("xbox", "ps", "keyboard"))
    parser.add_argument("--bindings", type=pathlib.Path,
                        help="PORTHEON/SacredFire bbport.ini with key.<action> bindings")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.archive, args.output, args.bindings)
    else:
        if not args.style:
            parser.error("--style is required for set")
        set_style(args.archive, args.output, args.style)


if __name__ == "__main__":
    main()
