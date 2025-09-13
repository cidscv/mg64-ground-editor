import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter, QColor, QAction
from PySide6.QtWidgets import QApplication, QWidget, QMainWindow, QFileDialog, QHBoxLayout, QVBoxLayout, QPushButton, QButtonGroup, QSizePolicy, QLabel, QMessageBox

PALETTE_HEX = ["#A7CC75", "#446530", "#F2EFDB", "#936253", "#2F3E34", "#78FB4D", "#041810", "#75FF9C", "#533131", "#131AA5"]
PALLET_NAME = ["Fairway", "Rough", "Bunker", "Bare Ground", "Deep Rough", "Green", "OB", "Tee Ground", "Rock", "Cartway"]
GROUND_ID_TO_HEX = {
    0x00: "#A7CC75",  # Fairway
    0x01: "#446530",  # Rough
    0x02: "#F2EFDB",  # Bunker
    0x03: "#936253",  # Bare Ground
    0x04: "#131AA5",  # Cartway
    0x05: "#2F3E34",  # Deep Rough
    0x06: "#78FB4D",  # Green
    0x07: "#041810",  # Out of Bounds
    0x08: "#75FF9C",  # Tee Ground
    0x09: "#533131",  # Rock
}
CANVAS_W, CANVAS_H = 256, 512
DISPLAY_SCALE = 2

COLOR_TO_ID = {
    (QColor(h).red()<<16) | (QColor(h).green()<<8) | QColor(h).blue(): gid
    for gid, h in GROUND_ID_TO_HEX.items()
}

ERASE_FALLBACK_ID = 0x07

def _nearest_id_from_rgb(r: int, g: int, b: int) -> int:
    best_gid, best_d = None, 1e18
    for gid, hx in GROUND_ID_TO_HEX.items():
        qc = QColor(hx)
        dr, dg, db = r - qc.red(), g - qc.green(), b - qc.blue()
        d = dr*dr + dg*dg + db*db
        if d < best_d:
            best_d, best_gid = d, gid
    return best_gid

def nearest_palette_color(c: QColor) -> QColor:
    # Euclidean in RGB
    r, g, b, _ = c.getRgb()
    best = None
    bestd = 1e9
    for hx in PALETTE_HEX:
        pc = QColor(hx)
        dr = r - pc.red(); dg = g - pc.green(); db = b - pc.blue()
        d = dr*dr + dg*dg + db*db
        if d < bestd: bestd, best = d, pc
    return best

class Canvas(QWidget):
    def __init__(self):
        # set up 256x512 px canvas to work in. default canvas colour is OB (#041810). default current colour is fairway (#A7CC75)
        super().__init__()
        self.image = QImage(CANVAS_W, CANVAS_H, QImage.Format_ARGB32)
        self.image.fill(QColor(PALETTE_HEX[6]))
        self.current_color = QColor(PALETTE_HEX[0])
        self.eraser = False
        self.setFixedSize(CANVAS_W*DISPLAY_SCALE, CANVAS_H*DISPLAY_SCALE)
        self.setMouseTracking(True)
        self.brush_sizes = [1, 3, 5, 8, 16]
        self.brush = 1
    
    # set our brush, colours, eraser
    def set_brush(self, size: int):
        self.brush = size

    def set_color(self, qcolor: QColor, eraser_btn: QPushButton):
        self.current_color = qcolor
        self.eraser = False
        eraser_btn.setChecked(False)

    def set_eraser(self, on: bool):
        self.eraser = on
        if on == False:
            self.current_color = QColor(PALETTE_HEX[0])

    def paintEvent(self, _):
        qp = QPainter(self)
        try:
            # Nearest-neighbor: just ensure smoothing is OFF.
            qp.setRenderHint(QPainter.SmoothPixmapTransform, False)
            # Draw scaled to the widget rect
            qp.drawImage(self.rect(), self.image)
        finally:
            qp.end()

    # canvas actions
    def _stamp(self, x: int, y: int):
        half = self.brush // 2
        x0 = max(0, x - half)
        y0 = max(0, y - half)
        w  = min(self.brush, CANVAS_W  - x0)
        h  = min(self.brush, CANVAS_H - y0)

        qp = QPainter(self.image)                # paint onto the QImage
        try:
            qp.setCompositionMode(QPainter.CompositionMode_Source)  # overwrite pixels incl. alpha
            color = QColor(PALETTE_HEX[6]) if self.eraser else self.current_color
            qp.fillRect(x0, y0, w, h, color)
        finally:
            qp.end()
        self.update()

    def _put_pixel(self, pos):
        x = pos.x() // DISPLAY_SCALE
        y = pos.y() // DISPLAY_SCALE
        if 0 <= x < CANVAS_W and 0 <= y < CANVAS_H:
            self._stamp(x, y)

    # canvas event handlers
    def mousePressEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._put_pixel(e.position().toPoint())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._put_pixel(e.position().toPoint())

