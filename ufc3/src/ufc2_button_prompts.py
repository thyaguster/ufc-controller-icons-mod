"""Reversible PS / Xbox / Switch / Keyboard button-prompt patcher for UFC 2 v1.13 (CUSA01968)."""
from __future__ import annotations

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

from keyboard_art import descriptor, render as render_keycap  # noqa: E402
from keyboard_bindings import load_bbport  # noqa: E402
from ufc4_gnf_codec import dimensions, replace_image  # noqa: E402

_NON_BUTTON_GNFS = frozenset({
    "black_large/blurred_strip.gnf",
    "box_art.gnf",
    "careehubmainicon.gnf",
    "controller.gnf",
    "controller_swatch.gnf",
    "controller_white.gnf",
})


def parse_ufc2_toc(archive: Path) -> tuple[int, list[tuple[int, str, int, int]]]:
    """Parse UFC 2's EB\\x00\\x03 .big TOC into (count, [(toc_idx, full_path, offset, size)])."""
    with archive.open("rb") as f:
        hdr = f.read(20)
        magic, count, _, name_off, dir_hint = struct.unpack(">4sIIII", hdr)
        if magic != b"EB\x00\x03":
            raise ValueError(f"Unsupported .big archive header in {archive.name}: {magic!r}")
        f.seek(0)
        toc = f.read(min(archive.stat().st_size, max(dir_hint + 0x40000, 0x200000)))

    entries = [
        (
            struct.unpack_from(">I", toc, 0x30 + i * 16)[0] * 16,
            struct.unpack_from(">I", toc, 0x30 + i * 16 + 8)[0],
        )
        for i in range(count)
    ]

    fstride = None
    for cand in range(48, 80):
        if name_off + 8 * cand >= len(toc):
            break
        if all(
            struct.unpack_from(">H", toc, name_off + k * cand)[0] < 4096
            and toc[name_off + k * cand + 2] >= 32
            for k in range(min(count, 8))
        ):
            fstride = cand
            break
    if fstride is None:
        raise ValueError(f"Could not detect filename stride in {archive.name}")

    dir_start = toc.find(b"samplegame/ui\x00", name_off)
    if dir_start < 0:
        raise ValueError(f"Could not locate directory table in {archive.name}")

    # Auto-detect directory stride from consecutive skins/buttons/ps3 entries
    p1 = toc.find(b"samplegame/ui/kettle_assets/skins/buttons/ps3", dir_start)
    p2 = toc.find(b"samplegame/ui/kettle_assets/skins/buttons/ps3", p1 + 1) if p1 >= 0 else -1
    dstride = (p2 - p1) if (p1 >= 0 and p2 > p1 and (p2 - p1) <= 0x100) else 0x4D

    dirs: list[str] = []
    pos = dir_start
    while pos + dstride <= len(toc) and toc[pos] != 0:
        dirs.append(toc[pos:pos + dstride].split(b"\x00", 1)[0].decode("ascii", "replace"))
        pos += dstride

    out: list[tuple[int, str, int, int]] = []
    for i in range(count):
        p = name_off + i * fstride
        d_idx = struct.unpack_from(">H", toc, p)[0]
        fn = toc[p + 2:p + fstride].split(b"\x00", 1)[0].decode("ascii", "replace")
        full = f"{dirs[d_idx]}/{fn}" if d_idx < len(dirs) else fn
        out.append((i, full, entries[i][0], entries[i][1]))
    return count, out


def decompress_chunkzip(raw: bytes) -> bytes:
    """Decompress an EA chunkzip v2 blob (single or multi-chunk)."""
    if len(raw) < 48 or raw[:8] != b"chunkzip":
        return raw
    ver, uncomp_sz, _chunk_sz, chunk_count = struct.unpack_from(">IIII", raw, 8)
    if ver != 2 or chunk_count < 1:
        raise ValueError(f"Unsupported chunkzip version={ver} chunks={chunk_count}")
    out = bytearray()
    table_off = 32
    data_off = table_off + chunk_count * 16
    for i in range(chunk_count):
        _u0, _u1, csz, flag = struct.unpack_from(">IIII", raw, table_off + i * 16)
        chunk = raw[data_off:data_off + csz]
        data_off += csz
        out += zlib.decompress(chunk, -15) if flag == 1 else chunk
    if len(out) != uncomp_sz:
        raise ValueError(f"chunkzip size mismatch: got {len(out)}, expected {uncomp_sz}")
    return bytes(out)


def compress_chunkzip(plain: bytes) -> bytes:
    """Compress a payload (<= 128 KB) into EA chunkzip v2 format."""
    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    cdata = co.compress(plain) + co.flush()
    hdr = b"chunkzip" + struct.pack(
        ">IIIIIIIIII",
        2, len(plain), 0x00020000, 1, 0x00000010,
        0, 0, 0, len(cdata), 1,
    )
    return hdr + cdata


