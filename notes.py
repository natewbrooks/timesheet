"""
notes.py — full-app notes overlay (covers everything below the topbar).
Auto-saves. Bullet lists with proper Tab sub-bullet. Checklist with - [].
"""
from datetime import date, timedelta
import re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QTextEdit, QPushButton, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import (
    QTextCharFormat, QFont, QColor, QTextCursor,
    QTextListFormat, QTextBlockFormat
)


class NoteEditor(QTextEdit):
    """
    Rich text editor.
    - type "- " to start a bullet list
    - type "- [ ] " to start a checklist item
    - Tab on a list item = indent (sub-bullet)
    - Shift+Tab / Ctrl+[ = outdent
    - Ctrl+] = indent
    - Enter on empty bullet = exit list
    - No placeholder when list is active
    """
    content_changed = pyqtSignal()

    def __init__(self, C: dict, parent=None):
        super().__init__(parent)
        self._C = C
        self.setAcceptRichText(True)
        self.setPlaceholderText("Notes…")
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self.content_changed.emit)
        self.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self):
        if self.document().characterCount() > 1:
            self.setPlaceholderText("")
        else:
            self.setPlaceholderText("Notes…")
        self._debounce.start(300)

    def keyPressEvent(self, event):
        ctrl  = event.modifiers() == Qt.KeyboardModifier.ControlModifier
        key   = event.key()
        cursor = self.textCursor()

        # ── Ctrl+] indent, Ctrl+[ outdent ──────────────────────────────────
        if ctrl and key == Qt.Key.Key_BracketRight:
            self._change_indent(+1); return
        if ctrl and key == Qt.Key.Key_BracketLeft:
            self._change_indent(-1); return

        # ── Tab / Shift+Tab in list ─────────────────────────────────────────
        if key == Qt.Key.Key_Tab and not ctrl:
            if cursor.currentList():
                self._change_indent(+1); return
        if key == Qt.Key.Key_Backtab:
            if cursor.currentList():
                self._change_indent(-1); return

        # ── Enter in list ───────────────────────────────────────────────────
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not ctrl:
            if cursor.currentList():
                block_text = cursor.block().text().strip()
                if not block_text or block_text in ("[ ]", "[x]", "☐", "☑"):
                    self._exit_list(); return
                if block_text.startswith("[ ]") or block_text.startswith("[x]"):
                    super().keyPressEvent(event)
                    cursor2 = self.textCursor()
                    cursor2.insertText("[ ] ")
                    return

        # ── "- " triggers bullet list ───────────────────────────────────────
        if key == Qt.Key.Key_Space and not ctrl:
            block_text = cursor.block().text()
            if block_text == "-":
                self._start_list(cursor, checklist=False); return
            if block_text in ("- [ ]", "- []", "-[ ]", "-[]"):
                self._start_list(cursor, checklist=True); return

        super().keyPressEvent(event)

    def _start_list(self, cursor: QTextCursor, checklist: bool):
        cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        cursor.removeSelectedText()
        fmt = QTextListFormat()
        fmt.setStyle(QTextListFormat.Style.ListDisc)
        fmt.setIndent(1)
        cursor.createList(fmt)
        if checklist:
            cursor.insertText("[ ] ")
        self.setTextCursor(cursor)

    def _change_indent(self, direction: int):
        cursor = self.textCursor()
        lst    = cursor.currentList()
        if not lst:
            return
        fmt   = QTextListFormat(lst.format())
        new_i = max(1, min(8, fmt.indent() + direction))

        if direction == -1 and new_i < fmt.indent():
            # Outdent: if already at indent 1, exit the list entirely
            if fmt.indent() <= 1:
                self._exit_list()
                return
            fmt.setIndent(new_i)
            lst.setFormat(fmt)
        elif direction == +1 and new_i > fmt.indent():
            new_fmt = QTextListFormat()
            new_fmt.setStyle(
                QTextListFormat.Style.ListCircle if new_i % 2 == 0
                else QTextListFormat.Style.ListSquare if new_i % 3 == 0
                else QTextListFormat.Style.ListDisc
            )
            new_fmt.setIndent(new_i)
            cursor.createList(new_fmt)

    def _exit_list(self):
        cursor = self.textCursor()
        # Select and remove the empty list item text
        cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        cursor.removeSelectedText()
        # Remove the list format from the block
        block_fmt = QTextBlockFormat()
        block_fmt.setIndent(0)
        block_fmt.setObjectIndex(-1)
        cursor.setBlockFormat(block_fmt)
        # Apply plain char format to break out of list
        char_fmt = QTextCharFormat()
        cursor.setCharFormat(char_fmt)
        self.setTextCursor(cursor)


