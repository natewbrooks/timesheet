"""
data.py — persistence, settings, and utility functions
"""
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

# ── Paths (overridable in settings) ───────────────────────────────────────────
DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "timesheet"

def get_data_dir(settings: dict) -> Path:
    p = Path(settings.get("data_dir", str(DEFAULT_DATA_DIR)))
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_data_file(settings: dict) -> Path:
    return get_data_dir(settings) / "data.json"

def get_notes_file(settings: dict) -> Path:
    return get_data_dir(settings) / "notes.json"

SETTINGS_FILE = DEFAULT_DATA_DIR / "settings.json"

# ── Settings ───────────────────────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    # Pay
    "pay_type": "hourly",          # hourly | salary
    "hourly_rate": 0.0,
    "annual_salary": 0.0,
    "us_state": "CA",
    "pay_period": "weekly",        # weekly | biweekly | monthly

    # Week definition
    "week_start_day": "wednesday",  # day after deadline
    "deadline_day": "tuesday",
    "deadline_time": "23:59",

    # Hours target (global default)
    "default_target_hours": 40.0,

    # UI
    "toast_duration": 4,           # seconds
    "toast_position": "bottom_right",
    "hotkey_notes": "Ctrl+N",
    "data_dir": str(DEFAULT_DATA_DIR),

    # Theme
    "theme": "dark",
    "accent_color": "#4f7cff",
}

def load_settings() -> dict:
    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SETTINGS_FILE.exists():
        try:
            s = json.loads(SETTINGS_FILE.read_text())
            out = dict(DEFAULT_SETTINGS)
            out.update(s)
            return out
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)

def save_settings(s: dict):
    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(s, indent=2))

# ── Data ───────────────────────────────────────────────────────────────────────
def load_data(settings: dict) -> dict:
    f = get_data_file(settings)
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            pass
    return {}

def save_data(data: dict, settings: dict):
    get_data_file(settings).write_text(json.dumps(data, indent=2))

def load_notes(settings: dict) -> dict:
    f = get_notes_file(settings)
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            pass
    return {}

def save_notes(notes: dict, settings: dict):
    get_notes_file(settings).write_text(json.dumps(notes, indent=2))

# ── Sheet numbering ────────────────────────────────────────────────────────────
# Sheets are numbered sequentially from the first entry date, not by calendar week.
# Key: "sheet_N" (N=1,2,3…)
# Each sheet has: start_date, end_date, days (dict date_str -> list[int])
#                 target_hours, hourly_rate, pay_type, deadline_day, deadline_time

def day_name_to_weekday(name: str) -> int:
    """monday=0 … sunday=6"""
    days = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    try:
        return days.index(name.lower())
    except ValueError:
        return 0

def get_week_dates(start_date: date) -> list[date]:
    """7 days starting from start_date."""
    return [start_date + timedelta(days=i) for i in range(7)]

def find_or_create_sheet(data: dict, settings: dict, for_date: date = None) -> tuple[str, dict]:
    """
    Return (sheet_key, sheet_dict) for a given date.
    Creates a new sheet if the date doesn't fall in any existing one.
    """
    if for_date is None:
        for_date = date.today()

    # Find existing sheet that contains this date
    for key, sheet in data.items():
        try:
            start = date.fromisoformat(sheet["start_date"])
            end = date.fromisoformat(sheet["end_date"])
            if start <= for_date <= end:
                return key, sheet
        except Exception:
            continue

    # Create new sheet
    week_start_day = day_name_to_weekday(settings.get("week_start_day", "wednesday"))
    # Find the Monday-equivalent (week_start_day) on or before for_date
    offset = (for_date.weekday() - week_start_day) % 7
    start = for_date - timedelta(days=offset)
    end = start + timedelta(days=6)

    sheet_num = len([k for k in data if k.startswith("sheet_")]) + 1
    key = f"sheet_{sheet_num}"
    sheet = {
        "sheet_num": sheet_num,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "days": {},
        "target_hours": settings.get("default_target_hours", 40.0),
        "hourly_rate": settings.get("hourly_rate", 0.0),
        "pay_type": settings.get("pay_type", "hourly"),
        "annual_salary": settings.get("annual_salary", 0.0),
        "deadline_day": settings.get("deadline_day", "tuesday"),
        "deadline_time": settings.get("deadline_time", "23:59"),
    }
    data[key] = sheet
    return key, sheet

