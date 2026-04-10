# 🎮 SNES Mode7 Toolchain (Python)

A modern Python-based toolchain for building, editing, analysing, and optimising SNES Mode7 assets.

Includes a full editor and supporting utilities for real-world asset workflows.

---

## 🚀 Features

- 🖼 Convert PNG → full Mode7 project
- 🧱 Tile deduplication (8×8)
- 🎨 Palette optimisation (safe group-based)
- 🧹 Tile cleanup tools
- 📦 Batch + recursive processing
- 🛠 Full Mode7 Editor included

---

## 🧰 Tools

---

## 🖥 1. mode7_editor.py (MAIN TOOL)

Interactive editor for Mode7 projects.

### ✔ Features
- View/edit maps
- Zoom support (in/out)
- Tile inspection
- Palette preview
- Safe editing at 1:1 zoom+

usage: mode7_editor.py [-h] [--palette PALETTE] [--chr CHR_FILE] [--map MAP_FILES] [--width WIDTH] [--height HEIGHT]
                       [project]

positional arguments:
  project            Project name without .m7e extension

options:
  -h, --help         show this help message and exit
  --palette PALETTE  SNES palette file (.pal, 512 bytes)
  --chr CHR_FILE     Character file (.chr)
  --map MAP_FILES    Map file (.map). Can be used multiple times for multi-map mode
  --width WIDTH      Map width (default: 128)
  --height HEIGHT    Map height (default: 128)

This tool edits SNES Mode 7 projects using:
  - one shared palette (.pal, SNES 512-byte format)
  - one shared character set (.chr)
  - one or more map files (.map)

PROJECT MODE
  python mode7_editor.py test_map

  Loads:
    test_map.m7e

DIRECT FILE MODE
  python mode7_editor.py --palette level.pal --chr level.chr --map level.map --width 128 --height 128

DIRECT MULTI-MAP MODE
  python mode7_editor.py --palette level.pal --chr level.chr --map map1.map --map map2.map --width 128 --height 128

.M7E FORMAT
  Example:
    palette=test_map.pal
    tiles=test_map.chr
    maps=test_map_1.map,test_map_2.map,test_map_3.map
    width=128
    height=128

  Older single-map projects are also supported:
    map=test_map.map

MOUSE CONTROLS
  Tile sheet:
    Left click   Select tile

  Tile editor:
    Left click   Paint pixel
    Right click  Pick colour from pixel
    Alt+Left     Pick colour (eyedropper)

  Map editor:
    Left click        Paint selected tile
    Right click       Pick tile from map
    Middle drag       Pan map
    Mouse wheel       Zoom in/out
    Left paint        Disabled below 1:1 zoom

SHORTCUT KEYS
  X           Flip X
  Y           Flip Y
  R           Rotate clockwise
  Shift+R     Rotate anticlockwise
  Delete      Clear tile
  I           Invert tile
  C           Copy tile
  V           Paste tile
  Ctrl+Z      Undo character edit
  U           Undo last map paint

SAVE BUTTONS
  Save Project   Save all current project files
  Save Map       Save current map only
  Save Chr       Save character data only
  Save Palette   Save palette only

NOTES
  - Palette editing uses 0-255 sliders in the UI
  - Values are quantised immediately to valid SNES 5-bit steps
  - Palette files are saved back in native SNES 16-bit format
### ✔ Examples

```bash
python mode7_editor.py project.m7e
```

```bash
python mode7_editor.py my_level.m7e
```

```bash
python mode7_editor.py test_project.m7e
```
Let's you create a project.m7e and will generate default blank assets 128x128 x,y and a Ramped colour palette.

---

## 🖼 2. png_to_mode7_project.py

Convert PNG → full Mode7 project. Project files are just text files with a .m7e extension
It just provides a simpler way to keep palette, characters, tile, and size details.

Usage:
python png_to_mode7_project.py image.png

Options:
--exact-colours     Fail if >256 colours
--dither            Enable dithering
--save-preview      Save indexed preview PNG
-o output_name      Set output filename

### ✔ Examples

```bash
python png_to_mode7_project.py image.png
```

```bash
python png_to_mode7_project.py image.png -o level1
```

```bash
python png_to_mode7_project.py image.png --dither --save-preview
```

