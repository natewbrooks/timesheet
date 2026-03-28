#!/usr/bin/env python3
"""
timesheet.py — main application
"""
import sys
import csv
from datetime import date, timedelta, datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QScrollArea, QFrame, QDialog,
    QFileDialog, QProgressBar, QGraphicsDropShadowEffect,
    QToolButton, QDoubleSpinBox, QComboBox, QSizePolicy,
    QAbstractItemView, QCheckBox
)
from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, QPoint, QMimeData, QByteArray,
    QSize, QRect
)
from PyQt6.QtGui import (
    QFontDatabase, QColor, QShortcut, QKeySequence,
    QPainter, QPen, QDrag, QPixmap, QCursor
)

import data as D
import theme as TH
from toast import ToastManager
from notes import NotesOverlay
from settings_dialog import SettingsDialog


# ── Centered full-window time entry overlay ────────────────────────────────────

class TimeEntryOverlay(QWidget):
    """
    Semi-transparent full-window overlay with a centered, address-bar-style input.
    Shows 'Time entry for [Day]:' as a label above the input.
    """
    submitted = pyqtSignal(int)    # minutes
    cancelled = pyqtSignal()

    def __init__(self, parent: QWidget, C: dict):
        super().__init__(parent)
        self._C = C
        self._committed = False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet("background: rgba(0,0,0,0);")
        self.hide()
        self._build()

    def _build(self):
        C = self._C
        # Dark backdrop
        self._backdrop = QWidget(self)
        self._backdrop.setStyleSheet("background: rgba(0,0,0,0.55);")

        # Card — centered
        self._card = QWidget(self)
        self._card.setFixedWidth(420)
        self._card.setStyleSheet(f"""
            QWidget {{
                background: {C['surface']};
                border-radius: 12px;
                border: 1px solid {C['border2']};
            }}
        """)
        cl = QVBoxLayout(self._card)
        cl.setContentsMargins(28, 24, 28, 24)
        cl.setSpacing(12)

        # Day label
        self._day_label = QLabel("Time entry for Today:")
        self._day_label.setStyleSheet(
            f"color: {C['text2']}; font-size: 11px; letter-spacing: 0.5px; "
            f"background: transparent; border: none;"
        )
        self._day_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        cl.addWidget(self._day_label)

        # Input — address-bar style: rounded, solid bg, no underline
        self.input = QLineEdit()
        self.input.setPlaceholderText("2:30")
        self.input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.input.setFixedHeight(52)
        self.input.setStyleSheet(f"""
            QLineEdit {{
                background: {C['surface2']};
                border: 1px solid {C['border2']};
                border-radius: 8px;
                color: {C['text']};
                font-size: 26px;
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                padding: 0 16px;
                letter-spacing: 2px;
            }}
            QLineEdit:focus {{
                border-color: {C['accent']};
                background: {C['surface2']};
                color: {C['text']};
            }}
        """)
        self.input.returnPressed.connect(self._submit)
        self.input.textChanged.connect(self._update_preview)
        cl.addWidget(self.input)

        # Preview
        self._preview = QLabel("")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setFixedHeight(22)
        self._preview.setStyleSheet(
            f"color: {C['accent2']}; font-size: 14px; background: transparent; border: none;"
        )
        cl.addWidget(self._preview)

        # Hint row
        hint_row = QHBoxLayout()
        hint_row.setContentsMargins(0, 0, 0, 0)
        for text, style in [
            ("Enter to save", f"color: {C['text3']}; font-size: 10px;"),
            ("Esc to cancel",  f"color: {C['text3']}; font-size: 10px;"),
        ]:
            lbl = QLabel(text)
            lbl.setStyleSheet(f"{style} background: transparent; border: none;")
            hint_row.addWidget(lbl)
            hint_row.addStretch()
        cl.addLayout(hint_row)

        # Drop shadow on card
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 200))
        shadow.setOffset(0, 8)
        self._card.setGraphicsEffect(shadow)

    def open_for_day(self, day: date, initial_text: str = ""):
        self._committed = False
        day_name = day.strftime("%A, %b %-d")
        self._day_label.setText(f"Time entry for {day_name}:")
        self.input.setText(initial_text)
        self.input.setCursorPosition(len(initial_text))
        self._preview.setText("")
        self._reposition()
        self.show()
        self.raise_()
        self.input.setFocus()
        if initial_text:
            self._update_preview(initial_text)

    def _reposition(self):
        parent = self.parent()
        if not parent:
            return
        pw, ph = parent.width(), parent.height()
        self._backdrop.setGeometry(0, 0, pw, ph)
        cw, ch = self._card.sizeHint().width(), self._card.sizeHint().height()
        # use fixed width
        cw = 420
        cx = (pw - cw) // 2
        cy = (ph - ch) // 2 - 40  # slightly above center
        self._card.move(cx, cy)
        self._card.adjustSize()

    def _update_preview(self, text: str):
        mins = D.parse_time_input(text)
        if mins and mins > 0:
            self._preview.setText(D.format_hm_pretty(mins))
        else:
            self._preview.setText("")

    def _submit(self):
        if self._committed:
            return
        mins = D.parse_time_input(self.input.text())
        if mins and mins > 0:
            self._committed = True
            self.submitted.emit(mins)
            self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            self.hide()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        # Click outside card = cancel
        if not self._card.geometry().contains(event.pos()):
            self.cancelled.emit()
            self.hide()
        else:
            super().mousePressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()

    def showEvent(self, event):
        super().showEvent(event)
        self._reposition()


# ── Drag data ──────────────────────────────────────────────────────────────────

DRAG_MIME = "application/x-timeentry"


# ── Single entry widget (draggable) ───────────────────────────────────────────

