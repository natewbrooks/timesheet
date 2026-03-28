"""
toast.py — solid-bg toasts, pill-right / flat-left, colored left border only.
Auto-height, absolute stacking, no overflow clipping.
"""
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QSizePolicy
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor

TOAST_W   = 320
TOAST_GAP = 6
MARGIN    = 16


class ToastItem(QWidget):
    dismissed = pyqtSignal(object)

    def __init__(self, message: str, level: str, C: dict, duration: int, parent=None):
        super().__init__(parent)
        self._C         = C
        self._dismissed = False

        color_map = {
            "info":    C.get("toast_info",    C.get("accent",  "#4f7cff")),
            "success": C.get("toast_success", C.get("green",   "#3ddc84")),
            "warning": C.get("toast_warning", C.get("orange",  "#ffaa33")),
            "error":   C.get("toast_error",   C.get("red",     "#ff5a5a")),
        }
        accent = color_map.get(level, color_map["info"])
        bg     = C.get("surface2", "#1a1e29")
        border = C.get("border2",  "#252938")
        text_c = C.get("text",     "#e8eaf0")
        text2  = C.get("text2",    "#7a7f96")

        # Solid background. Right side fully rounded. Left side flat with colored 3px border.
        self.setStyleSheet(f"""
            ToastItem {{
                background-color: {bg};
                border-top:    1px solid {border};
                border-right:  1px solid {border};
                border-bottom: 1px solid {border};
                border-left:   3px solid {accent};
                border-top-right-radius:    20px;
                border-bottom-right-radius: 20px;
                border-top-left-radius:     3px;
                border-bottom-left-radius:  3px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 12, 10)
        layout.setSpacing(8)

        lbl = QLabel(message)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"color: {text_c}; font-size: 11px; border: none; background: transparent;"
        )
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout.addWidget(lbl, 1)

        x_btn = QPushButton("×")
        x_btn.setFixedSize(18, 18)
        x_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {text2}; font-size: 14px; padding: 0; border-radius: 9px;
            }}
            QPushButton:hover {{
                color: {text_c};
                background: rgba(255,255,255,0.08);
            }}
        """)
        x_btn.clicked.connect(self._dismiss)
        layout.addWidget(x_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.setFixedWidth(TOAST_W)
        # Let height grow with content
        self.adjustSize()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._dismiss)
        self._timer.start(duration * 1000)

    def _dismiss(self):
        if self._dismissed:
            return
        self._dismissed = True
        self._timer.stop()
        self.dismissed.emit(self)
        self.hide()
        self.deleteLater()


class ToastManager(QWidget):
    """
    Absolutely-positioned parent widget that stacks individual ToastItems.
    Each toast gets its natural height — no fixed heights, no squishing.
    Manager resizes to fit all current toasts.
    """

    def __init__(self, parent=None, C: dict = None, settings: dict = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._C        = C or {}
        self._settings = settings or {}
        self._toasts: list[ToastItem] = []
        self.setFixedWidth(TOAST_W)
        self.hide()

    def show_toast(self, message: str, level: str = "info"):
        duration = self._settings.get("toast_duration", 4)
        t = ToastItem(message, level, self._C, duration, self)
        t.dismissed.connect(self._on_dismissed)
        self._toasts.append(t)
        self._layout()
        t.show()

    def _on_dismissed(self, t: ToastItem):
        if t in self._toasts:
            self._toasts.remove(t)
        self._layout()

    def _layout(self):
        parent = self.parent()
        if not parent:
            return
        if not self._toasts:
            self.hide()
            return

        pos = self._settings.get("toast_position", "bottom_right")
        pw  = parent.width()
        ph  = parent.height()

        # Measure each toast naturally
        heights = []
        for t in self._toasts:
            t.setFixedWidth(TOAST_W)
            t.adjustSize()
            heights.append(max(t.sizeHint().height(), 40))

        total_h = sum(heights) + TOAST_GAP * max(0, len(self._toasts) - 1)

        # Position manager
        x = pw - TOAST_W - MARGIN if "right" in pos else MARGIN
        y = ph - total_h - MARGIN  if "bottom" in pos else MARGIN

        self.setFixedHeight(total_h)
        self.move(x, y)

        # Stack toasts
        if "bottom" in pos:
            # newest at bottom
            cur_y = 0
            for i, t in enumerate(self._toasts):
                h = heights[i]
                t.move(0, cur_y)
                t.setFixedHeight(h)
                cur_y += h + TOAST_GAP
        else:
            # newest at top
            cur_y = 0
            for i, t in enumerate(reversed(self._toasts)):
                orig_i = len(self._toasts) - 1 - i
                h = heights[orig_i]
                t.move(0, cur_y)
                t.setFixedHeight(h)
                cur_y += h + TOAST_GAP

        self.show()
        self.raise_()

    def reanchor(self):
        self._layout()

    def update_C(self, C: dict):
        self._C = C

    def update_settings(self, s: dict):
        self._settings = s