class NotesOverlay(QWidget):
    """
    Full-app overlay: covers everything below the topbar row.
    """
    notes_changed = pyqtSignal(dict)
    closed        = pyqtSignal()

    def __init__(self, parent=None, C: dict = None, settings: dict = None):
        super().__init__(parent)
        self._C            = C or {}
        self._settings     = settings or {}
        self._sheet_key    = ""
        self._sheet        = {}
        self._notes_data   = {}
        self._on_prev      = None
        self._on_next      = None
        self._editors: dict[str, NoteEditor] = {}
        self._preview_mode = False
        # Must be a child widget that renders on top — raise_ handles z-order
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()
        self._build()

    def _build(self):
        C = self._C
        self.setStyleSheet(f"NotesOverlay {{ background: {C['surface']}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ──────────────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(44)
        header.setStyleSheet(f"background: {C['surface']}; border-bottom: 1px solid {C['border']};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(8)

        def hbtn(text, tip, cb, w=32):
            b = QPushButton(text)
            b.setFixedSize(w, 28)
            b.setToolTip(tip)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none;
                    color: {C['text2']}; font-size: 16px; padding: 0;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    color: {C['text']}; background: {C['surface2']};
                }}
            """)
            b.clicked.connect(cb)
            return b

        hl.addWidget(hbtn("‹", "Previous sheet", self._go_prev))

        self._sheet_lbl = QLabel("")
        self._sheet_lbl.setStyleSheet(
            f"color: {C['text']}; font-size: 11px; letter-spacing: 1px;"
        )
        self._sheet_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(self._sheet_lbl, 1)

        hl.addWidget(hbtn("›", "Next sheet", self._go_next))

        self._preview_btn = QPushButton("Preview")
        self._preview_btn.setFixedWidth(62)
        self._preview_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {C['border2']};
                color: {C['text2']};
                border-radius: 4px;
                font-size: 10px;
                padding: 3px 8px;
            }}
            QPushButton:hover {{ color: {C['text']}; border-color: {C['accent']}; }}
        """)
        self._preview_btn.clicked.connect(self._toggle_preview)
        hl.addWidget(self._preview_btn)

        close_btn = hbtn("×", "Close  (ESC)", self._close_overlay, 28)
        hl.addWidget(close_btn)

        layout.addWidget(header)

        # ── Tabs ─────────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: {C['surface']}; }}
            QTabBar::tab {{
                background: {C['surface']};
                color: {C['text2']};
                padding: 6px 14px;
                border: none;
                border-bottom: 2px solid transparent;
                font-size: 10px;
                letter-spacing: 0.5px;
            }}
            QTabBar::tab:selected {{
                color: {C['text']};
                border-bottom: 2px solid {C['accent']};
            }}
            QTabBar::tab:hover {{ color: {C['text']}; }}
        """)
        layout.addWidget(self._tabs, 1)

        # ── Footer hint ───────────────────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(30)
        footer.setStyleSheet(f"background: {C['surface']}; border-top: 1px solid {C['border']};")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 0, 16, 0)

        self._save_lbl = QLabel("auto-saved")
        self._save_lbl.setStyleSheet(f"color: {C['text3']}; font-size: 9px;")
        fl.addWidget(self._save_lbl)
        fl.addStretch()

        hint = QLabel("ESC  ·  Tab = sub-bullet  ·  - [space] = bullet  ·  - [ ] [space] = checklist")
        hint.setStyleSheet(f"color: {C['text3']}; font-size: 9px;")
        fl.addWidget(hint)
        layout.addWidget(footer)

    # ── Opening / closing ──────────────────────────────────────────────────────

    def open_for_sheet(self, sheet_key: str, sheet: dict, notes_data: dict,
                       on_prev=None, on_next=None):
        self._sheet_key  = sheet_key
        self._sheet      = sheet
        self._notes_data = notes_data
        self._on_prev    = on_prev
        self._on_next    = on_next
        self._rebuild_tabs()
        self._load_notes()
        self._update_sheet_label()
        self.show()
        self.raise_()
        if self._tabs.count() > 0:
            w = self._tabs.widget(0)
            if isinstance(w, NoteEditor):
                w.setFocus()

    def _close_overlay(self):
        self._auto_save()
        self.hide()
        self.closed.emit()

    def update_sheet(self, sheet_key: str, sheet: dict, notes_data: dict):
        self._auto_save()
        self._sheet_key  = sheet_key
        self._sheet      = sheet
        self._notes_data = notes_data
        self._rebuild_tabs()
        self._load_notes()
        self._update_sheet_label()

    # ── Tab management ─────────────────────────────────────────────────────────

    def _rebuild_tabs(self):
        for ed in self._editors.values():
            try:
                ed.content_changed.disconnect()
            except Exception:
                pass
        self._editors.clear()
        while self._tabs.count():
            self._tabs.removeTab(0)

        C        = self._C
        ed_style = f"""
            QTextEdit {{
                background: {C['surface']};
                border: none;
                color: {C['text']};
                font-size: 13px;
                padding: 20px 24px;
                line-height: 1.6;
            }}
        """

        gen = NoteEditor(C)
        gen.setStyleSheet(ed_style)
        gen.content_changed.connect(self._auto_save)
        self._editors["general"] = gen
        self._tabs.addTab(gen, "General")

        try:
            start = date.fromisoformat(self._sheet["start_date"])
            for i in range(7):
                d       = start + timedelta(days=i)
                day_key = d.isoformat()
                ed      = NoteEditor(C)
                ed.setStyleSheet(ed_style)
                ed.content_changed.connect(self._auto_save)
                self._editors[day_key] = ed
                self._tabs.addTab(ed, d.strftime("%a %-d"))
        except Exception:
            pass

    def _load_notes(self):
        sheet_notes = self._notes_data.get(self._sheet_key, {})
        for key, ed in self._editors.items():
            html = sheet_notes.get(key, "")
            ed.blockSignals(True)
            if html:
                ed.setHtml(html)
            else:
                ed.clear()
                ed.setPlaceholderText("Notes…  — space for bullet  ·  Tab to sub-indent")
            ed.blockSignals(False)

    def _update_sheet_label(self):
        try:
            s     = self._sheet
            start = date.fromisoformat(s["start_date"])
            end   = date.fromisoformat(s["end_date"])
            num   = s.get("sheet_num", "?")
            self._sheet_lbl.setText(
                f"Sheet {num}  ·  {start.strftime('%b %-d')} – {end.strftime('%b %-d, %Y')}"
            )
        except Exception:
            self._sheet_lbl.setText(self._sheet_key)

    # ── Auto save ──────────────────────────────────────────────────────────────

    def _auto_save(self):
        if self._sheet_key not in self._notes_data:
            self._notes_data[self._sheet_key] = {}
        for key, ed in self._editors.items():
            self._notes_data[self._sheet_key][key] = ed.toHtml()
        self.notes_changed.emit(self._notes_data)
        self._save_lbl.setText("saved")
        QTimer.singleShot(1500, lambda: self._save_lbl.setText("auto-saved"))

    # ── Preview ────────────────────────────────────────────────────────────────

    def _toggle_preview(self):
        self._preview_mode = not self._preview_mode
        self._preview_btn.setText("Edit" if self._preview_mode else "Preview")
        for ed in self._editors.values():
            ed.setReadOnly(self._preview_mode)

    # ── Sheet navigation ───────────────────────────────────────────────────────

    def _go_prev(self):
        self._auto_save()
        if self._on_prev:
            result = self._on_prev(self._sheet_key)
            if result:
                self._sheet_key, self._sheet = result
                self._rebuild_tabs()
                self._load_notes()
                self._update_sheet_label()

    def _go_next(self):
        self._auto_save()
        if self._on_next:
            result = self._on_next(self._sheet_key)
            if result:
                self._sheet_key, self._sheet = result
                self._rebuild_tabs()
                self._load_notes()
                self._update_sheet_label()

    # ── Key events ─────────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._close_overlay()
        else:
            super().keyPressEvent(event)

    # ── Resize: fill parent properly ───────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)