class EntryWidget(QWidget):
    delete_requested = pyqtSignal(int)
    value_changed    = pyqtSignal(int, int)   # index, minutes
    move_requested   = pyqtSignal(int, int)   # from_index, to_index (within column)

    def __init__(self, index: int, minutes: int, C: dict, parent=None):
        super().__init__(parent)
        self.index    = index
        self._minutes = minutes
        self._C       = C
        self._editing = False
        self._drag_start = None
        self.setFixedHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build()
        self.setMouseTracking(True)

    def _build(self):
        C = self._C
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 6, 0)
        layout.setSpacing(4)

        # Drag handle
        self._handle = QLabel("⠿")
        self._handle.setFixedWidth(12)
        self._handle.setStyleSheet(f"color: {C['text3']}; font-size: 11px;")
        self._handle.setCursor(Qt.CursorShape.SizeAllCursor)
        layout.addWidget(self._handle)

        self._num = QLabel(f"{self.index + 1}")
        self._num.setFixedWidth(14)
        self._num.setStyleSheet(f"color: {C['text3']}; font-size: 9px;")
        layout.addWidget(self._num)

        self._display = QLabel(D.format_hm_pretty(self._minutes))
        self._display.setStyleSheet(f"color: {C['text']}; font-size: 12px;")
        layout.addWidget(self._display, 1)

        self._edit = QLineEdit(D.format_hm_short(self._minutes))
        self._edit.setStyleSheet(f"""
            QLineEdit {{
                background: {C['surface2']}; border: 1px solid {C['border2']};
                border-radius: 4px; color: {C['accent2']}; font-size: 12px; padding: 1px 4px;
            }}
            QLineEdit:focus {{ border-color: {C['accent']}; }}
        """)
        self._edit.hide()
        self._edit.returnPressed.connect(self._commit_edit)
        self._edit.editingFinished.connect(self._commit_edit)
        layout.addWidget(self._edit, 1)

        self._del = QPushButton("×")
        self._del.setFixedSize(18, 18)
        self._del.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: transparent; font-size: 13px; padding: 0; border-radius: 3px;
            }}
            QPushButton:hover {{
                color: {C['red']}; background: rgba(255,90,90,0.12);
            }}
        """)
        self._del.clicked.connect(lambda: self.delete_requested.emit(self.index))
        layout.addWidget(self._del)

    # ── Hover ──────────────────────────────────────────────────────────────────

    def enterEvent(self, e):
        C = self._C
        # Single flat bg on the whole row — no child-level backgrounds
        self.setStyleSheet(f"""
            EntryWidget {{
                background: {C['surface2']};
                border-radius: 4px;
            }}
            EntryWidget * {{
                background: transparent;
            }}
            QPushButton {{
                background: transparent; border: none;
                color: {C['text2']}; font-size: 13px; padding: 0; border-radius: 3px;
            }}
            QPushButton:hover {{
                color: {C['red']}; background: rgba(255,90,90,0.12);
            }}
        """)

    def leaveEvent(self, e):
        if not self._editing:
            self.setStyleSheet("")

    # ── Edit ───────────────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_start = e.pos()
            if not self._editing:
                self._start_edit()

    def mouseMoveEvent(self, e):
        if (self._drag_start and
                (e.pos() - self._drag_start).manhattanLength() > 8 and
                e.buttons() & Qt.MouseButton.LeftButton):
            self._start_drag()

    def mouseReleaseEvent(self, e):
        self._drag_start = None

    def _start_edit(self):
        self._editing = True
        self._display.hide()
        self._edit.setText(D.format_hm_short(self._minutes))
        self._edit.show()
        self._edit.setFocus()
        self._edit.selectAll()

    def _commit_edit(self):
        if not self._editing:
            return
        self._editing = False
        mins = D.parse_time_input(self._edit.text())
        if mins and mins > 0:
            self._minutes = mins
        self._display.setText(D.format_hm_pretty(self._minutes))
        self._edit.hide()
        self._display.show()
        self.value_changed.emit(self.index, self._minutes)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape and self._editing:
            self._editing = False
            self._edit.hide()
            self._display.show()
        else:
            super().keyPressEvent(e)

    # ── Drag ───────────────────────────────────────────────────────────────────

    def _start_drag(self):
        if self._editing:
            self._commit_edit()
        drag = QDrag(self)
        mime = QMimeData()
        # encode: column_day|entry_index|minutes
        col = self._find_column()
        if col is None:
            return
        payload = f"{col.day.isoformat()}|{self.index}|{self._minutes}"
        mime.setData(DRAG_MIME, QByteArray(payload.encode()))
        drag.setMimeData(mime)

        # Snapshot pixmap
        pm = QPixmap(self.size())
        pm.fill(QColor(0, 0, 0, 0))
        self.render(pm)
        drag.setPixmap(pm)
        drag.setHotSpot(self._drag_start or QPoint(self.width() // 2, self.height() // 2))
        drag.exec(Qt.DropAction.MoveAction)

    def _find_column(self) -> "DayColumn | None":
        w = self.parent()
        while w is not None:
            if isinstance(w, DayColumn):
                return w
            w = w.parent()
        return None

    # ── Accessors ──────────────────────────────────────────────────────────────

    def get_minutes(self) -> int:
        return self._minutes

    def set_index(self, i: int):
        self.index = i
        self._num.setText(str(i + 1))


# ── Day column (drag-drop target) ─────────────────────────────────────────────

class DayColumn(QWidget):
    data_changed  = pyqtSignal()
    hovered_day   = pyqtSignal(date, bool)    # day, entered/left

    def __init__(self, day: date, entries: list[int], C: dict, is_today: bool, parent=None):
        super().__init__(parent)
        self.day  = day
        self._entries: list[int] = list(entries)
        self._C   = C
        self._is_today = is_today
        self._entry_widgets: list[EntryWidget] = []
        self._hovered = False
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self._build()

    def _build(self):
        C = self._C
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(52)
        header.setStyleSheet(f"background: {C['surface']};")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(10, 10, 10, 8)
        hl.setSpacing(2)
        color     = C['accent']  if self._is_today else C['text2']
        num_color = C['accent2'] if self._is_today else C['text3']
        day_lbl = QLabel(self.day.strftime("%a").upper())
        day_lbl.setStyleSheet(f"color: {color}; font-size: 9px; letter-spacing: 2px;")
        hl.addWidget(day_lbl)
        num_lbl = QLabel(self.day.strftime("%-d"))
        num_lbl.setStyleSheet(f"color: {num_color}; font-size: 22px; font-weight: 300;")
        hl.addWidget(num_lbl)
        self._main_layout.addWidget(header)

        # Entries scroll area
        self._entries_container = QWidget()
        self._entries_container.setStyleSheet("background: transparent;")
        self._entries_layout = QVBoxLayout(self._entries_container)
        self._entries_layout.setContentsMargins(4, 4, 4, 4)
        self._entries_layout.setSpacing(1)
        self._entries_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(self._entries_container)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._main_layout.addWidget(scroll, 1)

        self._rebuild_entries()

        # Total
        self._total_area = QWidget()
        self._total_area.setFixedHeight(46)
        self._total_area.setStyleSheet(f"background: {C['surface']};")
        tl = QVBoxLayout(self._total_area)
        tl.setContentsMargins(10, 6, 10, 6)
        tl.setSpacing(1)
        tot_hint = QLabel("TOTAL")
        tot_hint.setStyleSheet(f"color: {C['text3']}; font-size: 8px; letter-spacing: 1.5px;")
        tl.addWidget(tot_hint)
        self.total_lbl = QLabel(D.format_hm_pretty(sum(self._entries)))
        self.total_lbl.setStyleSheet(f"color: {C['text']}; font-size: 13px; font-weight: 500;")
        tl.addWidget(self.total_lbl)
        self._main_layout.addWidget(self._total_area)

    # ── Entry management ───────────────────────────────────────────────────────

    def _rebuild_entries(self):
        for w in self._entry_widgets:
            self._entries_layout.removeWidget(w)
            w.deleteLater()
        self._entry_widgets.clear()
        for i, mins in enumerate(self._entries):
            if mins == 0:
                continue
            ew = EntryWidget(i, mins, self._C)
            ew.delete_requested.connect(self._delete_entry)
            ew.value_changed.connect(self._on_entry_edited)
            self._entries_layout.insertWidget(self._entries_layout.count() - 1, ew)
            self._entry_widgets.append(ew)

    def _delete_entry(self, index: int):
        # Find by widget index value
        for i, ew in enumerate(self._entry_widgets):
            if ew.index == index:
                self._entries.pop(i)
                break
        self._rebuild_entries()
        self._refresh_total()
        self.data_changed.emit()

    def _on_entry_edited(self, index: int, minutes: int):
        for i, ew in enumerate(self._entry_widgets):
            if ew.index == index:
                if i < len(self._entries):
                    self._entries[i] = minutes
                break
        self._refresh_total()
        self.data_changed.emit()

    def add_entry(self, minutes: int):
        self._entries.append(minutes)
        ew = EntryWidget(len(self._entries) - 1, minutes, self._C)
        ew.delete_requested.connect(self._delete_entry)
        ew.value_changed.connect(self._on_entry_edited)
        self._entries_layout.insertWidget(self._entries_layout.count() - 1, ew)
        self._entry_widgets.append(ew)
        self._refresh_total()
        self.data_changed.emit()

    def remove_entry_at(self, idx: int):
        """Remove by list index (used during drag-drop)."""
        if 0 <= idx < len(self._entries):
            self._entries.pop(idx)
        self._rebuild_entries()
        self._refresh_total()
        self.data_changed.emit()

    def _refresh_total(self):
        self.total_lbl.setText(D.format_hm_pretty(sum(self._entries)))

    def get_entries(self) -> list[int]:
        return [e for e in self._entries if e > 0]

    def get_total_minutes(self) -> int:
        return sum(e for e in self._entries if e > 0)

    # ── Hover highlight ────────────────────────────────────────────────────────

    def set_hovered(self, on: bool):
        C = self._C
        if on:
            col = C.get("col_hover", C.get("surface2", "#1e2235"))
            bg  = f"background: {col};"
        else:
            bg = "background: transparent;"
        self._entries_container.setStyleSheet(bg)
        # Force all child widget backgrounds transparent so highlight shows
        self.setAutoFillBackground(on)
        if on:
            pal = self.palette()
            pal.setColor(self.backgroundRole(), QColor(C.get("col_hover", "#1e2235")))
            self.setPalette(pal)
        else:
            self.setAutoFillBackground(False)

    def enterEvent(self, e):
        self._hovered = True
        self.set_hovered(True)
        self.hovered_day.emit(self.day, True)

    def leaveEvent(self, e):
        self._hovered = False
        self.set_hovered(False)
        self.hovered_day.emit(self.day, False)

    # ── Drag-drop ──────────────────────────────────────────────────────────────

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(DRAG_MIME):
            e.acceptProposedAction()
            self.set_hovered(True)

    def dragLeaveEvent(self, e):
        if not self._hovered:
            self.set_hovered(False)

    def dropEvent(self, e):
        if not e.mimeData().hasFormat(DRAG_MIME):
            return
        payload = e.mimeData().data(DRAG_MIME).data().decode()
        try:
            src_day_str, src_idx_str, mins_str = payload.split("|")
            src_idx = int(src_idx_str)
            mins    = int(mins_str)
        except Exception:
            return

        e.acceptProposedAction()

        # Find source column and remove from it
        main = self.window()
        for col in main._columns:
            if col.day.isoformat() == src_day_str:
                col.remove_entry_at(src_idx)
                break

        self.add_entry(mins)


# ── Marquee ────────────────────────────────────────────────────────────────────

class MarqueeLabel(QWidget):
    """
    Smooth pixel-scrolling marquee. Renders text on a QPixmap and scrolls it
    one pixel at a time using a timer — no text chopping, no character jumps.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._text     = ""
        self._offset   = 0.0          # float pixel offset for smooth scroll
        self._speed    = 0.4          # pixels per tick — very slow
        self._text_w   = 0            # cached pixel width of full text string
        self._gap      = 80           # gap in pixels between repetitions
        self._timer    = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)         # ~60fps timer, tiny increment each frame
        self.setFixedHeight(16)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    def set_text(self, text: str):
        self._text   = text
        self._offset = 0.0
        fm = self.fontMetrics()
        self._text_w = fm.horizontalAdvance(self._text)
        self.update()

    def _tick(self):
        if not self._text or self._text_w == 0:
            return
        total = self._text_w + self._gap
        self._offset = (self._offset + self._speed) % total
        self.update()

    def paintEvent(self, event):
        if not self._text:
            return
        from PyQt6.QtGui import QPainter, QColor
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # inherit color from parent stylesheet via palette
        C = getattr(self, "_C", None)
        if C:
            color = QColor(C.get("text3", "#3a3e50"))
        else:
            color = self.palette().color(self.foregroundRole())
        painter.setPen(color)
        painter.setFont(self.font())

        fm    = self.fontMetrics()
        y     = fm.ascent() + (self.height() - fm.height()) // 2
        total = self._text_w + self._gap
        x     = -int(self._offset)

        # Draw enough repetitions to fill the widget width
        while x < self.width():
            painter.drawText(x, y, self._text)
            x += total

        painter.end()


