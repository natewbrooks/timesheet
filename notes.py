"""
notes.py — full-app notes overlay with GitHub-flavored markdown support.
Auto-saves as plain markdown text. Edit/Preview toggle.
Overlay fully blocks input to underlying widgets.
"""
from datetime import date, timedelta
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QTextEdit, QPlainTextEdit, QPushButton, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer


# ── Markdown → styled HTML ────────────────────────────────────────────────────

def _render_markdown(text: str, C: dict) -> str:
    try:
        import markdown as md_lib
        body = md_lib.markdown(
            text,
            extensions=["fenced_code", "tables", "nl2br", "sane_lists", "attr_list"],
        )
    except Exception:
        import html
        body = f"<pre>{html.escape(text)}</pre>"

    bg       = C.get("surface",  "#12151f")
    text_c   = C.get("text",     "#e8eaf0")
    text2    = C.get("text2",    "#7a7f96")
    text3    = C.get("text3",    "#3a3e50")
    accent   = C.get("accent",   "#4f7cff")
    border   = C.get("border2",  "#252938")
    surface2 = C.get("surface2", "#1a1e29")
    code_bg  = C.get("bg",       "#0d0f17")

    css = f"""
    body {{
        font-family: 'JetBrains Mono', 'Fira Code', monospace;
        font-size: 13px; color: {text_c}; background: {bg};
        line-height: 1.7; padding: 20px 24px; margin: 0;
    }}
    h1, h2, h3, h4, h5, h6 {{
        color: {text_c}; font-weight: 600;
        margin-top: 1.4em; margin-bottom: 0.4em;
        border-bottom: 1px solid {border}; padding-bottom: 4px;
    }}
    h1 {{ font-size: 1.5em; }} h2 {{ font-size: 1.25em; }}
    h3 {{ font-size: 1.1em; border-bottom: none; }}
    h4, h5, h6 {{ font-size: 1em; border-bottom: none; color: {text2}; }}
    p {{ margin: 0.6em 0; }}
    a {{ color: {accent}; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{
        background: {code_bg}; color: {accent};
        padding: 2px 5px; border-radius: 4px;
        font-family: 'JetBrains Mono', monospace; font-size: 0.9em;
    }}
    pre {{
        background: {code_bg}; border: 1px solid {border};
        border-radius: 6px; padding: 14px 16px; margin: 1em 0;
    }}
    pre code {{ background: transparent; padding: 0; color: {text_c}; font-size: 12px; }}
    blockquote {{
        border-left: 3px solid {accent}; margin: 0.8em 0;
        padding: 4px 16px; color: {text2};
        background: {surface2}; border-radius: 0 4px 4px 0;
    }}
    ul, ol {{ padding-left: 1.6em; margin: 0.4em 0; }}
    li {{ margin: 0.25em 0; line-height: 1.6; }}
    li p {{ margin: 0; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 12px; }}
    th {{
        background: {surface2}; color: {text_c}; font-weight: 600;
        padding: 8px 12px; border: 1px solid {border}; text-align: left;
    }}
    td {{ padding: 6px 12px; border: 1px solid {border}; color: {text2}; }}
    tr:nth-child(even) td {{ background: {surface2}22; }}
    hr {{ border: none; border-top: 1px solid {border}; margin: 1.5em 0; }}
    del {{ color: {text3}; }} strong {{ color: {text_c}; font-weight: 700; }}
    em {{ color: {text2}; font-style: italic; }}
    input[type="checkbox"] {{ margin-right: 6px; }}
    """
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{css}</style></head><body>{body}</body></html>"""


# ── Per-tab editor (plain markdown input + rendered preview) ──────────────────

class MarkdownEditor(QWidget):
    content_changed = pyqtSignal()

    def __init__(self, C: dict, parent=None):
        super().__init__(parent)
        self._C = C
        self._preview_mode = False
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self.content_changed.emit)
        self._build()

    def _build(self):
        C = self._C
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._editor = QPlainTextEdit()
        self._editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {C['surface']}; border: none;
                color: {C['text']};
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 13px; padding: 20px 24px; line-height: 1.6;
                selection-background-color: {C['accent']}44;
            }}
        """)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._editor.setPlaceholderText(
            "Markdown notes…\n\n# Heading\n**bold**  *italic*  `code`\n"
            "- bullet\n- [ ] task item\n\n```python\ncode block\n```"
        )
        self._editor.textChanged.connect(lambda: self._debounce.start(400))
        self._editor.textChanged.connect(self._live_preview)
        layout.addWidget(self._editor)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setStyleSheet(f"""
            QTextEdit {{
                background: {C['surface']}; border: none; color: {C['text']}; padding: 0;
            }}
        """)
        self._preview.hide()
        layout.addWidget(self._preview)

    def _live_preview(self):
        if self._preview_mode:
            self._render()

    def _render(self):
        self._preview.setHtml(_render_markdown(self._editor.toPlainText(), self._C))

    def set_preview_mode(self, on: bool):
        self._preview_mode = on
        if on:
            self._render()
            self._editor.hide(); self._preview.show()
        else:
            self._preview.hide(); self._editor.show()
            if not self._editor.isHidden():
                self._editor.setFocus()

    def to_save(self) -> str:
        return self._editor.toPlainText()

    def load_saved(self, text: str):
        self._editor.blockSignals(True)
        self._editor.setPlainText(text)
        self._editor.blockSignals(False)

    def clear(self):
        self._editor.blockSignals(True)
        self._editor.clear()
        self._editor.blockSignals(False)

    def set_focus(self):
        if not self._preview_mode:
            self._editor.setFocus()


