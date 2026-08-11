"""GoogleSheetsModal.tsx karşılığı — Google Sheets webhook URL'i kaydetme ve
tetiklemeli senkron (admin-only, MainWindow'da gated)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.app_state import AppState
from core.sheets_sync import sync_all_to_sheets
from ui.workers import run_in_background


class SheetsSyncDialog(QDialog):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Google Sheets Senkronizasyonu")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)

        info = QLabel(
            "Verileri (kayıtlar, firmalar, satışlar) bir Google Apps Script Web App "
            "webhook'una tek yönlü olarak gönderir."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.url_edit = QLineEdit(state.sheets_url)
        self.url_edit.setPlaceholderText("https://script.google.com/macros/s/.../exec")
        layout.addWidget(QLabel("Web App URL"))
        layout.addWidget(self.url_edit)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Kaydet ve Senkronize Et")
        save_btn.setProperty("variant", "primary")
        save_btn.clicked.connect(self._save_and_sync)
        btn_row.addWidget(save_btn)

        sync_now_btn = QPushButton("Şimdi Senkronize Et")
        sync_now_btn.clicked.connect(self._sync_now)
        btn_row.addWidget(sync_now_btn)
        layout.addLayout(btn_row)

    def _save_and_sync(self) -> None:
        url = self.url_edit.text().strip()
        try:
            self.state.save_sheets_url(url)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Hata", f"URL kaydedilemedi:\n{exc}")
            return
        if url:
            self._sync_now()
        else:
            self.status_label.setText("URL kaydedildi (boş — senkron devre dışı).")

    def _sync_now(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "Eksik bilgi", "Önce bir Web App URL girin.")
            return
        self.status_label.setText("Senkronize ediliyor...")
        run_in_background(
            lambda: sync_all_to_sheets(self.state.records, self.state.companies, self.state.sales, url),
            self._on_sync_done,
            self._on_sync_error,
        )

    def _on_sync_done(self, result: tuple[bool, str]) -> None:
        ok, msg = result
        self.status_label.setText(("✓ " if ok else "✗ ") + msg)

    def _on_sync_error(self, msg: str) -> None:
        self.status_label.setText("Senkron sırasında beklenmeyen bir hata oluştu.")
        print(msg)
