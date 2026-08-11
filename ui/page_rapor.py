"""DashboardRapor.tsx karşılığı — KPI kartları, düşük stok uyarısı, aylık
üretim/satış bar grafiği (QtCharts ile, salt-okunur/hesaplama ekranı)."""

from __future__ import annotations

from collections import defaultdict

from PySide6.QtCharts import QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QValueAxis
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.app_state import AppState
from core.stock_logic import MONTH_SHORT_TR, format_number

UNIT_FIELD = {
    "Kg": ("uretimKg", "fireKg", "satisKg", "bitisStokKg"),
    "Teneke": ("uretimTeneke", "fireTeneke", "satisTeneke", "bitisStokTeneke"),
    "Adet": ("uretimAdet", "fireAdet", "satisAdet", "bitisStokAdet"),
}


class RaporPage(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state

        root = QVBoxLayout(self)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Birim:"))
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["Kg", "Teneke", "Adet"])
        self.unit_combo.currentTextChanged.connect(self._recompute)
        controls.addWidget(self.unit_combo)

        controls.addWidget(QLabel("Ürün:"))
        self.product_combo = QComboBox()
        self.product_combo.currentIndexChanged.connect(self._recompute)
        controls.addWidget(self.product_combo)
        controls.addStretch()
        root.addLayout(controls)

        self.low_stock_label = QLabel("")
        self.low_stock_label.setWordWrap(True)
        self.low_stock_label.setStyleSheet(
            "background: rgba(239,68,68,0.12); color: #F87171; border: 1px solid rgba(239,68,68,0.3); "
            "border-radius: 8px; padding: 10px; font-weight: 600;"
        )
        self.low_stock_label.hide()
        root.addWidget(self.low_stock_label)

        kpi_row = QHBoxLayout()
        self.kpi_uretim = self._kpi_card("Toplam Üretim", "#34D399")
        self.kpi_satis = self._kpi_card("Toplam Satış", "#60A5FA")
        self.kpi_fire = self._kpi_card("Fire / Wastage", "#F87171")
        self.kpi_gelir = self._kpi_card("Toplam Gelir (₺)", "#FBBF24")
        for card in (self.kpi_uretim, self.kpi_satis, self.kpi_fire, self.kpi_gelir):
            kpi_row.addWidget(card[0])
        root.addLayout(kpi_row)

        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setMinimumHeight(320)
        root.addWidget(self.chart_view)

        self.on_data_refreshed()

    def _kpi_card(self, title: str, color: str) -> tuple[QGroupBox, QLabel]:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        value_label = QLabel("0")
        value_label.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {color};")
        layout.addWidget(value_label)
        return box, value_label

    def on_data_refreshed(self) -> None:
        current = self.product_combo.currentData()
        self.product_combo.blockSignals(True)
        self.product_combo.clear()
        self.product_combo.addItem("Tüm Ürünler", None)
        codes = sorted({r["urunKodu"] for r in self.state.records})
        for code in codes:
            name = next((r["urunAdi"] for r in self.state.records if r["urunKodu"] == code), code)
            self.product_combo.addItem(f"{name} ({code})", code)
        idx = self.product_combo.findData(current)
        self.product_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.product_combo.blockSignals(False)
        self._recompute()

    def _filtered_records(self) -> list[dict]:
        code = self.product_combo.currentData()
        if not code:
            return self.state.records
        return [r for r in self.state.records if r["urunKodu"] == code]

    def _filtered_sales(self) -> list[dict]:
        code = self.product_combo.currentData()
        if not code:
            return self.state.sales
        return [s for s in self.state.sales if s["urunKodu"] == code]

    def _recompute(self) -> None:
        unit = self.unit_combo.currentText()
        uretim_field, fire_field, satis_field, bitis_field = UNIT_FIELD[unit]
        records = self._filtered_records()
        sales = self._filtered_sales()

        total_uretim = sum(r.get(uretim_field) or 0 for r in records)
        total_fire = sum(r.get(fire_field) or 0 for r in records)
        total_satis = sum(r.get(satis_field) or 0 for r in records)
        total_gelir = sum(s.get("tutar") or 0 for s in sales)

        # Fire oranı: üretimi sıfırdan farklı olan ilk birimi öncelik sırasıyla kullan
        # (Kg > Teneke > Adet) — web sürümüyle birebir aynı öncelik mantığı.
        fire_uretim = sum(r.get("uretimKg") or 0 for r in records)
        fire_fire = sum(r.get("fireKg") or 0 for r in records)
        if fire_uretim == 0:
            fire_uretim = sum(r.get("uretimTeneke") or 0 for r in records)
            fire_fire = sum(r.get("fireTeneke") or 0 for r in records)
        if fire_uretim == 0:
            fire_uretim = sum(r.get("uretimAdet") or 0 for r in records)
            fire_fire = sum(r.get("fireAdet") or 0 for r in records)
        fire_rate = (fire_fire / fire_uretim * 100) if fire_uretim else 0

        self.kpi_uretim[1].setText(f"{format_number(total_uretim)} {unit}")
        self.kpi_satis[1].setText(f"{format_number(total_satis)} {unit}")
        self.kpi_fire[1].setText(f"{format_number(total_fire)} {unit}  ({format_number(fire_rate)}%)")
        self.kpi_gelir[1].setText(f"₺{format_number(total_gelir)}")

        self._recompute_low_stock()
        self._recompute_chart(records)

    def _recompute_low_stock(self) -> None:
        latest: dict[str, dict] = {}
        for r in self.state.records:
            code = r["urunKodu"]
            existing = latest.get(code)
            if not existing or r["tarih"] > existing["tarih"]:
                latest[code] = r

        low = []
        for code, r in latest.items():
            teneke = r.get("bitisStokTeneke") or 0
            kg = r.get("bitisStokKg") or 0
            adet = r.get("bitisStokAdet") or 0
            if teneke <= 5 or kg <= 50 or (adet > 0 and adet <= 10):
                low.append(f"{r['urunAdi']}: {format_number(teneke)} T / {format_number(kg)} Kg / {format_number(adet)} Ad")

        if low:
            self.low_stock_label.setText("⚠ Düşük Stok Uyarısı: " + " | ".join(low))
            self.low_stock_label.show()
        else:
            self.low_stock_label.hide()

    def _recompute_chart(self, records: list[dict]) -> None:
        uretim_field, _, satis_field, _ = UNIT_FIELD[self.unit_combo.currentText()]
        monthly_uretim: dict[str, float] = defaultdict(float)
        monthly_satis: dict[str, float] = defaultdict(float)
        for r in records:
            tarih = r.get("tarih") or ""
            if len(tarih) < 7:
                continue
            key = tarih[:7]  # YYYY-MM
            monthly_uretim[key] += r.get(uretim_field) or 0
            monthly_satis[key] += r.get(satis_field) or 0

        months = sorted(set(monthly_uretim) | set(monthly_satis))[-6:]
        labels = []
        for m in months:
            year, mon = m.split("-")
            labels.append(f"{MONTH_SHORT_TR[int(mon) - 1]} {year[2:]}")

        uretim_set = QBarSet("Üretim")
        uretim_set.setColor(QColor("#10B981"))
        satis_set = QBarSet("Satış")
        satis_set.setColor(QColor("#3B82F6"))
        for m in months:
            uretim_set.append(monthly_uretim.get(m, 0))
            satis_set.append(monthly_satis.get(m, 0))

        series = QBarSeries()
        series.append(uretim_set)
        series.append(satis_set)

        # Grafik renkleri sabit kodlanmış (koyu-mod varsayımlı) değil, o an
        # aktif olan temanın kendi yüzey/metin rengiyle boyanıyor — aksi
        # halde açık modda grafik alanı koyu kalıp göze batıyordu (ekran
        # görüntüsüyle tespit edildi).
        from ui.theme import current_surface_color, current_text_color

        text_color = QColor(current_text_color())

        chart = QChart()
        chart.addSeries(series)
        chart.setBackgroundBrush(QColor(current_surface_color()))
        chart.legend().setLabelColor(text_color)
        chart.setTitleBrush(text_color)

        axis_x = QBarCategoryAxis()
        axis_x.append(labels)
        axis_x.setLabelsColor(text_color)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setLabelsColor(text_color)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        self.chart_view.setChart(chart)
