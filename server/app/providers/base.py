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
    # da dove è stata scattata ogni foto (nome file -> {"angle": gradi dal primo scatto, "ring": 0|1}),
    # se il telefono aveva la bussola; vuoto per le foto importate dalla galleria
    photo_views: dict = field(default_factory=dict)
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
        if sys.platform != "win32":
            # COLMAP di Ubuntu è compilato con Qt: senza uno schermo (Codespace, server) Qt può
            # interrompere il programma con SIGABRT (codice -6). "offscreen" = niente schermo richiesto.
            env = {**(env if env is not None else os.environ), "QT_QPA_PLATFORM": "offscreen"}
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
                rc = self._proc.returncode
                why = {-6: " — il programma si è interrotto da solo (SIGABRT)",
                       -9: " — terminato dal sistema, probabilmente memoria esaurita (prova con meno foto)",
                       -15: " — fermato dall'esterno, di solito per memoria quasi esaurita"}.get(rc, "")
                tail = self._log_tail()
                raise ProviderError(f"Il passo “{step}” è fallito (codice {rc}{why})." + (f" Ultime righe: {tail}" if tail else ""))
        finally:
            self._proc = None
            if self.log_file:
                log.close()
        self.progress(band[1], step)

    def _log_tail(self, lines: int = 3, limit: int = 300) -> str:
        """Ultime righe non vuote del log del programma: di solito contengono il motivo dell'errore."""
        try:
            text = Path(self.log_file).read_text(encoding="utf-8", errors="replace") if self.log_file else ""
        except OSError:
            return ""
        last = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("=====")][-lines:]
        return " | ".join(last)[-limit:]

    def _kill(self):
        p = self._proc
        if p and p.poll() is None:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
            else:
                p.send_signal(signal.SIGTERM)


def clean_in_subprocess(ctx: RunContext, source: Path, out: Path, *, points: bool = False, y_up: bool = False,
                        plane: bool = True, max_faces: int | None = None, band: tuple[float, float] = (88, 96)):
    """Pulizia del modello in un processo a parte (app/mesh/cli.py): se esaurisce la memoria muore
    lui, non il server, e il calcolo non blocca le risposte all'app. -> (mesh, passi, scostamento mm)."""
    import json

    root = Path(__file__).resolve().parents[2]  # cartella server/
    args = [*(["--points"] if points else []), *(["--y-up"] if y_up else []), *([] if plane else ["--no-plane"]),
            *(["--max-faces", str(max_faces)] if max_faces else [])]
    ctx.run([sys.executable, "-m", "app.mesh.cli", source, out, *args], band=band, step="Pulizia del modello",
            expected_s=90, cwd=root)
    meta = json.loads(Path(str(out) + ".json").read_text(encoding="utf-8"))
    if meta.get("error"):
        raise ProviderError(meta["error"])
    mesh = trimesh.load(out, force="mesh")
    mesh.metadata["fidelity"] = meta["fidelity"]  # per il report: il PLY non conserva i metadati
    return mesh, meta["steps"], meta.get("deviationMm")


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