# ── Notes overlay ─────────────────────────────────────────────────────────────

class NotesOverlay(QWidget):
    """
    Covers the entire content area below the topbar.
    Intercepts all mouse events so underlying column widgets are fully blocked.
    """
    notes_changed = pyqtSignal(dict)
    closed        = pyqtSignal()

    def __init__(self, parent=None, C: dict = None, settings: dict = None):
        super().__init__(parent)
        self._C          = C or {}
        self._settings   = settings or {}
        self._sheet_key  = ""
        self._sheet      = {}
        self._notes_data = {}
        self._on_prev    = None
        self._on_next    = None
        self._editors: dict[str, MarkdownEditor] = {}
        self._preview_mode = False

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Do NOT set WA_TransparentForMouseEvents — we want to block clicks
        self.hide()
        self._build()

    def _build(self):
        C = self._C
        self.setStyleSheet(f"NotesOverlay {{ background: {C['surface']}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(44)
        header.setStyleSheet(
            f"background: {C['surface']}; border-bottom: 1px solid {C['border']};"
        )
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(8)

        def hbtn(text, tip, cb, w=32):
            b = QPushButton(text); b.setFixedSize(w, 28); b.setToolTip(tip)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none;
                    color: {C['text2']}; font-size: 16px; padding: 0; border-radius: 4px;
                }}
                QPushButton:hover {{ color: {C['text']}; background: {C['surface2']}; }}
            """)
            b.clicked.connect(cb); return b

        hl.addWidget(hbtn("‹", "Previous sheet", self._go_prev))

        self._sheet_lbl = QLabel("")
        self._sheet_lbl.setStyleSheet(
            f"color: {C['text']}; font-size: 11px; letter-spacing: 1px;"
        )
        self._sheet_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(self._sheet_lbl, 1)
        hl.addWidget(hbtn("›", "Next sheet", self._go_next))

        self._preview_btn = QPushButton("Preview")
        self._preview_btn.setFixedWidth(66)
        self._preview_btn.setCheckable(True)
        self._preview_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {C['border2']};
                color: {C['text2']}; border-radius: 4px; font-size: 10px; padding: 3px 8px;
            }}
            QPushButton:checked {{
                background: {C['accent']}22; border-color: {C['accent']}; color: {C['accent']};
            }}
            QPushButton:hover:!checked {{ color: {C['text']}; border-color: {C['accent']}; }}
        """)
        self._preview_btn.clicked.connect(self._toggle_preview)
        hl.addWidget(self._preview_btn)
        hl.addWidget(hbtn("×", "Close  (ESC)", self._close_overlay, 28))
        layout.addWidget(header)

        # ── Tabs ──────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: {C['surface']}; }}
            QTabBar::tab {{
                background: {C['surface']}; color: {C['text2']};
                padding: 6px 14px; border: none;
                border-bottom: 2px solid transparent;
                font-size: 10px; letter-spacing: 0.5px;
            }}
            QTabBar::tab:selected {{ color: {C['text']}; border-bottom: 2px solid {C['accent']}; }}
            QTabBar::tab:hover {{ color: {C['text']}; }}
        """)
        layout.addWidget(self._tabs, 1)

        # ── Footer ────────────────────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(30)
        footer.setStyleSheet(
            f"background: {C['surface']}; border-top: 1px solid {C['border']};"
        )
        fl = QHBoxLayout(footer); fl.setContentsMargins(16, 0, 16, 0)
        self._save_lbl = QLabel("auto-saved")
        self._save_lbl.setStyleSheet(f"color: {C['text3']}; font-size: 9px;")
        fl.addWidget(self._save_lbl); fl.addStretch()
        hint = QLabel(
            "ESC to close  ·  Markdown: **bold** *italic* `code` # heading  - list  - [ ] task  ```code block```"
        )
        hint.setStyleSheet(f"color: {C['text3']}; font-size: 9px;")
        fl.addWidget(hint)
        layout.addWidget(footer)

    # ── Open/close ────────────────────────────────────────────────────────

    def open_for_sheet(self, sheet_key, sheet, notes_data, on_prev=None, on_next=None):
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
        ed = self._editors.get("general")
        if ed: ed.set_focus()

    def _close_overlay(self):
        self._auto_save(); self.hide(); self.closed.emit()

    def update_sheet(self, sheet_key, sheet, notes_data):
        self._auto_save()
        self._sheet_key  = sheet_key
        self._sheet      = sheet
        self._notes_data = notes_data
        self._rebuild_tabs(); self._load_notes(); self._update_sheet_label()

    # ── Tabs ──────────────────────────────────────────────────────────────

    def _rebuild_tabs(self):
        for ed in self._editors.values():
            try: ed.content_changed.disconnect()
            except Exception: pass
        self._editors.clear()
        while self._tabs.count(): self._tabs.removeTab(0)

        gen = MarkdownEditor(self._C)
        gen.content_changed.connect(self._auto_save)
        self._editors["general"] = gen
        self._tabs.addTab(gen, "General")

        try:
            start = date.fromisoformat(self._sheet["start_date"])
            for i in range(7):
                d = start + timedelta(days=i)
                ed = MarkdownEditor(self._C)
                ed.content_changed.connect(self._auto_save)
                self._editors[d.isoformat()] = ed
                self._tabs.addTab(ed, d.strftime("%a %-d"))
        except Exception:
            pass

        for ed in self._editors.values():
            ed.set_preview_mode(self._preview_mode)

    def _load_notes(self):
        sheet_notes = self._notes_data.get(self._sheet_key, {})
        for key, ed in self._editors.items():
            text = sheet_notes.get(key, "")
            ed.load_saved(text)

    def _update_sheet_label(self):
        try:
            s = self._sheet
            start = date.fromisoformat(s["start_date"])
            end   = date.fromisoformat(s["end_date"])
            self._sheet_lbl.setText(
                f"Sheet {s.get('sheet_num','?')}  ·  "
                f"{start.strftime('%b %-d')} – {end.strftime('%b %-d, %Y')}"
            )
        except Exception:
            self._sheet_lbl.setText(self._sheet_key)

    # ── Save ──────────────────────────────────────────────────────────────

    def _auto_save(self):
        if self._sheet_key not in self._notes_data:
            self._notes_data[self._sheet_key] = {}
        for key, ed in self._editors.items():
            self._notes_data[self._sheet_key][key] = ed.to_save()
        self.notes_changed.emit(self._notes_data)
        self._save_lbl.setText("saved")
        QTimer.singleShot(1500, lambda: self._save_lbl.setText("auto-saved"))

    # ── Preview ───────────────────────────────────────────────────────────

    def _toggle_preview(self):
        self._preview_mode = self._preview_btn.isChecked()
        self._preview_btn.setText("Edit" if self._preview_mode else "Preview")
        for ed in self._editors.values():
            ed.set_preview_mode(self._preview_mode)

    # ── Nav ───────────────────────────────────────────────────────────────

    def _go_prev(self):
        self._auto_save()
        if self._on_prev:
            r = self._on_prev(self._sheet_key)
            if r:
                self._sheet_key, self._sheet = r
                self._rebuild_tabs(); self._load_notes(); self._update_sheet_label()

    def _go_next(self):
        self._auto_save()
        if self._on_next:
            r = self._on_next(self._sheet_key)
            if r:
                self._sheet_key, self._sheet = r
                self._rebuild_tabs(); self._load_notes(); self._update_sheet_label()

    # ── Block all mouse events from reaching underlying widgets ───────────

    def mousePressEvent(self, e):   e.accept()
    def mouseReleaseEvent(self, e): e.accept()
    def mouseMoveEvent(self, e):    e.accept()
    def wheelEvent(self, e):        e.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._close_overlay()
        else:
            super().keyPressEvent(event)