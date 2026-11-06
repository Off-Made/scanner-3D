"""Interfaccia comune dei motori di ricostruzione ("provider").

Ogni provider riceve le foto e restituisce una mesh già pulita e stampabile
(Z verso l'alto, millimetri). Pulizia, report ed export sono identici per tutti.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import trimesh


class JobCancelled(Exception):
    pass


class ProviderError(Exception):
    """Errore comprensibile per l'utente (viene mostrato così com'è nell'app)."""


@dataclass
class RunContext:
    work_dir: Path
    report_progress: Callable[[float, str], None]
    is_cancelled: Callable[[], bool]
    log_file: Path | None = None
    _proc: subprocess.Popen | None = field(default=None, repr=False)

    def progress(self, pct: float, step: str) -> None:
        if self.is_cancelled():
            raise JobCancelled()
        self.report_progress(max(0.0, min(100.0, pct)), step)

    def run(self, cmd: list, band: tuple[float, float], step: str, expected_s: float, cwd: Path | None = None,
            env: dict | None = None) -> None:
        """Esegue un programma esterno a priorità bassa, aggiornando l'avanzamento nella banda
        [band[0], band[1]] in base al tempo atteso, e lo termina se il job viene annullato."""
        self.progress(band[0], step)
        kwargs: dict = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.BELOW_NORMAL_PRIORITY_CLASS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["preexec_fn"] = lambda: os.nice(5)
        log = open(self.log_file, "a", encoding="utf-8", errors="replace") if self.log_file else subprocess.DEVNULL
        try:
            if self.log_file:
                log.write(f"\n===== {step}: {' '.join(map(str, cmd))}\n")
                log.flush()
            self._proc = subprocess.Popen([str(c) for c in cmd], cwd=cwd or self.work_dir,
                                          stdout=log, stderr=subprocess.STDOUT, env=env, **kwargs)
            t0 = time.monotonic()
            while self._proc.poll() is None:
                if self.is_cancelled():
                    self._kill()
                    raise JobCancelled()
                # avanzamento asintotico: si avvicina alla fine della banda senza mai superarla
                frac = 1 - pow(2.718, -(time.monotonic() - t0) / max(expected_s, 1))
                self.report_progress(band[0] + (band[1] - band[0]) * 0.95 * frac, step)
                time.sleep(0.5)
            if self._proc.returncode != 0:
                raise ProviderError(f"Il passo “{step}” è fallito (codice {self._proc.returncode}).")
        finally:
            self._proc = None
            if self.log_file:
                log.close()
        self.progress(band[1], step)

    def _kill(self):
        p = self._proc
        if p and p.poll() is None:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
            else:
                p.send_signal(signal.SIGTERM)


class Provider:
    id: str = "base"
    label: str = ""
    description: str = ""
    min_photos: int = 1
    max_photos: int = 40

    def available(self) -> tuple[bool, str]:
        return True, ""

    def reconstruct(self, photos: list[Path], ctx: RunContext) -> tuple[trimesh.Trimesh, list[str]]:
        """Restituisce (mesh pulita, passi di pulizia eseguiti)."""
        raise NotImplementedError

    def info(self) -> dict:
        ok, why = self.available()
        return {"id": self.id, "label": self.label, "description": self.description,
                "minPhotos": self.min_photos, "maxPhotos": self.max_photos, "available": ok, "reason": why}
