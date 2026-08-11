"""DashboardDefter.tsx karşılığı — Üretim Kayıt Defteri. Rol bazlı alan
görünürlüğü, ürün hızlı seçimi, zincirden otomatik başlangıç stoğu senkronu,
başlangıç stoğu kilidi (Barkod Eşleştirme'den geldiyse salt-okunur), ve stok
zinciri yeniden hesaplama (recalculate_product_stock_chain) birebir korunur."""

from __future__ import annotations

import time
import uuid

from PySide6.QtCore import Qt
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
    QVBoxLayout,
    QWidget,
)

from core.app_state import AppState
from core.models import new_record_defaults
from core.stock_logic import (
    calculate_ending_stock,
    format_date_tr,
    format_number,
    generate_sale_id,
    get_previous_record,
    get_today_date_string,
    has_locked_starting_stock,
    recalculate_product_stock_chain,
)
from ui.workers import run_in_background


def _new_id() -> str:
    return f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:5]}"


def _spin() -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(-1_000_000_000, 1_000_000_000)
    box.setDecimals(2)
    box.setGroupSeparatorShown(True)
    return box


class DefterPage(QWidget):
    def __init__(self, state: AppState, set_saving, profile_role: str, parent=None):
        super().__init__(parent)
        self.state = state
        self.set_saving = set_saving
        self.profile_role = profile_role
        self.editing_id: str | None = None
        self._starting_stock_locked = False

        self._build_ui()
        self._refresh_product_combo()
        self._refresh_table()

    # -- UI kurulumu ---------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Vertical)
        root.addWidget(splitter)

        splitter.addWidget(self._build_form_panel())
        splitter.addWidget(self._build_table_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    def _build_form_panel(self) -> QWidget:
        panel = QGroupBox("Kayıt Ekle / Düzenle")
        layout = QVBoxLayout(panel)

        # Hızlı ürün seçimi
        quick_row = QHBoxLayout()
        quick_row.addWidget(QLabel("Mevcut Ürünlerden Seç:"))
        self.product_combo = QComboBox()
        self.product_combo.addItem("-- Seçin veya elle girin --", None)
        self.product_combo.currentIndexChanged.connect(self._on_product_combo_changed)
        quick_row.addWidget(self.product_combo, 1)
        layout.addLayout(quick_row)

        grid = QGridLayout()
        row = 0

        self.tarih_edit = QLineEdit(get_today_date_string())
        self.tarih_edit.setPlaceholderText("YYYY-AA-GG")
        grid.addWidget(QLabel("Tarih"), row, 0)
        grid.addWidget(self.tarih_edit, row, 1)

        self.urun_kodu_edit = QLineEdit()
        self.urun_kodu_edit.editingFinished.connect(self._on_urun_kodu_finished)
        grid.addWidget(QLabel("Ürün Kodu"), row, 2)
        grid.addWidget(self.urun_kodu_edit, row, 3)
        row += 1

        self.urun_adi_edit = QLineEdit()
        grid.addWidget(QLabel("Ürün Adı"), row, 0)
        grid.addWidget(self.urun_adi_edit, row, 1)

        self.barcode_edit = QLineEdit()
        grid.addWidget(QLabel("Barkod"), row, 2)
        grid.addWidget(self.barcode_edit, row, 3)
        row += 1

        layout.addLayout(grid)

        sections = QHBoxLayout()

        # Üretim / Fire — sadece uretim/admin
        self.uretim_teneke, self.uretim_kg, self.uretim_adet = _spin(), _spin(), _spin()
        self.fire_teneke, self.fire_kg, self.fire_adet = _spin(), _spin(), _spin()
        self.uretim_box = self._triple_box(
            "Üretim Miktarı", self.uretim_teneke, self.uretim_kg, self.uretim_adet
        )
        self.fire_box = self._triple_box(
            "Fire / Wastage", self.fire_teneke, self.fire_kg, self.fire_adet
        )
        if self.profile_role in ("uretim", "admin"):
            sections.addWidget(self.uretim_box)
            sections.addWidget(self.fire_box)
        for spin in (
            self.uretim_teneke, self.uretim_kg, self.uretim_adet,
            self.fire_teneke, self.fire_kg, self.fire_adet,
        ):
            spin.valueChanged.connect(self._refresh_ending_stock_preview)

        # Satış — sadece satis/admin
        self.satis_teneke, self.satis_kg, self.satis_adet = _spin(), _spin(), _spin()
        self.satis_box = self._triple_box(
            "Satış Miktarı", self.satis_teneke, self.satis_kg, self.satis_adet
        )
        self.satis_id_edit = QLineEdit()
        if self.profile_role in ("satis", "admin"):
            satis_col = QVBoxLayout()
            satis_col.addWidget(self.satis_box)
            id_row = QHBoxLayout()
            id_row.addWidget(QLabel("Satış ID"))
            id_row.addWidget(self.satis_id_edit)
            satis_col.addLayout(id_row)
            satis_widget = QWidget()
            satis_widget.setLayout(satis_col)
            sections.addWidget(satis_widget)
        for spin in (self.satis_teneke, self.satis_kg, self.satis_adet):
            spin.valueChanged.connect(self._refresh_ending_stock_preview)

        layout.addLayout(sections)

        # Başlangıç / Bitiş stoğu
        stock_row = QHBoxLayout()
        self.baslangic_teneke, self.baslangic_kg, self.baslangic_adet = _spin(), _spin(), _spin()
        self.baslangic_box = self._triple_box(
            "Başlangıç Stoğu", self.baslangic_teneke, self.baslangic_kg, self.baslangic_adet
        )
        stock_row.addWidget(self.baslangic_box)
        for spin in (self.baslangic_teneke, self.baslangic_kg, self.baslangic_adet):
            spin.valueChanged.connect(self._refresh_ending_stock_preview)

        self.bitis_label = QLabel("0 T / 0 Kg / 0 Ad")
        bitis_box = QGroupBox("Bitiş Stoğu (otomatik hesaplanır)")
        bitis_layout = QVBoxLayout(bitis_box)
        bitis_layout.addWidget(self.bitis_label)
        stock_row.addWidget(bitis_box)

        layout.addLayout(stock_row)

        # Fiyat
        price_row = QHBoxLayout()
        self.fiyat_teneke, self.fiyat_kg, self.fiyat_adet = _spin(), _spin(), _spin()
        price_row.addWidget(self._triple_box("Fiyat (₺)", self.fiyat_teneke, self.fiyat_kg, self.fiyat_adet))
        layout.addLayout(price_row)

        # Butonlar
        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("Kaydet")
        self.save_btn.clicked.connect(self._on_save_clicked)
        self.cancel_btn = QPushButton("İptal / Yeni Kayıt")
        self.cancel_btn.clicked.connect(self._reset_form)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        return panel

    def _triple_box(self, title: str, teneke: QDoubleSpinBox, kg: QDoubleSpinBox, adet: QDoubleSpinBox) -> QGroupBox:
        box = QGroupBox(title)
        grid = QGridLayout(box)
        grid.addWidget(QLabel("Teneke"), 0, 0)
        grid.addWidget(teneke, 1, 0)
        grid.addWidget(QLabel("Kg"), 0, 1)
        grid.addWidget(kg, 1, 1)
        grid.addWidget(QLabel("Adet"), 0, 2)
        grid.addWidget(adet, 1, 2)
        return box

    def _build_table_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Ara:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Ürün adı, kodu veya barkod...")
        self.search_edit.textChanged.connect(self._refresh_table)
        search_row.addWidget(self.search_edit)
        layout.addLayout(search_row)

        self.table = QTableWidget(0, 8)
        headers = ["Tarih", "Ürün", "Üretim", "Fire", "Satış / ID", "Açılış", "Bitiş", "İşlem"]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        if self.profile_role == "satis":
            self.table.setColumnHidden(2, True)
            self.table.setColumnHidden(3, True)
        layout.addWidget(self.table)

        return panel

    # -- Veri yenileme ----------------------------------------------------

    def on_data_refreshed(self) -> None:
        self._refresh_product_combo()
        self._refresh_table()

    def _refresh_product_combo(self) -> None:
        current = self.product_combo.currentData()
        self.product_combo.blockSignals(True)
        self.product_combo.clear()
        self.product_combo.addItem("-- Seçin veya elle girin --", None)

        latest_by_code: dict[str, dict] = {}
        for r in self.state.records:
            code = r["urunKodu"]
            existing = latest_by_code.get(code)
            if not existing or r["tarih"] > existing["tarih"] or r["id"] > existing["id"]:
                latest_by_code[code] = r
        for code, r in sorted(latest_by_code.items(), key=lambda kv: kv[1]["urunAdi"]):
            label = f"{r['urunAdi']} ({code}) — Bitiş: {format_number(r['bitisStokTeneke'])} T"
            self.product_combo.addItem(label, code)

        idx = self.product_combo.findData(current)
        self.product_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.product_combo.blockSignals(False)

    def _refresh_table(self) -> None:
        query = self.search_edit.text().strip().lower()
        rows = [
            r
            for r in self.state.records
            if not query
            or query in (r.get("urunAdi") or "").lower()
            or query in (r.get("urunKodu") or "").lower()
            or query in (r.get("barcode") or "").lower()
        ]
        rows.sort(key=lambda r: (r.get("tarih") or "", r.get("id") or ""), reverse=True)

        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(format_date_tr(r.get("tarih"))))
            self.table.setItem(i, 1, QTableWidgetItem(f"{r.get('urunAdi')} ({r.get('urunKodu')})"))
            self.table.setItem(
                i, 2,
                QTableWidgetItem(
                    f"{format_number(r.get('uretimTeneke'))} T / {format_number(r.get('uretimKg'))} Kg"
                ),
            )
            self.table.setItem(
                i, 3,
                QTableWidgetItem(
                    f"{format_number(r.get('fireTeneke'))} T / {format_number(r.get('fireKg'))} Kg"
                ),
            )
            satis_text = f"{format_number(r.get('satisTeneke'))} T / {format_number(r.get('satisKg'))} Kg"
            if r.get("satisId"):
                satis_text += f" [{r['satisId']}]"
            self.table.setItem(i, 4, QTableWidgetItem(satis_text))
            self.table.setItem(
                i, 5,
                QTableWidgetItem(
                    f"{format_number(r.get('baslangicStokTeneke'))} T / {format_number(r.get('baslangicStokKg'))} Kg"
                ),
            )
            self.table.setItem(
                i, 6,
                QTableWidgetItem(
                    f"{format_number(r.get('bitisStokTeneke'))} T / {format_number(r.get('bitisStokKg'))} Kg"
                ),
            )

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            edit_btn = QPushButton("Düzenle")
            edit_btn.clicked.connect(lambda _, rec=r: self._load_record_into_form(rec))
            action_layout.addWidget(edit_btn)
            del_btn = QPushButton("Sil")
            del_btn.clicked.connect(lambda _, rec=r: self._delete_record(rec))
            action_layout.addWidget(del_btn)
            self.table.setCellWidget(i, 7, action_widget)

    # -- Form davranışı ----------------------------------------------------

    def _on_product_combo_changed(self, _index: int) -> None:
        code = self.product_combo.currentData()
        if not code:
            return
        self._autofill_from_code(code)

    def _on_urun_kodu_finished(self) -> None:
        code = self.urun_kodu_edit.text().strip().upper()
        self.urun_kodu_edit.setText(code)
        if code:
            self._autofill_from_code(code)

    def _autofill_from_code(self, code: str) -> None:
        clean = code.strip().lower()
        matched = next(
            (
                r
                for r in self.state.records
                if (r.get("urunKodu") or "").strip().lower() == clean
                or (r.get("barcode") or "").strip().lower() == clean
            ),
            None,
        )
        if matched:
            self.urun_kodu_edit.setText(matched["urunKodu"])
            self.urun_adi_edit.setText(matched["urunAdi"])
            if not self.barcode_edit.text():
                self.barcode_edit.setText(matched.get("barcode") or matched["urunKodu"])
            if self.fiyat_kg.value() == 0:
                self.fiyat_kg.setValue(matched.get("fiyatKg") or 0)
            if self.fiyat_teneke.value() == 0:
                self.fiyat_teneke.setValue(matched.get("fiyatTeneke") or 0)
            if self.fiyat_adet.value() == 0:
                self.fiyat_adet.setValue(matched.get("fiyatAdet") or 0)
            self._sync_starting_stock_from_chain(matched["urunKodu"])
        self._apply_starting_stock_lock(matched["urunKodu"] if matched else code)

    def _sync_starting_stock_from_chain(self, code: str) -> None:
        prev = get_previous_record(
            self.state.records, code, self.tarih_edit.text().strip(), self.editing_id
        )
        if prev:
            self.baslangic_teneke.setValue(prev.get("bitisStokTeneke") or 0)
            self.baslangic_kg.setValue(prev.get("bitisStokKg") or 0)
            self.baslangic_adet.setValue(prev.get("bitisStokAdet") or 0)

    def _apply_starting_stock_lock(self, code: str) -> None:
        locked = has_locked_starting_stock(self.state.records, code) and self.profile_role in (
            "uretim", "admin"
        )
        self._starting_stock_locked = locked
        for spin in (self.baslangic_teneke, self.baslangic_kg, self.baslangic_adet):
            spin.setReadOnly(locked)
            spin.setButtonSymbols(
                QDoubleSpinBox.ButtonSymbols.NoButtons if locked else QDoubleSpinBox.ButtonSymbols.UpDownArrows
            )
        self.baslangic_box.setTitle(
            "Başlangıç Stoğu (Barkod Eşleştirmeden Kilitli)" if locked else "Başlangıç Stoğu"
        )

    def _refresh_ending_stock_preview(self) -> None:
        ending = calculate_ending_stock(
            {
                "baslangicStokKg": self.baslangic_kg.value(),
                "baslangicStokTeneke": self.baslangic_teneke.value(),
                "baslangicStokAdet": self.baslangic_adet.value(),
                "uretimKg": self.uretim_kg.value(),
                "uretimTeneke": self.uretim_teneke.value(),
                "uretimAdet": self.uretim_adet.value(),
                "fireKg": self.fire_kg.value(),
                "fireTeneke": self.fire_teneke.value(),
                "fireAdet": self.fire_adet.value(),
                "satisKg": self.satis_kg.value(),
                "satisTeneke": self.satis_teneke.value(),
                "satisAdet": self.satis_adet.value(),
            }
        )
        self.bitis_label.setText(
            f"{format_number(ending['bitisStokTeneke'])} T / "
            f"{format_number(ending['bitisStokKg'])} Kg / "
            f"{format_number(ending['bitisStokAdet'])} Ad"
        )

    def _reset_form(self) -> None:
        self.editing_id = None
        self.tarih_edit.setText(get_today_date_string())
        self.urun_kodu_edit.clear()
        self.urun_adi_edit.clear()
        self.barcode_edit.clear()
        for spin in (
            self.uretim_teneke, self.uretim_kg, self.uretim_adet,
            self.fire_teneke, self.fire_kg, self.fire_adet,
            self.satis_teneke, self.satis_kg, self.satis_adet,
            self.baslangic_teneke, self.baslangic_kg, self.baslangic_adet,
            self.fiyat_teneke, self.fiyat_kg, self.fiyat_adet,
        ):
            spin.setValue(0)
        self.satis_id_edit.clear()
        self._apply_starting_stock_lock("")
        self.product_combo.setCurrentIndex(0)
        self._refresh_ending_stock_preview()

    def _load_record_into_form(self, rec: dict) -> None:
        self.editing_id = rec["id"]
        self.tarih_edit.setText(rec.get("tarih") or "")
        self.urun_kodu_edit.setText(rec.get("urunKodu") or "")
        self.urun_adi_edit.setText(rec.get("urunAdi") or "")
        self.barcode_edit.setText(rec.get("barcode") or "")
        self.uretim_teneke.setValue(rec.get("uretimTeneke") or 0)
        self.uretim_kg.setValue(rec.get("uretimKg") or 0)
        self.uretim_adet.setValue(rec.get("uretimAdet") or 0)
        self.fire_teneke.setValue(rec.get("fireTeneke") or 0)
        self.fire_kg.setValue(rec.get("fireKg") or 0)
        self.fire_adet.setValue(rec.get("fireAdet") or 0)
        self.satis_teneke.setValue(rec.get("satisTeneke") or 0)
        self.satis_kg.setValue(rec.get("satisKg") or 0)
        self.satis_adet.setValue(rec.get("satisAdet") or 0)
        self.baslangic_teneke.setValue(rec.get("baslangicStokTeneke") or 0)
        self.baslangic_kg.setValue(rec.get("baslangicStokKg") or 0)
        self.baslangic_adet.setValue(rec.get("baslangicStokAdet") or 0)
        self.fiyat_teneke.setValue(rec.get("fiyatTeneke") or 0)
        self.fiyat_kg.setValue(rec.get("fiyatKg") or 0)
        self.fiyat_adet.setValue(rec.get("fiyatAdet") or 0)
        self.satis_id_edit.setText(rec.get("satisId") or "")
        self._apply_starting_stock_lock(rec.get("urunKodu") or "")
        self._refresh_ending_stock_preview()

    # -- Kaydetme / Silme ----------------------------------------------------

    def _on_save_clicked(self) -> None:
        urun_kodu = self.urun_kodu_edit.text().strip().upper()
        urun_adi = self.urun_adi_edit.text().strip()
        if not urun_kodu:
            QMessageBox.warning(self, "Eksik bilgi", "Ürün ID'si / Kodu girilmeden kayıt eklenemez.")
            return
        if not urun_adi:
            QMessageBox.warning(self, "Eksik bilgi", "Ürün adı girilmeden kayıt eklenemez.")
            return

        available_teneke = self.baslangic_teneke.value() + self.uretim_teneke.value() - self.fire_teneke.value()
        available_kg = self.baslangic_kg.value() + self.uretim_kg.value() - self.fire_kg.value()
        available_adet = self.baslangic_adet.value() + self.uretim_adet.value() - self.fire_adet.value()

        if self.satis_teneke.value() > available_teneke:
            QMessageBox.warning(
                self, "Stok Yetersiz",
                f"Satış (Teneke) miktarı mevcut stoğu aşıyor. Kullanılabilir: {format_number(available_teneke)} Teneke.",
            )
            return
        if self.satis_kg.value() > available_kg:
            QMessageBox.warning(
                self, "Stok Yetersiz",
                f"Satış (Kg) miktarı mevcut stoğu aşıyor. Kullanılabilir: {format_number(available_kg)} Kg.",
            )
            return
        if self.satis_adet.value() > available_adet:
            QMessageBox.warning(
                self, "Stok Yetersiz",
                f"Satış (Adet) miktarı mevcut stoğu aşıyor. Kullanılabilir: {format_number(available_adet)} Adet.",
            )
            return

        old_record = next((r for r in self.state.records if r["id"] == self.editing_id), None) if self.editing_id else None

        # Üretim/Admin bu alanı elle düzenleyebildiği için girdikleri değer esas alınır
        # (her zaman True); Satışçı ekranında zincirden otomatik senkron olduğu için
        # önceki kaydın bayrağı korunur (web'deki DashboardDefter.tsx ile birebir).
        if self.profile_role in ("uretim", "admin"):
            manual_baslangic_stok = True
        else:
            manual_baslangic_stok = bool(old_record.get("manualBaslangicStok")) if old_record else False

        has_sale = self.satis_kg.value() > 0 or self.satis_teneke.value() > 0 or self.satis_adet.value() > 0
        satis_id = self.satis_id_edit.text().strip().upper()
        if has_sale and not satis_id:
            existing_ids = {s["id"] for s in self.state.sales}
            for r in self.state.records:
                if r.get("satisId") and r["id"] != self.editing_id:
                    existing_ids.add(r["satisId"])
            satis_id = generate_sale_id(existing_ids, self.tarih_edit.text().strip() or get_today_date_string())

        new_record = {
            **new_record_defaults(),
            "id": self.editing_id or _new_id(),
            "tarih": self.tarih_edit.text().strip() or get_today_date_string(),
            "urunKodu": urun_kodu,
            "urunAdi": urun_adi,
            "barcode": self.barcode_edit.text().strip() or urun_kodu,
            "uretimKg": self.uretim_kg.value(), "uretimTeneke": self.uretim_teneke.value(), "uretimAdet": self.uretim_adet.value(),
            "fireKg": self.fire_kg.value(), "fireTeneke": self.fire_teneke.value(), "fireAdet": self.fire_adet.value(),
            "satisKg": self.satis_kg.value(), "satisTeneke": self.satis_teneke.value(), "satisAdet": self.satis_adet.value(),
            "baslangicStokKg": self.baslangic_kg.value(), "baslangicStokTeneke": self.baslangic_teneke.value(),
            "baslangicStokAdet": self.baslangic_adet.value(),
            "fiyatTeneke": self.fiyat_teneke.value(), "fiyatKg": self.fiyat_kg.value(), "fiyatAdet": self.fiyat_adet.value(),
            "satisId": satis_id,
            "linkedSaleId": old_record.get("linkedSaleId") if old_record else None,
            "manualBaslangicStok": manual_baslangic_stok,
            # Bu bayrak yalnızca Barkod Eşleştirme ekranından set edilir.
            "baslangicStokKilitli": bool(old_record.get("baslangicStokKilitli")) if old_record else False,
        }
        ending = calculate_ending_stock(new_record)
        new_record.update(ending)

        self.set_saving(True)

        def do_save():
            records = self.state.records
            updated_list = (
                [new_record if r["id"] == new_record["id"] else r for r in records]
                if self.editing_id
                else [*records, new_record]
            )
            updated_list = recalculate_product_stock_chain(updated_list, new_record["urunKodu"])
            if old_record and old_record["urunKodu"].strip().lower() != new_record["urunKodu"].strip().lower():
                updated_list = recalculate_product_stock_chain(updated_list, old_record["urunKodu"])

            changed_codes = {new_record["urunKodu"].strip().lower()}
            if old_record:
                changed_codes.add(old_record["urunKodu"].strip().lower())
            to_upsert = [r for r in updated_list if r["urunKodu"].strip().lower() in changed_codes]
            self.state.db.save_all_data(records=to_upsert)
            return None

        run_in_background(do_save, self._after_save, self._after_save_error)

    def _after_save(self, _result) -> None:
        self.set_saving(False)
        self.state.load_all()
        self._refresh_product_combo()
        self._refresh_table()
        self._reset_form()

    def _after_save_error(self, msg: str) -> None:
        self.set_saving(False)
        QMessageBox.critical(self, "Kayıt Hatası", f"Kayıt sırasında bir hata oluştu:\n{msg}")

    def _delete_record(self, rec: dict) -> None:
        reply = QMessageBox.question(
            self, "Kaydı Sil", f"'{rec.get('urunAdi')}' ({format_date_tr(rec.get('tarih'))}) kaydını silmek istiyor musunuz?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.set_saving(True)

        def do_delete():
            remaining = [r for r in self.state.records if r["id"] != rec["id"]]
            updated_list = recalculate_product_stock_chain(remaining, rec["urunKodu"])
            to_upsert = [r for r in updated_list if r["urunKodu"].strip().lower() == rec["urunKodu"].strip().lower()]
            self.state.db.save_all_data(records=to_upsert, deleted_record_ids=[rec["id"]])
            return None

        run_in_background(do_delete, self._after_save, self._after_save_error)
