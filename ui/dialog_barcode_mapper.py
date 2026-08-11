"""BarcodeAppIdMapperModal.tsx karşılığı — Barkod/Ürün Eşleştirme diyaloğu.
Ürün tanımlama, fiyat, ve (bu oturumda eklenen özellik) başlangıç stoğu
girme/kilitleme mantığı web sürümüyle birebir aynı."""

from __future__ import annotations

import time
import uuid

from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.app_state import AppState
from core.stock_logic import calculate_ending_stock, recalculate_product_stock_chain


def _new_id() -> str:
    return f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:5]}"


def _spin() -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(-1_000_000_000, 1_000_000_000)
    box.setDecimals(2)
    return box


class BarcodeMapperDialog(QDialog):
    def __init__(self, state: AppState, on_saved=None, parent=None):
        super().__init__(parent)
        self.state = state
        self.on_saved = on_saved
        self.setWindowTitle("Barkod - App İçi ID Eşleştirme & Birleştirme")
        self.setMinimumSize(640, 560)
        self._selected_code: str | None = None

        layout = QVBoxLayout(self)

        form_box = QGroupBox("Yeni Barkod / ID Birleştirme")
        form_grid = QGridLayout(form_box)

        self.app_id_edit = QLineEdit()
        form_grid.addWidget(QLabel("App İçi Ürün ID / Kodu"), 0, 0)
        form_grid.addWidget(self.app_id_edit, 0, 1)

        self.name_edit = QLineEdit()
        form_grid.addWidget(QLabel("Ürün Adı"), 0, 2)
        form_grid.addWidget(self.name_edit, 0, 3)

        self.barcode_edit = QLineEdit()
        form_grid.addWidget(QLabel("Fiziksel Barkod / QR"), 1, 0)
        form_grid.addWidget(self.barcode_edit, 1, 1)

        self.price_kg = _spin()
        form_grid.addWidget(QLabel("Kilo Fiyatı (₺/Kg)"), 2, 0)
        form_grid.addWidget(self.price_kg, 2, 1)

        self.price_teneke = _spin()
        form_grid.addWidget(QLabel("Teneke Fiyatı (₺/Teneke)"), 2, 2)
        form_grid.addWidget(self.price_teneke, 2, 3)

        self.price_adet = _spin()
        form_grid.addWidget(QLabel("Adet Fiyatı (₺/Adet)"), 3, 0)
        form_grid.addWidget(self.price_adet, 3, 1)

        layout.addWidget(form_box)

        stock_box = QGroupBox(
            "Başlangıç Stoğu (opsiyonel — girilirse Üretim Kayıt Defteri'nde bu ürün için "
            "başlangıç stoğu alanı kilitlenir)"
        )
        stock_grid = QGridLayout(stock_box)
        self.stock_teneke = _spin()
        self.stock_kg = _spin()
        self.stock_adet = _spin()
        stock_grid.addWidget(QLabel("Teneke"), 0, 0)
        stock_grid.addWidget(self.stock_teneke, 1, 0)
        stock_grid.addWidget(QLabel("Kg"), 0, 1)
        stock_grid.addWidget(self.stock_kg, 1, 1)
        stock_grid.addWidget(QLabel("Adet"), 0, 2)
        stock_grid.addWidget(self.stock_adet, 1, 2)
        self._entered_by_user = {"teneke": False, "kg": False, "adet": False}
        layout.addWidget(stock_box)
        self.lock_notice = QLabel("")
        self.lock_notice.setStyleSheet("color: #F59E0B; font-size: 11.5px;")
        self.lock_notice.setWordWrap(True)
        layout.addWidget(self.lock_notice)

        btn_row = QHBoxLayout()
        self.clear_btn = QPushButton("Temizle")
        self.clear_btn.clicked.connect(self._clear_form)
        btn_row.addWidget(self.clear_btn)
        save_btn = QPushButton("Eşleştirmeyi Kaydet")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addWidget(QLabel("Kayıtlı Ürün ve Barkod Listesi"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Ürün veya barkod ara...")
        self.search_edit.textChanged.connect(self._refresh_list)
        layout.addWidget(self.search_edit)

        self.product_list = QListWidget()
        self.product_list.itemClicked.connect(self._on_list_item_clicked)
        layout.addWidget(self.product_list)

        self._refresh_list()

    # -- yardımcılar ---------------------------------------------------

    def _unique_products(self) -> dict[str, dict]:
        products: dict[str, dict] = {}
        for r in self.state.records:
            code = r["urunKodu"].strip().upper()
            existing = products.get(code)
            if not existing:
                products[code] = {
                    "urunKodu": code,
                    "urunAdi": r["urunAdi"],
                    "barcode": r.get("barcode") or code,
                    "fiyatKg": r.get("fiyatKg") or 0,
                    "fiyatTeneke": r.get("fiyatTeneke") or 0,
                    "fiyatAdet": r.get("fiyatAdet") or 0,
                }
            else:
                if r.get("barcode"):
                    existing["barcode"] = r["barcode"]
                if r.get("fiyatKg"):
                    existing["fiyatKg"] = r["fiyatKg"]
                if r.get("fiyatTeneke"):
                    existing["fiyatTeneke"] = r["fiyatTeneke"]
                if r.get("fiyatAdet"):
                    existing["fiyatAdet"] = r["fiyatAdet"]
        return products

    def _earliest_record(self, code: str) -> dict | None:
        clean = code.strip().upper()
        matches = [r for r in self.state.records if r["urunKodu"].strip().upper() == clean]
        if not matches:
            return None
        return sorted(matches, key=lambda r: (r.get("tarih") or "", r.get("id") or ""))[0]

    def _refresh_list(self) -> None:
        query = self.search_edit.text().strip().lower()
        self.product_list.clear()
        for code, p in sorted(self._unique_products().items(), key=lambda kv: kv[1]["urunAdi"]):
            if query and query not in p["urunAdi"].lower() and query not in code.lower() and query not in p["barcode"].lower():
                continue
            item = QListWidgetItem(
                f"{p['urunAdi']} ({code}) — Barkod: {p['barcode']} — "
                f"₺{p['fiyatKg']}/Kg, ₺{p['fiyatTeneke']}/Teneke"
            )
            item.setData(1000, code)
            self.product_list.addItem(item)

    def _on_list_item_clicked(self, item: QListWidgetItem) -> None:
        code = item.data(1000)
        products = self._unique_products()
        p = products.get(code)
        if not p:
            return
        self._selected_code = code
        self.app_id_edit.setText(p["urunKodu"])
        self.name_edit.setText(p["urunAdi"])
        self.barcode_edit.setText(p["barcode"])
        self.price_kg.setValue(p["fiyatKg"])
        self.price_teneke.setValue(p["fiyatTeneke"])
        self.price_adet.setValue(p["fiyatAdet"])

        earliest = self._earliest_record(code)
        locked = bool(earliest and earliest.get("baslangicStokKilitli"))
        if locked:
            self.stock_teneke.setValue(earliest.get("baslangicStokTeneke") or 0)
            self.stock_kg.setValue(earliest.get("baslangicStokKg") or 0)
            self.stock_adet.setValue(earliest.get("baslangicStokAdet") or 0)
            self.lock_notice.setText(
                "Bu ürünün başlangıç stoğu zaten bu ekrandan kilitlenmiş. "
                "Değiştirip kaydederseniz Üretim ekranındaki değer de güncellenir."
            )
        else:
            self.stock_teneke.setValue(0)
            self.stock_kg.setValue(0)
            self.stock_adet.setValue(0)
            self.lock_notice.setText("")

    def _clear_form(self) -> None:
        self._selected_code = None
        self.app_id_edit.clear()
        self.name_edit.clear()
        self.barcode_edit.clear()
        for spin in (self.price_kg, self.price_teneke, self.price_adet, self.stock_teneke, self.stock_kg, self.stock_adet):
            spin.setValue(0)
        self.lock_notice.setText("")

    # -- kaydetme --------------------------------------------------------

    def _on_save(self) -> None:
        clean_app_id = self.app_id_edit.text().strip().upper()
        clean_name = self.name_edit.text().strip()
        clean_barcode = self.barcode_edit.text().strip()

        if not clean_app_id:
            QMessageBox.warning(self, "Eksik bilgi", "Lütfen bir App İçi Ürün ID / Kodu girin.")
            return
        if not clean_name:
            QMessageBox.warning(self, "Eksik bilgi", "Lütfen bir Ürün Adı girin.")
            return

        has_existing = any(r["urunKodu"].strip().upper() == clean_app_id for r in self.state.records)
        # Başlangıç stoğu alanlarından en az biri sıfırdan farklıysa "girildi" say —
        # tamamı boş/sıfır bırakılırsa mevcut kilit durumuna dokunulmaz.
        has_entered_stock = self.stock_teneke.value() != 0 or self.stock_kg.value() != 0 or self.stock_adet.value() != 0

        if has_existing:
            earliest = self._earliest_record(clean_app_id)
            earliest_id = earliest["id"] if earliest else None
            updated_records = []
            for r in self.state.records:
                if r["urunKodu"].strip().upper() != clean_app_id:
                    updated_records.append(r)
                    continue
                updated = {
                    **r,
                    "urunAdi": clean_name,
                    "barcode": clean_barcode or clean_app_id,
                    "fiyatKg": self.price_kg.value() or r.get("fiyatKg"),
                    "fiyatTeneke": self.price_teneke.value() or r.get("fiyatTeneke"),
                    "fiyatAdet": self.price_adet.value() or r.get("fiyatAdet"),
                }
                if r["id"] == earliest_id and has_entered_stock:
                    updated["baslangicStokTeneke"] = self.stock_teneke.value()
                    updated["baslangicStokKg"] = self.stock_kg.value()
                    updated["baslangicStokAdet"] = self.stock_adet.value()
                    updated["baslangicStokKilitli"] = True
                updated_records.append(updated)

            if has_entered_stock:
                updated_records = recalculate_product_stock_chain(updated_records, clean_app_id)

            to_upsert = [r for r in updated_records if r["urunKodu"].strip().upper() == clean_app_id]
        else:
            base_record = {
                "id": _new_id(),
                "tarih": time.strftime("%Y-%m-%d"),
                "urunKodu": clean_app_id,
                "urunAdi": clean_name,
                "barcode": clean_barcode or clean_app_id,
                "uretimKg": 0, "uretimTeneke": 0, "uretimAdet": 0,
                "fireKg": 0, "fireTeneke": 0, "fireAdet": 0,
                "satisKg": 0, "satisTeneke": 0, "satisAdet": 0,
                "baslangicStokKg": self.stock_kg.value(),
                "baslangicStokTeneke": self.stock_teneke.value(),
                "baslangicStokAdet": self.stock_adet.value(),
                "fiyatTeneke": self.price_teneke.value(),
                "fiyatKg": self.price_kg.value(),
                "fiyatAdet": self.price_adet.value(),
                "baslangicStokKilitli": has_entered_stock,
                "satisId": "", "linkedSaleId": None, "manualBaslangicStok": False,
            }
            ending = calculate_ending_stock(base_record)
            base_record.update(ending)
            to_upsert = [base_record]

        try:
            self.state.db.save_all_data(records=to_upsert)
            self.state.load_all()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Kayıt Hatası", f"Eşleştirme kaydedilemedi:\n{exc}")
            return

        QMessageBox.information(self, "Kaydedildi", f'"{clean_app_id}" - "{clean_name}" barkod eşleştirmesi güncellendi.')
        self._clear_form()
        self._refresh_list()
        if self.on_saved:
            self.on_saved()
