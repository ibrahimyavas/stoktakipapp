"""Uygulama teması — qt-material ile açık/koyu mod ve serbestçe seçilebilir
aksan rengi. Kullanıcı herhangi bir rengi seçebilir (sadece hazır 20 temadan
biri değil); bu yüzden qt-material'ın XML tema dosyasını dinamik olarak
(geçici bir dosyaya) üretip onu uyguluyoruz."""

from __future__ import annotations

import tempfile
from pathlib import Path

from qt_material import apply_stylesheet

# Ayarlar ekranında hızlı seçim için birkaç hazır aksan rengi — ama kullanıcı
# "Özel Renk..." ile bunlarla sınırlı kalmadan istediği herhangi bir rengi de
# seçebilir (bkz. ui/dialog_settings.py, QColorDialog).
PRESET_ACCENTS: dict[str, str] = {
    "Yeşil": "#10B981",
    "Mavi": "#3B82F6",
    "Mor": "#8B5CF6",
    "Turuncu": "#F59E0B",
    "Kırmızı": "#EF4444",
    "Camgöbeği": "#06B6D4",
    "Pembe": "#EC4899",
}

DEFAULT_ACCENT = PRESET_ACCENTS["Yeşil"]
DEFAULT_MODE = "dark"

# Rol rozetleri (ProfileSelector, MainWindow başlığı) için sabit renkler —
# bunlar kullanıcının seçtiği genel aksan renginden bağımsız, rolü ayırt
# etmeye yarıyor.
ROLE_COLORS = {"uretim": "#10B981", "satis": "#3B82F6", "admin": "#8B5CF6"}

_DARK_SURFACE = {
    "secondaryColor": "#1E1E22",
    "secondaryLightColor": "#2A2A30",
    "secondaryDarkColor": "#141417",
    "primaryTextColor": "#F1F5F9",
    "secondaryTextColor": "#F1F5F9",
}
_LIGHT_SURFACE = {
    "secondaryColor": "#F4F4F6",
    "secondaryLightColor": "#FFFFFF",
    "secondaryDarkColor": "#E4E4E8",
    "primaryTextColor": "#1A1A1E",
    "secondaryTextColor": "#3C3C43",
}


def _lighten(hex_color: str, amount: float = 0.35) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    r = int(r + (255 - r) * amount)
    g = int(g + (255 - g) * amount)
    b = int(b + (255 - b) * amount)
    return f"#{r:02x}{g:02x}{b:02x}"


# En son uygulanan tema — sayfaların (ör. Rapor grafiği) QWidget palette'i
# yerine burayı okuyup arka planlarını temaya göre boyayabilmesi için.
current_mode: str = DEFAULT_MODE
current_accent: str = DEFAULT_ACCENT


def current_surface_color() -> str:
    return (_DARK_SURFACE if current_mode == "dark" else _LIGHT_SURFACE)["secondaryColor"]


def current_text_color() -> str:
    return (_DARK_SURFACE if current_mode == "dark" else _LIGHT_SURFACE)["primaryTextColor"]


def _build_theme_xml(mode: str, accent: str) -> str:
    surface = _DARK_SURFACE if mode == "dark" else _LIGHT_SURFACE
    colors = {
        "primaryColor": accent,
        "primaryLightColor": _lighten(accent),
        **surface,
    }
    lines = ["<resources>"]
    for name, value in colors.items():
        lines.append(f'  <color name="{name}">{value}</color>')
    lines.append("</resources>")

    tmp_dir = Path(tempfile.gettempdir()) / "uretim_satis_defteri_theme"
    tmp_dir.mkdir(exist_ok=True)
    tmp_file = tmp_dir / f"theme_{mode}_{accent.lstrip('#')}.xml"
    tmp_file.write_text("\n".join(lines), encoding="utf-8")
    return str(tmp_file)


# qt-material varsayılan olarak buton/sekme/başlık metinlerini BÜYÜK HARFE
# çeviriyor — ekran görüntüsüyle doğrulandı, okumayı zorlaştırıp "göz yorucu"
# hissi veren en büyük etkenlerden biri bu. Kendi ek QSS'imizle kapatıyoruz.
# Ayrıca QGroupBox'lara (bölüm kartları) sayfa arka planından hafifçe daha
# aydınlık bir zemin veriyoruz ki bölümler birbirinden daha net ayrılsın.
_OVERRIDE_QSS = """
QPushButton, QTabBar, QGroupBox, QHeaderView::section, QToolButton {
    text-transform: none;
}
QGroupBox {
    font-weight: 700;
}
"""


def apply_theme(app, mode: str = DEFAULT_MODE, accent: str = DEFAULT_ACCENT) -> None:
    """Uygulamanın tamamına açık/koyu mod + seçilen aksan rengiyle qt-material
    temasını uygular. Ayarlar ekranından her değiştirildiğinde tekrar
    çağrılabilir (canlı önizleme)."""
    global current_mode, current_accent
    current_mode, current_accent = mode, accent
    theme_xml = _build_theme_xml(mode, accent)
    apply_stylesheet(app, theme=theme_xml, invert_secondary=(mode == "light"))
    app.setStyleSheet(app.styleSheet() + _OVERRIDE_QSS)


def chip_style(color: str, filled: bool = False) -> str:
    """QLabel için renkli 'chip' (rozet) stili — rol rengi vb. dinamik
    renkler için genel temadan bağımsız, tek satırlık yardımcı."""
    if filled:
        return f"background: {color}; color: #04120C; border-radius: 10px; padding: 3px 10px; font-weight: 700;"
    return f"background: {color}22; color: {color}; border-radius: 10px; padding: 3px 10px; font-weight: 700;"
