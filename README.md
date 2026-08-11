# Üretim & Satış Defteri — Masaüstü Uygulaması

Bu, ayrı bir repodaki (web/Cloudflare) React uygulamasının **Python + PySide6
(Qt) masaüstü karşılığıdır**. İkisi de **aynı Turso veritabanına** bağlanır —
aynı anda birlikte kullanılabilirler, veri kaybı olmaz (senkron modeli
non-destructive upsert + explicit delete, bkz. `core/db_core.py`). Bu repo
bilinçli olarak web uygulamasından ayrı tutuluyor: web tarayıcıda/Cloudflare'de
kalıyor, bu repo sadece masaüstü programı için.

## Neden bu var?

Web sürümü Cloudflare Workers üzerinde çalışıyor; bu, tarayıcı/internet
gerektirir ve deploy/token/edge-runtime karmaşıklığı getirir. Bu masaüstü
sürümü tüm o karmaşıklığı ortadan kaldırır — çift tıkla açılan, normal bir
program. Kamera ile barkod tarama şimdilik yok (kullanıcı kararı) — kod
alanlarına elle giriliyor.

## Geliştirme ortamı kurulumu

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 main.py
```

İlk açılışta bir Ayarlar penceresi çıkar — Turso bağlantı bilgilerini
(`TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`) girmeniz istenir. Bu bilgiler
OS'a uygun kullanıcı config klasöründe (`core/settings.py`, `platformdirs`
ile) yerel bir `config.json` dosyasında saklanır — repoya hiç gitmez.

## Proje yapısı

```
core/          Platform bağımsız iş mantığı (DB, stok hesapları, OCR, ayarlar)
ui/            PySide6 ekranlar ve diyaloglar
packaging/     PyInstaller spec dosyası
```

Web sürümündeki her ekranın burada bire bir karşılığı var:

| Web (`src/components/`) | Masaüstü (`ui/`) |
|---|---|
| `ProfileSelector.tsx` | `profile_selector.py` |
| `MobileNavigation.tsx` + `App.tsx` | `main_window.py` |
| `DashboardDefter.tsx` | `page_defter.py` |
| `DashboardSatis.tsx` | `page_satis.py` |
| `DashboardRapor.tsx` | `page_rapor.py` |
| `DashboardGenel.tsx` | `page_genel.py` |
| `BarcodeAppIdMapperModal.tsx` | `dialog_barcode_mapper.py` |
| `CompleteSaleModal.tsx` | `dialog_complete_sale.py` |
| `WaybillVaultModal.tsx` | `dialog_waybill_vault.py` |
| `QRCodeGeneratorModal.tsx` | `dialog_qr.py` (yerel `qrcode`, uzak API yok) |
| `GoogleSheetsModal.tsx` | `dialog_sheets_sync.py` |

## Kapsam dışı bırakılanlar (bilinçli kararlar)

- **Kamera ile canlı barkod/QR tarama** — kod alanlarına elle giriliyor.
- **PDF'i uygulama içinde gömülü önizleme** — OS'un varsayılan görüntüleyicisiyle
  harici açılıyor.
- Web sürümünün QR üretimi iki uzak API'ye (qrserver.com, Google Charts)
  bağımlıydı — burada tamamen yerel/offline (`qrcode` kütüphanesi).

## Paketleme (çift tıkla çalışan .exe/uygulama)

```bash
pip install pyinstaller
pyinstaller packaging/pyinstaller.spec
# Çıktı: dist/UretimSatisDefteri/
```

Windows ve macOS derlemeleri için o işletim sistemlerine ihtiyacınız yok —
`.github/workflows/build-desktop.yml`, bir `vX.Y.Z` tag'i push'landığında
GitHub'ın kendi Windows/Mac/Linux runner'larında otomatik derleyip bir
GitHub Release'e ekler:

```bash
git tag v1.0.0
git push origin v1.0.0
```

**Not:** `packaging/pyinstaller.spec`, PyInstaller'ın PySide6/shiboken6'nın
sürüm son ekli paylaşımlı kütüphane dosyalarını (`libshiboken6.abi3.so.6.11`
gibi) bazı sürümlerde atlaması nedeniyle elle bir düzeltme içeriyor — bu
olmadan derlenmiş uygulama hiç açılmıyordu (yerelde test edilip bulundu ve
düzeltildi).
