#!/usr/bin/env python3
"""
save_chunks.py

Extract variable-sized chunks from a binary file.

Chunk format:
  [4 bytes header][4 bytes size (big-endian)][payload...]
Total extracted length = size + 8 (includes header+size bytes)

Usage:
  python save_chunks.py input.bin base_name.bin [--chunk FORM]

Outputs:
  base_name_1.bin, base_name_2.bin, ...
"""

import argparse
import os
import sys


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract chunks from a binary file by 4-byte header + big-endian size.")
    p.add_argument("input", help="Input binary file (e.g., input.bin)")
    p.add_argument("base_name", help="Base output filename (e.g., output.bin -> output_1.bin etc.)")
    p.add_argument("--chunk", default="FORM", help='4-character chunk header to search for (default: "FORM")')
    return p.parse_args()


def split_base_filename(path: str):
    # Keep directory, split filename into stem/ext
    out_dir = os.path.dirname(path) or "."
    fname = os.path.basename(path)
    stem, ext = os.path.splitext(fname)
    if not ext:
        ext = ".bin"
    return out_dir, stem, ext


def read_u32_be(b: bytes) -> int:
    if len(b) != 4:
        raise ValueError("Need exactly 4 bytes for u32")
    return int.from_bytes(b, byteorder="big", signed=False)


def main() -> int:
    args = parse_args()

    if len(args.chunk) != 4:
        print(f'Error: --chunk must be exactly 4 characters (got "{args.chunk}")', file=sys.stderr)
        return 2

    header = args.chunk.encode("ascii", errors="strict")

    with open(args.input, "rb") as f:
        data = f.read()

    out_dir, stem, ext = split_base_filename(args.base_name)

    i = 0
    found = 0
    n = len(data)

    while True:
        pos = data.find(header, i)
        if pos == -1:
            break

        # Need at least header+size bytes present
        if pos + 8 > n:
            print(f"Warning: header found at 0x{pos:X} but not enough bytes for size field. Stopping.")
            break

        size = read_u32_be(data[pos + 4:pos + 8])
        total_len = size + 8

        end = pos + total_len
        if end > n:
            print(
                f"Warning: header at 0x{pos:X} claims size {size} (total {total_len}), "
                f"but file ends early (need 0x{end:X}, have 0x{n:X}). Stopping."
            )
            break

        found += 1
        out_path = os.path.join(out_dir, f"{stem}_{found}{ext}")
        with open(out_path, "wb") as out:
            out.write(data[pos:end])

        print(f"Wrote {out_path}  (offset=0x{pos:X}, size={size}, total={total_len})")

        # Skip past this chunk for the next search
        i = end

    if found == 0:
        print("No chunks found.")
        return 1

    print(f"Done. Extracted {found} chunk(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
