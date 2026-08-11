# PyInstaller spec — Üretim & Satış Defteri masaüstü uygulaması.
# Çalıştırma: desktop-app/ kökünden `pyinstaller packaging/pyinstaller.spec`
# --onedir modu kullanılıyor (tek dosyaya göre daha hızlı açılış, antivirüs
# false-positive riski daha düşük). Çıktı: dist/UretimSatisDefteri/

# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs, get_package_paths

block_cipher = None
ROOT = Path(SPECPATH).parent  # desktop-app/

# PyInstaller'ın otomatik bağımlılık tarayıcısı VE collect_dynamic_libs(),
# PySide6/shiboken6'nın sürüm son ekli paylaşımlı kütüphane dosyalarını
# (ör. libshiboken6.abi3.so.6.11 — ".so" ile bitmediği için glob desenini
# kaçırıyor) bazı sürümlerde atlıyor. Bu, derlenmiş uygulamanın hiç açılmayıp
# "cannot open shared object file" hatası vermesine yol açıyordu (yerelde
# test edilip bulundu) — paket dizinlerini elle tarayıp ekliyoruz.
def _find_versioned_libs(package_name: str) -> list[tuple[str, str]]:
    try:
        _, pkg_dir = get_package_paths(package_name)
    except Exception:
        return []
    pkg_path = Path(pkg_dir)
    found = []
    for pattern in ("lib*.so*", "lib*.dylib*", "*.dll"):
        for f in pkg_path.rglob(pattern):
            if f.is_file():
                found.append((str(f), "."))
    return found


extra_binaries = (
    collect_dynamic_libs("shiboken6")
    + collect_dynamic_libs("PySide6")
    + _find_versioned_libs("shiboken6")
    + _find_versioned_libs("PySide6")
)

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=extra_binaries,
    datas=[],
    hiddenimports=[
        "libsql_client",
        "libsql_client.http",
        "libsql_client.hrana",
        "libsql_client.sync",
        "PySide6.QtCharts",
        "PySide6.QtPrintSupport",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="UretimSatisDefteri",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI uygulaması — konsol penceresi açılmasın
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="UretimSatisDefteri",
)
