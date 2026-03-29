#!/usr/bin/env python3
"""
timesheet.py — main application
"""
import sys
import csv
import json
import time
from datetime import date, timedelta, datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QScrollArea, QFrame, QDialog,
    QFileDialog, QProgressBar, QGraphicsDropShadowEffect,
    QToolButton, QDoubleSpinBox, QComboBox, QSizePolicy,
    QAbstractItemView, QCheckBox, QInputDialog, QMessageBox, QListWidget,
    QListWidgetItem, QDialogButtonBox, QSplitter, QTextEdit, QMenu,
    QWidgetAction
)
from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, QPoint, QMimeData, QByteArray,
    QSize, QRect
)
from PyQt6.QtGui import (
    QFontDatabase, QColor, QShortcut, QKeySequence,
    QPainter, QPen, QDrag, QPixmap, QCursor, QAction
)

import data as D
import theme as TH
from toast import ToastManager
from notes import NotesOverlay
from settings_dialog import SettingsDialog


# ── Workspace helpers ──────────────────────────────────────────────────────────

ALL_WS = "All"

_TIMER_STATE_FILE = D.DEFAULT_DATA_DIR / "timer_state.json"


def _ws_root() -> Path:
    root = D.DEFAULT_DATA_DIR / "workspaces"
    root.mkdir(parents=True, exist_ok=True)
    return root


def list_workspaces() -> list[str]:
    root = _ws_root()
    names = [p.name for p in root.iterdir()
             if p.is_dir() and not p.name.startswith(".") and p.name != ALL_WS]
    names.sort()
    return [ALL_WS] + names


def create_workspace(name: str, color: str = "#4f7cff") -> bool:
    if name == ALL_WS:
        return False
    target = _ws_root() / name
    if target.exists():
        return False
    target.mkdir(parents=True, exist_ok=True)
    cfg = {"color": color, "hourly_rate": 0.0, "pay_type": "hourly",
           "annual_salary": 0.0, "default_target_hours": 40.0}
    (target / "workspace.json").write_text(json.dumps(cfg, indent=2))
    return True


def delete_workspace(name: str) -> bool:
    if name == ALL_WS:
        return False
    import shutil
    target = _ws_root() / name
    if target.exists():
        shutil.rmtree(target)
    return True


def rename_workspace(old: str, new: str) -> bool:
    if old == ALL_WS or new == ALL_WS:
        return False
    root = _ws_root()
    src, dst = root / old, root / new
    if dst.exists() or not src.exists():
        return False
    src.rename(dst)
    return True


def load_workspace_config(name: str) -> dict:
    if name == ALL_WS:
        return {}
    cfg_file = _ws_root() / name / "workspace.json"
    if cfg_file.exists():
        try:
            return json.loads(cfg_file.read_text())
        except Exception:
            pass
    return {"color": "#4f7cff", "hourly_rate": 0.0, "pay_type": "hourly",
            "annual_salary": 0.0, "default_target_hours": 40.0}


def save_workspace_config(name: str, cfg: dict):
    if name == ALL_WS:
        return
    cfg_file = _ws_root() / name / "workspace.json"
    cfg_file.write_text(json.dumps(cfg, indent=2))


def get_workspace_color(name: str) -> str:
    if name == ALL_WS:
        return "#888888"
    return load_workspace_config(name).get("color", "#4f7cff")


def settings_for_workspace(base_settings: dict, workspace: str) -> dict:
    s = dict(base_settings)
    if workspace == ALL_WS:
        s["data_dir"] = str(_ws_root() / "__all_placeholder__")
    else:
        ws_dir = str(_ws_root() / workspace)
        s["data_dir"] = ws_dir
        cfg = load_workspace_config(workspace)
        s["hourly_rate"]          = cfg.get("hourly_rate",          s.get("hourly_rate", 0.0))
        s["pay_type"]             = cfg.get("pay_type",             s.get("pay_type", "hourly"))
        s["annual_salary"]        = cfg.get("annual_salary",        s.get("annual_salary", 0.0))
        s["default_target_hours"] = cfg.get("default_target_hours", s.get("default_target_hours", 40.0))
    return s


def migrate_legacy_data(settings: dict):
    import shutil
    old_data  = D.DEFAULT_DATA_DIR / "data.json"
    old_notes = D.DEFAULT_DATA_DIR / "notes.json"
    if not old_data.exists():
        return
    existing = [p for p in _ws_root().iterdir()
                if p.is_dir() and not p.name.startswith(".") and p.name != ALL_WS]
    if existing:
        return
    create_workspace("Main", "#4f7cff")
    main_dir = _ws_root() / "Main"
    shutil.copy2(old_data, main_dir / "data.json")
    if old_notes.exists():
        shutil.copy2(old_notes, main_dir / "notes.json")


# ── Timer confirm overlay ─────────────────────────────────────────────────────

class TimerConfirmOverlay(QWidget):
    """
    Small modal: asks "append Xhr Ym to today?" — Enter = yes, Esc = no.
    Styled exactly like TimeEntryOverlay.
    """
    confirmed = pyqtSignal()
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
        self._backdrop = QWidget(self)
        self._backdrop.setStyleSheet("background: rgba(0,0,0,0.55);")

        self._card = QWidget(self)
        self._card.setFixedWidth(380)
        self._card.setStyleSheet(f"""
            QWidget {{
                background: {C['surface']}; border-radius: 12px;
                border: 1px solid {C['border2']};
            }}
        """)
        cl = QVBoxLayout(self._card)
        cl.setContentsMargins(28, 24, 28, 24)
        cl.setSpacing(14)

        self._title_lbl = QLabel("Log timer to today?")
        self._title_lbl.setStyleSheet(
            f"color: {C['text2']}; font-size: 11px; letter-spacing: 0.5px; "
            f"background: transparent; border: none;"
        )
        cl.addWidget(self._title_lbl)

        self._duration_lbl = QLabel("0:00:00")
        self._duration_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._duration_lbl.setStyleSheet(
            f"color: {C['accent2']}; font-size: 28px; "
            f"font-family: 'JetBrains Mono', monospace; letter-spacing: 2px; "
            f"background: transparent; border: none;"
        )
        cl.addWidget(self._duration_lbl)

        hint_row = QHBoxLayout(); hint_row.setContentsMargins(0, 0, 0, 0)
        for t in ["Enter — append to today", "Esc — discard"]:
            l = QLabel(t)
            l.setStyleSheet(
                f"color: {C['text3']}; font-size: 10px; background: transparent; border: none;"
            )
            hint_row.addWidget(l); hint_row.addStretch()
        cl.addLayout(hint_row)

        btn_row = QHBoxLayout(); btn_row.setContentsMargins(0, 0, 0, 0); btn_row.setSpacing(8)
        btn_row.addStretch()
        discard = QPushButton("Discard"); discard.setFixedWidth(80)
        discard.clicked.connect(self._cancel); btn_row.addWidget(discard)
        confirm = QPushButton("Append"); confirm.setFixedWidth(80)
        confirm.setStyleSheet(f"""
            QPushButton {{
                background: {C['accent']}; border: none; color: white;
                border-radius: 5px; font-size: 11px;
            }}
            QPushButton:hover {{ background: {C['accent2']}; }}
        """)
        confirm.clicked.connect(self._confirm); btn_row.addWidget(confirm)
        cl.addLayout(btn_row)

        sh = QGraphicsDropShadowEffect()
        sh.setBlurRadius(40); sh.setColor(QColor(0, 0, 0, 200)); sh.setOffset(0, 8)
        self._card.setGraphicsEffect(sh)

    def open(self, elapsed_seconds: int):
        self._committed = False
        h = elapsed_seconds // 3600
        m = (elapsed_seconds % 3600) // 60
        s = elapsed_seconds % 60
        self._duration_lbl.setText(f"{h}:{m:02d}:{s:02d}")
        self._title_lbl.setText("Append timer to today?")
        self._reposition(); self.show(); self.raise_()

    def _reposition(self):
        p = self.parent()
        if not p: return
        pw, ph = p.width(), p.height()
        self._backdrop.setGeometry(0, 0, pw, ph)
        self._card.adjustSize()
        self._card.move((pw - 380) // 2, (ph - self._card.sizeHint().height()) // 2 - 40)

    def _confirm(self):
        if self._committed: return
        self._committed = True
        self.confirmed.emit(); self.hide()

    def _cancel(self):
        self.cancelled.emit(); self.hide()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirm()
        elif e.key() == Qt.Key.Key_Escape:
            self._cancel()
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e):
        if not self._card.geometry().contains(e.pos()):
            self._cancel()
        else:
            super().mousePressEvent(e)

    def resizeEvent(self, e): super().resizeEvent(e); self._reposition()
    def showEvent(self, e):   super().showEvent(e);  self._reposition()


# ── New-workspace overlay ─────────────────────────────────────────────────────