def get_sheet_by_offset(data: dict, current_key: str, offset: int) -> tuple[str, dict] | None:
    """Navigate to next/prev sheet by sheet_num."""
    sheets = sorted(
        [(k, v) for k, v in data.items() if k.startswith("sheet_")],
        key=lambda x: x[1].get("sheet_num", 0)
    )
    keys = [s[0] for s in sheets]
    try:
        idx = keys.index(current_key) + offset
        if 0 <= idx < len(keys):
            k = keys[idx]
            return k, data[k]
    except ValueError:
        pass
    return None

# ── Time parsing ───────────────────────────────────────────────────────────────
def parse_time_input(text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    m = re.match(r'^(\d*):(\d+)$', text)
    if m:
        h = int(m.group(1)) if m.group(1) else 0
        mins = int(m.group(2))
        return h * 60 + mins
    m = re.match(r'^(\d+)$', text)
    if m:
        return int(m.group(1)) * 60
    return None

def format_hm_short(mins: int) -> str:
    """2:30 style — for editing"""
    h = mins // 60
    m = mins % 60
    return f"{h}:{m:02d}"

def format_hm_pretty(mins: int) -> str:
    """2hr 30m — for display"""
    if mins == 0:
        return "0m"
    h = mins // 60
    m = mins % 60
    if h == 0:
        return f"{m}m"
    if m == 0:
        return f"{h}hr"
    return f"{h}hr {m}m"

# ── Tax estimation ─────────────────────────────────────────────────────────────
# Approximate 2024 combined federal+state effective rates for ~median income
STATE_TAX_RATES = {
    "AL":0.05,"AK":0.0,"AZ":0.045,"AR":0.055,"CA":0.093,
    "CO":0.0455,"CT":0.065,"DE":0.066,"FL":0.0,"GA":0.055,
    "HI":0.09,"ID":0.058,"IL":0.0495,"IN":0.032,"IA":0.06,
    "KS":0.057,"KY":0.05,"LA":0.043,"ME":0.075,"MD":0.0575,
    "MA":0.05,"MI":0.0425,"MN":0.0985,"MS":0.05,"MO":0.054,
    "MT":0.069,"NE":0.0684,"NV":0.0,"NH":0.0,"NJ":0.1075,
    "NM":0.059,"NY":0.109,"NC":0.0525,"ND":0.029,"OH":0.04,
    "OK":0.05,"OR":0.099,"PA":0.0307,"RI":0.0599,"SC":0.07,
    "SD":0.0,"TN":0.0,"TX":0.0,"UT":0.0485,"VT":0.086,
    "VA":0.0575,"WA":0.0,"WV":0.065,"WI":0.0765,"WY":0.0,
    "DC":0.1075,
}
FEDERAL_RATE = 0.22  # approx effective federal for middle income

def estimate_net(gross: float, state: str) -> float:
    state_rate = STATE_TAX_RATES.get(state.upper(), 0.05)
    fica = 0.0765
    total_rate = min(FEDERAL_RATE + state_rate + fica, 0.65)
    return gross * (1 - total_rate)

def calc_earnings(minutes: int, sheet: dict, settings: dict) -> tuple[float, float]:
    """Returns (gross, net) for given minutes worked."""
    hrs = minutes / 60
    pay_type = sheet.get("pay_type", settings.get("pay_type", "hourly"))
    state = settings.get("us_state", "CA")
    if pay_type == "salary":
        salary = sheet.get("annual_salary", settings.get("annual_salary", 0.0))
        hourly_equiv = salary / 2080
    else:
        hourly_equiv = sheet.get("hourly_rate", settings.get("hourly_rate", 0.0))
    gross = hrs * hourly_equiv
    net = estimate_net(gross, state)
    return gross, net

# ── Deadline countdown ─────────────────────────────────────────────────────────
def hours_until_deadline(sheet: dict) -> float:
    """Hours remaining until this sheet's deadline datetime."""
    try:
        deadline_day = day_name_to_weekday(sheet.get("deadline_day", "tuesday"))
        dl_time_str = sheet.get("deadline_time", "23:59")
        h, m = map(int, dl_time_str.split(":"))
        end = date.fromisoformat(sheet["end_date"])
        deadline_dt = datetime.combine(end, datetime.min.time().replace(hour=h, minute=m))
        now = datetime.now()
        diff = (deadline_dt - now).total_seconds() / 3600
        return max(0.0, diff)
    except Exception:
        return 0.0
