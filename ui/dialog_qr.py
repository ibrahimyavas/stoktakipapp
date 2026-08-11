"""QRCodeGeneratorModal.tsx karşılığı — ama web sürümünün aksine iki uzak
üçüncü parti API'ye (qrserver.com, Google Charts) bağımlı değil; `qrcode`
kütüphanesiyle tamamen yerel/offline üretir. Yazdırma (QPrinter) ve
panoya kopyalama (QClipboard) native masaüstü API'leriyle yapılır."""

from __future__ import annotations

import io

import qrcode
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


def _make_qr_pixmap(code: str, size: int = 260) -> QPixmap:
    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(code)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qimg = QImage.fromData(buf.getvalue(), "PNG")
    return QPixmap.fromImage(qimg).scaled(size, size)


class QRCodeDialog(QDialog):
    def __init__(self, title: str, code: str, details: list[tuple[str, str]] | None = None, parent=None):
        super().__init__(parent)
        self.code = code
        self.setWindowTitle(title)
        self.setMinimumWidth(340)

        layout = QVBoxLayout(self)

        heading = QLabel(title)
        heading.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(heading)

        qr_label = QLabel()
        qr_label.setPixmap(_make_qr_pixmap(code))
        layout.addWidget(qr_label)

        code_label = QLabel(code)
        code_label.setStyleSheet("font-family: monospace; font-size: 14px; font-weight: 700; color: #34D399;")
        layout.addWidget(code_label)

        if details:
            table = QTableWidget(len(details), 2)
            table.horizontalHeader().setVisible(False)
            table.verticalHeader().setVisible(False)
            for i, (label, value) in enumerate(details):
                table.setItem(i, 0, QTableWidgetItem(label))
                table.setItem(i, 1, QTableWidgetItem(value))
            table.resizeColumnsToContents()
            table.setMaximumHeight(min(200, 30 * len(details) + 10))
            layout.addWidget(table)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("Kodu Kopyala")
        copy_btn.clicked.connect(self._copy_code)
        btn_row.addWidget(copy_btn)

        print_btn = QPushButton("Yazdır")
        print_btn.clicked.connect(self._print)
        btn_row.addWidget(print_btn)

        save_btn = QPushButton("PNG Olarak Kaydet")
        save_btn.clicked.connect(self._save_png)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)
        self._qr_label = qr_label

    def _copy_code(self) -> None:
        QApplication.clipboard().setText(self.code)

    def _print(self) -> None:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        from PySide6.QtGui import QPainter

        painter = QPainter(printer)
        pixmap = self._qr_label.pixmap()
        painter.drawPixmap(40, 40, pixmap)
        painter.drawText(40, 40 + pixmap.height() + 30, self.code)
        painter.end()

    def _save_png(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(self, "QR Kodu Kaydet", f"{self.code}.png", "PNG (*.png)")
        if path:
            self._qr_label.pixmap().save(path, "PNG")