class NewWorkspaceOverlay(QWidget):
    submitted = pyqtSignal(str, str)
    cancelled = pyqtSignal()

    _COLORS = ["#4f7cff", "#ff6b6b", "#43e97b", "#f7971e",
               "#a18cd1", "#fd79a8", "#00cec9", "#fdcb6e"]
    _cidx = 0

    def __init__(self, parent: QWidget, C: dict):
        super().__init__(parent)
        self._C = C
        self._committed = False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet("background: rgba(0,0,0,0);")
        self.hide(); self._build()

    def _build(self):
        C = self._C
        self._backdrop = QWidget(self)
        self._backdrop.setStyleSheet("background: rgba(0,0,0,0.55);")
        self._card = QWidget(self); self._card.setFixedWidth(420)
        self._card.setStyleSheet(f"""
            QWidget {{ background: {C['surface']}; border-radius: 12px; border: 1px solid {C['border2']}; }}
        """)
        cl = QVBoxLayout(self._card); cl.setContentsMargins(28, 24, 28, 24); cl.setSpacing(12)
        self._lbl = QLabel("New workspace name:")
        self._lbl.setStyleSheet(f"color: {C['text2']}; font-size: 11px; background: transparent; border: none;")
        cl.addWidget(self._lbl)
        self.input = QLineEdit(); self.input.setPlaceholderText("Company or project name…")
        self.input.setAlignment(Qt.AlignmentFlag.AlignCenter); self.input.setFixedHeight(52)
        self.input.setStyleSheet(f"""
            QLineEdit {{
                background: {C['surface2']}; border: 1px solid {C['border2']};
                border-radius: 8px; color: {C['text']}; font-size: 22px;
                font-family: 'JetBrains Mono', monospace; padding: 0 16px; letter-spacing: 1px;
            }}
            QLineEdit:focus {{ border-color: {C['accent']}; }}
        """)
        self.input.returnPressed.connect(self._submit); cl.addWidget(self.input)
        crow = QHBoxLayout(); crow.setContentsMargins(0, 0, 0, 0); crow.setSpacing(8)
        clbl = QLabel("Color:"); clbl.setStyleSheet(f"color: {C['text2']}; font-size: 11px; background: transparent; border: none;")
        crow.addWidget(clbl)
        self._swatch = QLabel(); self._swatch.setFixedSize(20, 20); crow.addWidget(self._swatch)
        self._color_inp = QLineEdit(); self._color_inp.setFixedHeight(28)
        self._color_inp.setStyleSheet(f"""
            QLineEdit {{ background: {C['surface2']}; border: 1px solid {C['border2']};
                border-radius: 5px; color: {C['text']}; font-size: 11px; padding: 0 8px; font-family: monospace; }}
            QLineEdit:focus {{ border-color: {C['accent']}; }}
        """)
        self._color_inp.textChanged.connect(self._upd_swatch); crow.addWidget(self._color_inp, 1)
        cyc = QPushButton("↻"); cyc.setFixedSize(28, 28)
        cyc.setStyleSheet(f"""
            QPushButton {{ background: {C['surface2']}; border: 1px solid {C['border2']};
                border-radius: 5px; color: {C['text2']}; font-size: 16px; padding: 0; }}
            QPushButton:hover {{ color: {C['accent']}; }}
        """)
        cyc.clicked.connect(self._cycle); crow.addWidget(cyc); cl.addLayout(crow)
        hrow = QHBoxLayout(); hrow.setContentsMargins(0, 0, 0, 0)
        for t in ["Enter to create", "Esc to cancel"]:
            l = QLabel(t); l.setStyleSheet(f"color: {C['text3']}; font-size: 10px; background: transparent; border: none;")
            hrow.addWidget(l); hrow.addStretch()
        cl.addLayout(hrow)
        sh = QGraphicsDropShadowEffect(); sh.setBlurRadius(40); sh.setColor(QColor(0, 0, 0, 200)); sh.setOffset(0, 8)
        self._card.setGraphicsEffect(sh)

    def open(self):
        self._committed = False; self.input.clear()
        color = self._COLORS[NewWorkspaceOverlay._cidx % len(self._COLORS)]
        self._color_inp.setText(color); self._upd_swatch(color)
        self._reposition(); self.show(); self.raise_(); self.input.setFocus()

    def _cycle(self):
        NewWorkspaceOverlay._cidx += 1
        self._color_inp.setText(self._COLORS[NewWorkspaceOverlay._cidx % len(self._COLORS)])

    def _upd_swatch(self, val):
        if val.startswith("#") and len(val) in (4, 7):
            self._swatch.setStyleSheet(f"background: {val}; border-radius: 4px; border: 1px solid #444;")
        else:
            self._swatch.setStyleSheet("background: #333; border-radius: 4px;")

    def _reposition(self):
        p = self.parent()
        if not p: return
        pw, ph = p.width(), p.height()
        self._backdrop.setGeometry(0, 0, pw, ph)
        self._card.adjustSize()
        cw, ch = 420, self._card.sizeHint().height()
        self._card.move((pw - cw) // 2, (ph - ch) // 2 - 40)

    def _submit(self):
        if self._committed: return
        name = self.input.text().strip()
        if not name: return
        color = self._color_inp.text().strip()
        if not (color.startswith("#") and len(color) in (4, 7)): color = "#4f7cff"
        self._committed = True
        NewWorkspaceOverlay._cidx += 1
        self.submitted.emit(name, color); self.hide()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape: self.cancelled.emit(); self.hide()
        else: super().keyPressEvent(e)

    def mousePressEvent(self, e):
        if not self._card.geometry().contains(e.pos()): self.cancelled.emit(); self.hide()
        else: super().mousePressEvent(e)

    def resizeEvent(self, e): super().resizeEvent(e); self._reposition()
    def showEvent(self, e):   super().showEvent(e);  self._reposition()


# ── Workspace dropdown ────────────────────────────────────────────────────────

class WorkspaceDropdown(QWidget):
    workspace_selected = pyqtSignal(str)

    def __init__(self, C: dict, active: str, parent=None):
        super().__init__(parent)
        self._C = C; self._active = active
        layout = QHBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self._btn = QPushButton(); self._btn.setFixedHeight(32)
        self._btn.clicked.connect(self._show_menu)
        self._btn.setStyleSheet(self._btn_style()); layout.addWidget(self._btn)
        self.update_active(active)

    def _btn_style(self):
        C = self._C
        return f"""
            QPushButton {{
                background: {C['surface2']}; border: 1px solid {C['border2']};
                border-radius: 6px; color: {C['text']}; font-size: 11px;
                padding: 0 16px; letter-spacing: 0.5px; font-weight: 500; min-width: 140px;
            }}
            QPushButton:hover {{ background: {C['surface']}; border-color: {C['accent']}; }}
            QPushButton::menu-indicator {{ width: 0; }}
        """

    def update_active(self, name: str):
        self._active = name; self._btn.setText(f"{name}  ▾")
        self._btn.setStyleSheet(self._btn_style())

    def _show_menu(self):
        C = self._C
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background: {C['surface']}; border: 1px solid {C['border2']};
                border-radius: 8px; padding: 6px 4px; }}
            QMenu::item {{ color: {C['text']}; font-size: 11px;
                padding: 7px 18px 7px 12px; border-radius: 4px; margin: 1px 4px; }}
            QMenu::item:selected {{ background: {C['surface2']}; }}
            QMenu::separator {{ height: 1px; background: {C['border']}; margin: 4px 8px; }}
        """)
        workspaces = list_workspaces()
        for i, name in enumerate(workspaces):
            dot = "◈" if name == ALL_WS else "●"
            label = f" {dot}  {name}" + ("  ✓" if name == self._active else "")
            act = QAction(label, self)
            if i < 9: act.setShortcut(QKeySequence(f"Ctrl+{i+1}"))
            act.triggered.connect(lambda checked, n=name: self.workspace_selected.emit(n))
            menu.addAction(act)
            if name == ALL_WS: menu.addSeparator()
        menu.exec(self._btn.mapToGlobal(QPoint(0, self._btn.height() + 4)))


# ── Time entry overlay ────────────────────────────────────────────────────────

class TimeEntryOverlay(QWidget):
    submitted = pyqtSignal(int)
    cancelled = pyqtSignal()

    def __init__(self, parent: QWidget, C: dict):
        super().__init__(parent)
        self._C = C; self._committed = False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet("background: rgba(0,0,0,0);"); self.hide(); self._build()

    def _build(self):
        C = self._C
        self._backdrop = QWidget(self); self._backdrop.setStyleSheet("background: rgba(0,0,0,0.55);")
        self._card = QWidget(self); self._card.setFixedWidth(420)
        self._card.setStyleSheet(f"""
            QWidget {{ background: {C['surface']}; border-radius: 12px; border: 1px solid {C['border2']}; }}
        """)
        cl = QVBoxLayout(self._card); cl.setContentsMargins(28, 24, 28, 24); cl.setSpacing(12)
        self._day_label = QLabel("Time entry for Today:")
        self._day_label.setStyleSheet(f"color: {C['text2']}; font-size: 11px; background: transparent; border: none;")
        self._day_label.setAlignment(Qt.AlignmentFlag.AlignLeft); cl.addWidget(self._day_label)
        self.input = QLineEdit(); self.input.setPlaceholderText("2:30")
        self.input.setAlignment(Qt.AlignmentFlag.AlignCenter); self.input.setFixedHeight(52)
        self.input.setStyleSheet(f"""
            QLineEdit {{
                background: {C['surface2']}; border: 1px solid {C['border2']};
                border-radius: 8px; color: {C['text']}; font-size: 26px;
                font-family: 'JetBrains Mono', monospace; padding: 0 16px; letter-spacing: 2px;
            }}
            QLineEdit:focus {{ border-color: {C['accent']}; }}
        """)
        self.input.returnPressed.connect(self._submit)
        self.input.textChanged.connect(self._update_preview); cl.addWidget(self.input)
        self._preview = QLabel(""); self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setFixedHeight(22)
        self._preview.setStyleSheet(f"color: {C['accent2']}; font-size: 14px; background: transparent; border: none;")
        cl.addWidget(self._preview)
        hr = QHBoxLayout(); hr.setContentsMargins(0, 0, 0, 0)
        for t, s in [("Enter to save", f"color: {C['text3']}; font-size: 10px;"),
                     ("Esc to cancel", f"color: {C['text3']}; font-size: 10px;")]:
            l = QLabel(t); l.setStyleSheet(f"{s} background: transparent; border: none;")
            hr.addWidget(l); hr.addStretch()
        cl.addLayout(hr)
        sh = QGraphicsDropShadowEffect(); sh.setBlurRadius(40); sh.setColor(QColor(0, 0, 0, 200)); sh.setOffset(0, 8)
        self._card.setGraphicsEffect(sh)

    def open_for_day(self, day: date, initial_text: str = ""):
        self._committed = False
        self._day_label.setText(f"Time entry for {day.strftime('%A, %b %-d')}:")
        self.input.setText(initial_text); self.input.setCursorPosition(len(initial_text))
        self._preview.setText(""); self._reposition()
        self.show(); self.raise_(); self.input.setFocus()
        if initial_text: self._update_preview(initial_text)

    def _reposition(self):
        p = self.parent()
        if not p: return
        pw, ph = p.width(), p.height()
        self._backdrop.setGeometry(0, 0, pw, ph); self._card.adjustSize()
        self._card.move((pw - 420) // 2, (ph - self._card.sizeHint().height()) // 2 - 40)

    def _update_preview(self, text):
        mins = D.parse_time_input(text)
        self._preview.setText(D.format_hm_pretty(mins) if mins and mins > 0 else "")

    def _submit(self):
        if self._committed: return
        mins = D.parse_time_input(self.input.text())
        if mins and mins > 0:
            self._committed = True; self.submitted.emit(mins); self.hide()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape: self.cancelled.emit(); self.hide()
        else: super().keyPressEvent(e)

    def mousePressEvent(self, e):
        if not self._card.geometry().contains(e.pos()): self.cancelled.emit(); self.hide()
        else: super().mousePressEvent(e)

    def resizeEvent(self, e): super().resizeEvent(e); self._reposition()
    def showEvent(self, e):   super().showEvent(e);  self._reposition()


DRAG_MIME = "application/x-timeentry"


# ── Entry widget ──────────────────────────────────────────────────────────────

class EntryWidget(QWidget):
    delete_requested = pyqtSignal(int)
    value_changed    = pyqtSignal(int, int)
    move_requested   = pyqtSignal(int, int)

    def __init__(self, index: int, minutes: int, C: dict, ws_color: str = None, parent=None):
        super().__init__(parent)
        self.index = index; self._minutes = minutes; self._C = C
        self._ws_color = ws_color; self._editing = False; self._drag_start = None
        self.setFixedHeight(32); self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build(); self.setMouseTracking(True)

    def _build(self):
        C = self._C
        layout = QHBoxLayout(self); layout.setContentsMargins(8, 0, 6, 0); layout.setSpacing(4)
        self._handle = QLabel("⠿"); self._handle.setFixedWidth(12)
        self._handle.setStyleSheet(f"color: {C['text3']}; font-size: 11px;")
        self._handle.setCursor(Qt.CursorShape.SizeAllCursor); layout.addWidget(self._handle)
        if self._ws_color:
            dot = QLabel("●"); dot.setFixedWidth(12)
            dot.setStyleSheet(f"color: {self._ws_color}; font-size: 8px;"); layout.addWidget(dot)
        self._num = QLabel(f"{self.index + 1}"); self._num.setFixedWidth(14)
        self._num.setStyleSheet(f"color: {C['text3']}; font-size: 9px;"); layout.addWidget(self._num)
        self._display = QLabel(D.format_hm_pretty(self._minutes))
        self._display.setStyleSheet(f"color: {C['text']}; font-size: 12px;"); layout.addWidget(self._display, 1)
        self._edit = QLineEdit(D.format_hm_short(self._minutes))
        self._edit.setStyleSheet(f"""
            QLineEdit {{ background: {C['surface2']}; border: 1px solid {C['border2']};
                border-radius: 4px; color: {C['accent2']}; font-size: 12px; padding: 1px 4px; }}
            QLineEdit:focus {{ border-color: {C['accent']}; }}
        """)
        self._edit.hide(); self._edit.returnPressed.connect(self._commit_edit)
        self._edit.editingFinished.connect(self._commit_edit); layout.addWidget(self._edit, 1)
        self._del = QPushButton("×"); self._del.setFixedSize(18, 18)
        self._del.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none;
                color: transparent; font-size: 13px; padding: 0; border-radius: 3px; }}
            QPushButton:hover {{ color: {C['red']}; background: rgba(255,90,90,0.12); }}
        """)
        self._del.clicked.connect(lambda: self.delete_requested.emit(self.index)); layout.addWidget(self._del)

    def enterEvent(self, e):
        C = self._C
        self.setStyleSheet(f"""
            EntryWidget {{ background: {C['surface2']}; border-radius: 4px; }}
            EntryWidget * {{ background: transparent; }}
            QPushButton {{ background: transparent; border: none;
                color: {C['text2']}; font-size: 13px; padding: 0; border-radius: 3px; }}
            QPushButton:hover {{ color: {C['red']}; background: rgba(255,90,90,0.12); }}
        """)

    def leaveEvent(self, e):
        if not self._editing: self.setStyleSheet("")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_start = e.pos()
            if not self._editing: self._start_edit()

    def mouseMoveEvent(self, e):
        if (self._drag_start and (e.pos() - self._drag_start).manhattanLength() > 8
                and e.buttons() & Qt.MouseButton.LeftButton):
            self._start_drag()

    def mouseReleaseEvent(self, e): self._drag_start = None

    def _start_edit(self):
        self._editing = True; self._display.hide()
        self._edit.setText(D.format_hm_short(self._minutes))
        self._edit.show(); self._edit.setFocus(); self._edit.selectAll()

    def _commit_edit(self):
        if not self._editing: return
        self._editing = False
        mins = D.parse_time_input(self._edit.text())
        if mins and mins > 0: self._minutes = mins
        self._display.setText(D.format_hm_pretty(self._minutes))
        self._edit.hide(); self._display.show()
        self.value_changed.emit(self.index, self._minutes)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape and self._editing:
            self._editing = False; self._edit.hide(); self._display.show()
        else: super().keyPressEvent(e)

    def _start_drag(self):
        if self._editing: self._commit_edit()
        col = self._find_column()
        if col is None: return
        drag = QDrag(self); mime = QMimeData()
        mime.setData(DRAG_MIME, QByteArray(f"{col.day.isoformat()}|{self.index}|{self._minutes}".encode()))
        drag.setMimeData(mime)
        pm = QPixmap(self.size()); pm.fill(QColor(0, 0, 0, 0)); self.render(pm)
        drag.setPixmap(pm)
        drag.setHotSpot(self._drag_start or QPoint(self.width() // 2, self.height() // 2))
        drag.exec(Qt.DropAction.MoveAction)

    def _find_column(self):
        w = self.parent()
        while w:
            if isinstance(w, DayColumn): return w
            w = w.parent()
        return None

    def get_minutes(self) -> int: return self._minutes
    def set_index(self, i: int): self.index = i; self._num.setText(str(i + 1))


# ── Day column ────────────────────────────────────────────────────────────────

class DayColumn(QWidget):
    data_changed = pyqtSignal()
    hovered_day  = pyqtSignal(date, bool)

    def __init__(self, day: date, entries: list, C: dict, is_today: bool,
                 read_only: bool = False, parent=None):
        super().__init__(parent)
        self.day = day; self._C = C; self._is_today = is_today
        self._read_only = read_only; self._hovered = False
        self.setAcceptDrops(not read_only); self.setMouseTracking(True)
        self._entries: list[int] = []; self._entry_colors: list[str | None] = []
        for e in entries:
            if isinstance(e, tuple): self._entries.append(e[0]); self._entry_colors.append(e[1])
            else: self._entries.append(e); self._entry_colors.append(None)
        self._entry_widgets: list[EntryWidget] = []; self._build()

    def _build(self):
        C = self._C
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0); self._main_layout.setSpacing(0)
        header = QWidget(); header.setFixedHeight(52)
        header.setStyleSheet(f"background: {C['surface']};")
        hl = QVBoxLayout(header); hl.setContentsMargins(10, 10, 10, 8); hl.setSpacing(2)
        color     = C['accent']  if self._is_today else C['text2']
        num_color = C['accent2'] if self._is_today else C['text3']
        day_lbl = QLabel(self.day.strftime("%a").upper())
        day_lbl.setStyleSheet(f"color: {color}; font-size: 9px; letter-spacing: 2px;"); hl.addWidget(day_lbl)
        num_lbl = QLabel(self.day.strftime("%-d"))
        num_lbl.setStyleSheet(f"color: {num_color}; font-size: 22px; font-weight: 300;"); hl.addWidget(num_lbl)
        self._main_layout.addWidget(header)
        self._entries_container = QWidget(); self._entries_container.setStyleSheet("background: transparent;")
        self._entries_layout = QVBoxLayout(self._entries_container)
        self._entries_layout.setContentsMargins(4, 4, 4, 4); self._entries_layout.setSpacing(1)
        self._entries_layout.addStretch()
        scroll = QScrollArea(); scroll.setWidget(self._entries_container); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._main_layout.addWidget(scroll, 1); self._rebuild_entries()
        self._total_area = QWidget(); self._total_area.setFixedHeight(46)
        self._total_area.setStyleSheet(f"background: {C['surface']};")
        tl = QVBoxLayout(self._total_area); tl.setContentsMargins(10, 6, 10, 6); tl.setSpacing(1)
        tot_hint = QLabel("TOTAL")
        tot_hint.setStyleSheet(f"color: {C['text3']}; font-size: 8px; letter-spacing: 1.5px;"); tl.addWidget(tot_hint)
        self.total_lbl = QLabel(D.format_hm_pretty(sum(self._entries)))
        self.total_lbl.setStyleSheet(f"color: {C['text']}; font-size: 13px; font-weight: 500;"); tl.addWidget(self.total_lbl)
        self._main_layout.addWidget(self._total_area)

    def _rebuild_entries(self):
        for w in self._entry_widgets: self._entries_layout.removeWidget(w); w.deleteLater()
        self._entry_widgets.clear()
        for i, mins in enumerate(self._entries):
            if not mins: continue
            ws_color = self._entry_colors[i] if i < len(self._entry_colors) else None
            ew = EntryWidget(i, mins, self._C, ws_color=ws_color)
            if not self._read_only:
                ew.delete_requested.connect(self._delete_entry)
                ew.value_changed.connect(self._on_entry_edited)
            self._entries_layout.insertWidget(self._entries_layout.count() - 1, ew)
            self._entry_widgets.append(ew)

    def _delete_entry(self, index: int):
        for i, ew in enumerate(self._entry_widgets):
            if ew.index == index:
                self._entries.pop(i)
                if i < len(self._entry_colors): self._entry_colors.pop(i)
                break
        self._rebuild_entries(); self._refresh_total(); self.data_changed.emit()

    def _on_entry_edited(self, index: int, minutes: int):
        for i, ew in enumerate(self._entry_widgets):
            if ew.index == index:
                if i < len(self._entries): self._entries[i] = minutes
                break
        self._refresh_total(); self.data_changed.emit()

    def add_entry(self, minutes: int):
        self._entries.append(minutes); self._entry_colors.append(None)
        ew = EntryWidget(len(self._entries) - 1, minutes, self._C)
        ew.delete_requested.connect(self._delete_entry); ew.value_changed.connect(self._on_entry_edited)
        self._entries_layout.insertWidget(self._entries_layout.count() - 1, ew)
        self._entry_widgets.append(ew); self._refresh_total(); self.data_changed.emit()

    def remove_entry_at(self, idx: int):
        if 0 <= idx < len(self._entries): self._entries.pop(idx)
        if 0 <= idx < len(self._entry_colors): self._entry_colors.pop(idx)
        self._rebuild_entries(); self._refresh_total(); self.data_changed.emit()

    def _refresh_total(self):
        self.total_lbl.setText(D.format_hm_pretty(sum(self._entries)))

    def get_entries(self) -> list[int]: return [e for e in self._entries if e > 0]
    def get_total_minutes(self) -> int: return sum(e for e in self._entries if e > 0)

    def set_hovered(self, on: bool):
        C = self._C; col = C.get("col_hover", C.get("surface2", "#1e2235"))
        self._entries_container.setStyleSheet(f"background: {col};" if on else "background: transparent;")
        self.setAutoFillBackground(on)
        if on:
            pal = self.palette(); pal.setColor(self.backgroundRole(), QColor(col)); self.setPalette(pal)
        else:
            self.setAutoFillBackground(False)

    def enterEvent(self, e): self._hovered = True; self.set_hovered(True); self.hovered_day.emit(self.day, True)
    def leaveEvent(self, e): self._hovered = False; self.set_hovered(False); self.hovered_day.emit(self.day, False)

    def dragEnterEvent(self, e):
        if not self._read_only and e.mimeData().hasFormat(DRAG_MIME):
            e.acceptProposedAction(); self.set_hovered(True)

    def dragLeaveEvent(self, e):
        if not self._hovered: self.set_hovered(False)

    def dropEvent(self, e):
        if self._read_only or not e.mimeData().hasFormat(DRAG_MIME): return
        payload = e.mimeData().data(DRAG_MIME).data().decode()
        try:
            src_day_str, src_idx_str, mins_str = payload.split("|")
            src_idx = int(src_idx_str); mins = int(mins_str)
        except Exception: return
        e.acceptProposedAction()
        for col in self.window()._columns:
            if col.day.isoformat() == src_day_str: col.remove_entry_at(src_idx); break
        self.add_entry(mins)


# ── Marquee ───────────────────────────────────────────────────────────────────

class MarqueeLabel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""; self._offset = 0.0; self._speed = 0.4; self._text_w = 0; self._gap = 80
        self._timer = QTimer(self); self._timer.timeout.connect(self._tick); self._timer.start(16)
        self.setFixedHeight(16); self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    def set_text(self, text: str):
        self._text = text; self._offset = 0.0
        self._text_w = self.fontMetrics().horizontalAdvance(text); self.update()

    def _tick(self):
        if not self._text or not self._text_w: return
        self._offset = (self._offset + self._speed) % (self._text_w + self._gap); self.update()

    def paintEvent(self, event):
        if not self._text: return
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        C = getattr(self, "_C", None)
        painter.setPen(QColor(C.get("text3", "#3a3e50")) if C else self.palette().color(self.foregroundRole()))
        painter.setFont(self.font()); fm = self.fontMetrics()
        y = fm.ascent() + (self.height() - fm.height()) // 2
        total = self._text_w + self._gap; x = -int(self._offset)
        while x < self.width(): painter.drawText(x, y, self._text); x += total
        painter.end()


# ── Sheet target override ─────────────────────────────────────────────────────

class SheetTargetDialog(QDialog):
    saved = pyqtSignal(float, float, str, float)

    def __init__(self, sheet: dict, C: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sheet Override"); self.setFixedWidth(340); self.setModal(True)
        self.setStyleSheet(f"QDialog {{ background: {C['surface']}; border: 1px solid {C['border2']}; border-radius: 8px; }}")
        layout = QVBoxLayout(self); layout.setContentsMargins(20, 20, 20, 20); layout.setSpacing(12)
        title = QLabel("SHEET OVERRIDES"); title.setStyleSheet(f"color: {C['text']}; font-size: 11px; letter-spacing: 2px;"); layout.addWidget(title)
        note = QLabel("Overrides workspace defaults for this sheet only."); note.setStyleSheet(f"color: {C['text3']}; font-size: 10px;"); note.setWordWrap(True); layout.addWidget(note)
        def mk(lbl_text, widget):
            r = QWidget(); r.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(r); rl.setContentsMargins(0,0,0,0); rl.setSpacing(12)
            l = QLabel(lbl_text); l.setStyleSheet(f"color: {C['text2']}; font-size: 11px;"); l.setFixedWidth(130)
            rl.addWidget(l); rl.addWidget(widget, 1); return r
        self.target_hrs = QDoubleSpinBox(); self.target_hrs.setRange(0, 168); self.target_hrs.setDecimals(1)
        self.target_hrs.setSuffix(" hrs"); self.target_hrs.setValue(sheet.get("target_hours", 40.0))
        self.target_hrs.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons); layout.addWidget(mk("Target Hours", self.target_hrs))
        self.pay_type = QComboBox(); self.pay_type.addItems(["Hourly", "Salary"])
        self.pay_type.setCurrentText(sheet.get("pay_type", "hourly").capitalize()); layout.addWidget(mk("Pay Type", self.pay_type))
        self.hourly = QDoubleSpinBox(); self.hourly.setRange(0, 10000); self.hourly.setDecimals(2)
        self.hourly.setPrefix("$ "); self.hourly.setValue(sheet.get("hourly_rate", 0.0))
        self.hourly.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons); layout.addWidget(mk("Hourly Rate", self.hourly))
        self.salary = QDoubleSpinBox(); self.salary.setRange(0, 10_000_000); self.salary.setDecimals(2)
        self.salary.setPrefix("$ "); self.salary.setSingleStep(1000); self.salary.setValue(sheet.get("annual_salary", 0.0))
        self.salary.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons); layout.addWidget(mk("Annual Salary", self.salary))
        br = QHBoxLayout(); br.addStretch()
        cancel = QPushButton("Cancel"); cancel.setFixedWidth(70); cancel.clicked.connect(self.reject); br.addWidget(cancel)
        save = QPushButton("Save"); save.setFixedWidth(70)
        save.setStyleSheet(f"QPushButton {{ background: {C['accent']}; border: none; color: white; border-radius: 5px; font-size: 11px; }} QPushButton:hover {{ background: {C['accent2']}; }}")
        save.clicked.connect(self._save); br.addWidget(save); layout.addLayout(br)

    def _save(self):
        self.saved.emit(self.target_hrs.value(), self.hourly.value(),
                        self.pay_type.currentText().lower(), self.salary.value()); self.accept()


