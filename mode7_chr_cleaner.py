#!/usr/bin/env python3
import sys
import glob
import shutil
import argparse
from pathlib import Path

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

    if "maps" in data:
        map_paths = [p.strip() for p in data["maps"].split(",") if p.strip()]
    elif "map" in data:
        map_paths = [data["map"].strip()]
    else:
        raise ValueError("Project missing map= or maps= entry")

    width = int(data.get("width", 128))
    height = int(data.get("height", 128))

    base = project_path.parent
    tiles_path = resolve_relative(base, data["tiles"])
    resolved_maps = [resolve_relative(base, p) for p in map_paths]

    return tiles_path, resolved_maps, width, height


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


def load_tiles(tiles_path):
    data = tiles_path.read_bytes()
    if len(data) % TILE_SIZE_BYTES != 0:
        raise ValueError(
            f"{tiles_path} size {len(data)} is not a multiple of {TILE_SIZE_BYTES}"
        )

    return [bytearray(data[i:i + TILE_SIZE_BYTES]) for i in range(0, len(data), TILE_SIZE_BYTES)]


def load_maps(map_paths, expected_size):
    maps = []
    for path in map_paths:
        data = bytearray(path.read_bytes())
        if len(data) != expected_size:
            raise ValueError(f"{path} is {len(data)} bytes, expected {expected_size}")
        maps.append(data)
    return maps


def tiles_used_by_maps(map_datas):
    used = set()
    for data in map_datas:
        used.update(data)
    return used


def format_preview(values, limit=24):
    if not values:
        return "none"
    preview = ", ".join(str(v) for v in values[:limit])
    if len(values) > limit:
        preview += ", ..."
    return preview


def write_backup_and_file(path, data_bytes, dry_run=False):
    backup = backup_path_for(path)
    if not dry_run:
        shutil.copy2(path, backup)
        path.write_bytes(data_bytes)
    return backup


def trailing_unused_below_exclude(used_tiles, exclude_from, tile_count):
    """
    Return the contiguous unused range immediately below exclude_from.
    Example:
      exclude=192, highest used below exclude is 150
      -> trailing unused is 151..191
    """
    upper = min(exclude_from, tile_count)
    if upper <= 0:
        return []

    trailing = []
    for i in range(upper - 1, -1, -1):
        if i in used_tiles:
            break
        trailing.append(i)

    trailing.reverse()
    return trailing


def blank_unused_tiles(tiles, used_tiles, exclude_from, tail_only=False):
    cleared = []
    protected_unused = []

    if tail_only:
        candidate_set = set(trailing_unused_below_exclude(used_tiles, exclude_from, len(tiles)))
    else:
        candidate_set = None

    for i in range(len(tiles)):
        if i in used_tiles:
            continue

        if i >= exclude_from:
            protected_unused.append(i)
            continue

        if tail_only and i not in candidate_set:
            continue

        if any(tiles[i]):
            tiles[i] = bytearray(TILE_SIZE_BYTES)
            cleared.append(i)

    return tiles, cleared, protected_unused


def compress_tiles_and_maps(tiles, map_datas, used_tiles, exclude_from, tail_only=False):
    tile_count = len(tiles)
    below_limit = min(exclude_from, tile_count)

    used_below = sorted(t for t in used_tiles if t < below_limit)

    if tail_only:
        trailing_unused = trailing_unused_below_exclude(used_tiles, exclude_from, tile_count)
        new_below_count = below_limit - len(trailing_unused)
        kept_below = list(range(new_below_count))
        removed_below = trailing_unused
    else:
        kept_below = used_below
        removed_below = sorted(t for t in range(below_limit) if t not in used_tiles)

    remap = {old: new for new, old in enumerate(kept_below)}

    new_tiles = []
    for old in kept_below:
        new_tiles.append(bytearray(tiles[old]))

    if exclude_from < tile_count:
        for old in range(exclude_from, tile_count):
            new_tiles.append(bytearray(tiles[old]))

    remapped_count = 0
    unchanged_high = 0

    new_maps = []
    for data in map_datas:
        out = bytearray(len(data))
        for i, value in enumerate(data):
            if value < exclude_from:
                if value in remap:
                    new_value = remap[value]
                    if new_value != value:
                        remapped_count += 1
                    out[i] = new_value
                else:
                    raise ValueError(
                        f"Map references tile {value} below exclude {exclude_from}, "
                        f"but it was removed by compression"
                    )
            else:
                out[i] = value
                unchanged_high += 1
        new_maps.append(out)

    stats = {
        "kept_below": kept_below,
        "removed_below": removed_below,
        "removed_count": len(removed_below),
        "remapped_count": remapped_count,
        "unchanged_high_refs": unchanged_high,
        "old_tile_count": tile_count,
        "new_tile_count": len(new_tiles),
    }

    return new_tiles, new_maps, stats


