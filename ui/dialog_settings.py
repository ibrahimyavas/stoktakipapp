"""İlk açılış ve sonrasında düzenlenebilir Ayarlar diyaloğu — Turso/Gemini/
Sheets bağlantı bilgilerini ve Görünüm (açık/koyu + aksan rengi) tercihlerini
core.settings.AppSettings olarak kaydeder."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.settings import AppSettings, save_settings
from ui.theme import PRESET_ACCENTS, apply_theme


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None, first_run: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Ayarlar")
        self.setMinimumWidth(480)
        self._settings = settings
        self._accent = settings.accent_color
        self._mode = settings.theme_mode

        layout = QVBoxLayout(self)

        if first_run:
            intro = QLabel(
                "Hoş geldiniz — devam etmeden önce veritabanı bağlantı bilgilerinizi "
                "girin. Bu bilgiler bilgisayarınızda yerel olarak saklanır."
            )
            intro.setWordWrap(True)
            layout.addWidget(intro)

        form = QFormLayout()

        self.turso_url_edit = QLineEdit(settings.turso_database_url)
        self.turso_url_edit.setPlaceholderText("libsql://...")
        form.addRow("Turso Database URL *", self.turso_url_edit)

        self.turso_token_edit = QLineEdit(settings.turso_auth_token)
        self.turso_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Turso Auth Token *", self.turso_token_edit)

        self.gemini_key_edit = QLineEdit(settings.gemini_api_key)
        self.gemini_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Gemini API Key (opsiyonel, OCR için)", self.gemini_key_edit)

        self.sheets_url_edit = QLineEdit(settings.sheets_url)
        self.sheets_url_edit.setPlaceholderText("https://script.google.com/...")
        form.addRow("Google Sheets Webhook URL (opsiyonel)", self.sheets_url_edit)

        layout.addLayout(form)

        layout.addWidget(self._build_appearance_box())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self._on_cancel)
        layout.addWidget(buttons)

    # -- Görünüm: açık/koyu + aksan rengi ---------------------------------

    def _build_appearance_box(self) -> QGroupBox:
        box = QGroupBox("Görünüm")
        layout = QVBoxLayout(box)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Mod:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Koyu", "dark")
        self.mode_combo.addItem("Açık", "light")
        self.mode_combo.setCurrentIndex(0 if self._mode == "dark" else 1)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        swatch_row = QHBoxLayout()
        swatch_row.addWidget(QLabel("Aksan Rengi:"))
        for name, hex_color in PRESET_ACCENTS.items():
            btn = QPushButton()
            btn.setToolTip(name)
            btn.setFixedSize(28, 28)
            btn.setStyleSheet(
                f"background: {hex_color}; border-radius: 14px; border: 2px solid rgba(255,255,255,0.25);"
            )
            btn.clicked.connect(lambda _, c=hex_color: self._set_accent(c))
            swatch_row.addWidget(btn)

        custom_btn = QPushButton("Özel Renk...")
        custom_btn.clicked.connect(self._pick_custom_color)
        swatch_row.addWidget(custom_btn)
        swatch_row.addStretch()
        layout.addLayout(swatch_row)

        self.preview_label = QLabel()
        self._update_preview_label()
        layout.addWidget(self.preview_label)

        return box

    def _update_preview_label(self) -> None:
        self.preview_label.setText(f"Seçili renk: {self._accent}")
        self.preview_label.setStyleSheet(f"color: {self._accent}; font-weight: 700;")

    def _set_accent(self, hex_color: str) -> None:
        self._accent = hex_color
        self._update_preview_label()
        self._live_preview()

    def _pick_custom_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._accent), self, "Aksan Rengi Seç")
        if color.isValid():
            self._set_accent(color.name())

    def _on_mode_changed(self, _index: int) -> None:
        self._mode = self.mode_combo.currentData()
        self._live_preview()

    def _live_preview(self) -> None:
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self._mode, self._accent)

    def _on_cancel(self) -> None:
        # Kaydedilmeden değiştirilen canlı önizlemeyi eski haline döndür.
        self._live_preview_revert()
        self.reject()

    def _live_preview_revert(self) -> None:
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self._settings.theme_mode, self._settings.accent_color)

    # -- Kaydetme ------------------------------------------------------

    def _on_save(self) -> None:
        url = self.turso_url_edit.text().strip()
        token = self.turso_token_edit.text().strip()
        if not url or not token:
            QMessageBox.warning(
                self, "Eksik bilgi", "Turso Database URL ve Auth Token zorunludur."
            )
            return

        self._settings.turso_database_url = url
        self._settings.turso_auth_token = token
        self._settings.gemini_api_key = self.gemini_key_edit.text().strip()
        self._settings.sheets_url = self.sheets_url_edit.text().strip()
        self._settings.theme_mode = self._mode
        self._settings.accent_color = self._accent
        save_settings(self._settings)
        self._live_preview()  # kaydedilen tema kalıcı olarak uygulansın
        self.accept()

    @property
    def settings(self) -> AppSettings:
        return self._settings
