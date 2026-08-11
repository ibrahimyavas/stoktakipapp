"""CompleteSaleModal.tsx karşılığı — Defter'de satış miktarı girilmiş ama
henüz firmaya işlenmemiş bir kaydı, tam bir SaleItem'a (firma/plaka/fatura
bilgileriyle) dönüştürür ("Firmaya İşle" akışı)."""

from __future__ import annotations

import time
import uuid

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.app_state import AppState
from core.stock_logic import calculate_total_amount, format_date_tr, format_number, generate_sale_id, get_today_date_string


def _new_id() -> str:
    return f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:5]}"


def _spin() -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(0, 1_000_000_000)
    box.setDecimals(2)
    return box


def _encode_image_file(path: str) -> str:
    import base64
    import mimetypes

    mime, _ = mimetypes.guess_type(path)
    mime = mime or "image/jpeg"
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{data}"


class CompleteSaleDialog(QDialog):
    def __init__(self, state: AppState, record_to_complete: dict | None = None, on_saved=None, parent=None):
        super().__init__(parent)
        self.state = state
        self.on_saved = on_saved
        self._photo_data_url: str = ""
        self.setWindowTitle("Satışı Tamamla / Firmaya İşle")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        self.record_combo = QComboBox()
        if record_to_complete is None:
            candidates = [
                r
                for r in self.state.records
                if r.get("satisKg") or r.get("satisTeneke") or r.get("satisAdet") or r.get("satisId")
            ]
            self.record_combo.addItem("-- Kayıt seçin --", None)
            for r in candidates:
                label = (
                    f"{format_date_tr(r['tarih'])} | {r['urunAdi']} ({r['urunKodu']}) - "
                    f"Satış: {format_number(r.get('satisTeneke'))} T / {format_number(r.get('satisKg'))} Kg"
                )
                self.record_combo.addItem(label, r["id"])
            self.record_combo.currentIndexChanged.connect(self._on_record_chosen)
            layout.addWidget(QLabel("Tamamlanacak Kayıt"))
            layout.addWidget(self.record_combo)
        else:
            self.record_combo.hide()

        grid = QGridLayout()
        row = 0

        self.satis_id_edit = QLineEdit()
        grid.addWidget(QLabel("Satış ID"), row, 0)
        grid.addWidget(self.satis_id_edit, row, 1)
        row += 1

        self.firma_combo = QComboBox()
        self._refresh_firma_combo()
        grid.addWidget(QLabel("Firma *"), row, 0)
        grid.addWidget(self.firma_combo, row, 1)
        row += 1

        self.plaka_edit = QLineEdit()
        grid.addWidget(QLabel("Araç Plakası"), row, 0)
        grid.addWidget(self.plaka_edit, row, 1)
        row += 1

        self.fiyat_kg, self.fiyat_teneke, self.fiyat_adet = _spin(), _spin(), _spin()
        grid.addWidget(QLabel("Kilo Fiyatı (₺/Kg)"), row, 0)
        grid.addWidget(self.fiyat_kg, row, 1)
        row += 1
        grid.addWidget(QLabel("Teneke Fiyatı (₺/Teneke)"), row, 0)
        grid.addWidget(self.fiyat_teneke, row, 1)
        row += 1
        grid.addWidget(QLabel("Adet Fiyatı (₺/Adet)"), row, 0)
        grid.addWidget(self.fiyat_adet, row, 1)
        row += 1

        self.irsaliye_tarihi_edit = QLineEdit(get_today_date_string())
        grid.addWidget(QLabel("İrsaliye Tarihi"), row, 0)
        grid.addWidget(self.irsaliye_tarihi_edit, row, 1)
        row += 1

        self.fatura_tarihi_edit = QLineEdit(get_today_date_string())
        grid.addWidget(QLabel("Fatura Tarihi"), row, 0)
        grid.addWidget(self.fatura_tarihi_edit, row, 1)
        row += 1

        photo_btn = QPushButton("İrsaliye Fotoğrafı Ekle...")
        photo_btn.clicked.connect(self._attach_photo)
        grid.addWidget(photo_btn, row, 0, 1, 2)
        row += 1

        layout.addLayout(grid)

        self.total_label = QLabel("Toplam Tutar: ₺0")
        self.total_label.setStyleSheet("font-weight: 700; font-size: 14px; color: #34D399;")
        layout.addWidget(self.total_label)
        for spin in (self.fiyat_kg, self.fiyat_teneke, self.fiyat_adet):
            spin.valueChanged.connect(self._refresh_total)

        save_btn = QPushButton("Satışı Tamamla")
        save_btn.setProperty("variant", "primary")
        save_btn.clicked.connect(self._on_save)
        layout.addWidget(save_btn)

        self._selected_record: dict | None = None
        if record_to_complete is not None:
            self._load_record(record_to_complete)

    def _refresh_firma_combo(self) -> None:
        self.firma_combo.clear()
        self.firma_combo.addItem("-- Firma seçin --", None)
        for c in sorted(self.state.companies, key=lambda c: c["ad"]):
            self.firma_combo.addItem(f"{c['ad']} ({c['kod']})", c["kod"])

    def _on_record_chosen(self, _index: int) -> None:
        rec_id = self.record_combo.currentData()
        rec = next((r for r in self.state.records if r["id"] == rec_id), None)
        if rec:
            self._load_record(rec)

    def _load_record(self, rec: dict) -> None:
        self._selected_record = rec
        self.satis_id_edit.setText(rec.get("satisId") or rec["id"])
        self.irsaliye_tarihi_edit.setText(rec.get("tarih") or get_today_date_string())
        self.fatura_tarihi_edit.setText(rec.get("tarih") or get_today_date_string())
        self.fiyat_kg.setValue(rec.get("fiyatKg") or 0)
        self.fiyat_teneke.setValue(rec.get("fiyatTeneke") or 0)
        self.fiyat_adet.setValue(rec.get("fiyatAdet") or 0)

        # Zaten bir SaleItem'a bağlıysa (edit-in-place), o kaydın firma/plaka/
        # tarih/foto bilgilerini önceden doldur.
        linked = None
        if rec.get("linkedSaleId"):
            linked = next((s for s in self.state.sales if s["id"] == rec["linkedSaleId"]), None)
        if not linked and rec.get("satisId"):
            linked = next((s for s in self.state.sales if s["id"] == rec["satisId"]), None)
        if linked:
            idx = self.firma_combo.findData(linked.get("sirketKodu"))
            if idx >= 0:
                self.firma_combo.setCurrentIndex(idx)
            self.plaka_edit.setText(linked.get("aracPlakasi") or "")
            self.irsaliye_tarihi_edit.setText(linked.get("irsaliyeTarihi") or self.irsaliye_tarihi_edit.text())
            self.fatura_tarihi_edit.setText(linked.get("faturaTarihi") or self.fatura_tarihi_edit.text())
            self.fiyat_adet.setValue(linked.get("fiyatAdet") or self.fiyat_adet.value())
            self._photo_data_url = linked.get("irsaliyeFotoUrl") or ""

        self._refresh_total()

    def _attach_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "İrsaliye Fotoğrafı Seç", "", "Görseller (*.png *.jpg *.jpeg)")
        if path:
            self._photo_data_url = _encode_image_file(path)
            QMessageBox.information(self, "Eklendi", "Fotoğraf eklendi.")

    def _refresh_total(self) -> None:
        if not self._selected_record:
            self.total_label.setText("Toplam Tutar: ₺0")
            return
        rec = self._selected_record
        total = calculate_total_amount(
            rec.get("satisTeneke"), rec.get("satisKg"),
            self.fiyat_teneke.value(), self.fiyat_kg.value(),
            rec.get("satisAdet"), self.fiyat_adet.value(),
        )
        self.total_label.setText(f"Toplam Tutar: ₺{format_number(total)}")

    def _on_save(self) -> None:
        rec = self._selected_record
        if not rec:
            QMessageBox.warning(self, "Eksik bilgi", "Lütfen tamamlanacak bir kayıt seçin.")
            return
        firma_kod = self.firma_combo.currentData()
        if not firma_kod:
            QMessageBox.warning(self, "Eksik bilgi", "Lütfen bir firma seçin.")
            return
        firma = next((c for c in self.state.companies if c["kod"] == firma_kod), None)

        existing_ids = {s["id"] for s in self.state.sales}
        entered_id = self.satis_id_edit.text().strip().upper()
        sale_id = entered_id or rec.get("satisId") or generate_sale_id(existing_ids, rec.get("tarih"))

        total = calculate_total_amount(
            rec.get("satisTeneke"), rec.get("satisKg"),
            self.fiyat_teneke.value(), self.fiyat_kg.value(),
            rec.get("satisAdet"), self.fiyat_adet.value(),
        )

        sale_item = {
            "id": sale_id,
            "kaynak": "defter",
            "kaynakKayitId": rec["id"],
            "irsaliyeTarihi": self.irsaliye_tarihi_edit.text().strip(),
            "faturaTarihi": self.fatura_tarihi_edit.text().strip(),
            "sirketKodu": firma["kod"],
            "sirketAdi": firma["ad"],
            "aracPlakasi": self.plaka_edit.text().strip().upper(),
            "urunKodu": rec["urunKodu"],
            "urunAdi": rec["urunAdi"],
            "miktarTeneke": rec.get("satisTeneke") or 0,
            "miktarKg": rec.get("satisKg") or 0,
            "miktarAdet": rec.get("satisAdet") or 0,
            "fiyatTeneke": self.fiyat_teneke.value(),
            "fiyatKg": self.fiyat_kg.value(),
            "fiyatAdet": self.fiyat_adet.value(),
            "tutar": total,
            "barcode": rec.get("barcode") or rec["urunKodu"],
            "irsaliyeFotoUrl": self._photo_data_url,
        }

        updated_record = {
            **rec,
            "satisId": sale_id,
            "linkedSaleId": sale_id,
            "fiyatTeneke": self.fiyat_teneke.value(),
            "fiyatKg": self.fiyat_kg.value(),
            "fiyatAdet": self.fiyat_adet.value(),
        }

        try:
            self.state.db.save_all_data(sales=[sale_item], records=[updated_record])
            self.state.load_all()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Kayıt Hatası", f"Satış tamamlanamadı:\n{exc}")
            return

        QMessageBox.information(
            self, "Tamamlandı", f"Satış tamamlandı — ID: {sale_id}, Toplam: ₺{format_number(total)}"
        )
        if self.on_saved:
            self.on_saved()
        self.accept()
