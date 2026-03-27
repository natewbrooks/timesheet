"""
settings_dialog.py — multi-panel settings with full color config
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QPushButton, QDoubleSpinBox, QComboBox, QLineEdit,
    QSpinBox, QFrame, QStackedWidget, QFileDialog, QTimeEdit,
    QCheckBox, QScrollArea, QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QTime
from data import DEFAULT_SETTINGS, STATE_TAX_RATES
from theme import COLOR_LABELS

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
PAY_PERIODS = ["Weekly", "Biweekly", "Monthly"]


def sep(C):
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {C['border']}; border: none;")
    return f


def section_lbl(text, C):
    l = QLabel(text)
    l.setStyleSheet(f"color: {C['text3']}; font-size: 9px; letter-spacing: 2px; margin-top: 10px;")
    return l


def field_lbl(text, C):
    l = QLabel(text)
    l.setStyleSheet(f"color: {C['text2']}; font-size: 11px;")
    l.setFixedWidth(170)
    return l


def make_row(lbl_widget, field_widget):
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    hl = QHBoxLayout(w)
    hl.setContentsMargins(0, 2, 0, 2)
    hl.setSpacing(12)
    hl.addWidget(lbl_widget)
    hl.addWidget(field_widget, 1)
    return w


# ── Colour swatch row ──────────────────────────────────────────────────────────
class ColorRow(QWidget):
    def __init__(self, key: str, label: str, value: str, C: dict, parent=None):
        super().__init__(parent)
        self.key = key
        self.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(self)
        hl.setContentsMargins(0, 2, 0, 2)
        hl.setSpacing(8)

        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {C['text2']}; font-size: 11px;")
        lbl.setFixedWidth(170)
        hl.addWidget(lbl)

        self.swatch = QLabel()
        self.swatch.setFixedSize(20, 20)
        self.swatch.setStyleSheet(f"background: {value}; border-radius: 4px; border: 1px solid {C['border2']};")
        hl.addWidget(self.swatch)

        self.inp = QLineEdit(value)
        self.inp.setPlaceholderText("#rrggbb")
        self.inp.textChanged.connect(self._update_swatch)
        hl.addWidget(self.inp, 1)

    def _update_swatch(self, val: str):
        if val.startswith("#") and len(val) in (4, 7):
            self.swatch.setStyleSheet(f"background: {val}; border-radius: 4px; border: 1px solid #252938;")

    def get_value(self) -> str:
        return self.inp.text().strip()


# ── Panels ─────────────────────────────────────────────────────────────────────
class PanelPay(QWidget):
    def __init__(self, settings: dict, C: dict, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(section_lbl("PAY TYPE", C))
        self.pay_type = QComboBox()
        self.pay_type.addItems(["Hourly", "Salary"])
        self.pay_type.setCurrentText(settings.get("pay_type", "hourly").capitalize())
        layout.addWidget(make_row(field_lbl("Type", C), self.pay_type))

        self.pay_period = QComboBox()
        self.pay_period.addItems(PAY_PERIODS)
        self.pay_period.setCurrentText(settings.get("pay_period", "weekly").capitalize())
        layout.addWidget(make_row(field_lbl("Pay Period", C), self.pay_period))

        layout.addWidget(sep(C))
        layout.addWidget(section_lbl("COMPENSATION", C))

        self.hourly_rate = QDoubleSpinBox()
        self.hourly_rate.setRange(0, 10000)
        self.hourly_rate.setDecimals(2)
        self.hourly_rate.setPrefix("$ ")
        self.hourly_rate.setValue(settings.get("hourly_rate", 0))
        self.hourly_rate.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        layout.addWidget(make_row(field_lbl("Hourly Rate", C), self.hourly_rate))

        self.annual_salary = QDoubleSpinBox()
        self.annual_salary.setRange(0, 10_000_000)
        self.annual_salary.setDecimals(2)
        self.annual_salary.setPrefix("$ ")
        self.annual_salary.setSingleStep(1000)
        self.annual_salary.setValue(settings.get("annual_salary", 0))
        self.annual_salary.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        layout.addWidget(make_row(field_lbl("Annual Salary", C), self.annual_salary))

        layout.addWidget(sep(C))
        layout.addWidget(section_lbl("TAX — US STATE", C))

        self.us_state = QComboBox()
        states = sorted(STATE_TAX_RATES.keys())
        self.us_state.addItems(states)
        cur = settings.get("us_state", "CA")
        if cur in states:
            self.us_state.setCurrentText(cur)
        layout.addWidget(make_row(field_lbl("State", C), self.us_state))

        self.tax_note = QLabel("")
        self.tax_note.setStyleSheet(f"color: {C['text3']}; font-size: 10px;")
        layout.addWidget(self.tax_note)
        self._upd_tax()
        self.us_state.currentTextChanged.connect(lambda _: self._upd_tax())

        layout.addStretch()

    def _upd_tax(self):
        from data import STATE_TAX_RATES, FEDERAL_RATE
        s = self.us_state.currentText()
        sr = STATE_TAX_RATES.get(s, 0)
        total = min((FEDERAL_RATE + sr + 0.0765) * 100, 65)
        self.tax_note.setText(f"Est. combined: ~{total:.1f}%  (federal {FEDERAL_RATE*100:.0f}% + {s} {sr*100:.1f}% + FICA 7.65%)")

    def get_values(self) -> dict:
        return {
            "pay_type": self.pay_type.currentText().lower(),
            "pay_period": self.pay_period.currentText().lower(),
            "hourly_rate": self.hourly_rate.value(),
            "annual_salary": self.annual_salary.value(),
            "us_state": self.us_state.currentText(),
        }


class PanelSchedule(QWidget):
    def __init__(self, settings: dict, C: dict, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(section_lbl("WEEK DEADLINE", C))

        self.deadline_day = QComboBox()
        self.deadline_day.addItems(DAYS)
        dd = settings.get("deadline_day", "tuesday").capitalize()
        self.deadline_day.setCurrentText(dd)
        layout.addWidget(make_row(field_lbl("Deadline Day", C), self.deadline_day))

        # 12-hour AM/PM time picker
        self.deadline_time = QTimeEdit()
        dl_time = settings.get("deadline_time", "23:59")
        h, m = map(int, dl_time.split(":"))
        self.deadline_time.setTime(QTime(h, m))
        self.deadline_time.setDisplayFormat("hh:mm AP")
        self.deadline_time.setButtonSymbols(QTimeEdit.ButtonSymbols.NoButtons)
        layout.addWidget(make_row(field_lbl("Deadline Time", C), self.deadline_time))

        layout.addWidget(sep(C))
        layout.addWidget(section_lbl("DEFAULT TARGET HOURS", C))

        note = QLabel("Each sheet can override independently.")
        note.setStyleSheet(f"color: {C['text3']}; font-size: 10px;")
        layout.addWidget(note)

        self.target_hours = QDoubleSpinBox()
        self.target_hours.setRange(0, 168)
        self.target_hours.setDecimals(1)
        self.target_hours.setSuffix(" hrs")
        self.target_hours.setValue(settings.get("default_target_hours", 40.0))
        self.target_hours.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        layout.addWidget(make_row(field_lbl("Default Target", C), self.target_hours))

        layout.addStretch()

    def get_values(self) -> dict:
        t = self.deadline_time.time()
        return {
            "deadline_day": self.deadline_day.currentText().lower(),
            "deadline_time": f"{t.hour():02d}:{t.minute():02d}",
            "default_target_hours": self.target_hours.value(),
        }


class PanelInterface(QWidget):
    def __init__(self, settings: dict, C: dict, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(section_lbl("THEME", C))

        self.theme = QComboBox()
        self.theme.addItems(["dark", "midnight", "slate"])
        self.theme.setCurrentText(settings.get("theme", "dark"))
        layout.addWidget(make_row(field_lbl("Base Theme", C), self.theme))

        layout.addWidget(sep(C))
        layout.addWidget(section_lbl("TOASTS", C))

        self.toast_duration = QSpinBox()
        self.toast_duration.setRange(1, 30)
        self.toast_duration.setSuffix(" sec")
        self.toast_duration.setValue(settings.get("toast_duration", 4))
        self.toast_duration.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        layout.addWidget(make_row(field_lbl("Toast Duration", C), self.toast_duration))

        self.toast_pos = QComboBox()
        self.toast_pos.addItems(["bottom_right", "top_right", "bottom_left", "top_left"])
        self.toast_pos.setCurrentText(settings.get("toast_position", "bottom_right"))
        layout.addWidget(make_row(field_lbl("Toast Position", C), self.toast_pos))

        layout.addWidget(sep(C))
        layout.addWidget(section_lbl("HOTKEYS", C))

        self.hotkey_notes = QLineEdit(settings.get("hotkey_notes", "Ctrl+N"))
        layout.addWidget(make_row(field_lbl("Open Notes", C), self.hotkey_notes))

        self.hotkey_preview = QLineEdit(settings.get("hotkey_preview", "Ctrl+P"))
        layout.addWidget(make_row(field_lbl("Toggle Preview", C), self.hotkey_preview))

        layout.addStretch()

    def get_values(self) -> dict:
        return {
            "theme": self.theme.currentText(),
            "toast_duration": self.toast_duration.value(),
            "toast_position": self.toast_pos.currentText(),
            "hotkey_notes": self.hotkey_notes.text().strip(),
            "hotkey_preview": self.hotkey_preview.text().strip(),
        }


class PanelColors(QWidget):
    def __init__(self, settings: dict, C: dict, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._C = C

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(section_lbl("COLOR OVERRIDES", C))
        note = QLabel("Overrides the selected base theme. Leave blank to use theme default.")
        note.setStyleSheet(f"color: {C['text3']}; font-size: 10px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        self._rows: dict[str, ColorRow] = {}
        color_overrides = settings.get("color_overrides", {})

        for key, label in COLOR_LABELS.items():
            val = color_overrides.get(key, C.get(key, ""))
            row = ColorRow(key, label, val, C)
            self._rows[key] = row
            layout.addWidget(row)

        layout.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll)

    def get_values(self) -> dict:
        overrides = {}
        for key, row in self._rows.items():
            v = row.get_value()
            if v.startswith("#"):
                overrides[key] = v
        return {"color_overrides": overrides}


class PanelStorage(QWidget):
    def __init__(self, settings: dict, C: dict, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(section_lbl("DATA LOCATION", C))
        note = QLabel("Changing this won't move existing files.")
        note.setStyleSheet(f"color: {C['text3']}; font-size: 10px;")
        layout.addWidget(note)

        path_row = QWidget()
        path_row.setStyleSheet("background: transparent;")
        pr_l = QHBoxLayout(path_row)
        pr_l.setContentsMargins(0, 0, 0, 0)
        pr_l.setSpacing(8)

        self.data_dir = QLineEdit(settings.get("data_dir", ""))
        self.data_dir.setPlaceholderText("~/.local/share/timesheet")
        pr_l.addWidget(self.data_dir, 1)

        browse_btn = QPushButton("Browse")
        browse_btn.setFixedWidth(70)
        browse_btn.clicked.connect(self._browse)
        pr_l.addWidget(browse_btn)

        layout.addWidget(path_row)
        layout.addStretch()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Select data folder")
        if d:
            self.data_dir.setText(d)

    def get_values(self) -> dict:
        return {"data_dir": self.data_dir.text().strip()}


# ── Main dialog ────────────────────────────────────────────────────────────────
class SettingsDialog(QDialog):
    settings_saved = pyqtSignal(dict)

    def __init__(self, settings: dict, C: dict, parent=None):
        super().__init__(parent)
        self._settings = dict(settings)
        self._C = C
        self.setWindowTitle("Settings")
        self.setFixedSize(640, 500)
        self.setModal(True)
        self._build()

    def _build(self):
        C = self._C
        self.setStyleSheet(f"""
            QDialog {{ background: {C['surface']}; border: 1px solid {C['border2']}; }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar
        sidebar = QWidget()
        sidebar.setFixedWidth(140)
        sidebar.setStyleSheet(f"background: {C['bg']}; border-right: 1px solid {C['border']};")
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0, 16, 0, 16)
        sl.setSpacing(2)

        title = QLabel("SETTINGS")
        title.setStyleSheet(f"color: {C['text3']}; font-size: 9px; letter-spacing: 3px; padding: 0 16px 12px 16px;")
        sl.addWidget(title)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background: {C['surface']};")
        self._nav_btns = []

        panels = [
            ("Pay",       PanelPay(self._settings, C)),
            ("Schedule",  PanelSchedule(self._settings, C)),
            ("Interface", PanelInterface(self._settings, C)),
            ("Colors",    PanelColors(self._settings, C)),
            ("Storage",   PanelStorage(self._settings, C)),
        ]
        self._panel_objs = {}

        for i, (name, panel) in enumerate(panels):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none;
                    color: {C['text2']}; text-align: left;
                    padding: 8px 16px; font-size: 11px; border-radius: 0;
                }}
                QPushButton:checked {{
                    color: {C['text']}; background: {C['surface']};
                    border-left: 2px solid {C['accent']};
                }}
                QPushButton:hover:!checked {{
                    color: {C['text']}; background: {C['surface2']};
                }}
            """)
            btn.clicked.connect(lambda _, idx=i: self._switch(idx))
            sl.addWidget(btn)
            self._nav_btns.append(btn)
            self._stack.addWidget(panel)
            self._panel_objs[name] = panel

        sl.addStretch()
        layout.addWidget(sidebar)

        right = QWidget()
        right.setStyleSheet(f"background: {C['surface']};")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self._stack, 1)

        footer = QWidget()
        footer.setFixedHeight(50)
        footer.setStyleSheet(f"background: {C['surface']}; border-top: 1px solid {C['border']};")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 0, 16, 0)
        fl.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.reject)
        fl.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setFixedWidth(80)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C['accent']}; border: none; color: white;
                border-radius: 5px; font-size: 11px;
            }}
            QPushButton:hover {{ background: {C['accent2']}; }}
        """)
        save_btn.clicked.connect(self._save)
        fl.addWidget(save_btn)
        rl.addWidget(footer)
        layout.addWidget(right, 1)

    def _switch(self, idx: int):
        self._stack.setCurrentIndex(idx)
        for i, b in enumerate(self._nav_btns):
            b.setChecked(i == idx)

    def _save(self):
        for name, panel in self._panel_objs.items():
            self._settings.update(panel.get_values())
        from data import save_settings
        save_settings(self._settings)
        self.settings_saved.emit(self._settings)
        self.accept()
