"""
Uygulama ayarları (Turso/Gemini/Sheets bağlantı bilgileri) — paketlenmiş bir
.exe'nin içine .env gömülemeyeceği için, OS'a uygun kullanıcı config
klasöründe bir JSON dosyasında saklanır (platformdirs ile yol bulunur).

Windows:  %APPDATA%\\UretimSatisDefteri\\config.json
macOS:    ~/Library/Application Support/UretimSatisDefteri/config.json
Linux:    ~/.config/UretimSatisDefteri/config.json
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_config_dir

APP_NAME = "UretimSatisDefteri"
APP_AUTHOR = "UretimSatisDefteri"


def config_dir() -> Path:
    return Path(user_config_dir(APP_NAME, APP_AUTHOR))


def config_file() -> Path:
    return config_dir() / "config.json"


@dataclass
class AppSettings:
    turso_database_url: str = ""
    turso_auth_token: str = ""
    gemini_api_key: str = ""
    sheets_url: str = ""
    # Son seçilen rol (uretim/satis/admin) — bir sonraki açılışta hatırlanır.
    last_profile: str = ""
    # Görünüm: "dark" / "light" + serbestçe seçilebilir aksan rengi (#RRGGBB).
    theme_mode: str = "dark"
    accent_color: str = "#10B981"

    def is_configured(self) -> bool:
        return bool(self.turso_database_url and self.turso_auth_token)


def load_settings() -> AppSettings:
    path = config_file()
    if not path.exists():
        return AppSettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        defaults = AppSettings()
        # Eksik alanlar (ör. eski bir config.json'da henüz olmayan yeni
        # tema alanları) her zaman kendi varsayılanını alır — "" değil,
        # aksi halde tema uygulaması boş renk/mod ile bozulurdu.
        return AppSettings(
            **{k: raw.get(k, getattr(defaults, k)) for k in AppSettings.__dataclass_fields__}
        )
    except (json.JSONDecodeError, OSError, TypeError):
        return AppSettings()


def save_settings(settings: AppSettings) -> None:
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    config_file().write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