def _load_klps_ufc23_gnfs() -> dict[str, bytes]:
    candidates = [Path(__file__).with_name("ufc23_xbox_gnf.zip")]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.insert(0, Path(meipass) / "ufc23_xbox_gnf.zip")
    for base in Path(__file__).resolve().parents:
        candidates.append(base / "ufc3" / "src" / "ufc23_xbox_gnf.zip")
        candidates.append(base / "KLPS_UFC2-3-4_Xbox_Icons_Pack" / "src" / "ufc23_xbox_gnf.zip")
    for zp in candidates:
        if zp.is_file():
            with zipfile.ZipFile(zp) as z:
                return {
                    n.split("skins/buttons/ps3/", 1)[1]: z.read(n)
                    for n in z.namelist()
                    if "skins/buttons/ps3/" in n and n.endswith(".gnf")
                }
    return {}


def _ensure_backup(ui_big: Path, cache: Path) -> dict:
    """Create or load the verified original UFC 2 backup in cache."""
    cache.mkdir(parents=True, exist_ok=True)
    meta_p = cache / "ufc2_backup.json"
    blob_p = cache / "ufc2_orig_cz.bin"
    if meta_p.is_file() and blob_p.is_file():
        return json.loads(meta_p.read_text(encoding="utf-8"))

    _, toc = parse_ufc2_toc(ui_big)
    orig_file_size = ui_big.stat().st_size
    items = []
    blob = bytearray()
    with ui_big.open("rb") as f:
        for toc_idx, full, off, sz in toc:
            if "skins/buttons/ps3/" not in full or not full.endswith(".gnf"):
                continue
            rel = full.split("skins/buttons/ps3/", 1)[1]
            if rel in _NON_BUTTON_GNFS or not descriptor(rel.removesuffix(".gnf")):
                continue
            f.seek(off)
            raw = f.read(sz)
            dec = decompress_chunkzip(raw)
            if dec[:4] != b"GNF ":
                continue
            try:
                dimensions(dec)
            except Exception:
                continue
            items.append({
                "toc_idx": toc_idx,
                "rel": rel,
                "orig_off": off,
                "orig_sz": sz,
                "blob_off": len(blob),
                "blob_len": len(raw),
            })
            blob += raw

    if not items:
        raise ValueError("No valid BC7 button GNFs found in UFC 2 inxp_ui_40.big")
    backup = {"orig_file_size": orig_file_size, "items": items}
    blob_p.write_bytes(bytes(blob))
    meta_p.write_text(json.dumps(backup, indent=2), encoding="utf-8")
    return backup