# ── Sheet target override ──────────────────────────────────────────────────────

class SheetTargetDialog(QDialog):
    saved = pyqtSignal(float, float, str, float)

    def __init__(self, sheet: dict, C: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sheet Override")
        self.setFixedWidth(340)
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog {{
                background: {C['surface']};
                border: 1px solid {C['border2']};
                border-radius: 8px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("SHEET OVERRIDES")
        title.setStyleSheet(f"color: {C['text']}; font-size: 11px; letter-spacing: 2px;")
        layout.addWidget(title)

        note = QLabel("Overrides global defaults for this sheet only.")
        note.setStyleSheet(f"color: {C['text3']}; font-size: 10px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        def mk(lbl_text, widget):
            r = QWidget(); r.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(r); rl.setContentsMargins(0,0,0,0); rl.setSpacing(12)
            l = QLabel(lbl_text)
            l.setStyleSheet(f"color: {C['text2']}; font-size: 11px;"); l.setFixedWidth(130)
            rl.addWidget(l); rl.addWidget(widget, 1)
            return r

        self.target_hrs = QDoubleSpinBox()
        self.target_hrs.setRange(0, 168); self.target_hrs.setDecimals(1)
        self.target_hrs.setSuffix(" hrs")
        self.target_hrs.setValue(sheet.get("target_hours", 40.0))
        self.target_hrs.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        layout.addWidget(mk("Target Hours", self.target_hrs))

        self.pay_type = QComboBox()
        self.pay_type.addItems(["Hourly", "Salary"])
        self.pay_type.setCurrentText(sheet.get("pay_type", "hourly").capitalize())
        layout.addWidget(mk("Pay Type", self.pay_type))

        self.hourly = QDoubleSpinBox()
        self.hourly.setRange(0, 10000); self.hourly.setDecimals(2); self.hourly.setPrefix("$ ")
        self.hourly.setValue(sheet.get("hourly_rate", 0.0))
        self.hourly.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        layout.addWidget(mk("Hourly Rate", self.hourly))

        self.salary = QDoubleSpinBox()
        self.salary.setRange(0, 10_000_000); self.salary.setDecimals(2)
        self.salary.setPrefix("$ "); self.salary.setSingleStep(1000)
        self.salary.setValue(sheet.get("annual_salary", 0.0))
        self.salary.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        layout.addWidget(mk("Annual Salary", self.salary))

        br = QHBoxLayout(); br.addStretch()
        cancel = QPushButton("Cancel"); cancel.setFixedWidth(70); cancel.clicked.connect(self.reject)
        br.addWidget(cancel)
        save = QPushButton("Save"); save.setFixedWidth(70)
        save.setStyleSheet(f"""
            QPushButton {{
                background: {C['accent']}; border: none; color: white;
                border-radius: 5px; font-size: 11px;
            }}
            QPushButton:hover {{ background: {C['accent2']}; }}
        """)
        save.clicked.connect(self._save)
        br.addWidget(save)
        layout.addLayout(br)

    def _save(self):
        self.saved.emit(self.target_hrs.value(), self.hourly.value(),
                        self.pay_type.currentText().lower(), self.salary.value())
        self.accept()


# ── Main window ────────────────────────────────────────────────────────────────

class TimesheetApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Timesheet")
        self.setMinimumSize(680, 560)
        self.resize(860, 640)

        self._settings      = D.load_settings()
        self._data          = D.load_data(self._settings)
        self._notes_data    = D.load_notes(self._settings)
        self._C             = TH.get_theme(
            self._settings.get("theme", "dark"),
            self._settings.get("color_overrides", {})
        )
        self._current_key   = ""
        self._current_sheet: dict = {}
        self._columns: list[DayColumn] = []
        self._notes_open    = False
        self._hovered_day: date | None = None

        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._do_save)

        self._build_ui()
        self._setup_shortcuts()
        self._load_sheet_for_date(date.today())

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        C = self._C
        self.setStyleSheet(TH.make_stylesheet(C))
        self._toast = ToastManager(self, C, self._settings)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Main column
        main_col = QWidget()
        main_layout = QVBoxLayout(main_col)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._topbar_ref = self._mk_topbar()
        main_layout.addWidget(self._topbar_ref)
        main_layout.addWidget(self._mk_marquee_bar())
        main_layout.addWidget(self._mk_nav())
        main_layout.addWidget(self._mk_progress())

        self.columns_widget = QWidget()
        self.columns_widget.setStyleSheet(f"background: {C['bg']};")
        self.columns_layout = QHBoxLayout(self.columns_widget)
        self.columns_layout.setContentsMargins(0, 0, 0, 0)
        self.columns_layout.setSpacing(0)
        main_layout.addWidget(self.columns_widget, 1)

        root_layout.addWidget(main_col, 1)

        # Notes overlay — absolute positioned, covers full content area below topbar
        self._notes_overlay = NotesOverlay(central, C, self._settings)
        self._notes_overlay.notes_changed.connect(self._on_notes_changed)
        self._notes_overlay.closed.connect(self._on_notes_closed)
        self._notes_overlay.hide()
        # NOT added to layout — it's positioned manually in _position_notes_overlay()

        # Time entry overlay (full-window centered)
        self._entry_overlay = TimeEntryOverlay(central, C)
        self._entry_overlay.setGeometry(central.rect())
        self._entry_overlay.hide()

    # ── Top bar ────────────────────────────────────────────────────────────────

    def _mk_topbar(self) -> QWidget:
        C = self._C
        bar = QWidget()
        bar.setFixedHeight(50)
        bar.setStyleSheet(f"background: {C['surface']}; border-bottom: 1px solid {C['border']};")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 14, 0)
        layout.setSpacing(6)

        title = QLabel("TIMESHEET")
        title.setStyleSheet(f"color: {C['text']}; font-size: 12px; font-weight: 700; letter-spacing: 5px;")
        layout.addWidget(title)
        layout.addStretch()

        self.earnings_lbl = QLabel("")
        self.earnings_lbl.setStyleSheet(f"color: {C['green']}; font-size: 11px;")
        layout.addWidget(self.earnings_lbl)
        layout.addSpacing(10)

        def tbtn(symbol: str, tip: str, cb) -> QToolButton:
            b = QToolButton()
            b.setText(symbol)
            b.setToolTip(tip)
            b.setFixedSize(34, 34)
            b.clicked.connect(cb)
            return b

        layout.addWidget(tbtn("✎", "Notes (Ctrl+N)",    self._toggle_notes))
        layout.addWidget(tbtn("◎", "Sheet overrides",   self._open_sheet_override))
        layout.addWidget(tbtn("⧖", "Status",             self._show_status_toast))
        layout.addWidget(tbtn("⤓", "Export",             self._show_export_menu))
        layout.addWidget(tbtn("⚙", "Settings",           self._open_settings))
        return bar

    # ── Marquee bar ────────────────────────────────────────────────────────────

    def _mk_marquee_bar(self) -> QWidget:
        C = self._C
        bar = QWidget()
        bar.setFixedHeight(26)
        bar.setStyleSheet(f"background: {C['bg']};")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(12)

        self._marquee = MarqueeLabel()
        self._marquee._C = C
        from PyQt6.QtGui import QFont as _QF
        self._marquee.setFont(_QF("JetBrains Mono", 9))
        self._marquee.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._marquee, 1)

        self._deadline_lbl = QLabel("")
        self._deadline_lbl.setStyleSheet(f"color: {C['text3']}; font-size: 10px;")
        self._deadline_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._deadline_lbl)
        return bar

    # ── Nav bar ────────────────────────────────────────────────────────────────

    def _mk_nav(self) -> QWidget:
        C = self._C
        nav = QWidget()
        nav.setFixedHeight(42)
        nav.setStyleSheet(f"background: {C['surface']};")
        layout = QHBoxLayout(nav)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        self._prev_btn = QPushButton("‹   Prev")
        self._prev_btn.setFixedWidth(88)
        self._prev_btn.clicked.connect(self._prev_sheet)
        layout.addWidget(self._prev_btn)

        self.sheet_lbl = QLabel("")
        self.sheet_lbl.setStyleSheet(f"color: {C['text2']}; font-size: 11px; letter-spacing: 0.5px;")
        self.sheet_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.sheet_lbl, 1)

        today_btn = QToolButton()
        today_btn.setText("⊙")
        today_btn.setToolTip("Go to today")
        today_btn.setFixedSize(38, 32)
        today_btn.setStyleSheet(f"""
            QToolButton {{
                font-size: 22px; background: transparent; border: none;
                color: {C['text2']}; border-radius: 5px; padding: 0;
            }}
            QToolButton:hover {{ color: {C['accent']}; background: {C['surface2']}; }}
        """)
        today_btn.clicked.connect(self._goto_today)
        layout.addWidget(today_btn)

        next_btn = QPushButton("Next   ›")
        next_btn.setFixedWidth(88)
        next_btn.clicked.connect(self._next_sheet)
        layout.addWidget(next_btn)
        return nav

    # ── Progress bar ───────────────────────────────────────────────────────────

    def _mk_progress(self) -> QWidget:
        C = self._C
        w = QWidget()
        w.setFixedHeight(52)
        w.setStyleSheet(f"background: {C['surface']};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(5)

        self.progress_lbl = QLabel("")
        self.progress_lbl.setStyleSheet(f"color: {C['text2']}; font-size: 10px;")
        layout.addWidget(self.progress_lbl)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(10)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {C['bg']};
                border: none; border-radius: 2px;
            }}
        """)
        bottom.addWidget(self.progress_bar, 1)
        self.target_lbl = QLabel("")
        self.target_lbl.setStyleSheet(f"color: {C['text3']}; font-size: 10px;")
        self.target_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bottom.addWidget(self.target_lbl)
        layout.addLayout(bottom)
        return w

    # ── Sheet loading ──────────────────────────────────────────────────────────

    def _load_sheet_for_date(self, d: date):
        key, sheet = D.find_or_create_sheet(self._data, self._settings, d)
        self._current_key   = key
        self._current_sheet = sheet
        D.save_data(self._data, self._settings)
        self._render_sheet()

    def _render_sheet(self):
        C = self._C
        sheet = self._current_sheet

        while self.columns_layout.count():
            item = self.columns_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._columns.clear()

        try:
            start = date.fromisoformat(sheet["start_date"])
            end   = date.fromisoformat(sheet["end_date"])
            num   = sheet.get("sheet_num", "?")
            self.sheet_lbl.setText(
                f"Sheet {num}  ·  {start.strftime('%b %-d')} – {end.strftime('%b %-d, %Y')}"
            )
            dates = [start + timedelta(days=i) for i in range(7)]
        except Exception:
            self.sheet_lbl.setText(self._current_key)
            dates = []

        days_data = sheet.get("days", {})
        today     = date.today()

        for i, d in enumerate(dates):
            entries = days_data.get(d.isoformat(), [])
            col = DayColumn(d, entries, C, d == today)
            col.data_changed.connect(self._on_data_changed)
            col.data_changed.connect(self._refresh_earnings)
            col.hovered_day.connect(self._on_col_hover)

            if i > 0:
                vsep = QFrame()
                vsep.setFrameShape(QFrame.Shape.VLine)
                vsep.setStyleSheet(f"background: {C['border']}; border: none; max-width: 1px;")
                self.columns_layout.addWidget(vsep)

            self.columns_layout.addWidget(col, 1)
            self._columns.append(col)

        self._refresh_progress()
        self._refresh_earnings()
        self._refresh_deadline()
        self._refresh_marquee()

        # Show/hide prev button depending on whether an earlier sheet exists
        has_prev = D.get_sheet_by_offset(self._data, self._current_key, -1) is not None
        self._prev_btn.setVisible(has_prev)

        if self._notes_open:
            self._notes_overlay.update_sheet(
                self._current_key, self._current_sheet, self._notes_data
            )

    # ── Column hover tracking ──────────────────────────────────────────────────

    def _on_col_hover(self, day: date, entered: bool):
        if entered:
            self._hovered_day = day
        elif self._hovered_day == day:
            self._hovered_day = None

    # ── Key capture ────────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        text = event.text()
        if text and (text.isdigit() or text == ":") and not self._any_input_focused():
            target_day = self._hovered_day or date.today()
            self._open_entry_overlay(target_day, text)
            return
        super().keyPressEvent(event)

    def _any_input_focused(self) -> bool:
        fw = QApplication.focusWidget()
        return isinstance(fw, (QLineEdit,))

    def _open_entry_overlay(self, day: date, initial: str = ""):
        col = self._col_for_day(day)
        if col is None:
            return
        overlay = self._entry_overlay
        overlay.setGeometry(self.centralWidget().rect())

        # Disconnect old connections
        try:
            overlay.submitted.disconnect()
        except Exception:
            pass
        try:
            overlay.cancelled.disconnect()
        except Exception:
            pass

        overlay.submitted.connect(col.add_entry)
        overlay.submitted.connect(
            lambda m: self._toast.show_toast(f"{D.format_hm_pretty(m)} added", "success")
        )
        overlay.open_for_day(day, initial)

    def _col_for_day(self, day: date) -> "DayColumn | None":
        for col in self._columns:
            if col.day == day:
                return col
        return None

    # ── Data ───────────────────────────────────────────────────────────────────

    def _on_data_changed(self):
        self._save_timer.start(400)
        self._refresh_progress()
        self._refresh_marquee()

    def _do_save(self):
        days = {}
        for col in self._columns:
            entries = col.get_entries()
            if entries:
                days[col.day.isoformat()] = entries
        self._current_sheet["days"] = days
        D.save_data(self._data, self._settings)

    # ── Progress ───────────────────────────────────────────────────────────────

    def _refresh_progress(self):
        C = self._C
        total      = sum(col.get_total_minutes() for col in self._columns)
        target_mins = int(self._current_sheet.get("target_hours", 40.0) * 60)

        if target_mins == 0:
            self.progress_lbl.setText(D.format_hm_pretty(total))
            self.progress_bar.setValue(0); self.target_lbl.setText(""); return

        pct       = min(100, int(total / target_mins * 100))
        remaining = max(0, target_mins - total)
        color     = C['green'] if pct >= 100 else (C['orange'] if pct >= 60 else C['red'])

        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {C['bg']};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: 2px;
            }}
        """)
        self.progress_bar.setValue(pct)
        self.progress_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.progress_lbl.setText(
            f"<span style='color:{color};'>{pct}%</span>"
            f"<span style='color:{C['text3']};'>  ·  </span>"
            f"<span style='color:{C['text2']};'>{D.format_hm_pretty(total)} logged</span>"
            f"<span style='color:{C['text3']};'>  ·  </span>"
            f"<span style='color:{color};'>{D.format_hm_pretty(remaining)} remaining</span>"
        )
        dd  = self._current_sheet.get("deadline_day",  "tuesday")
        dt  = self._current_sheet.get("deadline_time", "23:59")
        try:
            h, m = map(int, dt.split(":")); ampm = "AM" if h < 12 else "PM"; h12 = h % 12 or 12
            dt_str = f"{h12}:{m:02d} {ampm}"
        except Exception:
            dt_str = dt
        self.target_lbl.setText(
            f"Target: {D.format_hm_pretty(target_mins)} by {dd.capitalize()} {dt_str}"
        )

    def _refresh_deadline(self):
        hrs = D.hours_until_deadline(self._current_sheet)
        if hrs > 0:
            h = int(hrs); m = int((hrs - h) * 60)
            self._deadline_lbl.setText(f"{h}hr {m}m until deadline")
        else:
            self._deadline_lbl.setText("")

    def _refresh_earnings(self):
        C    = self._C
        total = sum(col.get_total_minutes() for col in self._columns)
        gross, net = D.calc_earnings(total, self._current_sheet, self._settings)
        if gross == 0:
            self.earnings_lbl.setText(""); return
        state = self._settings.get("us_state", "CA")
        self.earnings_lbl.setText(f"~${net:,.2f} net  ·  ${gross:,.2f} gross  ({state})")

    def _get_days_remaining(self) -> int:
        """Returns number of calendar days left until (and including) the deadline day."""
        today = date.today()
        try:
            end = date.fromisoformat(self._current_sheet["end_date"])
            deadline_day_name = self._current_sheet.get("deadline_day", "tuesday").lower()
            # Find the deadline date within the sheet week
            days_map = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}
            start = date.fromisoformat(self._current_sheet["start_date"])
            target_weekday = days_map.get(deadline_day_name, 1)
            deadline_date = start + timedelta(days=(target_weekday - start.weekday()) % 7)
            days_left = (deadline_date - today).days
            return max(1, days_left)
        except Exception:
            return 1
    
    def _refresh_marquee(self):
        total       = sum(col.get_total_minutes() for col in self._columns)
        target_mins = int(self._current_sheet.get("target_hours", 40.0) * 60)
        remaining   = max(0, target_mins - total)
        hrs_til     = D.hours_until_deadline(self._current_sheet)
        gross, net  = D.calc_earnings(total, self._current_sheet, self._settings)

        parts = [f"{D.format_hm_pretty(total)} logged this sheet"]
        if remaining:
            parts.append(f"{D.format_hm_pretty(remaining)} to target")
        if hrs_til > 0:
            parts.append(f"{hrs_til:.1f}hr until deadline")
        if net > 0:
            parts.append(f"~${net:,.2f} net earned")
        if remaining > 0 and hrs_til > 0:
            days_left = self._get_days_remaining()
            per_day = remaining / days_left
            deadline_day = self._current_sheet.get("deadline_day", "tuesday").capitalize()
            parts.append(
                f"~{D.format_hm_pretty(int(per_day))}/day to hit target by {deadline_day}"
            )

        self._marquee.set_text("   ·   ".join(parts))

    # ── Navigation ─────────────────────────────────────────────────────────────

    def _prev_sheet(self):
        self._do_save()
        r = D.get_sheet_by_offset(self._data, self._current_key, -1)
        if r:
            self._current_key, self._current_sheet = r
            self._render_sheet()
        # else: button is hidden — shouldn't be called

    def _next_sheet(self):
        self._do_save()
        r = D.get_sheet_by_offset(self._data, self._current_key, +1)
        if r:
            self._current_key, self._current_sheet = r
            self._render_sheet()
        else:
            # Create a new future sheet by advancing one week from current end date
            try:
                cur_end = date.fromisoformat(self._current_sheet["end_date"])
                next_day = cur_end + timedelta(days=1)
            except Exception:
                next_day = date.today() + timedelta(weeks=1)
            self._load_sheet_for_date(next_day)
            self._toast.show_toast("New sheet created", "info")

    def _goto_today(self):
        self._do_save(); self._load_sheet_for_date(date.today())

    # ── Status ─────────────────────────────────────────────────────────────────

    def _show_status_toast(self):
        total       = sum(col.get_total_minutes() for col in self._columns)
        target_mins = int(self._current_sheet.get("target_hours", 40.0) * 60)
        remaining   = max(0, target_mins - total)
        hrs_til     = D.hours_until_deadline(self._current_sheet)
        today_name  = date.today().strftime("%A")
        deadline    = self._current_sheet.get("deadline_day", "tuesday").capitalize()

        if remaining == 0:
            self._toast.show_toast("Target reached — great work!", "success")
        else:
            days_left = self._get_days_remaining()
            per_day = remaining / days_left
            self._toast.show_toast(
                f"{D.format_hm_pretty(remaining)} left · {today_name} · "
                f"{D.format_hm_pretty(int(per_day))}/day to hit goal by {deadline}", "info"
            )

    # ── Notes ──────────────────────────────────────────────────────────────────

    def _position_notes_overlay(self):
        """Cover everything below the topbar."""
        central = self.centralWidget()
        if not central:
            return
        topbar_h = self._topbar_ref.height() if hasattr(self, "_topbar_ref") else 50
        x = 0
        y = topbar_h
        w = central.width()
        h = central.height() - topbar_h
        self._notes_overlay.setGeometry(x, y, w, h)
        self._notes_overlay.raise_()

    def _on_notes_closed(self):
        self._notes_open = False
        self._notes_overlay.hide()

    def _toggle_notes(self):
        if self._notes_open:
            self._notes_overlay.hide(); self._notes_open = False
        else:
            self._position_notes_overlay()
            self._notes_overlay.open_for_sheet(
                self._current_key, self._current_sheet, self._notes_data,
                on_prev=lambda k: D.get_sheet_by_offset(self._data, k, -1),
                on_next=lambda k: D.get_sheet_by_offset(self._data, k, +1),
            )
            self._notes_open = True

    def _on_notes_changed(self, notes: dict):
        self._notes_data = notes
        D.save_notes(self._notes_data, self._settings)

    # ── Sheet override ─────────────────────────────────────────────────────────

    def _open_sheet_override(self):
        dlg = SheetTargetDialog(self._current_sheet, self._C, self)
        dlg.saved.connect(self._on_sheet_override); dlg.exec()

    def _on_sheet_override(self, tgt: float, hourly: float, pay_type: str, salary: float):
        self._current_sheet.update({
            "target_hours": tgt, "hourly_rate": hourly,
            "pay_type": pay_type, "annual_salary": salary,
        })
        D.save_data(self._data, self._settings)
        self._refresh_progress(); self._refresh_earnings()
        self._toast.show_toast("Sheet overrides saved", "success")

    # ── Export ─────────────────────────────────────────────────────────────────

    def _show_export_menu(self):
        C = self._C
        dlg = QDialog(self)
        dlg.setWindowTitle("Export"); dlg.setFixedWidth(260)
        dlg.setStyleSheet(f"""
            QDialog {{ background: {C['surface']}; border: 1px solid {C['border2']}; border-radius: 8px; }}
        """)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16); layout.setSpacing(8)
        layout.addWidget(QLabel("EXPORT") if False else
                         (lambda l: (l.setStyleSheet(
                             f"color:{C['text']};font-size:11px;letter-spacing:2px;"), l)[1])(QLabel("EXPORT")))

        self._export_notes = False
        cb = QCheckBox("Include notes in PDF")
        cb.setStyleSheet(f"color: {C['text2']}; font-size: 11px;")
        cb.stateChanged.connect(lambda s: setattr(self, "_export_notes", bool(s)))
        layout.addWidget(cb)

        for lbl, fn in [
            ("CSV — this sheet",  self._export_csv),
            ("CSV — all sheets",  self._export_all_csv),
            ("PDF — this sheet",  self._export_pdf),
        ]:
            b = QPushButton(lbl)
            b.clicked.connect(lambda _, f=fn: (dlg.close(), f()))
            layout.addWidget(b)
        dlg.exec()

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV",
            str(Path.home() / f"timesheet_sheet{self._current_sheet.get('sheet_num','X')}.csv"),
            "CSV Files (*.csv)"
        )
        if not path: return
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Date","Day","Entry","Minutes","Hours"])
            for col in self._columns:
                for i, mins in enumerate(col.get_entries()):
                    w.writerow([col.day.isoformat(), col.day.strftime("%A"), i+1, mins, round(mins/60,2)])
            total = sum(col.get_total_minutes() for col in self._columns)
            w.writerow([]); w.writerow(["TOTAL","","",total,round(total/60,2)])
        self._toast.show_toast(f"CSV saved: {Path(path).name}", "success")

    def _export_all_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export All", str(Path.home() / "timesheet_all.csv"), "CSV Files (*.csv)"
        )
        if not path: return
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Sheet","Date","Day","Entry","Minutes","Hours"])
            for key, sheet in sorted(self._data.items(), key=lambda x: x[1].get("sheet_num", 0)):
                for ds, entries in sorted(sheet.get("days", {}).items()):
                    d = date.fromisoformat(ds)
                    for i, mins in enumerate(entries):
                        if mins:
                            w.writerow([key,ds,d.strftime("%A"),i+1,mins,round(mins/60,2)])
        self._toast.show_toast(f"All data exported: {Path(path).name}", "success")

    def _export_pdf(self):
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib import colors
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import mm
        except ImportError:
            self._toast.show_toast("pip install reportlab for PDF export", "error"); return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export PDF",
            str(Path.home() / f"timesheet_sheet{self._current_sheet.get('sheet_num','X')}.pdf"),
            "PDF Files (*.pdf)"
        )
        if not path: return

        sheet = self._current_sheet
        doc   = SimpleDocTemplate(path, pagesize=A4,
                                  leftMargin=20*mm, rightMargin=20*mm,
                                  topMargin=20*mm, bottomMargin=20*mm)
        styles = getSampleStyleSheet(); story = []
        try:
            start = date.fromisoformat(sheet["start_date"]); end = date.fromisoformat(sheet["end_date"])
            story.append(Paragraph(
                f"Timesheet — Sheet {sheet.get('sheet_num','?')}  ·  "
                f"{start.strftime('%b %-d')} to {end.strftime('%b %-d, %Y')}", styles["Title"]
            ))
        except Exception:
            story.append(Paragraph("Timesheet", styles["Title"]))
        story.append(Spacer(1, 6*mm))

        td = [["Day","Date","Sessions","Total"]]
        for col in self._columns:
            entries  = col.get_entries()
            sessions = ", ".join(D.format_hm_short(e) for e in entries) or "—"
            td.append([col.day.strftime("%A"), col.day.strftime("%b %-d"), sessions,
                       D.format_hm_pretty(sum(entries)) if entries else "—"])
        td.append(["","","TOTAL", D.format_hm_pretty(sum(col.get_total_minutes() for col in self._columns))])

        table = Table(td, colWidths=[35*mm,25*mm,90*mm,25*mm])
        table.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1a1e29")),
            ("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
            ("FONTSIZE",(0,0),(-1,-1),10),
            ("ROWBACKGROUNDS",(0,1),(-1,-2),[colors.HexColor("#f5f5f5"),colors.white]),
            ("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),
            ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
            ("LEFTPADDING",(0,0),(-1,-1),8),
        ]))
        story.insert(2, table)

        if self._export_notes:
            notes_html = self._notes_data.get(self._current_key, {}).get("general", "")
            if notes_html:
                import re
                plain = re.sub(r'<[^>]+>', '', notes_html)
                story.append(Spacer(1, 6*mm))
                story.append(Paragraph("Notes", styles["Heading2"]))
                story.append(Paragraph(plain, styles["Normal"]))

        doc.build(story)
        self._toast.show_toast(f"PDF saved: {Path(path).name}", "success")

    # ── Settings ───────────────────────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self._settings, self._C, self)
        dlg.settings_saved.connect(self._on_settings_saved); dlg.exec()

    def _on_settings_saved(self, s: dict):
        self._settings = s
        self._C = TH.get_theme(s.get("theme","dark"), s.get("color_overrides",{}))
        self.setStyleSheet(TH.make_stylesheet(self._C))
        self._toast.update_C(self._C); self._toast.update_settings(self._settings)
        self._refresh_progress(); self._refresh_earnings()
        self._toast.show_toast("Settings saved", "success")

    # ── Shortcuts ──────────────────────────────────────────────────────────────

    def _setup_shortcuts(self):
        QShortcut(QKeySequence(self._settings.get("hotkey_notes",   "Ctrl+N")), self).activated.connect(self._toggle_notes)
        QShortcut(QKeySequence(self._settings.get("hotkey_preview",  "Ctrl+P")), self).activated.connect(
            lambda: self._notes_overlay._toggle_preview() if self._notes_open else None
        )

    # ── Resize / close ─────────────────────────────────────────────────────────

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._toast.reanchor()
        if hasattr(self, "_entry_overlay"):
            self._entry_overlay.setGeometry(self.centralWidget().rect())
        if hasattr(self, "_notes_overlay") and self._notes_open:
            self._position_notes_overlay()

    def closeEvent(self, e):
        self._do_save(); super().closeEvent(e)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    import os
    os.environ["QT_WAYLAND_APP_ID"] = "timesheet"
    
    app = QApplication(sys.argv)
    app.setApplicationName("Timesheet")
    for fp in [
        "/usr/share/fonts/TTF/JetBrainsMono-Regular.ttf",
        "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf",
        "/usr/share/fonts/TTF/FiraCode-Regular.ttf",
        "/usr/share/fonts/truetype/firacode/FiraCode-Regular.ttf",
    ]:
        QFontDatabase.addApplicationFont(fp)
    window = TimesheetApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
