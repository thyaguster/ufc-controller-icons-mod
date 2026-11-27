"""Reversible UFC 4 fight-HUD and tutorial icon textures."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).with_name("ufc4_keyboard")))

from ufc4_gnf_codec import dimensions, replace_image
from ufc4_keyboard.keyboard_art import descriptor, render
from ufc4_keyboard.keyboard_bindings import load_bbport
from ufc4_stock_xbox import render as render_stock_xbox

PREFIX = "ufc4_direct_icons_"


def _rows(manifest: Path) -> dict[tuple[int, str], str]:
    result = {}
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            path = row["RelPath"]
            if "/skins/buttons/ps/" not in path or row["TakeFrom"] != "TakeSourceAsIs":
                continue
            name = path.split("/skins/buttons/ps/", 1)[1]
            if descriptor(name.removesuffix(".gnf")) is None or name.startswith("controller"):
                continue
            result[(int(row["InArchiveSize"]), row["Blake2b"].lower())] = name
    return result


def _decode_bc7_gnf_rgba(gnf: bytes):
    """Decode a PS4 BC7 GNF texture into a PIL RGBA image using Pillow's DX10 DDS reader."""
    import io, struct
    from PIL import Image
    w, h = dimensions(gnf)
    bw, bh = (w + 3) // 4, (h + 3) // 4
    pitch = max(8, ((bw + 7) // 8) * 8)
    linear = bytearray(bw * bh * 16)
    tex = gnf[256:]
    for by in range(bh):
        for bx in range(bw):
            low = sum((((bx >> bit) & 1) << (2 * bit)) | (((by >> bit) & 1) << (2 * bit + 1)) for bit in range(3))
            off = (((by // 8) * (pitch // 8) + bx // 8) * 64 + low) * 16
            dst = (by * bw + bx) * 16
            linear[dst:dst + 16] = tex[off:off + 16]
    dds = bytearray(148)
    dds[0:4] = b"DDS "
    struct.pack_into("<IIIIIII", dds, 4, 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000, h, w, bw * bh * 16, 0, 1)
    struct.pack_into("<IIIIIIII", dds, 76, 32, 0x4, 0, 0, 0, 0, 0, 0)
    dds[84:88] = b"DX10"
    struct.pack_into("<II", dds, 108, 0x1000, 0)
    struct.pack_into("<IIIII", dds, 128, 98, 3, 0, 1, 0)
    return Image.open(io.BytesIO(bytes(dds) + bytes(linear))).convert("RGBA")


def _load_klps_ufc4_xbox_gnf() -> dict[str, bytes]:
    """Load the 43 KLPS UFC 4 Xbox GNF textures if the pack is present."""
    import zipfile
    candidates = [Path(__file__).with_name("ufc4_xbox_gnf.zip")]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.insert(0, Path(meipass) / "ufc4_xbox_gnf.zip")
    for base in Path(__file__).resolve().parents:
        candidates.append(base / "KLPS_UFC2-3-4_Xbox_Icons_Pack" / "src" / "ufc4_xbox_gnf.zip")
    for cand in candidates:
        if cand.is_file():
            with zipfile.ZipFile(cand) as zf:
                return {
                    n.split("skins/buttons/ps/", 1)[1]: zf.read(n)
                    for n in zf.namelist()
                    if "skins/buttons/ps/" in n and n.endswith(".gnf")
                }
    return {}


def _load_klps_ufc23_xbox_gnf() -> dict[str, bytes]:
    """Load KLPS UFC 2/3 Xbox GNF textures (for dark-disc black_large A/B/X/Y)."""
    import zipfile
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "ufc23_xbox_gnf.zip")
    for base in Path(__file__).resolve().parents:
        candidates.append(base / "ufc3" / "src" / "ufc23_xbox_gnf.zip")
        candidates.append(base / "KLPS_UFC2-3-4_Xbox_Icons_Pack" / "src" / "ufc23_xbox_gnf.zip")
    for cand in candidates:
        if cand.is_file():
            with zipfile.ZipFile(cand) as zf:
                return {
                    n.split("skins/buttons/ps3/", 1)[1]: zf.read(n)
                    for n in zf.namelist()
                    if "skins/buttons/ps3/" in n and n.endswith(".gnf")
                }
    return {}


def _fit_gnf_rgba(raw_gnf: bytes, width: int, height: int) -> bytes:
    """Decode a BC7 GNF, crop alpha bounds, and aspect-fit into (width, height) RGBA."""
    from PIL import Image
    im = _decode_bc7_gnf_rgba(raw_gnf)
    bb = im.getchannel("A").point(lambda v: 255 if v > 15 else 0).getbbox()
    if bb:
        im = im.crop(bb)
    pad = 2 if min(width, height) <= 32 else 0
    tw_max = max(1, width - pad)
    th_max = max(1, height - pad)
    sc = min(tw_max / im.width, th_max / im.height)
    tw, th = max(1, round(im.width * sc)), max(1, round(im.height * sc))
    fitted = im.resize((tw, th), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (width, height))
    canvas.alpha_composite(fitted, ((width - tw) // 2, (height - th) // 2))
    return canvas.tobytes()


def prepare(archive: Path, manifest: Path, output: Path, bindings_path: Path | None = None,
            xbox_menus: str = "white", xbox_moves: str = "ring", gamepad_family: str = "xbox") -> int:
    """Build a validated original and two variants from the player's archive."""
    map_file = output / f"{PREFIX}map.json"
    if map_file.exists():
        metadata = json.loads(map_file.read_text(encoding="utf-8"))
        prior = {key: (output / f"{PREFIX}{key}.bin").read_bytes() for key in ("ps", "xbox", "keyboard")}
        # Accept the earlier full-size Xbox artwork during an upgrade.
        legacy_xbox = bytearray()
        legacy_cursor = 0
        for row in metadata:
            size = row["size"]
            original = prior["ps"][legacy_cursor:legacy_cursor+size]
            width, height = dimensions(original)
            rgba = render_stock_xbox(output / "ufc4_buttonart_ps.bin", width, height,
                                     row["name"], scale_factor=1.0)
            legacy_xbox += replace_image(original, rgba) if rgba else original
            legacy_cursor += size
        cursor = 0
        with archive.open("rb") as stream:
            for row in metadata:
                size = row["size"]
                stream.seek(row["offset"])
                current = stream.read(size)
                candidates = [blob[cursor:cursor+size] for blob in prior.values()]
                candidates.append(legacy_xbox[cursor:cursor+size])
                if current not in candidates:
                    raise ValueError(f"UFC 4 icon texture changed: {row['name']}")
                cursor += size
        if cursor != len(prior["ps"]):
            raise ValueError("Prepared UFC 4 icon texture inventory is incomplete")
    else:
        targets = _rows(manifest)
        sizes = {size for size, _ in targets}
        data = archive.read_bytes()
        positions = {}
        at = 0
        while True:
            at = data.find(b"GNF ", at)
            if at < 0:
                break
            for size in sizes:
                if at+size > len(data):
                    continue
                digest = hashlib.blake2b(data[at:at+size], digest_size=32).hexdigest()
                name = targets.get((size, digest))
                if name:
                    positions[name] = (at, size)
            at += 4
        if len(positions) != len(targets) or len(targets) < 100:
            raise ValueError(f"Found {len(positions)} of {len(targets)} original UFC 4 icon textures")
        metadata = [{"name": name, "offset": offset, "size": size}
                    for name, (offset, size) in sorted(positions.items(), key=lambda item: item[1][0])]
        prior = None
    klps_gnf = _load_klps_ufc4_xbox_gnf()
    klps23_gnf = _load_klps_ufc23_xbox_gnf() if (gamepad_family == "xbox" and xbox_moves == "disc") else {}
    from gamepad_presets import gamepad_icon, fit_rgba_image
    bindings = load_bbport(bindings_path)
    blobs = {"ps": bytearray(), "xbox": bytearray(), "keyboard": bytearray()}
    cursor = 0
    for row in metadata:
        name, offset, size = row["name"], row["offset"], row["size"]
        original = prior["ps"][cursor:cursor+size] if prior else data[offset:offset+size]
        width, height = dimensions(original)
        desc = descriptor(name.removesuffix(".gnf"))
        keyboard = replace_image(original, render(width, height, desc, bindings), separate_alpha=True)
        stem = name.rsplit("/", 1)[-1].removesuffix(".gnf").removesuffix("_hold").removeprefix("ue_")
        is_face = stem in ("digital_one", "digital_two", "digital_three", "digital_four")
        is_menu = name.startswith(("white/", "ue_"))
        ground_stick = name in ("text_ground_game_hud/las.gnf", "text_ground_game_hud/ras.gnf")

        if gamepad_family == "switch":
            var = "outline" if (xbox_menus if is_menu else xbox_moves) == "outline" else "solid"
            im = None if ground_stick else gamepad_icon("switch", stem, var)
            xbox = replace_image(original, fit_rgba_image(im, width, height).tobytes(), separate_alpha=True) if im else original
        elif gamepad_family == "ps":
            im = None
            if not ground_stick:
                if is_face and not is_menu:
                    if xbox_moves == "kenney":
                        im = gamepad_icon("ps", stem, "kenney_color")
                elif is_face and is_menu and xbox_menus == "ps4_color":
                    im = gamepad_icon("ps", stem, "ps4_ea")
                elif is_face and is_menu and xbox_menus == "kenney_color":
                    im = gamepad_icon("ps", stem, "kenney_color")
                elif is_menu and xbox_menus in ("kenney", "kenney_color"):
                    im = gamepad_icon("ps", stem, "kenney_white")
                elif not is_face and (xbox_menus in ("kenney", "kenney_color") or xbox_moves == "kenney"):
                    im = gamepad_icon("ps", stem, "kenney_white")
            xbox = replace_image(original, fit_rgba_image(im, width, height).tobytes(), separate_alpha=True) if im else original
        elif klps_gnf:
            klps_tex = klps_gnf.get(name)
            kenney_im = None
            custom_tex = None
            force_fit = False
            if is_face and is_menu and xbox_menus == "kenney":
                kenney_im = gamepad_icon("xbox", stem, "kenney_white")
            elif is_face and not is_menu and xbox_moves == "kenney":
                kenney_im = gamepad_icon("xbox", stem, "kenney_color")
            elif not is_face and not ground_stick and xbox_menus == "kenney":
                kenney_im = gamepad_icon("xbox", stem, "kenney_white")
            elif is_face and is_menu and xbox_menus != "white":
                custom_tex = klps_gnf.get(f"ue_{stem}.gnf") if xbox_menus == "outline" else klps_gnf.get(f"{stem}.gnf")
                force_fit = True
            elif is_face and not is_menu and xbox_moves != "ring":
                if xbox_moves == "disc":
                    custom_tex = klps23_gnf.get(f"black_large/{stem}.gnf")
                    force_fit = True
                elif xbox_moves == "white":
                    custom_tex = klps_gnf.get(f"white/{stem}.gnf")
                    force_fit = True
            if kenney_im is not None:
                xbox = replace_image(original, fit_rgba_image(kenney_im, width, height).tobytes(), separate_alpha=True)
            elif custom_tex is not None:
                if not force_fit and len(custom_tex) == size and dimensions(custom_tex) == (width, height):
                    xbox = original[:256] + custom_tex[256:]
                else:
                    xbox = replace_image(original, _fit_gnf_rgba(custom_tex, width, height), separate_alpha=True)
            else:
                xbox = (original[:256] + klps_tex[256:]) if klps_tex and len(klps_tex) == size else original
        else:
            # The original ground stick indicators read better than the Xbox
            # replacement in the fight HUD.
            ground_stick = name in ("text_ground_game_hud/las.gnf", "text_ground_game_hud/ras.gnf")
            xbox_rgba = None if ground_stick else render_stock_xbox(output / "ufc4_buttonart_ps.bin", width, height, name)
            clean_inline = not name.startswith(("ground_game_hud/", "text_ground_game_hud/", "ue_")) and (
                name.rsplit("/", 1)[-1] in {
                    "left_trigger.gnf", "right_trigger.gnf",
                    "left_bumper.gnf", "right_bumper.gnf",
                    "digital_one.gnf", "digital_two.gnf",
                    "digital_three.gnf", "digital_four.gnf",
                    "las_c.gnf", "ras_c.gnf",
                }
            )
            xbox = replace_image(original, xbox_rgba, separate_alpha=clean_inline) if xbox_rgba else original
        for style, variant in (("ps", original), ("xbox", xbox), ("keyboard", keyboard)):
            if len(variant) != size:
                raise ValueError(f"Size mismatch in {name}")
            blobs[style] += variant
        cursor += size
    # Migrate whichever prepared variant is currently installed before the
    # previous asset snapshot is replaced (including older drawn Xbox art).
    if prior:
        cursor = 0
        with archive.open("r+b") as stream:
            for row in metadata:
                size = row["size"]
                stream.seek(row["offset"])
                current = stream.read(size)
                for key in blobs:
                    if current == prior[key][cursor:cursor+size] or (key == "xbox" and current == legacy_xbox[cursor:cursor+size]):
                        stream.seek(row["offset"])
                        stream.write(blobs[key][cursor:cursor+size])
                        break
                cursor += size
            stream.flush()
    output.mkdir(parents=True, exist_ok=True)
    for style, blob in blobs.items():
        (output / f"{PREFIX}{style}.bin").write_bytes(blob)
    (output / f"{PREFIX}map.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return len(metadata)


def set_style(archive: Path, output: Path, style: str) -> None:
    metadata = json.loads((output / f"{PREFIX}map.json").read_text(encoding="utf-8"))
    blobs = {key: (output / f"{PREFIX}{key}.bin").read_bytes() for key in ("ps", "xbox", "keyboard")}
    total = sum(row["size"] for row in metadata)
    if any(len(blob) != total for blob in blobs.values()):
        raise ValueError("Prepared direct icon assets are incomplete")
    patches = []
    cursor = 0
    with archive.open("r+b") as stream:
        for row in metadata:
            size = row["size"]
            stream.seek(row["offset"])
            current = stream.read(size)
            if current not in tuple(blob[cursor:cursor+size] for blob in blobs.values()):
                raise ValueError(f"UFC 4 icon texture changed: {row['name']}")
            desired = blobs[style][cursor:cursor+size]
            if desired != current:
                patches.append((row["offset"], current, desired))
            cursor += size
        try:
            for offset, _, desired in patches:
                stream.seek(offset)
                stream.write(desired)
            stream.flush()
            for offset, _, desired in patches:
                stream.seek(offset)
                if stream.read(len(desired)) != desired:
                    raise IOError("Direct icon verification failed")
        except Exception:
            for offset, original, _ in patches:
                stream.seek(offset)
                stream.write(original)
            stream.flush()
            raise
