"""WaybillVaultModal.tsx karşılığı — İrsaliye Arşivi. Kamera yerine dosya
seçiciyle fotoğraf ekleme (kullanıcı kararı), Gemini OCR ile otomatik alan
doldurma, liste/arama/görüntüle/sil."""

from __future__ import annotations

import base64
import re
import time
import uuid

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.app_state import AppState
from core.ocr import run_ocr
from core.stock_logic import format_date_tr, get_today_date_string
from ui.workers import run_in_background


def _new_id() -> str:
    return f"IRS-{int(time.time() * 1000)}"


def _encode_image_file(path: str) -> str:
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/jpeg;base64,{data}"


class WaybillVaultDialog(QDialog):
    def __init__(self, state: AppState, gemini_api_key: str, on_saved=None, parent=None):
        super().__init__(parent)
        self.state = state
        self.gemini_api_key = gemini_api_key
        self.on_saved = on_saved
        self._photo_data_url = ""
        self._photo_path = ""

        self.setWindowTitle("İrsaliye Arşivi")
        self.setMinimumSize(600, 640)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tabs.addTab(self._build_list_tab(), "Kayıtlı İrsaliyeler")
        self.tabs.addTab(self._build_add_tab(), "Yeni İrsaliye Fotoğrafı")

        self._refresh_list()

    # -- Liste sekmesi -------------------------------------------------

    def _build_list_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("İrsaliye no, firma, tarih veya not ara...")
        self.search_edit.textChanged.connect(self._refresh_list)
        layout.addWidget(self.search_edit)

        self.list_table = QTableWidget(0, 5)
        self.list_table.setHorizontalHeaderLabels(["İrsaliye No", "Firma", "Tarih", "Tutar", "İşlem"])
        self.list_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.list_table.setAlternatingRowColors(True)
        layout.addWidget(self.list_table)

        return widget

    def _refresh_list(self) -> None:
        query = self.search_edit.text().strip().lower()
        rows = [
            w
            for w in self.state.waybills
            if not query
            or query in (w.get("irsaliyeNo") or "").lower()
            or query in (w.get("firmaAdi") or "").lower()
            or query in (w.get("tarih") or "").lower()
            or query in (w.get("notlar") or "").lower()
            or query in (w.get("okunanMetin") or "").lower()
        ]
        rows.sort(key=lambda w: w.get("eklenmeTarihi") or "", reverse=True)

        self.list_table.setRowCount(len(rows))
        for i, w in enumerate(rows):
            self.list_table.setItem(i, 0, QTableWidgetItem(w.get("irsaliyeNo") or ""))
            self.list_table.setItem(i, 1, QTableWidgetItem(w.get("firmaAdi") or ""))
            self.list_table.setItem(i, 2, QTableWidgetItem(format_date_tr(w.get("tarih"))))
            self.list_table.setItem(i, 3, QTableWidgetItem(str(w.get("tutar") or 0)))

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            view_btn = QPushButton("İncele")
            view_btn.clicked.connect(lambda _, item=w: self._view(item))
            action_layout.addWidget(view_btn)
            del_btn = QPushButton("Sil")
            del_btn.clicked.connect(lambda _, item=w: self._delete(item))
            action_layout.addWidget(del_btn)
            self.list_table.setCellWidget(i, 4, action_widget)

    def _view(self, item: dict) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(item.get("irsaliyeNo") or "İrsaliye")
        layout = QVBoxLayout(dialog)
        img_label = QLabel()
        try:
            _, b64data = (item.get("fotoUrl") or "").split(",", 1)
            pixmap = QPixmap()
            pixmap.loadFromData(base64.b64decode(b64data))
            img_label.setPixmap(pixmap.scaledToWidth(500))
        except (ValueError, Exception):
            img_label.setText("Görsel yok.")
        layout.addWidget(img_label)
        text_view = QPlainTextEdit(item.get("okunanMetin") or "")
        text_view.setReadOnly(True)
        layout.addWidget(text_view)
        dialog.exec()

    def _delete(self, item: dict) -> None:
        reply = QMessageBox.question(self, "Sil", f"'{item.get('irsaliyeNo')}' irsaliyesini silmek istiyor musunuz?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.state.db.save_all_data(deleted_waybill_ids=[item["id"]])
        self.state.load_all()
        self._refresh_list()
        if self.on_saved:
            self.on_saved()

    # -- Ekleme sekmesi --------------------------------------------------

    def _build_add_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        pick_btn = QPushButton("Fotoğraf Seç...")
        pick_btn.clicked.connect(self._pick_photo)
        layout.addWidget(pick_btn)

        self.photo_preview = QLabel("Henüz fotoğraf seçilmedi.")
        self.photo_preview.setFixedHeight(160)
        layout.addWidget(self.photo_preview)

        self.ocr_status_label = QLabel("")
        self.ocr_status_label.setStyleSheet("color: #94A3B8;")
        layout.addWidget(self.ocr_status_label)

        grid = QGridLayout()
        self.irsaliye_no_edit = QLineEdit()
        grid.addWidget(QLabel("İrsaliye No"), 0, 0)
        grid.addWidget(self.irsaliye_no_edit, 0, 1)

        self.firma_combo = QComboBox()
        self.firma_combo.setEditable(True)
        self.firma_combo.currentTextChanged.connect(lambda t: self.firma_adi_edit.setText(t))
        grid.addWidget(QLabel("Firma"), 1, 0)
        grid.addWidget(self.firma_combo, 1, 1)
        self.firma_adi_edit = QLineEdit()
        self.firma_adi_edit.hide()  # firma_combo (editable) tek başına yeterli, arka planda senkron tutuluyor

        self.tarih_edit = QLineEdit(get_today_date_string())
        grid.addWidget(QLabel("Tarih"), 2, 0)
        grid.addWidget(self.tarih_edit, 2, 1)

        self.tutar_edit = QLineEdit("0")
        grid.addWidget(QLabel("Tutar"), 3, 0)
        grid.addWidget(self.tutar_edit, 3, 1)

        self.notlar_edit = QLineEdit()
        grid.addWidget(QLabel("Notlar"), 4, 0)
        grid.addWidget(self.notlar_edit, 4, 1)

        layout.addLayout(grid)

        layout.addWidget(QLabel("OCR ile Okunan Ham Metin:"))
        self.raw_text_view = QPlainTextEdit()
        self.raw_text_view.setReadOnly(True)
        self.raw_text_view.setMaximumHeight(100)
        layout.addWidget(self.raw_text_view)

        save_btn = QPushButton("İrsaliyeyi Kaydet")
        save_btn.setProperty("variant", "primary")
        save_btn.clicked.connect(self._on_save)
        layout.addWidget(save_btn)

        self._refresh_firma_combo()
        return widget

    def _refresh_firma_combo(self) -> None:
        self.firma_combo.clear()
        for c in sorted(self.state.companies, key=lambda c: c["ad"]):
            self.firma_combo.addItem(c["ad"])

    def _pick_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "İrsaliye Fotoğrafı Seç", "", "Görseller (*.png *.jpg *.jpeg)")
        if not path:
            return
        self._photo_path = path
        self._photo_data_url = _encode_image_file(path)
        pixmap = QPixmap(path)
        self.photo_preview.setPixmap(pixmap.scaledToHeight(160))

        self.ocr_status_label.setText("Yazı okunuyor (OCR)...")
        run_in_background(
            lambda: run_ocr(path, "irsaliye", self.gemini_api_key),
            self._on_ocr_done,
            self._on_ocr_error,
        )

    def _on_ocr_done(self, result: dict) -> None:
        if result.get("error"):
            self.ocr_status_label.setText(f"OCR hatası: {result['error']}")
            return
        self.ocr_status_label.setText("OCR tamamlandı — boş alanlar otomatik dolduruldu.")

        if not self.irsaliye_no_edit.text() and result.get("irsaliyeNo"):
            self.irsaliye_no_edit.setText(str(result["irsaliyeNo"]))
        if not self.firma_combo.currentText() and result.get("firmaAdi"):
            self.firma_combo.setCurrentText(str(result["firmaAdi"]))
        if self.tarih_edit.text() == get_today_date_string() and result.get("tarih"):
            normalized = str(result["tarih"]).replace(".", "-")
            if re.match(r"^\d{4}-\d{2}-\d{2}$", normalized):
                self.tarih_edit.setText(normalized)
        if self.tutar_edit.text() in ("", "0") and result.get("tutar"):
            self.tutar_edit.setText(str(result["tutar"]))
        if not self.notlar_edit.text() and result.get("notlar"):
            self.notlar_edit.setText(str(result["notlar"]))
        if result.get("metin"):
            self.raw_text_view.setPlainText(str(result["metin"]))

    def _on_ocr_error(self, msg: str) -> None:
        self.ocr_status_label.setText("OCR sırasında beklenmeyen bir hata oluştu.")
        print(msg)

    def _on_save(self) -> None:
        if not self._photo_data_url:
            QMessageBox.warning(self, "Eksik bilgi", "Lütfen önce bir fotoğraf seçin.")
            return

        try:
            tutar = float(self.tutar_edit.text().replace(",", ".")) if self.tutar_edit.text() else 0
        except ValueError:
            tutar = 0

        item = {
            "id": _new_id(),
            "irsaliyeNo": self.irsaliye_no_edit.text().strip() or f"İRS-{int(time.time()) % 100000}",
            "firmaAdi": self.firma_combo.currentText().strip() or "Bilinmeyen Firma",
            "tarih": self.tarih_edit.text().strip() or get_today_date_string(),
            "tutar": tutar,
            "notlar": self.notlar_edit.text().strip(),
            "fotoUrl": self._photo_data_url,
            "okunanMetin": self.raw_text_view.toPlainText(),
            "eklenmeTarihi": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        try:
            self.state.db.save_all_data(waybills=[item])
            self.state.load_all()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Hata", f"İrsaliye kaydedilemedi:\n{exc}")
            return

        QMessageBox.information(self, "Kaydedildi", "İrsaliye arşive eklendi.")
        self._reset_add_form()
        self._refresh_list()
        self.tabs.setCurrentIndex(0)
        if self.on_saved:
            self.on_saved()

    def _reset_add_form(self) -> None:
        self._photo_data_url = ""
        self._photo_path = ""
        self.photo_preview.clear()
        self.photo_preview.setText("Henüz fotoğraf seçilmedi.")
        self.ocr_status_label.setText("")
        self.irsaliye_no_edit.clear()
        self.firma_combo.setCurrentText("")
        self.tarih_edit.setText(get_today_date_string())
        self.tutar_edit.setText("0")
        self.notlar_edit.clear()
        self.raw_text_view.clear()
