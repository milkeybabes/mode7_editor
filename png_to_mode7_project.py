#!/usr/bin/env python3
import sys
import argparse
from collections import OrderedDict
from pathlib import Path

from PIL import Image

TILE_SIZE = 8
MAX_TILES = 256
PALETTE_SIZE = 256
PALETTE_GROUPS = 16
COLOURS_PER_GROUP = 16


def snes8_to_5(v):
    return max(0, min(31, v >> 3))


def rgb_to_snes_word(r8, g8, b8):
    r5 = snes8_to_5(r8)
    g5 = snes8_to_5(g8)
    b5 = snes8_to_5(b8)
    return (b5 << 10) | (g5 << 5) | r5


def save_palette_snes(path, palette):
    out = bytearray()

    for r, g, b in palette:
        word = rgb_to_snes_word(r, g, b)
        out.append(word & 0xFF)
        out.append((word >> 8) & 0xFF)

    path.write_bytes(out)


def save_tiles(path, tiles):
    out = bytearray()
    for tile in tiles:
        out.extend(tile)
    path.write_bytes(out)


def save_map(path, map_data):
    path.write_bytes(bytearray(map_data))


def save_project(path, palette_name, tiles_name, map_name, width_tiles, height_tiles):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"palette={palette_name}\n")
        f.write(f"tiles={tiles_name}\n")
        f.write(f"maps={map_name}\n")
        f.write(f"width={width_tiles}\n")
        f.write(f"height={height_tiles}\n")


def pad_palette(palette_rgb):
    padded = list(palette_rgb[:PALETTE_SIZE])
    while len(padded) < PALETTE_SIZE:
        padded.append((0, 0, 0))
    return padded


def extract_palette_from_p_image(img):
    raw = img.getpalette()
    if raw is None:
        raise ValueError("Indexed image has no palette data")

    colours = []
    used_indices = set(img.getdata())

    for i in range(PALETTE_SIZE):
        base = i * 3
        if base + 2 >= len(raw):
            colours.append((0, 0, 0))
        else:
            colours.append((raw[base], raw[base + 1], raw[base + 2]))

    highest_used = max(used_indices) if used_indices else -1
    used_palette = colours[:highest_used + 1] if highest_used >= 0 else []
    return pad_palette(used_palette), len(used_indices), highest_used


def quantize_image(img, dither=False):
    method = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
    pal_img = img.convert("P", palette=Image.Palette.ADAPTIVE, colors=PALETTE_SIZE, dither=method)
    palette, used_count, highest_used = extract_palette_from_p_image(pal_img)
    return pal_img, palette, used_count, highest_used


def exact_index_image(img):
    pixels = list(img.getdata())
    colours = OrderedDict()

    indexed = []
    for rgb in pixels:
        if rgb not in colours:
            colours[rgb] = len(colours)
            if len(colours) > PALETTE_SIZE:
                raise ValueError(
                    f"Image uses more than {PALETTE_SIZE} exact colours; "
                    f"found at least {len(colours)}"
                )
        indexed.append(colours[rgb])

    pal = list(colours.keys())
    palette = pad_palette(pal)

    out = Image.new("P", img.size)
    out.putdata(indexed)

    flat_pal = []
    for r, g, b in palette:
        flat_pal.extend([r, g, b])
    out.putpalette(flat_pal)

    highest_used = max(indexed) if indexed else -1
    return out, palette, len(colours), highest_used


def image_to_tiles(indexed_img):
    width, height = indexed_img.size
    width_tiles = width // TILE_SIZE
    height_tiles = height // TILE_SIZE
    pixels = list(indexed_img.getdata())

    tiles = []
    tile_lookup = {}
    map_data = []

    for ty in range(height_tiles):
        for tx in range(width_tiles):
            tile = bytearray()
            for py in range(TILE_SIZE):
                src_y = ty * TILE_SIZE + py
                row_start = src_y * width + (tx * TILE_SIZE)
                tile.extend(pixels[row_start:row_start + TILE_SIZE])

            tile_key = bytes(tile)
            if tile_key not in tile_lookup:
                tile_index = len(tiles)
                if tile_index >= MAX_TILES:
                    raise ValueError(
                        f"Unique tile limit exceeded: need more than {MAX_TILES} tiles"
                    )
                tile_lookup[tile_key] = tile_index
                tiles.append(bytearray(tile))
            map_data.append(tile_lookup[tile_key])

    return tiles, map_data, width_tiles, height_tiles


