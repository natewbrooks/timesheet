"""
theme.py — colour palettes and full stylesheet
"""

THEMES = {
    "dark": {
        "bg":               "#0d0f14",
        "surface":          "#13161e",
        "surface2":         "#1a1e29",
        "border":           "#1c1f2b",
        "border2":          "#252938",
        "accent":           "#4f7cff",
        "accent2":          "#7a9fff",
        "text":             "#e8eaf0",
        "text2":            "#7a7f96",
        "text3":            "#3a3e50",
        "green":            "#3ddc84",
        "orange":           "#ffaa33",
        "red":              "#ff5a5a",
        "col_hover":        "#1e2235",
        "toast_info":       "#4f7cff",
        "toast_success":    "#3ddc84",
        "toast_warning":    "#ffaa33",
        "toast_error":      "#ff5a5a",
        "tooltip_bg":       "#1a1e29",
        "tooltip_text":     "#ffffff",
        "dropdown_bg":      "#0a0c10",
        "dropdown_sel":     "#1c1f2b",
        "dropdown_text":    "#e8eaf0",
    },
    "midnight": {
        "bg":               "#060810",
        "surface":          "#0d1018",
        "surface2":         "#121520",
        "border":           "#181c28",
        "border2":          "#1e2335",
        "accent":           "#b06aff",
        "accent2":          "#cc99ff",
        "text":             "#dde0f0",
        "text2":            "#6a6f88",
        "text3":            "#323548",
        "green":            "#39d977",
        "orange":           "#ffaa33",
        "red":              "#ff5566",
        "col_hover":        "#12151f",
        "toast_info":       "#b06aff",
        "toast_success":    "#39d977",
        "toast_warning":    "#ffaa33",
        "toast_error":      "#ff5566",
        "tooltip_bg":       "#0d1018",
        "tooltip_text":     "#ffffff",
        "dropdown_bg":      "#040608",
        "dropdown_sel":     "#181c28",
        "dropdown_text":    "#dde0f0",
    },
    "slate": {
        "bg":               "#141820",
        "surface":          "#1c2130",
        "surface2":         "#222840",
        "border":           "#282f44",
        "border2":          "#303858",
        "accent":           "#40c4aa",
        "accent2":          "#70dcc8",
        "text":             "#e0e8f0",
        "text2":            "#6d7a90",
        "text3":            "#3a4255",
        "green":            "#40dd90",
        "orange":           "#ffbb44",
        "red":              "#ff5566",
        "col_hover":        "#1c2435",
        "toast_info":       "#40c4aa",
        "toast_success":    "#40dd90",
        "toast_warning":    "#ffbb44",
        "toast_error":      "#ff5566",
        "tooltip_bg":       "#111520",
        "tooltip_text":     "#ffffff",
        "dropdown_bg":      "#0e1018",
        "dropdown_sel":     "#282f44",
        "dropdown_text":    "#e0e8f0",
    },
}

COLOR_LABELS = {
    "accent":           "Accent",
    "col_hover":        "Column Hover",
    "green":            "Success / Green",
    "orange":           "Warning / Orange",
    "red":              "Error / Red",
    "toast_info":       "Toast: Info",
    "toast_success":    "Toast: Success",
    "toast_warning":    "Toast: Warning",
    "toast_error":      "Toast: Error",
    "tooltip_bg":       "Tooltip Background",
    "tooltip_text":     "Tooltip Text",
    "dropdown_bg":      "Dropdown Background",
    "dropdown_sel":     "Dropdown Selection",
    "dropdown_text":    "Dropdown Text",
}


def get_theme(name: str, overrides: dict = None) -> dict:
    t = dict(THEMES.get(name, THEMES["dark"]))
    if overrides:
        for k, v in overrides.items():
            if v and str(v).startswith("#") and k in t:
                t[k] = v
    return t


