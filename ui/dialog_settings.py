"""İlk açılış ve sonrasında düzenlenebilir Ayarlar diyaloğu — Turso/Gemini/
Sheets bağlantı bilgilerini core.settings.AppSettings olarak kaydeder."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from core.settings import AppSettings, save_settings


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None, first_run: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Ayarlar")
        self.setMinimumWidth(480)
        self._settings = settings

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

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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
        save_settings(self._settings)
        self.accept()

    @property
    def settings(self) -> AppSettings:
        return self._settings