---

## 🧱 3. mode7_chr_cleaner.py

Clean unused tiles safely.
It uses the same .m7e structure as your editor, including:

tiles=...
map=... or maps=...
width=...
height=...

What it does:
usage: mode7_chr_cleaner.py [-h] [-r] [--dry-run] [--compress] [--tail-only] inputs [inputs ...] exclude

Default mode:
- only edits the .chr
- blanks unused tiles below your exclude number
- never touches maps

With --compress:
- compacts only the tile range below your exclude number
- rewrites only map tile numbers below that exclude number
- leaves every tile and every map reference >= 192 completely unchanged

### ✔ Examples

```bash
python mode7_chr_cleaner.py project.m7e 192 --tail-only
```
So this would open the .chr file and remove/blank out any unused tiles up to tile number 192
```bash
python mode7_chr_cleaner.py project.m7e 192 --compress
```
preserve tile 192 and above exactly where they are
- only compress tiles 0..191
- only remap map entries 0..191
- back up the .chr
- back up any .map files it modifies

It also prints a clearer report, including:

- tile count
- used tiles total
- used below exclude
- used at/above exclude
- removed tile count
- old/new .chr size
- bytes saved
- number of map entries remapped
- count of map refs >= exclude kept unchanged
- preview list of removed tile numbers

```bash
python mode7_chr_cleaner.py *.m7e 192 --tail-only
```
- This is wildcard support for a whole folder load of projects, so you can go make a coffee.
- if tile 150 is the highest used tile below 192
- then the trailing tail is 151..191
- only that range is blanked or removed
- any unused holes like 37, 52, 88 stay alone
```bash
python mode7_chr_cleaner.py *.m7e 192 --dry-run
```
Test the process and report results only; no files are modified.

## 🎨 4. mode7_palette_reducer.py

What it does:

- reads the .m7e project
- loads the .chr file and checks which colour values 0–255 are actually used
- converts those into palette groups 0–15 by colour // 16
- keeps used groups unchanged
- replaces unused groups in the .pal file with either:
- the same dummy ramp palettes used by your editor, or all zeroes with --blank

This matches SNES 16 groups × 16 colours structure from the editor’s default palette generation.

Remove unused palette groups. For the SNES we keep to the idea that we have groups of palettes 16 colours each. We let this be the deciding factor for blank/unused ones
Example:
python mode7_palette_reducer.py project.m7e

Options:
--blank   Fill unused groups with zero, default will insert a ramp colour palette, you can then clearly see unused palettes

### ✔ Examples

```bash
python mode7_palette_reducer.py project.m7e
```

```bash
python mode7_palette_reducer.py project.m7e --blank
```
Fill unused groups with zero:
```bash
python mode7_palette_reducer.py *.m7e
```
It also:
- backs up the original .pal to .pal_backup
- prints a report showing:
- tile count
- used colours
- highest colour used
- used palette groups
- unused palette groups
- fill mode
- which groups were actually changed
---

## 📊 SNES Constraints

- Tiles: 256
- Colours: 256
- Palette Groups: 16 × 16
- Tile Size: 8×8

---
## 🔍 5. split_chunk.py (DEBUG / RE TOOL)

Split raw binary data into chunks for inspection.

Designed for:
- SNES VRAM dumps (e.g. from Mesen)
- Mode7 map/tile data exploration
- Reverse engineering workflows
- 
usage: split_chunk.py [-h] [--offset OFFSET] [--repeat REPEAT] input_file output_base size
```bash
python split_chunk.py Battle_Course1.dmp Battle 4000
```
Will output .chr .map from the input binary file; you can specify a size, which normally is 4000 16k chunks

## 🔧 Python Requirements

This project requires **Python 3.10 or newer**.

---

### 🔧 Required Libraries

The following libraries are required for core functionality:

- Pillow – image processing and PNG output  
- numpy – fast tile, map, and pixel data processing  

Install them using:

```bash
pip install pillow PySide6 numpy
```
Note: PySide6 is:
- fairly large
- sometimes slow to install
- may need Visual C++ runtime on Windows

Note: The editor requires PySide6 (Qt). This is a larger dependency but enables full GUI editing.

## 📜 License

Free to use. Credit appreciated, beer tokens accepted! 👍