class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mario Golf 64 Ground Editor (256x512)")
        self.canvas = Canvas()

        # palette UI
        pal_layout = QHBoxLayout()

        # size buttons UI
        size_layout = QHBoxLayout()

        # eraser btn setup
        self.eraser_btn = QPushButton("Eraser")
        self.eraser_btn.setCheckable(True)
        self.eraser_btn.clicked.connect(lambda on: self.canvas.set_eraser(on))
        
        # current ground type label (default fairway)
        self.ground_type_lbl = QLabel(PALLET_NAME[0])

        # pallet buttons (default fairway)
        self.palette_group = QButtonGroup(self)
        self.palette_group.setExclusive(True)
        self.palette_buttons = []
        for i, (hx, name) in enumerate(zip(PALETTE_HEX, PALLET_NAME)):
            b = QPushButton()
            b.setCheckable(True)
            b.setFixedSize(24, 24)
            b.setToolTip(name)
            self.palette_group.addButton(b, i)
            pal_layout.addWidget(b)
            self.palette_buttons.append(b)
        
        self.palette_group.button(0).setChecked(True)
        
        # point size buttons (default 1)
        sizes = [1, 3, 5, 8, 16]
        self.size_group = QButtonGroup(self)
        self.size_group.setExclusive(True)
        for s in sizes:
            b = QPushButton(f"{s}px")
            b.setCheckable(True)
            if s == 1:
                b.setChecked(True)
            self.size_group.addButton(b, s)
            size_layout.addWidget(b)
        
        self.size_group.idClicked.connect(lambda size: self.canvas.set_brush(int(size)))

        # initial canvas setup
        self.canvas.set_color(QColor(PALETTE_HEX[0]), self.eraser_btn)
        self._refresh_palette_styles(active_idx=0)
        self.palette_group.idClicked.connect(self._on_palette_clicked)
        
        # menu setup
        pal_layout.addWidget(self.ground_type_lbl)
        pal_layout.addWidget(self.eraser_btn)

        # layout
        right = QVBoxLayout()
        right.addLayout(pal_layout)
        right.addWidget(self.canvas)
        right.addLayout(size_layout)
        w = QWidget(); w.setLayout(right)
        self.setCentralWidget(w)

        # file menu
        export_att_act = QAction("Export .att…", self)
        export_att_act.triggered.connect(self.export_att)
        new_act = QAction("New", self); new_act.triggered.connect(self.new_image)
        open_act = QAction("Open…", self); open_act.triggered.connect(self.open_image)
        save_act = QAction("Save…", self); save_act.triggered.connect(self.save_image)
        m = self.menuBar().addMenu("File")
        m.addAction(new_act); m.addAction(open_act); m.addAction(save_act)
        m.addAction(export_att_act)  # add to your File menu after Save

        # set canvas to fixed size to avoid scaling issues
        self.canvas.setFixedSize(CANVAS_W*DISPLAY_SCALE, CANVAS_H*DISPLAY_SCALE)
        self.canvas.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.adjustSize()
        self.setFixedSize(self.size())
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)

    # handlers
    def _on_palette_clicked(self, idx: int):
        self.canvas.set_color(QColor(PALETTE_HEX[idx]), self.eraser_btn)
        self.ground_type_lbl.setText(PALLET_NAME[idx])
        self._refresh_palette_styles(active_idx=idx)

    def _refresh_palette_styles(self, active_idx: int):
        for i, btn in enumerate(self.palette_buttons):
            border = "2px solid red" if i == active_idx else "1px solid #444"
            btn.setStyleSheet(f"background:{PALETTE_HEX[i]}; border:{border};")

    # file context menu actions
    def new_image(self):
        self.canvas.image.fill(QColor(PALETTE_HEX[6]))
        self.canvas.current_color = QColor(PALETTE_HEX[0])
        self.canvas.update()

    def open_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open PNG", filter="PNG Images (*.png)")
        if not path: return
        img = QImage(path)
        if img.isNull():
            return
        if img.size() != self.canvas.image.size():
            # strict: reject; or resample:
            img = img.scaled(CANVAS_W, CANVAS_H, transformMode=Qt.TransformationMode.FastTransformation)
        # optional: snap to palette
        for y in range(CANVAS_H):
            for x in range(CANVAS_W):
                c = QColor(img.pixelColor(x, y))
                if c.alpha() == 0:
                    self.canvas.image.setPixelColor(x, y, QColor(0, 0, 0, 0))
                else:
                    self.canvas.image.setPixelColor(x, y, nearest_palette_color(c))
        self.canvas.update()

    def save_image(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save PNG", filter="PNG Images (*.png)")
        if not path: return
        self.canvas.image.save(path, "PNG")
    
    def export_att(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Attribute Map (.att)",
                                            filter="Attribute Maps (*.att)")
        if not path:
            return

        img = self.canvas.image   # QImage, 256x512 ARGB32
        if img.width() != 256 or img.height() != 512:
            QMessageBox.critical(self, "Wrong size", "Canvas must be exactly 256x512.")
            return

        buf = bytearray(256 * 512)
        i = 0
        off_palette_count = 0

        for y in range(512):
            for x in range(256):
                c = img.pixelColor(x, y)
                if c.alpha() == 0:
                    gid = ERASE_FALLBACK_ID
                else:
                    key = (c.red()<<16) | (c.green()<<8) | c.blue()
                    gid = COLOR_TO_ID.get(key)
                    if gid is None:
                        gid = _nearest_id_from_rgb(c.red(), c.green(), c.blue())
                        off_palette_count += 1
                buf[i] = gid & 0xFF
                i += 1

        try:
            with open(path, "wb") as f:
                f.write(buf)  # 131,072 bytes
        except OSError as e:
            QMessageBox.critical(self, "Write failed", str(e))
            return

        if off_palette_count:
            QMessageBox.information(
                self, "Exported with coercion",
                f"Exported .att to {path}\n"
                f"Note: {off_palette_count} pixels were off-palette and were mapped to the nearest ground ID."
            )

def main():
    app = QApplication(sys.argv)
    win = Main()
    win.show()
    sys.exit(app.exec())
