"""ProfileSelector.tsx karşılığı — kullanıcı rol seçim ekranı.

Not: Renkler burada bilinçli olarak minimal tutuluyor — arka plan/metin
renkleri artık qt-material'ın uyguladığı temaya (açık/koyu + kullanıcının
seçtiği aksan) göre otomatik değişiyor; sadece rol rengi (info.color, her
zaman aynı — uretim/satis/admin ayırt edici renk) sabit kalıyor."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.models import PAGE_LABELS, PROFILES
from ui.theme import chip_style


class ProfileCard(QGroupBox):
    def __init__(self, role_key: str, on_click, parent=None):
        super().__init__(parent)
        info = PROFILES[role_key]
        self.setMinimumWidth(260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(12)

        title = QLabel(info.label)
        title.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {info.color};")
        layout.addWidget(title)

        desc = QLabel(info.description)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        pages_row = QHBoxLayout()
        for page in info.pages:
            chip = QLabel(PAGE_LABELS.get(page, page))
            chip.setStyleSheet(chip_style(info.color) + " font-size: 11px;")
            pages_row.addWidget(chip)
        pages_row.addStretch()
        layout.addLayout(pages_row)

        layout.addStretch()

        select_btn = QPushButton(f"{info.label} olarak devam et")
        select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        select_btn.setMinimumHeight(38)
        select_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {info.color};
                color: #04120C;
                border: none;
                border-radius: 8px;
                padding: 10px;
                font-weight: 700;
                font-size: 13px;
            }}
            QPushButton:hover {{ background: {info.color}CC; }}
            """
        )
        select_btn.clicked.connect(lambda: on_click(role_key))
        layout.addWidget(select_btn)


class ProfileSelectorWidget(QWidget):
    profile_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 60, 40, 60)
        outer.setSpacing(30)

        heading = QLabel("Üretim & Satış Defteri")
        heading.setStyleSheet("font-size: 24px; font-weight: 700;")
        outer.addWidget(heading)

        sub = QLabel("Devam etmek için rolünüzü seçin")
        outer.addWidget(sub)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(20)
        for role_key in ("uretim", "satis", "admin"):
            cards_row.addWidget(ProfileCard(role_key, self._on_select))
        outer.addLayout(cards_row)
        outer.addStretch()

    def _on_select(self, role_key: str) -> None:
        self.profile_selected.emit(role_key)