def build_preview_image(indexed_img, out_path):
    indexed_img.save(out_path)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Convert a PNG image into Mode7 editor files: .pal, .chr, .map, and .m7e. "
            "Image width and height must be divisible by 8. Fails if unique 8x8 tiles "
            "exceed 256."
        )
    )
    parser.add_argument("input_png", help="Input PNG image")
    parser.add_argument(
        "-o", "--output",
        help="Output basename. Default: input filename without extension"
    )
    parser.add_argument(
        "--exact-colours",
        action="store_true",
        help="Do not quantize. Fail if the source image uses more than 256 exact colours."
    )
    parser.add_argument(
        "--dither",
        action="store_true",
        help="When quantizing, use Floyd-Steinberg dithering."
    )
    parser.add_argument(
        "--save-preview",
        action="store_true",
        help="Save the indexed/quantized preview PNG beside the project files."
    )

    args = parser.parse_args()

    input_path = Path(args.input_png)
    if not input_path.is_file():
        print(f"Input file not found: {input_path}")
        sys.exit(1)

    out_base = Path(args.output) if args.output else input_path.with_suffix("")
    out_dir = out_base.parent if out_base.parent != Path("") else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_base.name

    img = Image.open(input_path).convert("RGB")
    width, height = img.size

    if width % TILE_SIZE != 0 or height % TILE_SIZE != 0:
        print(
            f"Image size must be divisible by {TILE_SIZE}: got {width}x{height}"
        )
        sys.exit(1)

    try:
        if args.exact_colours:
            indexed_img, palette, used_colours, highest_colour = exact_index_image(img)
            colour_mode = "exact"
        else:
            indexed_img, palette, used_colours, highest_colour = quantize_image(
                img, dither=args.dither
            )
            colour_mode = "quantized"

        tiles, map_data, width_tiles, height_tiles = image_to_tiles(indexed_img)

    except Exception as e:
        print(f"FAIL: {e}")
        sys.exit(1)

    palette_path = out_dir / f"{stem}.pal"
    chr_path = out_dir / f"{stem}.chr"
    map_path = out_dir / f"{stem}_1.map"
    project_path = out_dir / f"{stem}.m7e"

    save_palette_snes(palette_path, palette)
    save_tiles(chr_path, tiles)
    save_map(map_path, map_data)
    save_project(
        project_path,
        palette_path.name,
        chr_path.name,
        map_path.name,
        width_tiles,
        height_tiles
    )

    if args.save_preview:
        preview_path = out_dir / f"{stem}_indexed.png"
        build_preview_image(indexed_img, preview_path)
        print(f"Preview PNG          : {preview_path}")

    used_groups = sorted({i // COLOURS_PER_GROUP for i in range(highest_colour + 1)}) if highest_colour >= 0 else []

    print(f"Input PNG            : {input_path}")
    print(f"Mode                 : {colour_mode}")
    print(f"Image size           : {width}x{height}")
    print(f"Map size             : {width_tiles}x{height_tiles} tiles")
    print(f"Used colours         : {used_colours}")
    print(f"Highest colour index : {highest_colour}")
    print(f"Palette groups used  : {', '.join(str(g) for g in used_groups) if used_groups else 'none'}")
    print(f"Unique tiles         : {len(tiles)} / {MAX_TILES}")
    print(f"Palette file         : {palette_path}")
    print(f"CHR file             : {chr_path}")
    print(f"Map file             : {map_path}")
    print(f"Project file         : {project_path}")
    print("Done.")


if __name__ == "__main__":
    main()
