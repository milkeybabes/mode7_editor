import sys
import os
import argparse
import textwrap

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QScrollArea, QSizePolicy, QSlider
)
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor
from PySide6.QtCore import Qt

TILE_SIZE = 8
EDITOR_PIXEL_SIZE = 16
PALETTE_CELL_SIZE = EDITOR_PIXEL_SIZE
PALETTE_COLUMNS = 16


def snes5_to_8(v):
    return (v << 3) | (v >> 2)

def rgb8_to_snes5(v):
    return max(0, min(31, v >> 3))

def load_palette_snes(path):
    data = open(path, "rb").read()
    if len(data) != 512:
        raise ValueError(f"{path} must be 512 bytes for a 256-colour SNES palette, got {len(data)}")

    palette = []
    for i in range(0, len(data), 2):
        word = data[i] | (data[i + 1] << 8)

        r5 = word & 0x1F
        g5 = (word >> 5) & 0x1F
        b5 = (word >> 10) & 0x1F

        palette.append((
            snes5_to_8(r5),
            snes5_to_8(g5),
            snes5_to_8(b5)
        ))

    return palette

def save_palette(self):
    save_palette_snes(self.palette_path, self.palette)
    self.modified_pal = False
    self.update_status()

def save_map(self):
    with open(self.map_path, "wb") as f:
        f.write(self.map_data)
    self.modified_map = False
    self.update_status()

def save_chr(self):
    save_tiles(self.tiles_path, self.tiles)
    self.modified_chr = False
    self.update_status()
    
def save_palette_snes(path, palette):
    out = bytearray()

    for r8, g8, b8 in palette:
        r5 = rgb8_to_snes5(r8)
        g5 = rgb8_to_snes5(g8)
        b5 = rgb8_to_snes5(b8)

        word = (b5 << 10) | (g5 << 5) | r5
        out.append(word & 0xFF)
        out.append((word >> 8) & 0xFF)

    with open(path, "wb") as f:
        f.write(out)

def load_tiles(path):
    data = open(path, "rb").read()
    return [bytearray(data[i:i + 64]) for i in range(0, len(data), 64)]

def save_tiles(path, tiles):
    out = bytearray()
    for tile in tiles:
        out.extend(tile)
    with open(path, "wb") as f:
        f.write(out)

def load_map(path):
    return bytearray(open(path, "rb").read())

def load_project(name):
    filename = f"{name}.m7e"

    data = {}
    with open(filename, "r") as f:
        for line in f:
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()

    return data

def create_project(name, width=128, height=128):
    with open(f"{name}.m7e", "w") as f:
        f.write(f"palette={name}.pal\n")
        f.write(f"tiles={name}.chr\n")
        f.write(f"maps={name}_1.map\n")
        f.write(f"width={width}\n")
        f.write(f"height={height}\n")

    # palette (512 bytes)
    save_default_palette(f"{name}.pal")

    # tiles (start with 256 tiles)
    chr_data = bytearray()
    for tile_num in range(256):
        chr_data.extend([tile_num] * 64)

    with open(f"{name}.chr", "wb") as f:
        f.write(chr_data)

    # first map
    with open(f"{name}_1.map", "wb") as f:
        f.write(bytearray(width * height))

def rgb5_to_snes_word(r5, g5, b5):
    return (b5 << 10) | (g5 << 5) | r5


def save_default_palette(path):
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
    for r5, g5, b5 in ramps[:256]:
        word = rgb5_to_snes_word(r5, g5, b5)
        out.append(word & 0xFF)
        out.append((word >> 8) & 0xFF)

    with open(path, "wb") as f:
        f.write(out) 

def render_tile(tile, palette):
    img = QImage(8, 8, QImage.Format_RGB32)
    for y in range(8):
        for x in range(8):
            c = tile[y * 8 + x]
            r, g, b = palette[c]
            img.setPixel(x, y, (r << 16) | (g << 8) | b)
    return img

def flip_tile_x(tile):
    out = bytearray(64)
    for y in range(8):
        for x in range(8):
            out[y * 8 + x] = tile[y * 8 + (7 - x)]
    return out

def flip_tile_y(tile):
    out = bytearray(64)
    for y in range(8):
        for x in range(8):
            out[y * 8 + x] = tile[(7 - y) * 8 + x]
    return out

def rotate_tile_cw(tile):
    out = bytearray(64)
    for y in range(8):
        for x in range(8):
            out[y * 8 + x] = tile[(7 - x) * 8 + y]
    return out

def rotate_tile_ccw(tile):
    out = bytearray(64)
    for y in range(8):
        for x in range(8):
            out[y * 8 + x] = tile[x * 8 + (7 - y)]
    return out

