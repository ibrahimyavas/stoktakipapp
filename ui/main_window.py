"""MobileNavigation.tsx + App.tsx'in ana pencere karşılığı — rol bazlı sayfa
geçişi, "Kaydediliyor" göstergesi, ve periyodik cihazlar-arası senkron
(5 saniyede bir + pencere odaklandığında — web'deki polling ile aynı)."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from core.app_state import AppState
from core.models import PAGE_LABELS, PROFILES
from ui.workers import run_in_background


class PlaceholderPage(QWidget):
    """Henüz yazılmamış bir sayfa için geçici içerik — sonraki fazlarda
    gerçek sayfa widget'larıyla değiştirilecek."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        msg = QLabel(f"{label} — bu ekran henüz eklenmedi.")
        msg.setStyleSheet("color: #64748B; font-size: 14px; padding: 40px;")
        layout.addWidget(msg)
        layout.addStretch()


class MainWindow(QMainWindow):
    def __init__(
        self,
        state: AppState,
        profile_role: str,
        on_change_profile,
        gemini_api_key: str = "",
        app_settings=None,
        parent=None,
    ):
        super().__init__(parent)
        self.state = state
        self.profile_role = profile_role
        self.on_change_profile = on_change_profile
        self.gemini_api_key = gemini_api_key
        self.app_settings = app_settings
        self.page_widgets: dict[str, QWidget] = {}

        info = PROFILES[profile_role]
        self.setWindowTitle(f"Üretim & Satış Defteri — {info.label}")
        self.resize(1200, 800)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header(info))

        self.tab_bar = QTabBar()
        self.tab_bar.setStyleSheet(
            f"""
            QTabBar::tab {{
                background: rgba(255,255,255,0.03);
                color: #94A3B8;
                padding: 10px 18px;
                margin: 4px;
                border-radius: 8px;
            }}
            QTabBar::tab:selected {{
                background: {info.color}22;
                color: white;
                font-weight: 700;
            }}
            """
        )
        for page_key in info.pages:
            self.tab_bar.addTab(PAGE_LABELS.get(page_key, page_key))
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tab_bar)

        self.stack = QStackedWidget()
        root.addWidget(self.stack)
        for page_key in info.pages:
            page = self._create_page(page_key)
            self.page_widgets[page_key] = page
            self.stack.addWidget(page)

        self.setStatusBar(QStatusBar())

        # Periyodik cihazlar-arası senkron: web'deki 5sn polling ile aynı fikir.
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(5000)
        self._sync_timer.timeout.connect(self.refresh_from_server)
        self._sync_timer.start()

    # -- UI kurulum yardımcıları -------------------------------------------

    def _build_header(self, info) -> QWidget:
        header = QWidget()
        header.setStyleSheet("background: #141417; border-bottom: 1px solid rgba(255,255,255,0.08);")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 10, 16, 10)

        title = QLabel("Üretim & Satış Defteri")
        title.setStyleSheet("color: white; font-weight: 700; font-size: 15px;")
        layout.addWidget(title)

        role_badge = QLabel(info.label)
        role_badge.setStyleSheet(
            f"background: {info.color}22; color: {info.color}; border-radius: 8px; "
            "padding: 3px 10px; font-weight: 600; font-size: 12px;"
        )
        layout.addWidget(role_badge)

        self.saving_label = QLabel("")
        self.saving_label.setStyleSheet("color: #34D399; font-size: 12px;")
        layout.addWidget(self.saving_label)

        layout.addStretch()

        mapper_btn = QPushButton("Ürün / Barkod Eşleştirme")
        mapper_btn.clicked.connect(self._open_barcode_mapper)
        layout.addWidget(mapper_btn)

        waybill_btn = QPushButton("İrsaliye Arşivi")
        waybill_btn.clicked.connect(self._open_waybill_vault)
        layout.addWidget(waybill_btn)

        if self.profile_role == "admin":
            sheets_btn = QPushButton("Sheets Senkron")
            sheets_btn.clicked.connect(self._open_sheets_sync)
            layout.addWidget(sheets_btn)

        settings_btn = QPushButton("Ayarlar")
        settings_btn.clicked.connect(self._open_settings)
        layout.addWidget(settings_btn)

        change_profile_btn = QPushButton("Rol Değiştir")
        change_profile_btn.clicked.connect(self.on_change_profile)
        layout.addWidget(change_profile_btn)

        return header

    def _open_sheets_sync(self) -> None:
        from ui.dialog_sheets_sync import SheetsSyncDialog

        dialog = SheetsSyncDialog(self.state, parent=self)
        dialog.exec()

    def _open_settings(self) -> None:
        from core.settings import load_settings
        from ui.dialog_settings import SettingsDialog

        settings = self.app_settings or load_settings()
        dialog = SettingsDialog(settings, parent=self, first_run=False)
        if dialog.exec():
            self.gemini_api_key = dialog.settings.gemini_api_key
            QMessageBox.information(
                self,
                "Kaydedildi",
                "Ayarlar kaydedildi. Turso veritabanı bilgileri değiştiyse "
                "değişikliğin uygulanması için uygulamayı yeniden başlatın.",
            )

    def _open_barcode_mapper(self) -> None:
        from ui.dialog_barcode_mapper import BarcodeMapperDialog

        dialog = BarcodeMapperDialog(self.state, on_saved=self._on_refreshed_local, parent=self)
        dialog.exec()

    def _open_waybill_vault(self) -> None:
        from ui.dialog_waybill_vault import WaybillVaultDialog

        dialog = WaybillVaultDialog(
            self.state, self.gemini_api_key, on_saved=self._on_refreshed_local, parent=self
        )
        dialog.exec()

    def _on_refreshed_local(self) -> None:
        for page in self.page_widgets.values():
            if hasattr(page, "on_data_refreshed"):
                page.on_data_refreshed()

    def _create_page(self, page_key: str) -> QWidget:
        # Sonraki fazlarda gerçek sayfalarla değiştirilecek — şimdilik
        # yazılmış olanları buradan bağlıyoruz, geri kalanı placeholder.
        if page_key == "defter":
            try:
                from ui.page_defter import DefterPage

                return DefterPage(self.state, self.set_saving, self.profile_role)
            except ImportError:
                pass
        elif page_key == "satis":
            try:
                from ui.page_satis import SatisPage

                return SatisPage(self.state, self.set_saving)
            except ImportError:
                pass
        elif page_key == "rapor":
            try:
                from ui.page_rapor import RaporPage

                return RaporPage(self.state)
            except ImportError:
                pass
        elif page_key == "genel":
            try:
                from ui.page_genel import GenelPage

                return GenelPage(self.state, self.set_saving, can_edit_belge=self.profile_role in ("satis", "admin"))
            except ImportError:
                pass
        return PlaceholderPage(PAGE_LABELS.get(page_key, page_key))

    def _on_tab_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)

    # -- Durum göstergesi + senkron ----------------------------------------

    def set_saving(self, saving: bool) -> None:
        self.saving_label.setText("Kaydediliyor..." if saving else "")

    def refresh_from_server(self) -> None:
        run_in_background(self.state.db.get_all_data, self._on_refreshed, self._on_refresh_error)

    def _on_refreshed(self, data) -> None:
        self.state.records = data.records
        self.state.companies = data.companies
        self.state.sales = data.sales
        self.state.waybills = data.waybills
        self.state.sheets_url = data.sheetsUrl
        for page in self.page_widgets.values():
            if hasattr(page, "on_data_refreshed"):
                page.on_data_refreshed()

    def _on_refresh_error(self, msg: str) -> None:
        self.statusBar().showMessage("Senkron hatası — internet bağlantınızı kontrol edin.", 4000)
        print(msg)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        reply = QMessageBox.question(
            self,
            "Çıkış",
            "Uygulamadan çıkmak istiyor musunuz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()