def process_project(project_path, exclude_from, compress=False, dry_run=False, tail_only=False):
    tiles_path, map_paths, width, height = load_project(project_path)
    expected_size = width * height

    tiles = load_tiles(tiles_path)
    map_datas = load_maps(map_paths, expected_size)
    used_tiles = tiles_used_by_maps(map_datas)

    tile_count = len(tiles)
    used_in_range = sorted(t for t in used_tiles if t < tile_count)
    used_below = sorted(t for t in used_tiles if t < exclude_from and t < tile_count)
    used_high = sorted(t for t in used_tiles if t >= exclude_from and t < tile_count)
    trailing_unused = trailing_unused_below_exclude(used_tiles, exclude_from, tile_count)

    print(f"\nProject: {project_path}")
    print(f"  CHR file                 : {tiles_path}")
    print(f"  Map files                : {len(map_paths)}")
    print(f"  Tile count               : {tile_count}")
    print(f"  Exclude threshold        : {exclude_from}")
    print(f"  Used tiles total         : {len(used_in_range)}")
    print(f"  Used tiles below exclude : {len(used_below)}")
    print(f"  Used tiles >= exclude    : {len(used_high)}")
    print(f"  Trailing unused below exclude: {len(trailing_unused)}")
    print(f"  Trailing unused range    : {format_preview(trailing_unused)}")

    if compress:
        new_tiles, new_maps, stats = compress_tiles_and_maps(
            tiles, map_datas, used_tiles, exclude_from, tail_only=tail_only
        )

        mode_text = "compress trailing tail only" if tail_only else "compress all unused holes below exclude"
        print(f"  Mode                     : {mode_text}")
        print(f"  Removed below {exclude_from} : {stats['removed_count']}")
        print(f"  Old CHR bytes            : {stats['old_tile_count'] * TILE_SIZE_BYTES}")
        print(f"  New CHR bytes            : {stats['new_tile_count'] * TILE_SIZE_BYTES}")
        print(f"  Bytes saved              : {(stats['old_tile_count'] - stats['new_tile_count']) * TILE_SIZE_BYTES}")
        print(f"  Map entries remapped     : {stats['remapped_count']}")
        print(f"  Map refs >= exclude kept : {stats['unchanged_high_refs']}")
        print(f"  Removed tile numbers     : {format_preview(stats['removed_below'])}")

        if dry_run:
            print("  Dry run only             : no files written")
            return

        chr_backup = write_backup_and_file(
            tiles_path,
            b"".join(bytes(tile) for tile in new_tiles),
            dry_run=False
        )
        print(f"  CHR backup               : {chr_backup}")
        print("  CHR updated              : compacted")

        for path, data in zip(map_paths, new_maps):
            map_backup = write_backup_and_file(path, bytes(data), dry_run=False)
            print(f"  Map backup               : {map_backup}")
            print(f"  Map updated              : {path}")

    else:
        tiles, cleared, protected_unused = blank_unused_tiles(
            tiles, used_tiles, exclude_from, tail_only=tail_only
        )

        blanked_bytes = len(cleared) * TILE_SIZE_BYTES
        mode_text = "blank trailing tail only" if tail_only else "blank all unused holes below exclude"
        print(f"  Mode                     : {mode_text}")
        print(f"  Unused blanked below {exclude_from}: {len(cleared)}")
        print(f"  CHR size unchanged       : {tile_count * TILE_SIZE_BYTES}")
        print(f"  Protected unused >= exclude: {len(protected_unused)}")
        print(f"  Blanked tile numbers     : {format_preview(cleared)}")

        if dry_run:
            print("  Dry run only             : no files written")
            return

        chr_backup = write_backup_and_file(
            tiles_path,
            b"".join(bytes(tile) for tile in tiles),
            dry_run=False
        )
        print(f"  CHR backup               : {chr_backup}")
        print(f"  CHR updated              : {blanked_bytes} bytes zeroed")
        print("  Maps updated             : none")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Mode7 CHR cleaner for .m7e projects. Default mode blanks unused tiles "
            "below the exclude threshold without touching maps. Use --compress to "
            "compact tiles below the threshold and rewrite only map entries below "
            "that threshold. Tiles and map references >= exclude are never changed. "
            "Use --tail-only to affect only the trailing unused tail immediately "
            "below the exclude threshold."
        )
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input .m7e file(s), wildcard(s), or folder(s)"
    )
    parser.add_argument(
        "exclude",
        type=int,
        help="Do not alter any tile or map reference greater than or equal to this value"
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Recurse into subfolders when input is a folder"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would happen without writing files"
    )
    parser.add_argument(
        "--compress",
        action="store_true",
        help=(
            "Compact tiles below the exclude threshold and rewrite only map entries "
            "below that threshold. Tiles/references >= exclude stay unchanged."
        )
    )
    parser.add_argument(
        "--tail-only",
        action="store_true",
        help=(
            "Only affect the trailing unused run immediately below the exclude value. "
            "Example: with exclude 192, only tiles 191 downward until the first used "
            "tile is reached."
        )
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
                args.exclude,
                compress=args.compress,
                dry_run=args.dry_run,
                tail_only=args.tail_only
            )
        except Exception as e:
            failures += 1
            print(f"\nFAIL: {project} -> {e}")

    print(f"\nDone. Processed {len(projects)} project(s), failures: {failures}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
