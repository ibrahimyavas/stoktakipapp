"""
DB/ağ çağrılarını (Turso, Gemini OCR, Google Sheets webhook) UI thread'ini
kilitlemeden arka planda çalıştırmak için küçük bir yardımcı. Qt'de QRunnable
kendi başına sinyal yayamadığı için, sinyalleri taşıyan küçük bir QObject
(`_WorkerSignals`) ile sarmalıyoruz — standart PySide6 deseni.
"""

from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)


class _Worker(QRunnable):
    def __init__(self, fn: Callable[[], Any]):
        super().__init__()
        self.fn = fn
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception:
            self.signals.error.emit(traceback.format_exc())
        else:
            self.signals.finished.emit(result)


def run_in_background(
    fn: Callable[[], Any],
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[str], None] | None = None,
) -> None:
    """fn'i arka plan thread havuzunda çalıştırır; sonucu/hatayı UI thread'ine
    (Qt sinyal-slot mekanizması ile, otomatik olarak) geri taşır."""
    worker = _Worker(fn)
    if on_done:
        worker.signals.finished.connect(on_done)
    if on_error:
        worker.signals.error.connect(on_error)
    else:
        worker.signals.error.connect(lambda msg: print(f"[background error]\n{msg}"))
    QThreadPool.globalInstance().start(worker)
