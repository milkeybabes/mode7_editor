#!/usr/bin/env python3
"""
mode7_map_analyzer.py

Analyze SNES Mode 7 maps and character sets.

Features:
- Reports tile usage
- Finds unused tiles
- Optionally filters charset to only used tiles
- Optionally remaps the map to new tile indices
"""

import argparse
from collections import Counter
from pathlib import Path


def load_file(path):
    return Path(path).read_bytes()


def analyze_map(map_data):
    counts = Counter(map_data)
    unique = sorted(counts.keys())

    print("=== MAP ANALYSIS ===")
    print(f"Total tiles: {len(map_data)}")
    print(f"Unique tiles used: {len(unique)}")
    print(f"Min tile index: {min(unique):02X}")
    print(f"Max tile index: {max(unique):02X}")

    print("\nTop 16 most used tiles:")
    for val, count in counts.most_common(16):
        print(f"  {val:02X}: {count}")

    return counts, unique


def analyze_charset(char_data, tile_size):
    total_tiles = len(char_data) // tile_size
    print("\n=== CHARSET INFO ===")
    print(f"Total tiles in charset: {total_tiles}")
    print(f"Tile size: {tile_size} bytes")
    return total_tiles


def find_unused(total_tiles, used_tiles):
    unused = [i for i in range(total_tiles) if i not in used_tiles]

    print(f"\nUnused tiles: {len(unused)}")
    if unused:
        print(f"First 32 unused: {[f'{x:02X}' for x in unused[:32]]}")

    return unused

def analyze_ranges(used_tiles):
    print("\n=== TILE RANGE ANALYSIS ===")

    if not used_tiles:
        print("No tiles used!")
        return

    used = sorted(used_tiles)

    # --- Build used ranges ---
    ranges = []
    start = used[0]
    prev = used[0]

    for val in used[1:]:
        if val == prev + 1:
            prev = val
        else:
            ranges.append((start, prev))
            start = val
            prev = val
    ranges.append((start, prev))

    print("\nUsed ranges:")
    for a, b in ranges:
        print(f"  {a:02X}–{b:02X} ({b - a + 1})")

    # --- Find gaps ---
    gaps = []
    for i in range(len(ranges) - 1):
        gap_start = ranges[i][1] + 1
        gap_end = ranges[i + 1][0] - 1
        if gap_start <= gap_end:
            gaps.append((gap_start, gap_end))

    if gaps:
        print("\nGaps:")
        for a, b in gaps:
            print(f"  {a:02X}–{b:02X} ({b - a + 1})")

        # Largest gap
        largest = max(gaps, key=lambda g: g[1] - g[0])
        size = largest[1] - largest[0] + 1
        print(f"\nLargest gap: {largest[0]:02X}–{largest[1]:02X} ({size})")
    else:
        print("\nNo gaps found (fully packed)")
        
 
def filter_charset(char_data, tile_size, used_tiles):
    used_sorted = sorted(used_tiles)

    new_data = bytearray()
    remap = {}

    for new_index, old_index in enumerate(used_sorted):
        start = old_index * tile_size
        end = start + tile_size
        new_data.extend(char_data[start:end])
        remap[old_index] = new_index

    return new_data, remap


def remap_map(map_data, remap):
    return bytes(remap[val] for val in map_data)


def main():
    parser = argparse.ArgumentParser(description="Mode 7 Map Analyzer")
    parser.add_argument("map_file")
    parser.add_argument("--chars", help="Character file")
    parser.add_argument("--tile-size", type=lambda x: int(x, 0), default=64)
    parser.add_argument("--filter", action="store_true", help="Create filtered charset")
    parser.add_argument("--out-chars", default="filtered_chars.bin")
    parser.add_argument("--out-map", default="remapped_map.bin")

    args = parser.parse_args()

    map_data = load_file(args.map_file)
    counts, used_tiles = analyze_map(map_data)
    analyze_ranges(used_tiles)
    
    if args.chars:
        char_data = load_file(args.chars)
        total_tiles = analyze_charset(char_data, args.tile_size)

        unused = find_unused(total_tiles, used_tiles)

        print(f"\nUsage: {len(used_tiles)}/{total_tiles} "
              f"({(len(used_tiles)/total_tiles)*100:.2f}%)")

        if args.filter:
            print("\n=== FILTERING CHARSET ===")

            new_chars, remap = filter_charset(
                char_data, args.tile_size, used_tiles
            )

            new_map = remap_map(map_data, remap)

            Path(args.out_chars).write_bytes(new_chars)
            Path(args.out_map).write_bytes(new_map)

            print(f"Filtered charset written: {args.out_chars}")
            print(f"Remapped map written: {args.out_map}")
            print(f"New tile count: {len(new_chars)//args.tile_size}")


if __name__ == "__main__":
    main()