class TileViewer(QLabel):
    def __init__(self, tiles, palette, parent):
        super().__init__()
        self.tiles = tiles
        self.palette = palette
        self.parent = parent
        self.tiles_per_row = 16
        self.tile_scale = 2
        self.build()

    def build(self):
        rows = (len(self.tiles) + self.tiles_per_row - 1) // self.tiles_per_row
        w = self.tiles_per_row * TILE_SIZE
        h = rows * TILE_SIZE

        img = QImage(w, h, QImage.Format_RGB32)
        painter = QPainter(img)

        for i, tile in enumerate(self.tiles):
            x = (i % self.tiles_per_row) * TILE_SIZE
            y = (i // self.tiles_per_row) * TILE_SIZE
            painter.drawImage(x, y, render_tile(tile, self.palette))

        sel = self.parent.selected_tile
        sx = (sel % self.tiles_per_row) * TILE_SIZE
        sy = (sel // self.tiles_per_row) * TILE_SIZE
        painter.setPen(QPen(Qt.red, 1))
        painter.drawRect(sx, sy, TILE_SIZE - 1, TILE_SIZE - 1)

        painter.end()

        pix = QPixmap.fromImage(img).scaled(
            img.width() * self.tile_scale,
            img.height() * self.tile_scale,
            Qt.KeepAspectRatio,
            Qt.FastTransformation
        )
        self.setPixmap(pix)
        self.adjustSize()

    def mousePressEvent(self, event):
        x = int(event.position().x()) // self.tile_scale
        y = int(event.position().y()) // self.tile_scale

        tx = x // TILE_SIZE
        ty = y // TILE_SIZE

        index = ty * self.tiles_per_row + tx
        if 0 <= index < len(self.tiles):
            self.parent.selected_tile = index
            self.parent.update_status()
            self.build()
            self.parent.tile_editor.build()
            self.parent.palette_controls.refresh_from_selected_colour()

class PaletteView(QLabel):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.cell_size = PALETTE_CELL_SIZE
        self.cols = PALETTE_COLUMNS
        self.build()

    def build(self):
        palette = self.parent.palette
        rows = (len(palette) + self.cols - 1) // self.cols

        w = self.cols * self.cell_size
        h = rows * self.cell_size

        img = QImage(w, h, QImage.Format_RGB32)
        painter = QPainter(img)

        for i, (r, g, b) in enumerate(palette):
            x = (i % self.cols) * self.cell_size
            y = (i // self.cols) * self.cell_size
            painter.fillRect(x, y, self.cell_size, self.cell_size, QColor(r, g, b))

        painter.setPen(QPen(Qt.gray, 1))
        for i in range(self.cols + 1):
            painter.drawLine(i * self.cell_size, 0, i * self.cell_size, h)
        for i in range(rows + 1):
            painter.drawLine(0, i * self.cell_size, w, i * self.cell_size)

        sel = self.parent.selected_color
        sx = (sel % self.cols) * self.cell_size
        sy = (sel // self.cols) * self.cell_size
        painter.setPen(QPen(Qt.red, 2))
        painter.drawRect(sx, sy, self.cell_size - 1, self.cell_size - 1)

        painter.end()

        self.setPixmap(QPixmap.fromImage(img))
        self.adjustSize()

    def mousePressEvent(self, event):
        x = int(event.position().x()) // self.cell_size
        y = int(event.position().y()) // self.cell_size

        if x < 0 or x >= self.cols:
            return

        idx = y * self.cols + x

        if 0 <= idx < len(self.parent.palette):
            self.parent.selected_color = idx
            self.parent.update_status()
            self.build()
            self.parent.palette_controls.refresh_from_selected_colour()

class PaletteControls(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.updating = False

        self.setFixedWidth(260)

        self.preview = QLabel()
        self.preview.setFixedSize(48, 48)

        self.r_label = QLabel("R: 0")
        self.g_label = QLabel("G: 0")
        self.b_label = QLabel("B: 0")

        self.r_slider = QSlider(Qt.Horizontal)
        self.g_slider = QSlider(Qt.Horizontal)
        self.b_slider = QSlider(Qt.Horizontal)

        for slider in (self.r_slider, self.g_slider, self.b_slider):
            slider.setRange(0, 255)
            slider.setFixedWidth(170)

        self.r_slider.valueChanged.connect(self.slider_changed)
        self.g_slider.valueChanged.connect(self.slider_changed)
        self.b_slider.valueChanged.connect(self.slider_changed)

        sliders_layout = QVBoxLayout()
        sliders_layout.setAlignment(Qt.AlignTop)
        sliders_layout.setSpacing(4)
        sliders_layout.addWidget(self.r_label)
        sliders_layout.addWidget(self.r_slider)
        sliders_layout.addWidget(self.g_label)
        sliders_layout.addWidget(self.g_slider)
        sliders_layout.addWidget(self.b_label)
        sliders_layout.addWidget(self.b_slider)

        main_layout = QHBoxLayout()
        main_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        main_layout.setSpacing(10)
        main_layout.addWidget(self.preview)
        main_layout.addLayout(sliders_layout)
        self.setLayout(main_layout)

        self.refresh_from_selected_colour()

    def quantise_rgb(self, r8, g8, b8):
        r5 = rgb8_to_snes5(r8)
        g5 = rgb8_to_snes5(g8)
        b5 = rgb8_to_snes5(b8)
        return (
            snes5_to_8(r5),
            snes5_to_8(g5),
            snes5_to_8(b5)
        )

    def set_preview(self, r, g, b):
        img = QImage(48, 48, QImage.Format_RGB32)
        img.fill((r << 16) | (g << 8) | b)
        self.preview.setPixmap(QPixmap.fromImage(img))

    def refresh_from_selected_colour(self):
        self.updating = True

        r, g, b = self.parent.palette[self.parent.selected_color]

        self.r_slider.setValue(r)
        self.g_slider.setValue(g)
        self.b_slider.setValue(b)

        self.r_label.setText(f"R: {r}")
        self.g_label.setText(f"G: {g}")
        self.b_label.setText(f"B: {b}")

        self.set_preview(r, g, b)

        self.updating = False

    def slider_changed(self):
        if self.updating:
            return

        r = self.r_slider.value()
        g = self.g_slider.value()
        b = self.b_slider.value()

        r, g, b = self.quantise_rgb(r, g, b)

        self.updating = True
        self.r_slider.setValue(r)
        self.g_slider.setValue(g)
        self.b_slider.setValue(b)
        self.updating = False

        self.parent.palette[self.parent.selected_color] = (r, g, b)
        self.parent.modified_pal = True

        self.r_label.setText(f"R: {r}")
        self.g_label.setText(f"G: {g}")
        self.b_label.setText(f"B: {b}")
        self.set_preview(r, g, b)

        self.parent.palette_view.build()
        self.parent.tile_editor.build()
        self.parent.tile_view.build()
        self.parent.map_view.redraw()
        self.parent.update_status()

class TileOps(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent

        self.setFixedWidth(160)

        self.flip_x_btn = QPushButton("Flip X")
        self.flip_y_btn = QPushButton("Flip Y")
        self.clear_btn = QPushButton("Clear")
        self.invert_btn = QPushButton("Invert")
        self.copy_btn = QPushButton("Copy")
        self.paste_btn = QPushButton("Paste")
        self.rotate_cw_btn = QPushButton("Rot.CW")
        self.rotate_ccw_btn = QPushButton("Rot.CCW")

        buttons = [
            self.flip_x_btn, self.flip_y_btn,
            self.clear_btn, self.invert_btn,
            self.copy_btn, self.paste_btn,
            self.rotate_cw_btn, self.rotate_ccw_btn
        ]

        for b in buttons:
            b.setFixedSize(60, 20)

        self.flip_x_btn.clicked.connect(self.flip_x)
        self.flip_y_btn.clicked.connect(self.flip_y)
        self.clear_btn.clicked.connect(self.clear_tile)
        self.invert_btn.clicked.connect(self.invert_tile)
        self.copy_btn.clicked.connect(self.copy_tile)
        self.paste_btn.clicked.connect(self.paste_tile)
        self.rotate_cw_btn.clicked.connect(self.rotate_cw)
        self.rotate_ccw_btn.clicked.connect(self.rotate_ccw)

        col1 = QVBoxLayout()
        col1.setSpacing(5)
        col1.addWidget(self.flip_x_btn)
        col1.addWidget(self.clear_btn)
        col1.addWidget(self.copy_btn)
        col1.addWidget(self.rotate_cw_btn)

        col2 = QVBoxLayout()
        col2.setSpacing(5)
        col2.addWidget(self.flip_y_btn)
        col2.addWidget(self.invert_btn)
        col2.addWidget(self.paste_btn)
        col2.addWidget(self.rotate_ccw_btn)

        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.setSpacing(6)
        layout.addLayout(col1)
        layout.addLayout(col2)

        self.setLayout(layout)

    def current_tile(self):
        return self.parent.tiles[self.parent.selected_tile]

    def replace_current_tile(self, new_tile):
        self.parent.tiles[self.parent.selected_tile] = bytearray(new_tile)
        self.parent.modified_chr = True
        self.parent.tile_editor.build()
        self.parent.tile_view.build()
        self.parent.map_view.redraw()
        self.parent.update_status()

    def flip_x(self):
        self.replace_current_tile(flip_tile_x(self.current_tile()))

    def flip_y(self):
        self.replace_current_tile(flip_tile_y(self.current_tile()))

    def rotate_cw(self):
        self.replace_current_tile(rotate_tile_cw(self.current_tile()))

    def rotate_ccw(self):
        self.replace_current_tile(rotate_tile_ccw(self.current_tile()))

    def clear_tile(self):
        self.replace_current_tile(bytearray([0] * 64))

    def invert_tile(self):
        tile = self.current_tile()
        max_index = len(self.parent.palette) - 1
        new_tile = bytearray(64)
        for i in range(64):
            new_tile[i] = max_index - tile[i]
        self.replace_current_tile(new_tile)

    def copy_tile(self):
        self.parent.copied_tile = bytearray(self.current_tile())

    def paste_tile(self):
        if self.parent.copied_tile is not None:
            self.replace_current_tile(bytearray(self.parent.copied_tile))

class MapView(QLabel):
    ZOOM_LEVELS = [0.125, 0.25, 0.5, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0]

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.scale = 1.0
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.base_pixmap = None

        self.panning = False
        self.pan_start = None
        self.h_scroll_start = 0
        self.v_scroll_start = 0

        self.redraw()

    def can_edit_map(self):
        return self.scale >= 1.0

    def zoom_text(self):
        if self.scale >= 1.0:
            if float(self.scale).is_integer():
                return f"{int(self.scale)}:1"
            return f"{self.scale:g}:1"

        inv = 1.0 / self.scale
        if float(inv).is_integer():
            return f"1:{int(inv)}"
        return f"1:{inv:g}"

    def current_zoom_index(self):
        try:
            return self.ZOOM_LEVELS.index(self.scale)
        except ValueError:
            return min(range(len(self.ZOOM_LEVELS)), key=lambda i: abs(self.ZOOM_LEVELS[i] - self.scale))

    def set_scale(self, scale):
        self.scale = scale
        self.apply_zoom()
        self.parent.update_status()

    def redraw(self):
        p = self.parent
        w = p.map_width
        h = p.map_height

        img = QImage(w * 8, h * 8, QImage.Format_RGB32)
        painter = QPainter(img)

        for my in range(h):
            for mx in range(w):
                tile_index = p.map_data[my * w + mx]
                if tile_index >= len(p.tiles):
                    tile_index = 0
                tile = p.tiles[tile_index]
                painter.drawImage(mx * 8, my * 8, render_tile(tile, p.palette))

        painter.end()

        self.base_pixmap = QPixmap.fromImage(img)
        self.apply_zoom()

    def apply_zoom(self):
        if self.base_pixmap is None:
            return

        scaled_w = max(1, int(round(self.base_pixmap.width() * self.scale)))
        scaled_h = max(1, int(round(self.base_pixmap.height() * self.scale)))

        scaled = self.base_pixmap.scaled(
            scaled_w,
            scaled_h,
            Qt.KeepAspectRatio,
            Qt.FastTransformation
        )
        self.setPixmap(scaled)
        self.adjustSize()

    def zoom_in(self):
        idx = self.current_zoom_index()
        if idx < len(self.ZOOM_LEVELS) - 1:
            self.set_scale(self.ZOOM_LEVELS[idx + 1])

    def zoom_out(self):
        idx = self.current_zoom_index()
        if idx > 0:
            self.set_scale(self.ZOOM_LEVELS[idx - 1])

    def fit_to_window(self):
        if self.base_pixmap is None:
            return

        scroll = self.parent.map_scroll.viewport().size()
        if scroll.width() <= 0 or scroll.height() <= 0:
            return

        scale_x = scroll.width() / self.base_pixmap.width()
        scale_y = scroll.height() / self.base_pixmap.height()
        best = min(scale_x, scale_y)

        candidates = [z for z in self.ZOOM_LEVELS if z <= best]
        if candidates:
            self.set_scale(candidates[-1])
        else:
            self.set_scale(self.ZOOM_LEVELS[0])

    def map_pos_from_event(self, event):
        x = int(event.position().x() / self.scale)
        y = int(event.position().y() / self.scale)
        tx = x // 8
        ty = y // 8
        return tx, ty

    def mousePressEvent(self, event):
        p = self.parent

        if event.button() == Qt.MiddleButton:
            self.panning = True
            self.pan_start = event.globalPosition().toPoint()
            self.h_scroll_start = p.map_scroll.horizontalScrollBar().value()
            self.v_scroll_start = p.map_scroll.verticalScrollBar().value()
            self.setCursor(Qt.ClosedHandCursor)
            return

        tx, ty = self.map_pos_from_event(event)

        if tx < 0 or ty < 0 or tx >= p.map_width or ty >= p.map_height:
            return

        idx = ty * p.map_width + tx

        if event.button() == Qt.LeftButton:
            if not self.can_edit_map():
                p.update_status()
                return

            if p.map_data[idx] != p.selected_tile:
                p.push_map_undo(idx)
                p.map_data[idx] = p.selected_tile
                p.modified_map = True
                self.redraw()
                p.update_status()

        elif event.button() == Qt.RightButton:
            p.selected_tile = p.map_data[idx]
            p.update_status()
            p.tile_view.build()
            p.tile_editor.build()
            p.palette_controls.refresh_from_selected_colour()

    def mouseMoveEvent(self, event):
        p = self.parent

        if self.panning:
            current = event.globalPosition().toPoint()
            delta = current - self.pan_start

            p.map_scroll.horizontalScrollBar().setValue(self.h_scroll_start - delta.x())
            p.map_scroll.verticalScrollBar().setValue(self.v_scroll_start - delta.y())
            return

        tx, ty = self.map_pos_from_event(event)

        if 0 <= tx < p.map_width and 0 <= ty < p.map_height:
            p.hover_x = tx
            p.hover_y = ty
            p.update_status()
        else:
            p.hover_x = -1
            p.hover_y = -1
            p.update_status()

        if not self.can_edit_map():
            return

        if event.buttons() & Qt.LeftButton:
            if tx < 0 or ty < 0 or tx >= p.map_width or ty >= p.map_height:
                return

            idx = ty * p.map_width + tx
            if p.map_data[idx] != p.selected_tile:
                p.push_map_undo(idx)
                p.map_data[idx] = p.selected_tile
                p.modified_map = True
                self.redraw()
                p.update_status()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self.panning:
            self.panning = False
            self.setCursor(Qt.ArrowCursor)
            return

    def wheelEvent(self, event):
        if self.base_pixmap is None:
            event.accept()
            return

        old_scale = self.scale
        old_idx = self.current_zoom_index()
        delta = event.angleDelta().y()

        if delta > 0 and old_idx < len(self.ZOOM_LEVELS) - 1:
            new_scale = self.ZOOM_LEVELS[old_idx + 1]
        elif delta < 0 and old_idx > 0:
            new_scale = self.ZOOM_LEVELS[old_idx - 1]
        else:
            event.accept()
            return

        mouse_pos = event.position()
        image_x = mouse_pos.x() / old_scale
        image_y = mouse_pos.y() / old_scale

        self.scale = new_scale
        self.apply_zoom()

        new_h = int(image_x * self.scale - mouse_pos.x())
        new_v = int(image_y * self.scale - mouse_pos.y())

        hbar = self.parent.map_scroll.horizontalScrollBar()
        vbar = self.parent.map_scroll.verticalScrollBar()

        hbar.setValue(new_h)
        vbar.setValue(new_v)

        self.parent.update_status()
        event.accept()

class Editor(QWidget):
    def __init__(self, tiles_path, palette_path, map_paths, width, height):        
        super().__init__()

        self.map_width = width
        self.map_height = height

        self.tiles_path = tiles_path
        self.palette_path = palette_path
 
        self.tiles = load_tiles(self.tiles_path)
        self.palette = load_palette_snes(self.palette_path)
 
        self.map_paths = map_paths
        self.map_index = 0

        self.map_data_list = [load_map(p) for p in self.map_paths]
        self.map_data = self.map_data_list[self.map_index]
        self.map_path = self.map_paths[self.map_index]

        prev_map_btn = QPushButton("<")
        prev_map_btn.setFixedWidth(30)
        prev_map_btn.clicked.connect(self.prev_map)

        next_map_btn = QPushButton(">")
        next_map_btn.setFixedWidth(30)
        next_map_btn.clicked.connect(self.next_map)

        self.map_label = QLabel("Map 1/1")

        expected = self.map_width * self.map_height
        if len(self.map_data) != expected:
            raise ValueError(f"mode7.map is {len(self.map_data)} bytes, expected {expected}")

        self.undo_tile = None
        self.undo_tile_index = None   
        self.undo_map_index = None
        self.undo_map_value = None        

        self.selected_tile = 0
        self.selected_color = 0
        self.copied_tile = None

        self.modified_map = False
        self.modified_chr = False
        self.modified_pal = False

        self.hover_x = -1
        self.hover_y = -1

        self.status = QLabel()
        self.status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.tile_view = TileViewer(self.tiles, self.palette, self)
        self.tile_editor = TileEditor(self)
        self.tile_ops = TileOps(self)
        self.palette_view = PaletteView(self)
        self.palette_controls = PaletteControls(self)
        self.map_view = MapView(self)

        self.map_scroll = QScrollArea()
        self.map_scroll.setWidget(self.map_view)
        self.map_scroll.setWidgetResizable(False)

        self.tile_scroll = QScrollArea()
        self.tile_scroll.setWidget(self.tile_view)
        self.tile_scroll.setWidgetResizable(False)
        tile_panel_width = (16 * TILE_SIZE * self.tile_view.tile_scale) + 4
        self.tile_scroll.setFixedWidth(tile_panel_width)

        load_proj_btn = QPushButton("Load All")
        load_proj_btn.clicked.connect(self.load_project_dialog)

        save_proj_btn = QPushButton("Save All")
        save_proj_btn.clicked.connect(self.save_project)

        save_map_btn = QPushButton("Save Map")
        save_map_btn.clicked.connect(self.save_map)

        save_chr_btn = QPushButton("Save Chr")
        save_chr_btn.clicked.connect(self.save_chr)

        save_pal_btn = QPushButton("Save Palette")
        save_pal_btn.clicked.connect(self.save_palette)

        zoom_in_btn = QPushButton("Zoom +")
        zoom_in_btn.clicked.connect(self.map_view.zoom_in)

        zoom_out_btn = QPushButton("Zoom -")
        zoom_out_btn.clicked.connect(self.map_view.zoom_out)

        fit_btn = QPushButton("Fit")
        fit_btn.clicked.connect(self.map_view.fit_to_window)

        left_layout = QVBoxLayout()
        left_layout.addWidget(self.tile_scroll)

        tile_row = QHBoxLayout()
        
        tile_row.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        tile_row.addWidget(self.tile_editor)
        tile_row.addWidget(self.tile_ops)
        left_layout.addLayout(tile_row)

        left_layout.addWidget(self.palette_view)
        left_layout.addWidget(self.palette_controls)
        left_layout.addStretch()

        right_layout = QVBoxLayout()
        right_layout.addWidget(self.map_scroll)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(16)  # reduce gap between panels
        top_layout.setContentsMargins(2, 2, 2, 2)

        top_layout.addLayout(left_layout)
        top_layout.addLayout(right_layout, 1)  # map takes remaining space

        controls = QHBoxLayout()
        controls.addWidget(load_proj_btn)
        controls.addWidget(save_proj_btn)
        controls.addWidget(save_map_btn)
        controls.addWidget(save_chr_btn)
        controls.addWidget(save_pal_btn)
        controls.addWidget(zoom_out_btn)
        controls.addWidget(zoom_in_btn)
        controls.addWidget(fit_btn)
        controls.addWidget(self.status)
        controls.addWidget(prev_map_btn)
        controls.addWidget(self.map_label)
        controls.addWidget(next_map_btn)

        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addLayout(controls)

        self.setLayout(main_layout)
        self.setWindowTitle("Mode7 Editor (Stage 1)")
        self.resize(1400, 900)
        self.showMaximized()
        self.setFocusPolicy(Qt.StrongFocus)
        self.update_status()

    def update_status(self):
        hover_text = ""
        if self.hover_x >= 0 and self.hover_y >= 0:
            idx = self.hover_y * self.map_width + self.hover_x
            hover_tile = self.map_data[idx]
            hover_text = f"   Hover: ({self.hover_x},{self.hover_y}) tile {hover_tile}"

        zoom = self.map_view.zoom_text() if hasattr(self, "map_view") else "1:1"
        edit_mode = "   View only" if hasattr(self, "map_view") and not self.map_view.can_edit_map() else ""

        mods = []
        if self.modified_map:
            mods.append("map")
        if self.modified_chr:
            mods.append("chr")
        if self.modified_pal:
            mods.append("pal")
        mod_text = ""
        if mods:
            mod_text = "   *modified: " + ",".join(mods) + "*"

        self.status.setText(
            f"Selected tile: {self.selected_tile}   Colour: {self.selected_color}   Zoom: {zoom}{edit_mode}{hover_text}{mod_text}"
        )
        self.update_window_title()
        total = len(self.map_paths)
        current = self.map_index + 1
        self.map_label.setText(f"Map {current}/{total}")
    
    def save_map(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Map", "mode7.map")
        if path:
            with open(path, "wb") as f:
                f.write(self.map_data)
            self.modified_map = False
            self.update_status()

    def save_chr(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Chr", "chars.chr")
        if path:
            save_tiles(path, self.tiles)
            self.modified_chr = False
            self.update_status()

    def save_palette(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Palette", "palette.pal")
        if path:
            save_palette_snes(path, self.palette)
            self.modified_pal = False
            self.update_status()
            
    def load_project_dialog(self):
    
        path, _ = QFileDialog.getOpenFileName(self, "Load Project", "", "*.m7e")
        if not path:
            return

        proj = {}
        with open(path, "r") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    proj[k.strip()] = v.strip()

        # reload data
        self.tiles_path = proj["tiles"]
        self.palette_path = proj["palette"]

        if "maps" in proj:
            self.map_paths = [p.strip() for p in proj["maps"].split(",") if p.strip()]
        elif "map" in proj:
            self.map_paths = [proj["map"].strip()]
        else:
            raise ValueError("Project must define 'map' or 'maps'")

        self.map_width = int(proj.get("width", 128))
        self.map_height = int(proj.get("height", 128))

        self.tiles = load_tiles(self.tiles_path)
        self.palette = load_palette_snes(self.palette_path)
        self.map_data_list = [load_map(p) for p in self.map_paths]
        self.map_index = 0
        self.map_data = self.map_data_list[self.map_index]
        self.map_path = self.map_paths[self.map_index]

        expected = self.map_width * self.map_height
        for map_file, map_data in zip(self.map_paths, self.map_data_list):
            if len(map_data) != expected:
                raise ValueError(f"{map_file} is {len(map_data)} bytes, expected {expected}")

        # refresh everything
        self.tile_view.tiles = self.tiles
        self.tile_view.palette = self.palette
        self.palette_view.build()
        self.tile_view.build()
        self.tile_editor.build()
        self.map_view.redraw()

        self.modified_map = False
        self.modified_chr = False
        self.modified_pal = False
        self.hover_x = -1
        self.hover_y = -1

        self.update_status()

    def save_project(self):
        name, _ = QFileDialog.getSaveFileName(self, "Save All", "", "*.m7e")
        if not name:
            return

        if not name.endswith(".m7e"):
            name += ".m7e"

        # --- SAVE ALL DATA FIRST ---
        with open(self.map_path, "wb") as f:
            f.write(self.map_data)

        save_tiles(self.tiles_path, self.tiles)
        save_palette_snes(self.palette_path, self.palette)

        # --- SAVE PROJECT FILE ---
        with open(name, "w") as f:
            f.write(f"palette={self.palette_path}\n")
            f.write(f"tiles={self.tiles_path}\n")
            f.write(f"map={self.map_path}\n")
            f.write(f"width={self.map_width}\n")
            f.write(f"height={self.map_height}\n")

        # reset dirty flags
        self.modified_map = False
        self.modified_chr = False
        self.modified_pal = False

        self.update_status()

    def showEvent(self, event):
        super().showEvent(event)
        self.map_view.fit_to_window()

    def apply_shortcut(self, action):
        if action == "flip_x":
            self.tile_ops.flip_x()
        elif action == "flip_y":
            self.tile_ops.flip_y()
        elif action == "rotate_cw":
            self.tile_ops.rotate_cw()
        elif action == "rotate_ccw":
            self.tile_ops.rotate_ccw()
        elif action == "clear":
            self.tile_ops.clear_tile()
        elif action == "invert":
            self.tile_ops.invert_tile()
        elif action == "copy":
            self.tile_ops.copy_tile()
        elif action == "paste":
            self.tile_ops.paste_tile()

    def keyPressEvent(self, event):
        
        key = event.key()
        mods = event.modifiers()

        if key == Qt.Key_Z and mods == Qt.ControlModifier:
            self.undo()
            event.accept()
            return

        if key == Qt.Key_X and mods == Qt.NoModifier:
            self.apply_shortcut("flip_x")
            event.accept()
            return

        if key == Qt.Key_Y and mods == Qt.NoModifier:
            self.apply_shortcut("flip_y")
            event.accept()
            return

        if key == Qt.Key_R and mods == Qt.NoModifier:
            self.apply_shortcut("rotate_cw")
            event.accept()
            return

        if key == Qt.Key_R and mods == Qt.ShiftModifier:
            self.apply_shortcut("rotate_ccw")
            event.accept()
            return

        if key == Qt.Key_Delete and mods == Qt.NoModifier:
            self.apply_shortcut("clear")
            event.accept()
            return

        if key == Qt.Key_I and mods == Qt.NoModifier:
            self.apply_shortcut("invert")
            event.accept()
            return

        if key == Qt.Key_C and mods == Qt.NoModifier:
            self.apply_shortcut("copy")
            event.accept()
            return

        if key == Qt.Key_V and mods == Qt.NoModifier:
            self.apply_shortcut("paste")
            event.accept()
            return
            
        if key == Qt.Key_U and mods == Qt.NoModifier:
            self.undo_map()
            event.accept()
            return

        super().keyPressEvent(event)

    def push_undo(self):
        self.undo_tile_index = self.selected_tile
        self.undo_tile = bytearray(self.tiles[self.selected_tile])    

    def undo(self):
        if self.undo_tile is not None and self.undo_tile_index is not None:
            self.tiles[self.undo_tile_index] = bytearray(self.undo_tile)
            self.selected_tile = self.undo_tile_index
            self.modified_chr = True
            self.tile_editor.build()
            self.tile_view.build()
            self.map_view.redraw()
            self.palette_controls.refresh_from_selected_colour()
            self.update_status()

    def push_map_undo(self, map_index):
        self.undo_map_index = map_index
        self.undo_map_value = self.map_data[map_index]

    def undo_map(self):
        if self.undo_map_index is not None and self.undo_map_value is not None:
            self.map_data[self.undo_map_index] = self.undo_map_value
            self.modified_map = True
            self.map_view.redraw()
            self.update_status()        
    
    def update_window_title(self):
        name = "Mode7 Editor"

        if hasattr(self, "map_path"):
            base = os.path.splitext(os.path.basename(self.tiles_path))[0]            
            name += f" - {base}"

        if self.modified_map or self.modified_chr or self.modified_pal:
            name += " *"

        self.setWindowTitle(name)
 
    def closeEvent(self, event):
        if self.modified_map or self.modified_chr or self.modified_pal:
            from PySide6.QtWidgets import QMessageBox

            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "Save all before exiting?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )

            if reply == QMessageBox.Yes:
                self.save_project()
                event.accept()
            elif reply == QMessageBox.No:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def update_current_map(self):
        self.map_data = self.map_data_list[self.map_index]
        self.map_path = self.map_paths[self.map_index]
        self.map_view.redraw()
        self.update_status()

    def prev_map(self):
        if self.map_index > 0:
            self.map_index -= 1
            self.update_current_map()

    def next_map(self):
        if self.map_index < len(self.map_paths) - 1:
            self.map_index += 1
            self.update_current_map()

class TileEditor(QLabel):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setMouseTracking(True)
        self.setFixedSize(8 * EDITOR_PIXEL_SIZE, 8 * EDITOR_PIXEL_SIZE)
        self.setCursor(Qt.ArrowCursor)
        self.build()

    def build(self):
        tile = self.parent.tiles[self.parent.selected_tile]
        palette = self.parent.palette

        img = QImage(
            8 * EDITOR_PIXEL_SIZE,
            8 * EDITOR_PIXEL_SIZE,
            QImage.Format_RGB32
        )
        painter = QPainter(img)

        for y in range(8):
            for x in range(8):
                c = tile[y * 8 + x]
                r, g, b = palette[c]
                painter.fillRect(
                    x * EDITOR_PIXEL_SIZE,
                    y * EDITOR_PIXEL_SIZE,
                    EDITOR_PIXEL_SIZE,
                    EDITOR_PIXEL_SIZE,
                    QColor(r, g, b)
                )

        painter.setPen(QPen(Qt.gray, 1))
        for i in range(9):
            painter.drawLine(i * EDITOR_PIXEL_SIZE, 0, i * EDITOR_PIXEL_SIZE, 8 * EDITOR_PIXEL_SIZE)
            painter.drawLine(0, i * EDITOR_PIXEL_SIZE, 8 * EDITOR_PIXEL_SIZE, i * EDITOR_PIXEL_SIZE)

        painter.end()

        self.setPixmap(QPixmap.fromImage(img))

    def pixel_from_event(self, event):
        x = int(event.position().x()) // EDITOR_PIXEL_SIZE
        y = int(event.position().y()) // EDITOR_PIXEL_SIZE
        return x, y

    def mousePressEvent(self, event):
        mods = event.modifiers() | QApplication.keyboardModifiers()

        x, y = self.pixel_from_event(event)
        if not (0 <= x < 8 and 0 <= y < 8):
            return

        tile = self.parent.tiles[self.parent.selected_tile]
        idx = y * 8 + x

        # ALT = pick colour
        if (mods & Qt.AltModifier) and event.button() == Qt.LeftButton:
            self.parent.selected_color = tile[idx]
            self.parent.update_status()
            self.parent.palette_view.build()
            self.parent.palette_controls.refresh_from_selected_colour()
            return

        if event.button() == Qt.LeftButton:
            self.parent.push_undo()
            tile[idx] = self.parent.selected_color
            self.parent.modified_chr = True
            self.build()
            self.parent.tile_view.build()
            self.parent.map_view.redraw()
            self.parent.update_status()

        elif event.button() == Qt.RightButton:
            self.parent.selected_color = tile[idx]
            self.parent.update_status()
            self.parent.palette_view.build()
            self.parent.palette_controls.refresh_from_selected_colour()
            
    def mouseMoveEvent(self, event):
        mods = QApplication.keyboardModifiers()

        # change cursor live
        if mods & Qt.AltModifier:
            self.setCursor(Qt.CrossCursor)
            return
        else:
            self.setCursor(Qt.ArrowCursor)

        if event.buttons() & Qt.LeftButton:
            self.mousePressEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)

    help_text = textwrap.dedent("""
        Mode7 Editor

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
    """)

    parser = argparse.ArgumentParser(
        description="SNES Mode 7 editor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=help_text
    )

    parser.add_argument(
        "project",
        nargs="?",
        help="Project name without .m7e extension"
    )
    parser.add_argument(
        "--palette",
        help="SNES palette file (.pal, 512 bytes)"
    )
    parser.add_argument(
        "--chr",
        dest="chr_file",
        help="Character file (.chr)"
    )
    parser.add_argument(
        "--map",
        dest="map_files",
        action="append",
        help="Map file (.map). Can be used multiple times for multi-map mode"
    )
    parser.add_argument(
        "--width",
        type=int,
        default=128,
        help="Map width (default: 128)"
    )
    parser.add_argument(
        "--height",
        type=int,
        default=128,
        help="Map height (default: 128)"
    )

    args = parser.parse_args()

    # --- PROJECT MODE ---
    if args.project:
        project_name = args.project

        if not os.path.exists(f"{project_name}.m7e"):
            print(f"Project '{project_name}' not found.")
            try:
                create = input("Create new project? (y/n): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nCancelled. Use --help for usage.")
                sys.exit(0)

            if create == "y":
                create_project(project_name, width=args.width, height=args.height)
            else:
                print("Project creation cancelled. Use --help for usage.")
                sys.exit(0)

        proj = load_project(project_name)

        if "maps" in proj:
            maps = [m.strip() for m in proj["maps"].split(",")]
        elif "map" in proj:
            maps = [proj["map"]]
        else:
            raise ValueError("Project must define 'map' or 'maps'")

        win = Editor(
            tiles_path=proj["tiles"],
            palette_path=proj["palette"],
            map_paths=maps,
            width=int(proj.get("width", args.width)),
            height=int(proj.get("height", args.height))
        )

    # --- DIRECT FILE MODE ---
    elif args.palette and args.chr_file and args.map_files:
        win = Editor(
            tiles_path=args.chr_file,
            palette_path=args.palette,
            map_paths=args.map_files,
            width=args.width,
            height=args.height
        )

    else:
        parser.print_help()
        sys.exit(0)

    win.show()
    sys.exit(app.exec())
    