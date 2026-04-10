#!/usr/bin/env python3
import sys
import glob
import shutil
import argparse
from pathlib import Path

PALETTE_GROUPS = 16
COLOURS_PER_GROUP = 16
TOTAL_COLOURS = PALETTE_GROUPS * COLOURS_PER_GROUP
PALETTE_BYTES = TOTAL_COLOURS * 2
TILE_SIZE_BYTES = 64


def gather_inputs(inputs, recursive=False):
    files = []

    for item in inputs:
        matches = glob.glob(item, recursive=recursive)
        if matches:
            for match in matches:
                p = Path(match)
                if p.is_file() and p.suffix.lower() == ".m7e":
                    files.append(p)
                elif p.is_dir():
                    if recursive:
                        files.extend([f for f in p.rglob("*.m7e") if f.is_file()])
                    else:
                        files.extend([f for f in p.glob("*.m7e") if f.is_file()])
            continue

        p = Path(item)
        if p.is_file() and p.suffix.lower() == ".m7e":
            files.append(p)
        elif p.is_dir():
            if recursive:
                files.extend([f for f in p.rglob("*.m7e") if f.is_file()])
            else:
                files.extend([f for f in p.glob("*.m7e") if f.is_file()])
        else:
            print(f"Warning: no .m7e match for {item}")

    seen = set()
    unique = []
    for f in files:
        key = str(f.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(f)

    return unique


def resolve_relative(base, path_str):
    p = Path(path_str)
    if p.is_absolute():
        return p
    return (base / p).resolve()


def load_project(project_path):
    data = {}
    with open(project_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()

    if "tiles" not in data:
        raise ValueError("Project missing tiles= entry")
    if "palette" not in data:
        raise ValueError("Project missing palette= entry")

    base = project_path.parent
    tiles_path = resolve_relative(base, data["tiles"])
    palette_path = resolve_relative(base, data["palette"])
    return tiles_path, palette_path


def backup_path_for(path):
    candidate = path.with_name(path.name + "_backup")
    if not candidate.exists():
        return candidate

    index = 2
    while True:
        candidate = path.with_name(f"{path.name}_backup{index}")
        if not candidate.exists():
            return candidate
        index += 1


def rgb5_to_snes_word(r5, g5, b5):
    return (b5 << 10) | (g5 << 5) | r5


def build_dummy_palette():
    ramps = []

    def make_ramp(mode):
        vals = [round(i * 31 / 15) for i in range(16)]
        out = []

        for v in vals:
            if mode == "gray":
                out.append((v, v, v))
            elif mode == "red":
                out.append((v, 0, 0))
            elif mode == "green":
                out.append((0, v, 0))
            elif mode == "blue":
                out.append((0, 0, v))
            elif mode == "yellow":
                out.append((v, v, 0))
            elif mode == "magenta":
                out.append((v, 0, v))
            elif mode == "cyan":
                out.append((0, v, v))
            elif mode == "orange":
                out.append((v, v // 2, 0))
            elif mode == "purple":
                out.append((v // 2, 0, v))
            elif mode == "lime":
                out.append((v // 2, v, 0))
            elif mode == "rg":
                out.append((v, v, v // 4))
            elif mode == "rb":
                out.append((v, v // 4, v))
            elif mode == "gb":
                out.append((v // 4, v, v))
            elif mode == "warm":
                out.append((v, min(31, int(v * 0.75)), min(31, int(v * 0.5))))
            elif mode == "cool":
                out.append((min(31, int(v * 0.5)), min(31, int(v * 0.75)), v))
            elif mode == "white":
                out.append((v, v, min(31, v + 4)))
        return out

    ramp_names = [
        "gray", "red", "green", "blue",
        "yellow", "magenta", "cyan", "orange",
        "purple", "lime", "rg", "rb",
        "gb", "warm", "cool", "white"
    ]

    for name in ramp_names:
        ramps.extend(make_ramp(name))

    out = bytearray()
    for r5, g5, b5 in ramps[:TOTAL_COLOURS]:
        word = rgb5_to_snes_word(r5, g5, b5)
        out.append(word & 0xFF)
        out.append((word >> 8) & 0xFF)

    return bytes(out)


def blank_group_bytes():
    return b"\x00" * (COLOURS_PER_GROUP * 2)


def load_palette_file(path):
    data = path.read_bytes()
    if len(data) != PALETTE_BYTES:
        raise ValueError(
            f"{path} must be {PALETTE_BYTES} bytes for 16 SNES palettes, got {len(data)}"
        )
    return bytearray(data)


def used_palette_groups_from_chr(tiles_path):
    data = tiles_path.read_bytes()
    if len(data) % TILE_SIZE_BYTES != 0:
        raise ValueError(
            f"{tiles_path} size {len(data)} is not a multiple of {TILE_SIZE_BYTES}"
        )

    used_colours = set(data)
    used_groups = sorted({value // COLOURS_PER_GROUP for value in used_colours})
    return used_colours, used_groups, len(data) // TILE_SIZE_BYTES


def format_group_list(values):
    if not values:
        return "none"
    return ", ".join(str(v) for v in values)


def process_project(project_path, use_blank=False, dry_run=False):
    tiles_path, palette_path = load_project(project_path)

    used_colours, used_groups, tile_count = used_palette_groups_from_chr(tiles_path)
    unused_groups = [g for g in range(PALETTE_GROUPS) if g not in used_groups]

    palette_data = load_palette_file(palette_path)
    filler = bytearray(blank_group_bytes() if use_blank else build_dummy_palette())

    changed_groups = []
    already_matching_groups = []

    for group in unused_groups:
        start = group * COLOURS_PER_GROUP * 2
        end = start + (COLOURS_PER_GROUP * 2)
        replacement = filler[start:end]
        if palette_data[start:end] != replacement:
            palette_data[start:end] = replacement
            changed_groups.append(group)
        else:
            already_matching_groups.append(group)

    used_count = len(used_colours)
    highest_colour = max(used_colours) if used_colours else -1

    print(f"\nProject: {project_path}")
    print(f"  CHR file              : {tiles_path}")
    print(f"  Palette file          : {palette_path}")
    print(f"  Tile count            : {tile_count}")
    print(f"  Used colours          : {used_count}")
    print(f"  Highest colour used   : {highest_colour}")
    print(f"  Used palette groups   : {len(used_groups)}")
    print(f"  Used group numbers    : {format_group_list(used_groups)}")
    print(f"  Unused palette groups : {len(unused_groups)}")
    print(f"  Unused group numbers  : {format_group_list(unused_groups)}")
    print(f"  Fill mode             : {'blank' if use_blank else 'dummy ramps'}")
    print(f"  Groups changed        : {len(changed_groups)}")
    if changed_groups:
        print(f"  Changed group numbers : {format_group_list(changed_groups)}")
    if already_matching_groups:
        print(f"  Already matched fill  : {format_group_list(already_matching_groups)}")

    if dry_run:
        print("  Dry run only          : no files written")
        return

    backup = backup_path_for(palette_path)
    shutil.copy2(palette_path, backup)
    palette_path.write_bytes(palette_data)

    print(f"  Backup written        : {backup}")
    print("  Palette updated       : unused groups replaced")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Reduce a Mode7 palette by clearing any unused 16-colour palette groups "
            "based only on colour indices used in the CHR data. By default, unused "
            "groups are replaced with the same dummy ramp palette groups used by the "
            "editor. Use --blank to fill unused groups with zero."
        )
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input .m7e file(s), wildcard(s), or folder(s)"
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Recurse into subfolders when input is a folder"
    )
    parser.add_argument(
        "--blank",
        action="store_true",
        help="Fill unused palette groups with zeros instead of editor dummy ramps"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would happen without writing files"
    )

    args = parser.parse_args()

    projects = gather_inputs(args.inputs, recursive=args.recursive)
    if not projects:
        print("No .m7e project files found.")
        sys.exit(1)

    failures = 0
    for project in projects:
        try:
            process_project(
                project,
                use_blank=args.blank,
                dry_run=args.dry_run
            )
        except Exception as e:
            failures += 1
            print(f"\nFAIL: {project} -> {e}")

    print(f"\nDone. Processed {len(projects)} project(s), failures: {failures}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
