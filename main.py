"""Üretim & Satış Defteri — masaüstü uygulaması giriş noktası."""

from __future__ import annotations

import sys
from pathlib import Path

# desktop-app/ kökünü import path'ine ekle (core/ ve ui/ paketlerini bulabilsin).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication, QMessageBox

from core.app_state import AppState
from core.db_core import DbCore
from core.models import PROFILES
from core.settings import load_settings, save_settings
from ui.dialog_settings import SettingsDialog
from ui.main_window import MainWindow
from ui.profile_selector import ProfileSelectorWidget
from ui.theme import apply_theme


class AppController:
    """Ekranlar arası geçişi (Ayarlar → Rol Seçimi → Ana Pencere) yönetir —
    App.tsx'teki en üst seviye state makinesinin karşılığı."""

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("Üretim & Satış Defteri")
        apply_theme(self.app)
        self.settings = load_settings()
        self.db: DbCore | None = None
        self.state: AppState | None = None
        self.window = None  # aktif üst seviye pencere/widget referansı (GC'yi engellemek için)

    def run(self) -> int:
        if not self.settings.is_configured():
            if not self._show_settings(first_run=True):
                return 0  # kullanıcı Ayarlar'ı iptal etti, çıkış

        if not self._connect_db():
            return 1

        self._show_profile_selector()
        return self.app.exec()

    def _show_settings(self, first_run: bool = False) -> bool:
        dialog = SettingsDialog(self.settings, first_run=first_run)
        ok = dialog.exec()
        return bool(ok)

    def _connect_db(self) -> bool:
        try:
            self.db = DbCore(
                url=self.settings.turso_database_url,
                auth_token=self.settings.turso_auth_token,
            )
            self.state = AppState(self.db)
            self.state.load_all()
            return True
        except Exception as exc:  # noqa: BLE001 — kullanıcıya göstermek için genel yakalama
            QMessageBox.critical(
                None,
                "Bağlantı Hatası",
                "Veritabanına bağlanılamadı. Ayarlar'daki Turso bilgilerinizi "
                f"kontrol edin.\n\nDetay: {exc}",
            )
            return False

    def _show_profile_selector(self) -> None:
        # Daha önce seçilmiş bir rol varsa (DB'de saklı — web app ile aynı
        # `profile` alanı), doğrudan ona atla.
        if self.state.profile and self.state.profile in PROFILES:
            self._show_main_window(self.state.profile)
            return

        selector = ProfileSelectorWidget()
        selector.profile_selected.connect(self._on_profile_selected)
        selector.showMaximized()
        self.window = selector

    def _on_profile_selected(self, role_key: str) -> None:
        self.state.save_profile(role_key)
        self._show_main_window(role_key)

    def _show_main_window(self, role_key: str) -> None:
        main_window = MainWindow(
            self.state,
            role_key,
            on_change_profile=self._change_profile,
            gemini_api_key=self.settings.gemini_api_key,
            app_settings=self.settings,
        )
        main_window.showMaximized()
        self.window = main_window

    def _change_profile(self) -> None:
        self.state.save_profile("")
        self._show_profile_selector()


def main() -> int:
    controller = AppController()
    return controller.run()


if __name__ == "__main__":
    raise SystemExit(main())
