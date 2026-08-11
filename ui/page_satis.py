"""DashboardSatis.tsx karşılığı — Satış ekranı: stok özeti, firma yönetimi,
bekleyen satışlar (Firmaya İşle), ve firma bazlı satış listesi."""

from __future__ import annotations

import time
import uuid

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from core.app_state import AppState
from core.stock_logic import (
    calculate_ending_stock,
    format_date_tr,
    format_number,
    get_today_date_string,
    recalculate_product_stock_chain,
)
from ui.dialog_complete_sale import CompleteSaleDialog
from ui.dialog_qr import QRCodeDialog


def _new_id() -> str:
    return f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:5]}"


class SatisPage(QWidget):
    def __init__(self, state: AppState, set_saving, parent=None):
        super().__init__(parent)
        self.state = state
        self.set_saving = set_saving
        self.company_edit_id: str | None = None

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)

        tabs.addTab(self._build_stock_and_sale_tab(), "Stok & Yeni Satış")
        tabs.addTab(self._build_pending_tab(), "Bekleyen Satışlar")
        tabs.addTab(self._build_company_tab(), "Firmalar")
        tabs.addTab(self._build_sales_list_tab(), "Satış Listesi")

        self.on_data_refreshed()

    # -- Sekme 1: Stok özeti + hızlı satış başlatma ------------------------

    def _build_stock_and_sale_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        quick_box = QGroupBox("Yeni Satış Başlat")
        quick_grid = QGridLayout(quick_box)
        self.quick_product_combo = QComboBox()
        quick_grid.addWidget(QLabel("Ürün"), 0, 0)
        quick_grid.addWidget(self.quick_product_combo, 0, 1)

        self.quick_teneke, self.quick_kg, self.quick_adet = QDoubleSpinBox(), QDoubleSpinBox(), QDoubleSpinBox()
        for s in (self.quick_teneke, self.quick_kg, self.quick_adet):
            s.setRange(0, 1_000_000_000)
            s.setDecimals(2)
        quick_grid.addWidget(QLabel("Teneke"), 1, 0)
        quick_grid.addWidget(self.quick_teneke, 1, 1)
        quick_grid.addWidget(QLabel("Kg"), 2, 0)
        quick_grid.addWidget(self.quick_kg, 2, 1)
        quick_grid.addWidget(QLabel("Adet"), 3, 0)
        quick_grid.addWidget(self.quick_adet, 3, 1)

        start_btn = QPushButton("Satışı Başlat → Firmaya İşle")
        start_btn.setProperty("variant", "primary")
        start_btn.clicked.connect(self._start_quick_sale)
        quick_grid.addWidget(start_btn, 4, 0, 1, 2)
        layout.addWidget(quick_box)

        self.stock_table = QTableWidget(0, 4)
        self.stock_table.setHorizontalHeaderLabels(["Ürün", "Teneke", "Kg", "Adet"])
        self.stock_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.stock_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.stock_table)

        return widget

    def _latest_stock_by_product(self) -> dict[str, dict]:
        latest: dict[str, dict] = {}
        for r in self.state.records:
            code = r["urunKodu"]
            existing = latest.get(code)
            if not existing or r["tarih"] > existing["tarih"] or r["id"] > existing["id"]:
                latest[code] = r
        return latest

    def _refresh_stock(self) -> None:
        latest = self._latest_stock_by_product()
        self.stock_table.setRowCount(len(latest))
        self.quick_product_combo.clear()
        for i, (code, r) in enumerate(sorted(latest.items(), key=lambda kv: kv[1]["urunAdi"])):
            out_of_stock = (r.get("bitisStokTeneke") or 0) <= 0 and (r.get("bitisStokKg") or 0) <= 0 and (r.get("bitisStokAdet") or 0) <= 0
            name_item = QTableWidgetItem(f"{r['urunAdi']} ({code})")
            if out_of_stock:
                name_item.setForeground(Qt.GlobalColor.red)
            self.stock_table.setItem(i, 0, name_item)
            self.stock_table.setItem(i, 1, QTableWidgetItem(format_number(r.get("bitisStokTeneke"))))
            self.stock_table.setItem(i, 2, QTableWidgetItem(format_number(r.get("bitisStokKg"))))
            self.stock_table.setItem(i, 3, QTableWidgetItem(format_number(r.get("bitisStokAdet"))))
            self.quick_product_combo.addItem(f"{r['urunAdi']} ({code})", code)

    def _start_quick_sale(self) -> None:
        code = self.quick_product_combo.currentData()
        if not code:
            QMessageBox.warning(self, "Ürün seçin", "Lütfen satılacak ürünü seçin.")
            return
        if self.quick_teneke.value() <= 0 and self.quick_kg.value() <= 0 and self.quick_adet.value() <= 0:
            QMessageBox.warning(self, "Miktar girin", "Lütfen en az bir satış miktarı girin.")
            return

        latest = self._latest_stock_by_product().get(code)
        available_teneke = latest.get("bitisStokTeneke", 0) if latest else 0
        available_kg = latest.get("bitisStokKg", 0) if latest else 0
        available_adet = latest.get("bitisStokAdet", 0) if latest else 0
        if self.quick_teneke.value() > available_teneke or self.quick_kg.value() > available_kg or self.quick_adet.value() > available_adet:
            QMessageBox.warning(self, "Stok Yetersiz", "Girilen miktar mevcut stoğu aşıyor.")
            return

        new_record = {
            "id": _new_id(),
            "tarih": get_today_date_string(),
            "urunKodu": code,
            "urunAdi": latest["urunAdi"] if latest else code,
            "barcode": latest.get("barcode") or code if latest else code,
            "uretimKg": 0, "uretimTeneke": 0, "uretimAdet": 0,
            "fireKg": 0, "fireTeneke": 0, "fireAdet": 0,
            "satisKg": self.quick_kg.value(), "satisTeneke": self.quick_teneke.value(), "satisAdet": self.quick_adet.value(),
            "baslangicStokKg": 0, "baslangicStokTeneke": 0, "baslangicStokAdet": 0,
            "fiyatTeneke": latest.get("fiyatTeneke") if latest else 0,
            "fiyatKg": latest.get("fiyatKg") if latest else 0,
            "fiyatAdet": latest.get("fiyatAdet") if latest else 0,
            "satisId": "", "linkedSaleId": None, "manualBaslangicStok": False, "baslangicStokKilitli": False,
        }

        try:
            updated_list = recalculate_product_stock_chain([*self.state.records, new_record], code)
            to_upsert = [r for r in updated_list if r["urunKodu"].strip().lower() == code.strip().lower()]
            self.state.db.save_all_data(records=to_upsert)
            self.state.load_all()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Hata", f"Satış başlatılamadı:\n{exc}")
            return

        rec = next(r for r in self.state.records if r["id"] == new_record["id"])
        self.quick_teneke.setValue(0)
        self.quick_kg.setValue(0)
        self.quick_adet.setValue(0)
        self.on_data_refreshed()

        dialog = CompleteSaleDialog(self.state, record_to_complete=rec, on_saved=self.on_data_refreshed, parent=self)
        dialog.exec()

    # -- Sekme 2: Bekleyen satışlar --------------------------------------

    def _build_pending_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("Satış miktarı girilmiş ama henüz bir firmaya işlenmemiş kayıtlar:"))
        self.pending_table = QTableWidget(0, 5)
        self.pending_table.setHorizontalHeaderLabels(["Tarih", "Ürün", "Satış", "Satış ID", "İşlem"])
        self.pending_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.pending_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.pending_table)
        return widget

    def _pending_records(self) -> list[dict]:
        linked_sale_ids = {s["id"] for s in self.state.sales}
        pending = []
        for r in self.state.records:
            has_qty = (r.get("satisKg") or 0) > 0 or (r.get("satisTeneke") or 0) > 0 or (r.get("satisAdet") or 0) > 0
            has_id = bool(r.get("satisId"))
            if not (has_qty or has_id):
                continue
            already_linked = r.get("linkedSaleId") and r["linkedSaleId"] in linked_sale_ids
            if already_linked:
                continue
            pending.append(r)
        return pending

    def _refresh_pending(self) -> None:
        rows = self._pending_records()
        self.pending_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.pending_table.setItem(i, 0, QTableWidgetItem(format_date_tr(r.get("tarih"))))
            self.pending_table.setItem(i, 1, QTableWidgetItem(f"{r['urunAdi']} ({r['urunKodu']})"))
            self.pending_table.setItem(
                i, 2,
                QTableWidgetItem(f"{format_number(r.get('satisTeneke'))} T / {format_number(r.get('satisKg'))} Kg"),
            )
            self.pending_table.setItem(i, 3, QTableWidgetItem(r.get("satisId") or "-"))
            btn = QPushButton("Firmaya İşle")
            btn.clicked.connect(lambda _, rec=r: self._process_pending(rec))
            self.pending_table.setCellWidget(i, 4, btn)

    def _process_pending(self, rec: dict) -> None:
        dialog = CompleteSaleDialog(self.state, record_to_complete=rec, on_saved=self.on_data_refreshed, parent=self)
        dialog.exec()

    # -- Sekme 3: Firma yönetimi -----------------------------------------

    def _build_company_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        form_box = QGroupBox("Firma Ekle / Düzenle")
        grid = QGridLayout(form_box)
        self.company_kod_edit = QLineEdit()
        self.company_ad_edit = QLineEdit()
        self.company_tel_edit = QLineEdit()
        grid.addWidget(QLabel("Kod"), 0, 0)
        grid.addWidget(self.company_kod_edit, 0, 1)
        grid.addWidget(QLabel("Ad"), 0, 2)
        grid.addWidget(self.company_ad_edit, 0, 3)
        grid.addWidget(QLabel("Telefon"), 1, 0)
        grid.addWidget(self.company_tel_edit, 1, 1)
        save_btn = QPushButton("Kaydet")
        save_btn.clicked.connect(self._save_company)
        grid.addWidget(save_btn, 1, 2)
        clear_btn = QPushButton("Temizle")
        clear_btn.clicked.connect(self._clear_company_form)
        grid.addWidget(clear_btn, 1, 3)
        layout.addWidget(form_box)

        self.company_table = QTableWidget(0, 4)
        self.company_table.setHorizontalHeaderLabels(["Kod", "Ad", "Telefon", "İşlem"])
        self.company_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.company_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.company_table)

        return widget

    def _refresh_companies(self) -> None:
        rows = sorted(self.state.companies, key=lambda c: c["ad"])
        self.company_table.setRowCount(len(rows))
        for i, c in enumerate(rows):
            self.company_table.setItem(i, 0, QTableWidgetItem(c["kod"]))
            self.company_table.setItem(i, 1, QTableWidgetItem(c["ad"]))
            self.company_table.setItem(i, 2, QTableWidgetItem(c.get("telefon") or ""))
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            edit_btn = QPushButton("Düzenle")
            edit_btn.clicked.connect(lambda _, comp=c: self._load_company(comp))
            action_layout.addWidget(edit_btn)
            del_btn = QPushButton("Sil")
            del_btn.clicked.connect(lambda _, comp=c: self._delete_company(comp))
            action_layout.addWidget(del_btn)
            self.company_table.setCellWidget(i, 3, action_widget)

    def _load_company(self, c: dict) -> None:
        self.company_edit_id = c["id"]
        self.company_kod_edit.setText(c["kod"])
        self.company_ad_edit.setText(c["ad"])
        self.company_tel_edit.setText(c.get("telefon") or "")

    def _clear_company_form(self) -> None:
        self.company_edit_id = None
        self.company_kod_edit.clear()
        self.company_ad_edit.clear()
        self.company_tel_edit.clear()

    def _save_company(self) -> None:
        kod = self.company_kod_edit.text().strip().upper()
        ad = self.company_ad_edit.text().strip()
        if not kod or not ad:
            QMessageBox.warning(self, "Eksik bilgi", "Firma kodu ve adı zorunludur.")
            return
        company = {
            "id": self.company_edit_id or _new_id(),
            "kod": kod,
            "ad": ad,
            "telefon": self.company_tel_edit.text().strip(),
            "eposta": "",
            "adres": "",
        }
        try:
            self.state.db.save_all_data(companies=[company])
            self.state.load_all()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Hata", f"Firma kaydedilemedi:\n{exc}")
            return
        self._clear_company_form()
        self.on_data_refreshed()

    def _delete_company(self, c: dict) -> None:
        if any(s.get("sirketKodu") == c["kod"] for s in self.state.sales):
            QMessageBox.warning(
                self, "Silinemez",
                f"'{c['ad']}' firmasına ait satış kayıtları var, önce onları silin/taşıyın.",
            )
            return
        reply = QMessageBox.question(self, "Firmayı Sil", f"'{c['ad']}' firmasını silmek istiyor musunuz?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.state.db.save_all_data(deleted_company_ids=[c["id"]])
        self.state.load_all()
        self.on_data_refreshed()

    # -- Sekme 4: Satış listesi -------------------------------------------

    def _build_sales_list_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        search_row = QHBoxLayout()
        self.sales_search_edit = QLineEdit()
        self.sales_search_edit.setPlaceholderText("Satış ID, firma veya ürün ara...")
        self.sales_search_edit.textChanged.connect(self._refresh_sales_list)
        search_row.addWidget(self.sales_search_edit)
        layout.addLayout(search_row)

        self.sales_table = QTableWidget(0, 7)
        self.sales_table.setHorizontalHeaderLabels(
            ["Satış ID", "Firma", "Ürün", "Miktar", "Tutar", "Tarih", "İşlem"]
        )
        self.sales_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.sales_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.sales_table)

        return widget

    def _refresh_sales_list(self) -> None:
        query = self.sales_search_edit.text().strip().lower()
        rows = [
            s
            for s in self.state.sales
            if not query
            or query in (s.get("id") or "").lower()
            or query in (s.get("sirketAdi") or "").lower()
            or query in (s.get("urunAdi") or "").lower()
        ]
        rows.sort(key=lambda s: s.get("irsaliyeTarihi") or "", reverse=True)

        self.sales_table.setRowCount(len(rows))
        for i, s in enumerate(rows):
            self.sales_table.setItem(i, 0, QTableWidgetItem(s.get("id") or ""))
            self.sales_table.setItem(i, 1, QTableWidgetItem(s.get("sirketAdi") or ""))
            self.sales_table.setItem(i, 2, QTableWidgetItem(s.get("urunAdi") or ""))
            self.sales_table.setItem(
                i, 3,
                QTableWidgetItem(f"{format_number(s.get('miktarTeneke'))} T / {format_number(s.get('miktarKg'))} Kg"),
            )
            self.sales_table.setItem(i, 4, QTableWidgetItem(f"₺{format_number(s.get('tutar'))}"))
            self.sales_table.setItem(i, 5, QTableWidgetItem(format_date_tr(s.get("irsaliyeTarihi"))))

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            qr_btn = QPushButton("QR Fiş")
            qr_btn.clicked.connect(lambda _, sale=s: self._show_qr(sale))
            action_layout.addWidget(qr_btn)
            del_btn = QPushButton("Sil")
            del_btn.clicked.connect(lambda _, sale=s: self._delete_sale(sale))
            action_layout.addWidget(del_btn)
            self.sales_table.setCellWidget(i, 6, action_widget)

    def _show_qr(self, sale: dict) -> None:
        details = [
            ("Firma", sale.get("sirketAdi") or ""),
            ("Ürün", sale.get("urunAdi") or ""),
            ("Plaka", sale.get("aracPlakasi") or ""),
            ("Miktar", f"{format_number(sale.get('miktarTeneke'))} T / {format_number(sale.get('miktarKg'))} Kg"),
            ("Tutar", f"₺{format_number(sale.get('tutar'))}"),
        ]
        dialog = QRCodeDialog(f"Satış Fişi — {sale.get('id')}", sale.get("id") or "", details, parent=self)
        dialog.exec()

    def _delete_sale(self, sale: dict) -> None:
        reply = QMessageBox.question(self, "Satışı Sil", f"'{sale.get('id')}' satışını silmek istiyor musunuz?")
        if reply != QMessageBox.StandardButton.Yes:
            return

        # İlişkili Defter kaydının bağlantısını kaldır (satisId korunur, tekrar işlenebilsin diye).
        linked_record = next(
            (r for r in self.state.records if r.get("linkedSaleId") == sale["id"] or r.get("satisId") == sale["id"]),
            None,
        )
        try:
            if linked_record:
                updated = {**linked_record, "linkedSaleId": None}
                self.state.db.save_all_data(records=[updated], deleted_sale_ids=[sale["id"]])
            else:
                self.state.db.save_all_data(deleted_sale_ids=[sale["id"]])
            self.state.load_all()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Hata", f"Satış silinemedi:\n{exc}")
            return
        self.on_data_refreshed()

    # -- Ortak yenileme ----------------------------------------------------

    def on_data_refreshed(self) -> None:
        self._refresh_stock()
        self._refresh_pending()
        self._refresh_companies()
        self._refresh_sales_list()