# ── Workspace settings dialog ─────────────────────────────────────────────────

class WorkspaceSettingsDialog(QDialog):
    saved = pyqtSignal(dict)

    def __init__(self, name: str, cfg: dict, C: dict, parent=None):
        super().__init__(parent)
        self._name = name
        self.setWindowTitle(f"Workspace: {name}"); self.setFixedWidth(400); self.setModal(True)
        self.setStyleSheet(f"QDialog {{ background: {C['surface']}; border: 1px solid {C['border2']}; border-radius: 8px; }} QLabel {{ background: transparent; }}")
        layout = QVBoxLayout(self); layout.setContentsMargins(24, 20, 24, 20); layout.setSpacing(10)
        title = QLabel(f"WORKSPACE — {name.upper()}"); title.setStyleSheet(f"color: {C['text']}; font-size: 10px; letter-spacing: 2px;"); layout.addWidget(title)
        def mk(lbl_text, widget):
            r = QWidget(); r.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(r); rl.setContentsMargins(0,0,0,0); rl.setSpacing(12)
            l = QLabel(lbl_text); l.setStyleSheet(f"color: {C['text2']}; font-size: 11px;"); l.setFixedWidth(160)
            rl.addWidget(l); rl.addWidget(widget, 1); return r
        crow = QWidget(); crow.setStyleSheet("background: transparent;")
        cr = QHBoxLayout(crow); cr.setContentsMargins(0,0,0,0); cr.setSpacing(8)
        cl_lbl = QLabel("Workspace Color"); cl_lbl.setStyleSheet(f"color: {C['text2']}; font-size: 11px;"); cl_lbl.setFixedWidth(160); cr.addWidget(cl_lbl)
        self._swatch = QLabel(); self._swatch.setFixedSize(20, 20); cr.addWidget(self._swatch)
        self._color_inp = QLineEdit(cfg.get("color", "#4f7cff"))
        self._color_inp.setStyleSheet(f"QLineEdit {{ background: {C['surface2']}; border: 1px solid {C['border2']}; border-radius: 5px; color: {C['text']}; font-size: 11px; padding: 0 8px; font-family: monospace; }}")
        self._color_inp.textChanged.connect(self._upd_swatch); self._upd_swatch(cfg.get("color", "#4f7cff"))
        cr.addWidget(self._color_inp, 1); layout.addWidget(crow)
        self._name_inp = QLineEdit(name)
        self._name_inp.setStyleSheet(f"QLineEdit {{ background: {C['surface2']}; border: 1px solid {C['border2']}; border-radius: 5px; color: {C['text']}; font-size: 11px; padding: 2px 8px; }}")
        layout.addWidget(mk("Rename workspace", self._name_inp))
        self.pay_type = QComboBox(); self.pay_type.addItems(["Hourly", "Salary"])
        self.pay_type.setCurrentText(cfg.get("pay_type", "hourly").capitalize()); layout.addWidget(mk("Default Pay Type", self.pay_type))
        self.hourly = QDoubleSpinBox(); self.hourly.setRange(0, 10000); self.hourly.setDecimals(2)
        self.hourly.setPrefix("$ "); self.hourly.setValue(cfg.get("hourly_rate", 0.0))
        self.hourly.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons); layout.addWidget(mk("Default Hourly Rate", self.hourly))
        self.salary = QDoubleSpinBox(); self.salary.setRange(0, 10_000_000); self.salary.setDecimals(2)
        self.salary.setPrefix("$ "); self.salary.setSingleStep(1000); self.salary.setValue(cfg.get("annual_salary", 0.0))
        self.salary.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons); layout.addWidget(mk("Default Annual Salary", self.salary))
        self.target = QDoubleSpinBox(); self.target.setRange(0, 168); self.target.setDecimals(1)
        self.target.setSuffix(" hrs"); self.target.setValue(cfg.get("default_target_hours", 40.0))
        self.target.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons); layout.addWidget(mk("Default Target Hours", self.target))
        br = QHBoxLayout(); br.addStretch()
        self._del_btn = QPushButton("Delete workspace")
        self._del_btn.setStyleSheet(f"QPushButton {{ background: transparent; border: 1px solid {C['red']}; border-radius: 5px; color: {C['red']}; font-size: 10px; padding: 4px 10px; }} QPushButton:hover {{ background: {C['red']}; color: #fff; }}")
        self._del_btn.clicked.connect(self._confirm_delete); br.addWidget(self._del_btn); br.addStretch()
        cancel = QPushButton("Cancel"); cancel.setFixedWidth(70); cancel.clicked.connect(self.reject); br.addWidget(cancel)
        save = QPushButton("Save"); save.setFixedWidth(70)
        save.setStyleSheet(f"QPushButton {{ background: {C['accent']}; border: none; color: white; border-radius: 5px; font-size: 11px; }} QPushButton:hover {{ background: {C['accent2']}; }}")
        save.clicked.connect(self._save); br.addWidget(save); layout.addLayout(br)

    def _upd_swatch(self, val):
        if val.startswith("#") and len(val) in (4, 7):
            self._swatch.setStyleSheet(f"background: {val}; border-radius: 4px; border: 1px solid #444;")
        else:
            self._swatch.setStyleSheet("background: #333; border-radius: 4px;")

    def _confirm_delete(self):
        self.saved.emit({"__delete__": True}); self.accept()

    def _save(self):
        self.saved.emit({
            "name": self._name_inp.text().strip() or self._name,
            "color": self._color_inp.text().strip(),
            "pay_type": self.pay_type.currentText().lower(),
            "hourly_rate": self.hourly.value(),
            "annual_salary": self.salary.value(),
            "default_target_hours": self.target.value(),
        }); self.accept()