def apply_ufc2(databigs_dir: Path, cache: Path, style: str,
               bindings_path: Path | None = None,
               menus_preset: str = "white", moves_preset: str = "ring") -> int:
    """Apply 'ps', 'xbox', 'switch', or 'keyboard' to UFC 2 inxp_ui_40.big (100% reversible)."""
    ui_big = databigs_dir / "inxp_ui_40.big"
    if not ui_big.is_file():
        raise FileNotFoundError(f"Expected inxp_ui_40.big in {databigs_dir}")

    backup = _ensure_backup(ui_big, cache)
    orig_blob = (cache / "ufc2_orig_cz.bin").read_bytes()
    orig_file_size = int(backup["orig_file_size"])
    items = backup["items"]
    is_ps_stock = (style == "ps" and menus_preset == "stock" and moves_preset == "stock")

    bindings = load_bbport(bindings_path) if style == "keyboard" else None
    klps_gnfs = _load_klps_ufc23_gnfs() if style == "xbox" else {}
    from gamepad_presets import gamepad_icon, fit_rgba_image
    from ufc4_direct_icons import _fit_gnf_rgba

    # Prepare new chunkzip blobs for each item
    updates: list[tuple[dict, bytes]] = []
    for it in items:
        orig_cz = orig_blob[it["blob_off"]:it["blob_off"] + it["blob_len"]]
        if is_ps_stock:
            updates.append((it, orig_cz))
            continue
        orig_gnf = decompress_chunkzip(orig_cz)
        w, h = dimensions(orig_gnf)
        rel = it["rel"]
        stem = rel.rsplit("/", 1)[-1].removesuffix(".gnf").removesuffix("_hold").removeprefix("ue_")
        is_face = stem in ("digital_one", "digital_two", "digital_three", "digital_four")
        is_menu = rel.startswith(("white/", "ue_"))
        ground_stick = rel in ("text_ground_game_hud/las.gnf", "text_ground_game_hud/ras.gnf")

        new_gnf = orig_gnf
        if style == "keyboard":
            desc = descriptor(rel.removesuffix(".gnf"))
            new_gnf = replace_image(orig_gnf, render_keycap(w, h, desc, bindings), separate_alpha=True)
        elif style == "switch":
            var = "outline" if (menus_preset if is_menu else moves_preset) == "outline" else "solid"
            im = None if ground_stick else gamepad_icon("switch", stem, var)
            if im is not None:
                new_gnf = replace_image(orig_gnf, fit_rgba_image(im, w, h).tobytes(), separate_alpha=True)
        elif style == "ps":
            im = None
            if not ground_stick:
                if is_face and not is_menu and moves_preset == "kenney":
                    im = gamepad_icon("ps", stem, "kenney_color")
                elif is_face and is_menu and menus_preset == "ps4_color":
                    im = gamepad_icon("ps", stem, "ps4_ea")
                elif is_face and is_menu and menus_preset == "kenney_color":
                    im = gamepad_icon("ps", stem, "kenney_color")
                elif is_menu and menus_preset in ("kenney", "kenney_color"):
                    im = gamepad_icon("ps", stem, "kenney_white")
                elif not is_face and (menus_preset in ("kenney", "kenney_color") or moves_preset == "kenney"):
                    im = gamepad_icon("ps", stem, "kenney_white")
            if im is not None:
                new_gnf = replace_image(orig_gnf, fit_rgba_image(im, w, h).tobytes(), separate_alpha=True)
        elif style == "xbox":
            kenney_im = None
            custom_tex = None
            if not ground_stick:
                if is_face and is_menu and menus_preset == "kenney":
                    kenney_im = gamepad_icon("xbox", stem, "kenney_white")
                elif is_face and not is_menu and moves_preset == "kenney":
                    kenney_im = gamepad_icon("xbox", stem, "kenney_color")
                elif not is_face and menus_preset == "kenney":
                    kenney_im = gamepad_icon("xbox", stem, "kenney_white")
                elif is_face and is_menu and menus_preset != "white":
                    custom_tex = klps_gnfs.get(f"ue_{stem}.gnf") if menus_preset == "outline" else klps_gnfs.get(f"{stem}.gnf")
                elif is_face and not is_menu and moves_preset != "ring":
                    if moves_preset == "disc":
                        custom_tex = klps_gnfs.get(f"black_large/{stem}.gnf")
                    elif moves_preset == "white":
                        custom_tex = klps_gnfs.get(f"white/{stem}.gnf")
            if kenney_im is not None:
                new_gnf = replace_image(orig_gnf, fit_rgba_image(kenney_im, w, h).tobytes(), separate_alpha=True)
            elif custom_tex is not None:
                new_gnf = replace_image(orig_gnf, _fit_gnf_rgba(custom_tex, w, h), separate_alpha=True)
            elif not ground_stick:
                km = klps_gnfs.get(rel) or klps_gnfs.get(f"white/{rel}") or klps_gnfs.get(rel.removeprefix("white/"))
                if km and len(km) == len(orig_gnf) and dimensions(km) == (w, h):
                    new_gnf = orig_gnf[:256] + km[256:]

        new_cz = orig_cz if new_gnf == orig_gnf else compress_chunkzip(new_gnf)
        updates.append((it, new_cz))

    with ui_big.open("r+b") as f:
        # Reset archive tail cleanly before writing new appended blobs
        f.truncate(orig_file_size)
        append_cursor = (orig_file_size + 15) & ~15
        if append_cursor > orig_file_size:
            f.seek(orig_file_size)
            f.write(b"\x00" * (append_cursor - orig_file_size))

        for it, new_cz in updates:
            toc_pos = 0x30 + it["toc_idx"] * 16
            if is_ps_stock or len(new_cz) <= it["orig_sz"]:
                dst_off = it["orig_off"]
                f.seek(dst_off)
                f.write(new_cz)
                if len(new_cz) < it["orig_sz"]:
                    f.write(b"\x00" * (it["orig_sz"] - len(new_cz)))
                new_sz = it["orig_sz"] if is_ps_stock else len(new_cz)
            else:
                dst_off = append_cursor
                f.seek(dst_off)
                f.write(new_cz)
                pad = (-len(new_cz)) & 15
                if pad:
                    f.write(b"\x00" * pad)
                append_cursor = dst_off + len(new_cz) + pad
                new_sz = len(new_cz)
            # Update TOC entry offset (//16) and size
            f.seek(toc_pos)
            f.write(struct.pack(">I", dst_off // 16))
            f.seek(toc_pos + 8)
            f.write(struct.pack(">I", new_sz))

        final_size = orig_file_size if is_ps_stock else append_cursor
        if is_ps_stock:
            f.truncate(orig_file_size)
        f.seek(0x1C)
        f.write(struct.pack(">I", final_size))
        f.flush()

    return len(updates)
