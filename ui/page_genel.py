"""DashboardGenel.tsx karşılığı — Satış + Firma + Stok verilerini birleştiren
genel tablo, arama/filtre, CSV export, belge ekle/görüntüle."""

from __future__ import annotations

import base64
import csv
import io
import mimetypes
import tempfile
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.app_state import AppState
from core.stock_logic import format_date_tr, format_number, get_today_date_string
from ui.dialog_qr import QRCodeDialog


def _encode_file(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "application/octet-stream"
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{data}"


class GenelPage(QWidget):
    def __init__(self, state: AppState, set_saving, can_edit_belge: bool = True, parent=None):
        super().__init__(parent)
        self.state = state
        self.set_saving = set_saving
        self.can_edit_belge = can_edit_belge

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Satış ID, firma, ürün veya plaka ara...")
        self.search_edit.textChanged.connect(self._refresh_table)
        top_row.addWidget(self.search_edit)

        export_btn = QPushButton("CSV Olarak Dışa Aktar")
        export_btn.clicked.connect(self._export_csv)
        top_row.addWidget(export_btn)
        layout.addLayout(top_row)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["Satış ID", "Tarih", "Firma", "Ürün", "Plaka", "Miktar", "Fiyat", "Tutar", "Belge"]
        )
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.on_data_refreshed()

    # -- veri --------------------------------------------------------------

    def _master_rows(self) -> list[dict]:
        company_by_kod = {c["kod"]: c for c in self.state.companies}
        rows = []
        for s in self.state.sales:
            row = {**s, "_firma": company_by_kod.get(s.get("sirketKodu"), {}).get("ad", s.get("sirketAdi", ""))}
            rows.append(row)
        rows.sort(key=lambda r: r.get("irsaliyeTarihi") or "", reverse=True)
        return rows

    def on_data_refreshed(self) -> None:
        self._refresh_table()

    def _refresh_table(self) -> None:
        query = self.search_edit.text().strip().lower()
        rows = [
            r
            for r in self._master_rows()
            if not query
            or query in (r.get("id") or "").lower()
            or query in (r.get("_firma") or "").lower()
            or query in (r.get("urunAdi") or "").lower()
            or query in (r.get("aracPlakasi") or "").lower()
        ]

        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(r.get("id") or ""))
            self.table.setItem(i, 1, QTableWidgetItem(format_date_tr(r.get("irsaliyeTarihi"))))
            self.table.setItem(i, 2, QTableWidgetItem(r.get("_firma") or ""))
            self.table.setItem(i, 3, QTableWidgetItem(r.get("urunAdi") or ""))
            self.table.setItem(i, 4, QTableWidgetItem(r.get("aracPlakasi") or ""))
            self.table.setItem(
                i, 5,
                QTableWidgetItem(f"{format_number(r.get('miktarTeneke'))} T / {format_number(r.get('miktarKg'))} Kg"),
            )
            self.table.setItem(i, 6, QTableWidgetItem(f"₺{format_number(r.get('fiyatKg') or r.get('fiyatTeneke'))}"))
            self.table.setItem(i, 7, QTableWidgetItem(f"₺{format_number(r.get('tutar'))}"))

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            if r.get("irsaliyeFotoUrl"):
                view_btn = QPushButton("Görüntüle")
                view_btn.clicked.connect(lambda _, sale=r: self._view_document(sale))
                action_layout.addWidget(view_btn)
                if self.can_edit_belge:
                    remove_btn = QPushButton("Kaldır")
                    remove_btn.clicked.connect(lambda _, sale=r: self._remove_document(sale))
                    action_layout.addWidget(remove_btn)
            elif self.can_edit_belge:
                add_btn = QPushButton("Belge Ekle")
                add_btn.clicked.connect(lambda _, sale=r: self._attach_document(sale))
                action_layout.addWidget(add_btn)
            qr_btn = QPushButton("QR")
            qr_btn.clicked.connect(lambda _, sale=r: self._show_qr(sale))
            action_layout.addWidget(qr_btn)
            self.table.setCellWidget(i, 8, action_widget)

    # -- belge ekle/görüntüle/kaldır ---------------------------------------

    def _attach_document(self, sale: dict) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Belge Seç", "", "Belgeler (*.png *.jpg *.jpeg *.pdf)"
        )
        if not path:
            return
        data_url = _encode_file(path)
        self._save_sale_document(sale["id"], data_url)

    def _remove_document(self, sale: dict) -> None:
        self._save_sale_document(sale["id"], "")

    def _save_sale_document(self, sale_id: str, data_url: str) -> None:
        sale = next((s for s in self.state.sales if s["id"] == sale_id), None)
        if not sale:
            return
        updated = {**sale, "irsaliyeFotoUrl": data_url}
        try:
            self.state.db.save_all_data(sales=[updated])
            self.state.load_all()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Hata", f"Belge kaydedilemedi:\n{exc}")
            return
        self._refresh_table()

    def _view_document(self, sale: dict) -> None:
        data_url = sale.get("irsaliyeFotoUrl") or ""
        if not data_url:
            return
        if data_url.startswith("data:application/pdf"):
            # PDF'i uygulama içinde göstermek yerine OS'un varsayılan
            # görüntüleyicisiyle harici açıyoruz (ekstra ağır bir PDF-render
            # bağımlılığı eklemeden en güvenilir yol).
            try:
                header, b64data = data_url.split(",", 1)
                raw = base64.b64decode(b64data)
                tmp = Path(tempfile.gettempdir()) / f"belge-{sale.get('id', 'x')}.pdf"
                tmp.write_bytes(raw)
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(tmp)))
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "Hata", f"PDF açılamadı:\n{exc}")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Belge — {sale.get('id')}")
        layout = QVBoxLayout(dialog)
        label = QLabel()
        try:
            header, b64data = data_url.split(",", 1)
            raw = base64.b64decode(b64data)
            pixmap = QPixmap()
            pixmap.loadFromData(raw)
            label.setPixmap(pixmap.scaledToWidth(600))
        except Exception:
            label.setText("Görsel yüklenemedi.")
        layout.addWidget(label)
        dialog.exec()

    def _show_qr(self, sale: dict) -> None:
        details = [
            ("Firma", sale.get("_firma") or sale.get("sirketAdi") or ""),
            ("Ürün", sale.get("urunAdi") or ""),
            ("Tutar", f"₺{format_number(sale.get('tutar'))}"),
        ]
        dialog = QRCodeDialog(f"Satış Fişi — {sale.get('id')}", sale.get("id") or "", details, parent=self)
        dialog.exec()

    # -- CSV export ----------------------------------------------------------

    def _export_csv(self) -> None:
        default_name = f"genel-tablo-{get_today_date_string()}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "CSV Olarak Kaydet", default_name, "CSV (*.csv)")
        if not path:
            return

        rows = self._master_rows()
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=";")
        writer.writerow(
            [
                "Satış ID", "İrsaliye Tarihi", "Fatura Tarihi", "Firma Kodu", "Firma Adı",
                "Araç Plakası", "Ürün Kodu", "Ürün Adı", "Miktar (Teneke)", "Miktar (Kg)",
                "Miktar (Adet)", "Fiyat (Teneke)", "Fiyat (Kg)", "Fiyat (Adet)", "Tutar", "Barkod",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.get("id"), r.get("irsaliyeTarihi"), r.get("faturaTarihi"),
                    r.get("sirketKodu"), r.get("_firma"), r.get("aracPlakasi"),
                    r.get("urunKodu"), r.get("urunAdi"),
                    r.get("miktarTeneke"), r.get("miktarKg"), r.get("miktarAdet"),
                    r.get("fiyatTeneke"), r.get("fiyatKg"), r.get("fiyatAdet"),
                    r.get("tutar"), r.get("barcode"),
                ]
            )

        try:
            # ﻿ (BOM) — Excel'in UTF-8 Türkçe karakterleri doğru göstermesi için (web sürümüyle aynı).
            Path(path).write_text("﻿" + buf.getvalue(), encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Hata", f"CSV kaydedilemedi:\n{exc}")
            return
        QMessageBox.information(self, "Tamamlandı", f"CSV dosyası kaydedildi:\n{path}")