# ── Main window ───────────────────────────────────────────────────────────────

class TimesheetApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Timesheet")
        self.setMinimumSize(680, 560); self.resize(900, 660)

        self._settings = D.load_settings()
        migrate_legacy_data(self._settings)

        real_ws = [p for p in _ws_root().iterdir()
                   if p.is_dir() and not p.name.startswith(".") and p.name != ALL_WS]
        if not real_ws: create_workspace("Main", "#4f7cff")

        available = list_workspaces()
        startup = self._settings.get("startup_workspace", "")
        last    = self._settings.get("last_workspace", "")
        if startup and startup in available: self._active_workspace = startup
        elif last and last in available:     self._active_workspace = last
        else: self._active_workspace = available[1] if len(available) > 1 else available[0]

        self._ws_settings = settings_for_workspace(self._settings, self._active_workspace)
        self._data        = self._load_ws_data(self._active_workspace)
        self._notes_data  = D.load_notes(self._ws_settings) if self._active_workspace != ALL_WS else {}
        self._C           = TH.get_theme(self._settings.get("theme", "dark"),
                                         self._settings.get("color_overrides", {}))
        self._current_key   = ""
        self._current_sheet: dict = {}
        self._columns: list[DayColumn] = []
        self._notes_open  = False
        self._hovered_day: date | None = None
        self._all_week_start: date = date.today()

        # ── Timer state ───────────────────────────────────────────────────
        self._timer_elapsed  = 0       # accumulated seconds
        self._timer_start_ts: float | None = None  # wall time of current run
        self._timer_tick = QTimer(); self._timer_tick.setInterval(1000)
        self._timer_tick.timeout.connect(self._timer_on_tick)
        self._timer_blink_state = False
        self._timer_blink = QTimer(); self._timer_blink.setInterval(600)
        self._timer_blink.timeout.connect(self._timer_blink_tick)

        self._save_timer = QTimer(); self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._do_save)

        self._build_ui()
        self._setup_shortcuts()
        self._timer_restore()
        self._load_sheet_for_date(date.today())

    # ── Data helpers ──────────────────────────────────────────────────────

    def _load_ws_data(self, ws: str) -> dict:
        if ws == ALL_WS: return {}
        return D.load_data(settings_for_workspace(self._settings, ws))

    def _all_ws_data(self) -> dict:
        result = {}
        for name in list_workspaces():
            if name == ALL_WS: continue
            ws_s  = settings_for_workspace(self._settings, name)
            data  = D.load_data(ws_s); color = get_workspace_color(name)
            result[name] = (data, color)
        return result

    def _build_all_week_entries(self, week_start: date) -> dict:
        days = {(week_start + timedelta(days=i)).isoformat(): [] for i in range(7)}
        week_end = week_start + timedelta(days=6)
        for name, (data, color) in self._all_ws_data().items():
            for key, sheet in data.items():
                try:
                    s = date.fromisoformat(sheet["start_date"]); e = date.fromisoformat(sheet["end_date"])
                except Exception: continue
                if s > week_end or e < week_start: continue
                for ds, entries in sheet.get("days", {}).items():
                    if ds in days:
                        for m in entries:
                            if m: days[ds].append((m, color))
        return days

    # ── UI build ──────────────────────────────────────────────────────────

    def _build_ui(self):
        C = self._C
        self.setStyleSheet(TH.make_stylesheet(C))
        self._toast = ToastManager(self, C, self._settings)

        central = QWidget(); self.setCentralWidget(central)
        root = QHBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        main_col = QWidget()
        ml = QVBoxLayout(main_col); ml.setContentsMargins(0,0,0,0); ml.setSpacing(0)

        self._topbar_ref = self._mk_topbar()
        ml.addWidget(self._topbar_ref)
        ml.addWidget(self._mk_marquee_bar())
        ml.addWidget(self._mk_nav())
        ml.addWidget(self._mk_progress())

        self.columns_widget = QWidget()
        self.columns_widget.setStyleSheet(f"background: {C['bg']};")
        self.columns_layout = QHBoxLayout(self.columns_widget)
        self.columns_layout.setContentsMargins(0,0,0,0); self.columns_layout.setSpacing(0)
        ml.addWidget(self.columns_widget, 1)
        root.addWidget(main_col, 1)

        # Notes overlay — child of central, positioned after topbar
        self._notes_overlay = NotesOverlay(central, C, self._settings)
        self._notes_overlay.notes_changed.connect(self._on_notes_changed)
        self._notes_overlay.closed.connect(self._on_notes_closed)
        self._notes_overlay.hide()

        self._entry_overlay = TimeEntryOverlay(central, C)
        self._entry_overlay.setGeometry(central.rect()); self._entry_overlay.hide()

        self._new_ws_overlay = NewWorkspaceOverlay(central, C)
        self._new_ws_overlay.setGeometry(central.rect())
        self._new_ws_overlay.submitted.connect(self._on_new_workspace_created)
        self._new_ws_overlay.hide()

        # Timer confirm popup — child of central
        self._timer_confirm = TimerConfirmOverlay(central, C)
        self._timer_confirm.confirmed.connect(self._timer_do_log)
        self._timer_confirm.cancelled.connect(self._timer_do_discard)
        self._timer_confirm.hide()

    # ── Topbar ────────────────────────────────────────────────────────────

    def _mk_topbar(self) -> QWidget:
        C = self._C
        bar = QWidget(); bar.setFixedHeight(50)
        bar.setStyleSheet(f"background: {C['surface']}; border-bottom: 1px solid {C['border']};")
        layout = QHBoxLayout(bar); layout.setContentsMargins(16, 0, 14, 0); layout.setSpacing(6)
        title = QLabel("TIMESHEET")
        title.setStyleSheet(f"color: {C['text']}; font-size: 12px; font-weight: 700; letter-spacing: 5px;")
        layout.addWidget(title); layout.addStretch(1)
        self._ws_dropdown = WorkspaceDropdown(C, self._active_workspace)
        self._ws_dropdown.workspace_selected.connect(self._switch_workspace)
        layout.addWidget(self._ws_dropdown); layout.addStretch(1)
        self.earnings_lbl = QLabel("")
        self.earnings_lbl.setStyleSheet(f"color: {C['green']}; font-size: 11px;")
        layout.addWidget(self.earnings_lbl); layout.addSpacing(8)
        def tbtn(sym, tip, cb):
            b = QToolButton(); b.setText(sym); b.setToolTip(tip)
            b.setFixedSize(34, 34); b.clicked.connect(cb); return b
        layout.addWidget(tbtn("✎", "Notes (Ctrl+N)",      self._toggle_notes))
        layout.addWidget(tbtn("◎", "Sheet overrides",     self._open_sheet_override))
        layout.addWidget(tbtn("⧖", "Status",               self._show_status_toast))
        layout.addWidget(tbtn("⤓", "Export",               self._show_export_menu))
        layout.addWidget(tbtn("⊞", "Workspace settings",  self._open_workspace_settings))
        layout.addWidget(tbtn("+", "New workspace",        self._open_new_workspace_overlay))
        layout.addWidget(tbtn("⚙", "Settings",             self._open_settings))
        return bar

    # ── Marquee bar ───────────────────────────────────────────────────────

    def _mk_marquee_bar(self) -> QWidget:
        C = self._C; bar = QWidget(); bar.setFixedHeight(26); bar.setStyleSheet(f"background: {C['bg']};")
        layout = QHBoxLayout(bar); layout.setContentsMargins(20, 0, 20, 0); layout.setSpacing(12)
        self._marquee = MarqueeLabel(); self._marquee._C = C
        from PyQt6.QtGui import QFont as _QF
        self._marquee.setFont(_QF("JetBrains Mono", 9))
        self._marquee.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._marquee, 1)
        self._deadline_lbl = QLabel("")
        self._deadline_lbl.setStyleSheet(f"color: {C['text3']}; font-size: 10px;")
        self._deadline_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._deadline_lbl); return bar

    # ── Nav bar (with built-in timer) ─────────────────────────────────────

    def _mk_nav(self) -> QWidget:
        C = self._C
        nav = QWidget(); nav.setFixedHeight(42)
        nav.setStyleSheet(f"background: {C['surface']};")
        layout = QHBoxLayout(nav); layout.setContentsMargins(16, 0, 16, 0); layout.setSpacing(8)

        self._prev_btn = QPushButton("‹   Prev"); self._prev_btn.setFixedWidth(88)
        self._prev_btn.clicked.connect(self._prev_sheet); layout.addWidget(self._prev_btn)

        self.sheet_lbl = QLabel("")
        self.sheet_lbl.setStyleSheet(f"color: {C['text2']}; font-size: 11px; letter-spacing: 0.5px;")
        self.sheet_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(self.sheet_lbl, 1)

        # ── Timer section (left of go-to-today) ──────────────────────────
        timer_container = QWidget(); timer_container.setStyleSheet("background: transparent;")
        tl = QHBoxLayout(timer_container); tl.setContentsMargins(0, 0, 0, 0); tl.setSpacing(4)

        # Time display — monospace, fixed width to prevent layout shift
        self._timer_lbl = QLabel("0:00:00")
        self._timer_lbl.setStyleSheet(
            f"color: {C['text3']}; font-size: 11px; "
            f"font-family: 'JetBrains Mono', monospace; min-width: 54px;"
        )
        self._timer_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        tl.addWidget(self._timer_lbl)

        # Play / pause button
        self._timer_play_btn = QPushButton("▶")
        self._timer_play_btn.setFixedSize(28, 28)
        self._timer_play_btn.setToolTip("Start timer")
        self._timer_play_btn.clicked.connect(self._timer_toggle)
        self._timer_play_btn.setStyleSheet(self._timer_btn_style(running=False))
        tl.addWidget(self._timer_play_btn)

        # Stop / confirm button (only visible while running or paused with time)
        self._timer_stop_btn = QPushButton("■")
        self._timer_stop_btn.setFixedSize(28, 28)
        self._timer_stop_btn.setToolTip("Stop and log")
        self._timer_stop_btn.clicked.connect(self._timer_stop)
        self._timer_stop_btn.setStyleSheet(self._timer_stop_style())
        self._timer_stop_btn.hide()
        tl.addWidget(self._timer_stop_btn)

        layout.addWidget(timer_container)

        # Go to today
        today_btn = QToolButton(); today_btn.setText("⊙"); today_btn.setToolTip("Go to today")
        today_btn.setFixedSize(38, 32)
        today_btn.setStyleSheet(f"""
            QToolButton {{ font-size: 22px; background: transparent; border: none;
                color: {C['text2']}; border-radius: 5px; padding: 0; }}
            QToolButton:hover {{ color: {C['accent']}; background: {C['surface2']}; }}
        """)
        today_btn.clicked.connect(self._goto_today); layout.addWidget(today_btn)

        next_btn = QPushButton("Next   ›"); next_btn.setFixedWidth(88)
        next_btn.clicked.connect(self._next_sheet); layout.addWidget(next_btn)
        return nav

    def _timer_btn_style(self, running: bool) -> str:
        C = self._C
        if running:
            return f"""
                QPushButton {{
                    background: transparent; border: none;
                    color: {C.get('red','#ff5a5a')}; font-size: 9px;
                    border-radius: 14px; padding: 0;
                }}
                QPushButton:hover {{ background: {C.get('red','#ff5a5a')}22; }}
            """
        return f"""
            QPushButton {{
                background: transparent; border: none;
                color: {C['text3']}; font-size: 9px; border-radius: 14px; padding: 0;
            }}
            QPushButton:hover {{ color: {C['text2']}; background: {C['surface2']}; }}
        """

    def _timer_stop_style(self) -> str:
        C = self._C
        return f"""
            QPushButton {{
                background: transparent; border: none;
                color: {C['text3']}; font-size: 9px; border-radius: 14px; padding: 0;
            }}
            QPushButton:hover {{ color: {C.get('orange','#ffaa33')}; background: {C['surface2']}; }}
        """

    # ── Timer logic ───────────────────────────────────────────────────────

    def _timer_restore(self):
        """Load persisted timer state on startup."""
        if not _TIMER_STATE_FILE.exists(): return
        try:
            state = json.loads(_TIMER_STATE_FILE.read_text())
            self._timer_elapsed = state.get("elapsed", 0)
            if state.get("running") and state.get("started_at"):
                wall = time.time() - state["started_at"]
                self._timer_elapsed += int(wall)
                self._timer_start_ts = time.time()
                self._timer_tick.start(); self._timer_blink.start()
                self._timer_play_btn.setText("⏸")
                self._timer_play_btn.setStyleSheet(self._timer_btn_style(running=True))
                self._timer_stop_btn.show()
            elif self._timer_elapsed > 0:
                self._timer_stop_btn.show()
            self._timer_update_label()
        except Exception:
            pass

    def _timer_persist(self):
        D.DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
        _TIMER_STATE_FILE.write_text(json.dumps({
            "running":    self._timer_start_ts is not None,
            "elapsed":    self._timer_elapsed,
            "started_at": self._timer_start_ts,
        }))

    def _timer_toggle(self):
        """Start or pause the timer."""
        if self._timer_start_ts is not None:
            # Pause
            self._timer_elapsed += int(time.time() - self._timer_start_ts)
            self._timer_start_ts = None
            self._timer_tick.stop(); self._timer_blink.stop()
            self._timer_play_btn.setText("▶")
            self._timer_play_btn.setStyleSheet(self._timer_btn_style(running=False))
            self._timer_update_label()
        else:
            # Start / resume
            self._timer_start_ts = time.time()
            self._timer_tick.start(); self._timer_blink.start()
            self._timer_play_btn.setText("⏸")
            self._timer_play_btn.setStyleSheet(self._timer_btn_style(running=True))
            self._timer_stop_btn.show()
        self._timer_persist()

    def _timer_stop(self):
        """Show confirm popup."""
        if self._timer_start_ts is not None:
            self._timer_elapsed += int(time.time() - self._timer_start_ts)
            self._timer_start_ts = None
            self._timer_tick.stop(); self._timer_blink.stop()
            self._timer_play_btn.setText("▶")
            self._timer_play_btn.setStyleSheet(self._timer_btn_style(running=False))
        total_secs = self._timer_elapsed
        # Show confirm overlay
        central = self.centralWidget()
        self._timer_confirm.setGeometry(central.rect())
        self._timer_confirm.open(total_secs)
        self._timer_confirm.raise_()

    def _timer_do_log(self):
        """Confirmed: append to today."""
        minutes = max(1, self._timer_elapsed // 60)
        today = date.today()
        # Ensure we're on today's sheet
        if self._active_workspace != ALL_WS:
            key_check = None
            for key, sheet in self._data.items():
                try:
                    s = date.fromisoformat(sheet["start_date"]); e = date.fromisoformat(sheet["end_date"])
                    if s <= today <= e: key_check = key; break
                except Exception: pass
            if key_check != self._current_key:
                self._do_save(); self._load_sheet_for_date(today)
        col = self._col_for_day(today)
        if col:
            col.add_entry(minutes)
            self._toast.show_toast(f"Timer: {D.format_hm_pretty(minutes)} logged to today", "success")
        self._timer_reset()

    def _timer_do_discard(self):
        """Discarded: just reset."""
        self._timer_reset()

    def _timer_reset(self):
        self._timer_elapsed = 0; self._timer_start_ts = None
        self._timer_tick.stop(); self._timer_blink.stop()
        self._timer_play_btn.setText("▶")
        self._timer_play_btn.setStyleSheet(self._timer_btn_style(running=False))
        self._timer_stop_btn.hide()
        self._timer_lbl.setText("0:00:00")
        self._timer_lbl.setStyleSheet(
            f"color: {self._C['text3']}; font-size: 11px; "
            f"font-family: 'JetBrains Mono', monospace; min-width: 54px;"
        )
        if _TIMER_STATE_FILE.exists(): _TIMER_STATE_FILE.unlink()

    def _timer_on_tick(self):
        self._timer_update_label(); self._timer_persist()

    def _timer_blink_tick(self):
        """Make the record dot blink red."""
        self._timer_blink_state = not self._timer_blink_state
        C = self._C
        if self._timer_blink_state:
            self._timer_play_btn.setText("⏸")
            color = C.get("red", "#ff5a5a")
        else:
            self._timer_play_btn.setText("⏸")
            color = C.get("red", "#ff5a5a") + "66"  # dimmed
        self._timer_play_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {color}; font-size: 9px; border-radius: 14px; padding: 0;
            }}
            QPushButton:hover {{ background: {C.get('red','#ff5a5a')}22; }}
        """)

    def _timer_update_label(self):
        total = self._timer_elapsed
        if self._timer_start_ts is not None:
            total += int(time.time() - self._timer_start_ts)
        h = total // 3600; m = (total % 3600) // 60; s = total % 60
        label = f"{h}:{m:02d}:{s:02d}"
        C = self._C
        if self._timer_start_ts is not None:
            color = C.get("red", "#ff5a5a")
        elif total > 0:
            color = C.get("text2", "#7a7f96")
        else:
            color = C.get("text3", "#3a3e50")
        self._timer_lbl.setText(label)
        self._timer_lbl.setStyleSheet(
            f"color: {color}; font-size: 11px; "
            f"font-family: 'JetBrains Mono', monospace; min-width: 54px;"
        )

    # ── Progress bar ──────────────────────────────────────────────────────

    def _mk_progress(self) -> QWidget:
        C = self._C; w = QWidget(); w.setFixedHeight(52); w.setStyleSheet(f"background: {C['surface']};")
        layout = QVBoxLayout(w); layout.setContentsMargins(20, 8, 20, 8); layout.setSpacing(5)
        self.progress_lbl = QLabel(""); self.progress_lbl.setStyleSheet(f"color: {C['text2']}; font-size: 10px;"); layout.addWidget(self.progress_lbl)
        bottom = QHBoxLayout(); bottom.setContentsMargins(0, 0, 0, 0); bottom.setSpacing(10)
        self.progress_bar = QProgressBar(); self.progress_bar.setFixedHeight(3); self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"QProgressBar {{ background: {C['bg']}; border: none; border-radius: 2px; }}")
        bottom.addWidget(self.progress_bar, 1)
        self.target_lbl = QLabel(""); self.target_lbl.setStyleSheet(f"color: {C['text3']}; font-size: 10px;")
        self.target_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bottom.addWidget(self.target_lbl); layout.addLayout(bottom); return w

    # ── Sheet loading ─────────────────────────────────────────────────────

    def _load_sheet_for_date(self, d: date):
        if self._active_workspace == ALL_WS: self._load_all_view_for_date(d); return
        key, sheet = D.find_or_create_sheet(self._data, self._ws_settings, d)
        self._current_key = key; self._current_sheet = sheet
        D.save_data(self._data, self._ws_settings); self._render_sheet()

    def _load_all_view_for_date(self, d: date):
        wsd = D.day_name_to_weekday(self._settings.get("week_start_day", "wednesday"))
        offset = (d.weekday() - wsd) % 7; ws = d - timedelta(days=offset)
        self._all_week_start = ws; self._current_key = f"all_{ws.isoformat()}"
        self._current_sheet = {
            "start_date": ws.isoformat(), "end_date": (ws + timedelta(days=6)).isoformat(),
            "sheet_num": "All", "target_hours": 0,
            "deadline_day": self._settings.get("deadline_day", "tuesday"),
            "deadline_time": self._settings.get("deadline_time", "23:59"),
        }
        self._render_sheet()

    def _render_sheet(self):
        C = self._C; is_all = (self._active_workspace == ALL_WS); sheet = self._current_sheet
        while self.columns_layout.count():
            item = self.columns_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._columns.clear()
        try:
            start = date.fromisoformat(sheet["start_date"]); end = date.fromisoformat(sheet["end_date"])
            num   = sheet.get("sheet_num", "?")
            if is_all:
                ws_list = [n for n in list_workspaces() if n != ALL_WS]
                legend  = "  ".join(f"● {n}" for n in ws_list[:6])
                self.sheet_lbl.setTextFormat(Qt.TextFormat.PlainText)
                self.sheet_lbl.setText(f"All workspaces  ·  {start.strftime('%b %-d')} – {end.strftime('%b %-d, %Y')}  ·  {legend}")
            else:
                self.sheet_lbl.setTextFormat(Qt.TextFormat.PlainText)
                self.sheet_lbl.setText(f"Sheet {num}  ·  {start.strftime('%b %-d')} – {end.strftime('%b %-d, %Y')}")
            dates = [start + timedelta(days=i) for i in range(7)]
        except Exception:
            self.sheet_lbl.setText(self._current_key); dates = []
        today = date.today()
        all_entries = self._build_all_week_entries(date.fromisoformat(sheet["start_date"])) if is_all else {}
        days_data   = sheet.get("days", {})
        for i, d in enumerate(dates):
            entries = all_entries.get(d.isoformat(), []) if is_all else days_data.get(d.isoformat(), [])
            col = DayColumn(d, entries, C, d == today, read_only=is_all)
            col.data_changed.connect(self._on_data_changed)
            col.data_changed.connect(self._refresh_earnings)
            col.hovered_day.connect(self._on_col_hover)
            if i > 0:
                vsep = QFrame(); vsep.setFrameShape(QFrame.Shape.VLine)
                vsep.setStyleSheet(f"background: {C['border']}; border: none; max-width: 1px;")
                self.columns_layout.addWidget(vsep)
            self.columns_layout.addWidget(col, 1); self._columns.append(col)
        self._refresh_progress(); self._refresh_earnings()
        self._refresh_deadline(); self._refresh_marquee()
        has_prev = not is_all and D.get_sheet_by_offset(self._data, self._current_key, -1) is not None
        self._prev_btn.setVisible(has_prev)
        if self._notes_open:
            self._notes_overlay.update_sheet(self._current_key, self._current_sheet, self._notes_data)

    # ── Column hover ──────────────────────────────────────────────────────

    def _on_col_hover(self, day: date, entered: bool):
        if entered: self._hovered_day = day
        elif self._hovered_day == day: self._hovered_day = None

    # ── Key capture ───────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        text = event.text()
        if text and (text.isdigit() or text == ":") and not self._any_input_focused():
            if self._active_workspace != ALL_WS:
                self._open_entry_overlay(self._hovered_day or date.today(), text); return
        super().keyPressEvent(event)

    def _any_input_focused(self) -> bool:
        from PyQt6.QtWidgets import QPlainTextEdit
        fw = QApplication.focusWidget()
        return isinstance(fw, (QLineEdit, QPlainTextEdit, QTextEdit))

    def _open_entry_overlay(self, day: date, initial: str = ""):
        col = self._col_for_day(day)
        if col is None: return
        overlay = self._entry_overlay; overlay.setGeometry(self.centralWidget().rect())
        try: overlay.submitted.disconnect()
        except Exception: pass
        try: overlay.cancelled.disconnect()
        except Exception: pass
        overlay.submitted.connect(col.add_entry)
        overlay.submitted.connect(lambda m: self._toast.show_toast(f"{D.format_hm_pretty(m)} added", "success"))
        overlay.open_for_day(day, initial)

    def _col_for_day(self, day: date):
        return next((c for c in self._columns if c.day == day), None)

    # ── Data ──────────────────────────────────────────────────────────────

    def _on_data_changed(self):
        self._save_timer.start(400); self._refresh_progress(); self._refresh_marquee()

    def _do_save(self):
        if self._active_workspace == ALL_WS: return
        days = {}
        for col in self._columns:
            entries = col.get_entries()
            if entries: days[col.day.isoformat()] = entries
        self._current_sheet["days"] = days
        D.save_data(self._data, self._ws_settings)

    # ── Progress ──────────────────────────────────────────────────────────

    def _refresh_progress(self):
        C = self._C; total = sum(col.get_total_minutes() for col in self._columns)
        is_all = (self._active_workspace == ALL_WS)
        if is_all:
            self.progress_lbl.setTextFormat(Qt.TextFormat.PlainText)
            self.progress_lbl.setText(f"{D.format_hm_pretty(total)} total across all workspaces this week")
            self.progress_bar.setValue(0); self.target_lbl.setText(""); return
        target_mins = int(self._current_sheet.get("target_hours", 40.0) * 60)
        if target_mins == 0:
            self.progress_lbl.setText(D.format_hm_pretty(total)); self.progress_bar.setValue(0); self.target_lbl.setText(""); return
        pct = min(100, int(total / target_mins * 100)); remaining = max(0, target_mins - total)
        color = C['green'] if pct >= 100 else (C['orange'] if pct >= 60 else C['red'])
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{ background: {C['bg']}; border: none; border-radius: 2px; }}
            QProgressBar::chunk {{ background: {color}; border-radius: 2px; }}
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
        dd = self._current_sheet.get("deadline_day", "tuesday"); dt = self._current_sheet.get("deadline_time", "23:59")
        try:
            h, m = map(int, dt.split(":")); ampm = "AM" if h < 12 else "PM"; h12 = h % 12 or 12
            dt_str = f"{h12}:{m:02d} {ampm}"
        except Exception: dt_str = dt
        self.target_lbl.setText(f"Target: {D.format_hm_pretty(target_mins)} by {dd.capitalize()} {dt_str}")

    def _refresh_deadline(self):
        if self._active_workspace == ALL_WS: self._deadline_lbl.setText(""); return
        hrs = D.hours_until_deadline(self._current_sheet)
        if hrs > 0:
            h = int(hrs); m = int((hrs - h) * 60)
            self._deadline_lbl.setText(f"{h}hr {m}m until deadline")
        else: self._deadline_lbl.setText("")

    def _refresh_earnings(self):
        C = self._C; total = sum(col.get_total_minutes() for col in self._columns); is_all = (self._active_workspace == ALL_WS)
        if is_all:
            tg = tn = 0.0
            week_dates = {(self._all_week_start + timedelta(days=i)).isoformat() for i in range(7)}
            for name, (data, color) in self._all_ws_data().items():
                ws_s = settings_for_workspace(self._settings, name)
                for key, sheet in data.items():
                    for ds, entries in sheet.get("days", {}).items():
                        if ds in week_dates:
                            mins = sum(e for e in entries if e); g, n = D.calc_earnings(mins, sheet, ws_s); tg += g; tn += n
            if tg == 0: self.earnings_lbl.setText("")
            else:
                state = self._settings.get("us_state", "CA")
                self.earnings_lbl.setText(f"~${tn:,.2f} net  ·  ${tg:,.2f} gross  ({state})")
        else:
            gross, net = D.calc_earnings(total, self._current_sheet, self._ws_settings)
            if gross == 0: self.earnings_lbl.setText(""); return
            state = self._settings.get("us_state", "CA")
            self.earnings_lbl.setText(f"~${net:,.2f} net  ·  ${gross:,.2f} gross  ({state})")

    def _get_days_remaining(self) -> int:
        try:
            start = date.fromisoformat(self._current_sheet["start_date"])
            dl = self._current_sheet.get("deadline_day", "tuesday").lower()
            days_map = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}
            tw = days_map.get(dl, 1)
            deadline_date = start + timedelta(days=(tw - start.weekday()) % 7)
            return max(1, (deadline_date - date.today()).days)
        except Exception: return 1

    def _refresh_marquee(self):
        total = sum(col.get_total_minutes() for col in self._columns); is_all = (self._active_workspace == ALL_WS)
        if is_all:
            parts = [f"{D.format_hm_pretty(total)} total this week"]
            week_dates = {(self._all_week_start + timedelta(days=i)).isoformat() for i in range(7)}
            for name, (data, color) in self._all_ws_data().items():
                ws_mins = sum(m for key, sheet in data.items() for ds, entries in sheet.get("days", {}).items() if ds in week_dates for m in entries if m)
                if ws_mins: parts.append(f"● {name}: {D.format_hm_pretty(ws_mins)}")
            self._marquee.set_text("   ·   ".join(parts)); return
        target_mins = int(self._current_sheet.get("target_hours", 40.0) * 60)
        remaining = max(0, target_mins - total); hrs_til = D.hours_until_deadline(self._current_sheet)
        gross, net = D.calc_earnings(total, self._current_sheet, self._ws_settings)
        parts = [f"{D.format_hm_pretty(total)} logged this sheet"]
        if remaining: parts.append(f"{D.format_hm_pretty(remaining)} to target")
        if hrs_til > 0: parts.append(f"{hrs_til:.1f}hr until deadline")
        if net > 0: parts.append(f"~${net:,.2f} net earned")
        if remaining > 0 and hrs_til > 0:
            per_day = remaining / self._get_days_remaining()
            parts.append(f"~{D.format_hm_pretty(int(per_day))}/day to hit target by {self._current_sheet.get('deadline_day','tuesday').capitalize()}")
        self._marquee.set_text("   ·   ".join(parts))

    # ── Navigation ────────────────────────────────────────────────────────

    def _prev_sheet(self):
        if self._active_workspace == ALL_WS: self._load_all_view_for_date(self._all_week_start - timedelta(days=1)); return
        self._do_save(); r = D.get_sheet_by_offset(self._data, self._current_key, -1)
        if r: self._current_key, self._current_sheet = r; self._render_sheet()

    def _next_sheet(self):
        if self._active_workspace == ALL_WS: self._load_all_view_for_date(self._all_week_start + timedelta(days=7)); return
        self._do_save(); r = D.get_sheet_by_offset(self._data, self._current_key, +1)
        if r: self._current_key, self._current_sheet = r; self._render_sheet()
        else:
            try: next_day = date.fromisoformat(self._current_sheet["end_date"]) + timedelta(days=1)
            except Exception: next_day = date.today() + timedelta(weeks=1)
            self._load_sheet_for_date(next_day); self._toast.show_toast("New sheet created", "info")

    def _goto_today(self): self._do_save(); self._load_sheet_for_date(date.today())

    # ── Status ────────────────────────────────────────────────────────────

    def _show_status_toast(self):
        total = sum(col.get_total_minutes() for col in self._columns)
        if self._active_workspace == ALL_WS: self._toast.show_toast(f"All workspaces: {D.format_hm_pretty(total)} this week", "info"); return
        target_mins = int(self._current_sheet.get("target_hours", 40.0) * 60)
        remaining = max(0, target_mins - total)
        deadline = self._current_sheet.get("deadline_day", "tuesday").capitalize()
        if remaining == 0: self._toast.show_toast("Target reached — W!", "success")
        else:
            per_day = remaining / self._get_days_remaining()
            self._toast.show_toast(f"{D.format_hm_pretty(remaining)} remaining.  {D.format_hm_pretty(int(per_day))}/day to hit goal by {deadline}", "info")

    # ── Notes ─────────────────────────────────────────────────────────────

    def _position_notes_overlay(self):
        central = self.centralWidget()
        if not central: return
        topbar_h = self._topbar_ref.height() if hasattr(self, "_topbar_ref") else 50
        # Cover everything below the topbar — geometry in central widget coords
        self._notes_overlay.setGeometry(0, topbar_h, central.width(), central.height() - topbar_h)
        self._notes_overlay.raise_()

    def _on_notes_closed(self):
        self._notes_open = False; self._notes_overlay.hide()

    def _toggle_notes(self):
        if self._active_workspace == ALL_WS:
            self._toast.show_toast("Notes not available in All view", "info"); return
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
        self._notes_data = notes; D.save_notes(self._notes_data, self._ws_settings)

    # ── Sheet override ────────────────────────────────────────────────────

    def _open_sheet_override(self):
        if self._active_workspace == ALL_WS:
            self._toast.show_toast("Sheet overrides not available in All view", "info"); return
        dlg = SheetTargetDialog(self._current_sheet, self._C, self)
        dlg.saved.connect(self._on_sheet_override); dlg.exec()

    def _on_sheet_override(self, tgt, hourly, pay_type, salary):
        self._current_sheet.update({"target_hours": tgt, "hourly_rate": hourly, "pay_type": pay_type, "annual_salary": salary})
        D.save_data(self._data, self._ws_settings); self._refresh_progress(); self._refresh_earnings()
        self._toast.show_toast("Sheet overrides saved", "success")

    # ── Workspaces ────────────────────────────────────────────────────────

    def _open_new_workspace_overlay(self):
        overlay = self._new_ws_overlay; overlay.setGeometry(self.centralWidget().rect()); overlay.open()

    def _on_new_workspace_created(self, name: str, color: str):
        if name == ALL_WS: self._toast.show_toast(f"'{ALL_WS}' is reserved", "error"); return
        if not create_workspace(name, color): self._toast.show_toast(f"'{name}' already exists", "error"); return
        self._toast.show_toast(f"Workspace '{name}' created", "success")
        self._switch_workspace(name)

    def _open_workspace_settings(self):
        if self._active_workspace == ALL_WS: self._toast.show_toast("No settings for All view", "info"); return
        cfg = load_workspace_config(self._active_workspace)
        dlg = WorkspaceSettingsDialog(self._active_workspace, cfg, self._C, self)
        dlg.saved.connect(self._on_workspace_settings_saved); dlg.exec()

    def _on_workspace_settings_saved(self, result: dict):
        if result.get("__delete__"):
            reply = QMessageBox.question(
                self, "Delete workspace",
                f"Delete '{self._active_workspace}' and ALL its timesheet data?\nThis cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
            )
            if reply != QMessageBox.StandardButton.Yes: return
            old = self._active_workspace

            # ── FIX: delete first, then get updated list (old name is gone) ──
            delete_workspace(old)
            available = [w for w in list_workspaces() if w != old]
            next_ws = available[0] if available else ALL_WS

            # Reset active workspace BEFORE calling _switch_workspace so the
            # early-return guard (name == self._active_workspace) doesn't fire
            self._active_workspace = "__deleted__"
            self._switch_workspace(next_ws)
            self._toast.show_toast(f"Workspace '{old}' deleted", "info")
            return

        old_name = self._active_workspace
        new_name = result.get("name", old_name).strip()
        cfg = {k: v for k, v in result.items() if k != "name"}
        save_workspace_config(old_name, cfg)
        if new_name and new_name != old_name and new_name != ALL_WS:
            if rename_workspace(old_name, new_name):
                self._active_workspace = new_name
                self._settings["last_workspace"] = new_name
                D.save_settings(self._settings)
        self._ws_settings = settings_for_workspace(self._settings, self._active_workspace)
        self._ws_dropdown.update_active(self._active_workspace)
        self._refresh_progress(); self._refresh_earnings()
        self._toast.show_toast("Workspace settings saved", "success")

    def _switch_workspace(self, name: str):
        if name == self._active_workspace: return
        self._do_save()
        if self._active_workspace != ALL_WS and self._active_workspace != "__deleted__":
            D.save_notes(self._notes_data, self._ws_settings)
        self._active_workspace = name
        self._settings["last_workspace"] = name; D.save_settings(self._settings)
        self._ws_settings = settings_for_workspace(self._settings, name)
        self._data        = self._load_ws_data(name)
        self._notes_data  = D.load_notes(self._ws_settings) if name != ALL_WS else {}
        self._ws_dropdown.update_active(name)
        if self._notes_open: self._notes_overlay.hide(); self._notes_open = False
        self._load_sheet_for_date(date.today())
        self._toast.show_toast(f"Switched to '{name}'", "success")

    # ── Export ────────────────────────────────────────────────────────────

    def _show_export_menu(self):
        C = self._C; dlg = QDialog(self); dlg.setWindowTitle("Export"); dlg.setFixedWidth(260)
        dlg.setStyleSheet(f"QDialog {{ background: {C['surface']}; border: 1px solid {C['border2']}; border-radius: 8px; }}")
        layout = QVBoxLayout(dlg); layout.setContentsMargins(16,16,16,16); layout.setSpacing(8)
        hdr = QLabel("EXPORT"); hdr.setStyleSheet(f"color:{C['text']};font-size:11px;letter-spacing:2px;"); layout.addWidget(hdr)
        self._export_notes = False
        cb = QCheckBox("Include notes in PDF")
        cb.setStyleSheet(f"""
            QCheckBox {{
                color: {C['text2']}; font-size: 11px;
                background: transparent; border: none; spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 14px; height: 14px; border: 1px solid {C['border2']};
                border-radius: 3px; background: {C['surface2']};
            }}
            QCheckBox::indicator:checked {{
                background: {C['accent']}; border-color: {C['accent']};
            }}
        """)
        cb.stateChanged.connect(lambda s: setattr(self, "_export_notes", bool(s))); layout.addWidget(cb)
        is_all = (self._active_workspace == ALL_WS)
        exports = [("CSV — all workspaces this week", self._export_all_workspaces_csv)] if is_all else [
            ("CSV — this sheet", self._export_csv), ("CSV — all sheets", self._export_all_csv),
            ("PDF — this sheet", self._export_pdf),
        ]
        for lbl, fn in exports:
            b = QPushButton(lbl); b.clicked.connect(lambda _, f=fn: (dlg.close(), f())); layout.addWidget(b)
        dlg.exec()

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", str(Path.home() / f"timesheet_{self._active_workspace}_sheet{self._current_sheet.get('sheet_num','X')}.csv"), "CSV Files (*.csv)")
        if not path: return
        with open(path, "w", newline="") as f:
            w = csv.writer(f); w.writerow(["Date","Day","Entry","Minutes","Hours"])
            for col in self._columns:
                for i, mins in enumerate(col.get_entries()): w.writerow([col.day.isoformat(), col.day.strftime("%A"), i+1, mins, round(mins/60,2)])
            total = sum(col.get_total_minutes() for col in self._columns)
            w.writerow([]); w.writerow(["TOTAL","","",total,round(total/60,2)])
        self._toast.show_toast(f"CSV saved: {Path(path).name}", "success")

    def _export_all_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export All", str(Path.home() / f"{self._active_workspace}_all.csv"), "CSV Files (*.csv)")
        if not path: return
        with open(path, "w", newline="") as f:
            w = csv.writer(f); w.writerow(["Sheet","Date","Day","Entry","Minutes","Hours"])
            for key, sheet in sorted(self._data.items(), key=lambda x: x[1].get("sheet_num", 0)):
                for ds, entries in sorted(sheet.get("days", {}).items()):
                    d = date.fromisoformat(ds)
                    for i, mins in enumerate(entries):
                        if mins: w.writerow([key,ds,d.strftime("%A"),i+1,mins,round(mins/60,2)])
        self._toast.show_toast(f"Exported: {Path(path).name}", "success")

    def _export_all_workspaces_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export All Workspaces", str(Path.home() / "timesheet_all_workspaces.csv"), "CSV Files (*.csv)")
        if not path: return
        with open(path, "w", newline="") as f:
            w = csv.writer(f); w.writerow(["Workspace","Sheet","Date","Day","Entry","Minutes","Hours"])
            for name, (data, color) in self._all_ws_data().items():
                for key, sheet in sorted(data.items(), key=lambda x: x[1].get("sheet_num", 0)):
                    for ds, entries in sorted(sheet.get("days", {}).items()):
                        d = date.fromisoformat(ds)
                        for i, mins in enumerate(entries):
                            if mins: w.writerow([name,key,ds,d.strftime("%A"),i+1,mins,round(mins/60,2)])
        self._toast.show_toast(f"Exported: {Path(path).name}", "success")

    def _export_pdf(self):
        if self._active_workspace == ALL_WS: return
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib import colors; from reportlab.lib.styles import getSampleStyleSheet; from reportlab.lib.units import mm
        except ImportError: self._toast.show_toast("pip install reportlab for PDF export", "error"); return
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF", str(Path.home() / f"timesheet_{self._active_workspace}_sheet{self._current_sheet.get('sheet_num','X')}.pdf"), "PDF Files (*.pdf)")
        if not path: return
        sheet = self._current_sheet
        doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
        styles = getSampleStyleSheet(); story = []
        try:
            start = date.fromisoformat(sheet["start_date"]); end = date.fromisoformat(sheet["end_date"])
            story.append(Paragraph(f"Timesheet — {self._active_workspace}  ·  Sheet {sheet.get('sheet_num','?')}  ·  {start.strftime('%b %-d')} to {end.strftime('%b %-d, %Y')}", styles["Title"]))
        except Exception: story.append(Paragraph("Timesheet", styles["Title"]))
        story.append(Spacer(1, 6*mm))
        td = [["Day","Date","Sessions","Total"]]
        for col in self._columns:
            entries = col.get_entries(); sessions = ", ".join(D.format_hm_short(e) for e in entries) or "—"
            td.append([col.day.strftime("%A"), col.day.strftime("%b %-d"), sessions, D.format_hm_pretty(sum(entries)) if entries else "—"])
        td.append(["","","TOTAL", D.format_hm_pretty(sum(col.get_total_minutes() for col in self._columns))])
        table = Table(td, colWidths=[35*mm,25*mm,90*mm,25*mm])
        table.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1a1e29")), ("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"), ("FONTSIZE",(0,0),(-1,-1),10),
            ("ROWBACKGROUNDS",(0,1),(-1,-2),[colors.HexColor("#f5f5f5"),colors.white]),
            ("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),
            ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),("LEFTPADDING",(0,0),(-1,-1),8),
        ]))
        story.insert(2, table)
        if self._export_notes:
            notes_text = self._notes_data.get(self._current_key, {}).get("general", "")
            if notes_text:
                import re; plain = re.sub(r'<[^>]+>', '', notes_text)
                story.append(Spacer(1, 6*mm)); story.append(Paragraph("Notes", styles["Heading2"]))
                story.append(Paragraph(plain, styles["Normal"]))
        doc.build(story); self._toast.show_toast(f"PDF saved: {Path(path).name}", "success")

    # ── Settings ──────────────────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self._settings, self._C, self)
        dlg.settings_saved.connect(self._on_settings_saved); dlg.exec()

    def _on_settings_saved(self, s: dict):
        self._settings    = s
        self._ws_settings = settings_for_workspace(s, self._active_workspace)
        self._C           = TH.get_theme(s.get("theme","dark"), s.get("color_overrides",{}))
        self.setStyleSheet(TH.make_stylesheet(self._C))
        self._toast.update_C(self._C); self._toast.update_settings(self._settings)
        self._refresh_progress(); self._refresh_earnings()
        self._toast.show_toast("Settings saved", "success")

    # ── Shortcuts ─────────────────────────────────────────────────────────

    def _setup_shortcuts(self):
        QShortcut(QKeySequence(self._settings.get("hotkey_notes", "Ctrl+N")), self).activated.connect(self._toggle_notes)
        QShortcut(QKeySequence(self._settings.get("hotkey_preview", "Ctrl+P")), self).activated.connect(
            lambda: self._notes_overlay._toggle_preview() if self._notes_open else None
        )
        def _make_switcher(idx):
            def _switch():
                ws = list_workspaces()
                if idx < len(ws): self._switch_workspace(ws[idx])
            return _switch
        for i in range(9):
            QShortcut(QKeySequence(f"Ctrl+{i+1}"), self).activated.connect(_make_switcher(i))

    # ── Resize / close ────────────────────────────────────────────────────

    def resizeEvent(self, e):
        super().resizeEvent(e); self._toast.reanchor()
        central = self.centralWidget()
        if central:
            if hasattr(self, "_entry_overlay"): self._entry_overlay.setGeometry(central.rect())
            if hasattr(self, "_new_ws_overlay"): self._new_ws_overlay.setGeometry(central.rect())
            if hasattr(self, "_timer_confirm"): self._timer_confirm.setGeometry(central.rect())
        if hasattr(self, "_notes_overlay") and self._notes_open:
            self._position_notes_overlay()

    def closeEvent(self, e):
        self._do_save()
        # Persist timer if running
        if self._timer_start_ts is not None or self._timer_elapsed > 0:
            self._timer_persist()
        super().closeEvent(e)


# ── Entry point ───────────────────────────────────────────────────────────────

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
    window = TimesheetApp(); window.show(); sys.exit(app.exec())


if __name__ == "__main__":
    main()