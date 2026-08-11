"""Uygulama genelinde tutarlı, web sürümüyle aynı renk paletini kullanan koyu
tema. QApplication seviyesinde bir kere uygulanır (bkz. main.py); tek tek
widget'larda tekrar tekrar inline stil yazmaya gerek kalmaz."""

from __future__ import annotations

# Web sürümündeki (src/) renk paletiyle birebir aynı.
BG = "#0A0A0B"
PANEL = "#141417"
PANEL_ALT = "#18181C"
BORDER = "rgba(255,255,255,0.10)"
BORDER_SOFT = "rgba(255,255,255,0.06)"
TEXT = "#F1F5F9"
TEXT_HINT = "#94A3B8"
TEXT_MUTED = "#64748B"

GREEN = "#10B981"
GREEN_LIGHT = "#34D399"
BLUE = "#3B82F6"
BLUE_LIGHT = "#60A5FA"
PURPLE = "#8B5CF6"
RED = "#EF4444"
RED_LIGHT = "#F87171"
AMBER = "#F59E0B"

ROLE_COLORS = {"uretim": GREEN, "satis": BLUE, "admin": PURPLE}

QSS = f"""
* {{
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 13px;
}}

QWidget {{
    background-color: {BG};
    color: {TEXT};
}}

QMainWindow, QDialog {{
    background-color: {BG};
}}

QLabel {{
    background: transparent;
}}

QLabel[hint="true"] {{
    color: {TEXT_HINT};
    font-size: 11.5px;
    font-weight: 600;
}}

QGroupBox {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 12px;
    margin-top: 14px;
    padding: 12px;
    font-weight: 700;
    color: {TEXT_HINT};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {GREEN_LIGHT};
}}

QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit, QTextEdit {{
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 10px;
    color: {TEXT};
    selection-background-color: {GREEN};
}}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus, QDateEdit:focus {{
    border: 1px solid {GREEN};
}}
QLineEdit:read-only, QDoubleSpinBox:read-only {{
    color: {TEXT_MUTED};
    background-color: rgba(255,255,255,0.02);
}}

QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER};
    selection-background-color: {GREEN};
    color: {TEXT};
}}

QPushButton {{
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 16px;
    color: {TEXT};
    font-weight: 600;
}}
QPushButton:hover {{
    border: 1px solid {GREEN};
    color: {GREEN_LIGHT};
}}
QPushButton:pressed {{
    background-color: rgba(16,185,129,0.15);
}}
QPushButton:disabled {{
    color: {TEXT_MUTED};
    border: 1px solid {BORDER_SOFT};
}}

QPushButton[variant="primary"] {{
    background-color: {GREEN};
    border: 1px solid {GREEN};
    color: #04120C;
}}
QPushButton[variant="primary"]:hover {{
    background-color: {GREEN_LIGHT};
}}
QPushButton[variant="danger"] {{
    background-color: transparent;
    border: 1px solid {RED};
    color: {RED_LIGHT};
}}
QPushButton[variant="danger"]:hover {{
    background-color: rgba(239,68,68,0.12);
}}

QTableWidget {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
    gridline-color: {BORDER_SOFT};
    color: {TEXT};
    alternate-background-color: rgba(255,255,255,0.02);
}}
QHeaderView::section {{
    background-color: {PANEL_ALT};
    color: {TEXT_HINT};
    padding: 8px;
    border: none;
    border-bottom: 1px solid {BORDER};
    font-weight: 700;
    text-transform: uppercase;
    font-size: 11px;
}}
QTableWidget::item {{
    padding: 4px;
}}
QTableWidget::item:selected {{
    background-color: rgba(16,185,129,0.18);
    color: {TEXT};
}}

QListWidget {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
    color: {TEXT};
}}
QListWidget::item {{
    padding: 8px;
    border-bottom: 1px solid {BORDER_SOFT};
}}
QListWidget::item:selected {{
    background-color: rgba(16,185,129,0.18);
}}

QTabBar::tab {{
    background: rgba(255,255,255,0.03);
    color: {TEXT_HINT};
    padding: 10px 18px;
    margin: 4px 2px;
    border-radius: 8px;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    background: rgba(16,185,129,0.15);
    color: {TEXT};
}}
QTabBar::tab:hover {{
    color: {TEXT};
}}

QSplitter::handle {{
    background: {BORDER};
}}

QScrollBar:vertical {{
    background: {BG};
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: {PANEL_ALT};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {GREEN};
}}
QScrollBar:horizontal {{
    background: {BG};
    height: 10px;
}}
QScrollBar::handle:horizontal {{
    background: {PANEL_ALT};
    border-radius: 5px;
}}

QStatusBar {{
    background: {PANEL};
    color: {TEXT_HINT};
}}

QMessageBox {{
    background-color: {PANEL};
}}

QMenu {{
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER};
    color: {TEXT};
}}
QMenu::item:selected {{
    background-color: rgba(16,185,129,0.18);
}}
"""


def apply_theme(app) -> None:
    app.setStyleSheet(QSS)


def chip_style(color: str, filled: bool = False) -> str:
    """QLabel için renkli 'chip' (rozet) stili — rol rengi vb. dinamik
    renkler için QSS'in dışında, tek satırlık yardımcı."""
    if filled:
        return f"background: {color}; color: #04120C; border-radius: 10px; padding: 3px 10px; font-weight: 700;"
    return f"background: {color}22; color: {color}; border-radius: 10px; padding: 3px 10px; font-weight: 700;"