def make_stylesheet(C: dict) -> str:
    return f"""
QMainWindow, QWidget {{
    background-color: {C['bg']};
    color: {C['text']};
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Courier New', monospace;
    font-size: 12px;
}}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent;
    width: 3px;
    border-radius: 2px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C['border2']};
    border-radius: 2px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QLineEdit {{
    background: transparent;
    border: none;
    color: {C['text']};
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12px;
    padding: 1px 2px;
    selection-background-color: {C['accent']};
    text-decoration: none;
}}
QLineEdit:focus {{ color: {C['accent2']}; }}
QPushButton {{
    border: 1px solid {C['border2']};
    background: {C['surface']};
    color: {C['text2']};
    border-radius: 5px;
    padding: 5px 16px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 11px;
    text-decoration: none;
}}
QPushButton:hover {{
    background: {C['surface2']};
    border-color: {C['accent']};
    color: {C['text']};
}}
QPushButton:pressed {{ background: {C['border']}; }}
QDialog {{
    background: {C['surface']};
    border: 1px solid {C['border2']};
    border-radius: 10px;
}}
QLabel {{ background: transparent; color: {C['text']}; text-decoration: none; }}
QDoubleSpinBox, QSpinBox, QTimeEdit {{
    background: {C['surface2']};
    border: 1px solid {C['border2']};
    border-radius: 5px;
    color: {C['text']};
    padding: 5px 8px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12px;
}}
QDoubleSpinBox:focus, QSpinBox:focus, QTimeEdit:focus {{
    border-color: {C['accent']};
}}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button,
QTimeEdit::up-button, QTimeEdit::down-button {{
    width: 0; height: 0; border: none;
}}
QComboBox {{
    background: {C['dropdown_bg']};
    border: 1px solid {C['border2']};
    border-radius: 5px;
    color: {C['dropdown_text']};
    padding: 5px 8px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12px;
}}
QComboBox:focus {{ border-color: {C['accent']}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox::down-arrow {{ width: 0; height: 0; }}
QComboBox QAbstractItemView {{
    background: {C['dropdown_bg']};
    border: 1px solid {C['border2']};
    color: {C['dropdown_text']};
    selection-background-color: {C['dropdown_sel']};
    selection-color: {C['dropdown_text']};
    outline: none;
}}
QProgressBar {{
    border: none;
    border-radius: 2px;
    background: {C['surface2']};
    height: 3px;
}}
QProgressBar::chunk {{ border-radius: 2px; }}
QTextEdit {{
    background: {C['surface2']};
    border: 1px solid {C['border']};
    border-radius: 6px;
    color: {C['text']};
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12px;
    padding: 8px;
    selection-background-color: {C['accent']};
}}
QTabWidget::pane {{
    border: none;
    background: {C['surface']};
}}
QTabBar::tab {{
    background: {C['surface']};
    color: {C['text2']};
    padding: 6px 14px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 10px;
    letter-spacing: 0.5px;
    text-decoration: none;
}}
QTabBar::tab:selected {{
    color: {C['text']};
    border-bottom: 2px solid {C['accent']};
}}
QTabBar::tab:hover {{ color: {C['text']}; }}
QToolButton {{
    background: transparent;
    border: none;
    color: {C['text2']};
    padding: 6px 8px;
    border-radius: 5px;
    font-size: 15px;
    text-decoration: none;
}}
QToolButton:hover {{
    background: {C['surface2']};
    color: {C['text']};
}}
QCheckBox {{ color: {C['text2']}; spacing: 6px; font-size: 11px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px;
    background: {C['surface2']};
    border: 1px solid {C['border2']};
    border-radius: 3px;
}}
QCheckBox::indicator:checked {{
    background: {C['accent']};
    border-color: {C['accent']};
}}
QToolTip {{
    background-color: {C['tooltip_bg']};
    color: {C['tooltip_text']};
    border: 1px solid {C['border2']};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 11px;
    opacity: 255;
}}
"""
