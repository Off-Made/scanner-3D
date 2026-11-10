"""Gestione dei job di ricostruzione: un job alla volta (la RAM del PC è il limite),
stato salvato su disco in data/jobs/<id>/job.json così sopravvive ai riavvii del server."""
from __future__ import annotations

import json
import queue
import shutil
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .deps import describe_import_error
from .mesh.report import printability
from .providers.base import JobCancelled, Provider, ProviderError, RunContext

STATUSES = ("uploading", "queued", "running", "done", "error", "cancelled")


@dataclass
class Job:
    id: str
    provider: str
    name: str
    status: str = "uploading"
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    photos: int = 0
    progress: float = 0.0
    step: str = "In attesa delle foto"
    error: str | None = None
    report: dict | None = None
    cleanup: list[str] = field(default_factory=list)
    started: float | None = None
    finished: float | None = None
    queue_position: int = 0

    def public(self) -> dict:
        d = asdict(self)
        d["elapsedSeconds"] = round((self.finished or time.time()) - self.started, 1) if self.started else 0
        return d


class JobManager:
    def __init__(self, data_dir: Path, providers: dict[str, Provider], ttl_hours: float = 48):
        # percorso assoluto: i programmi esterni girano con una cartella di lavoro diversa
        self.dir = Path(data_dir).resolve() / "jobs"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.providers = providers
        self.ttl = ttl_hours * 3600
        self._jobs: dict[str, Job] = {}
        self._cancel: set[str] = set()
        self._lock = threading.RLock()
        self._queue: queue.Queue[str] = queue.Queue()
        self._order: list[str] = []
        self._load()
        self._worker = threading.Thread(target=self._loop, daemon=True, name="scan3d-worker")
        self._worker.start()

    # --- persistenza --------------------------------------------------------------
    def job_dir(self, job_id: str) -> Path:
        return self.dir / job_id

    def photos_dir(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "photos"

    def model_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "model.glb"

    def _save(self, job: Job) -> None:
        job.updated = time.time()
        p = self.job_dir(job.id) / "job.json"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(job)), encoding="utf-8")
        # Su Windows la sostituzione fallisce se un altro processo (tipicamente l'antivirus che
        # scansiona il file appena scritto) lo tiene aperto per un istante: riprovo.
        for attempt in range(20):
            try:
                tmp.replace(p)
                return
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.05)

    def _load(self) -> None:
        now = time.time()
        for f in self.dir.glob("*/job.json"):
            try:
                job = Job(**json.loads(f.read_text(encoding="utf-8")))
            except (ValueError, TypeError):
                continue
            if now - job.updated > self.ttl:  # pulizia dei job vecchi
                shutil.rmtree(f.parent, ignore_errors=True)
                continue
            if job.status in ("queued", "running"):
                job.status, job.error = "error", "Il server è stato riavviato durante l'elaborazione. Riprova."
                self._save(job)
            self._jobs[job.id] = job

    # --- API ----------------------------------------------------------------------
    def create(self, provider: str, name: str) -> Job:
        if provider not in self.providers:
            raise KeyError(provider)
        job = Job(id=uuid.uuid4().hex[:16], provider=provider, name=name.strip()[:80] or "Scansione")
        self.photos_dir(job.id).mkdir(parents=True)
        with self._lock:
            self._jobs[job.id] = job
            self._save(job)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status == "queued":
                job.queue_position = self._order.index(job_id) + 1 if job_id in self._order else 0
            return job

    def add_photo(self, job: Job) -> int:
        with self._lock:
            job.photos = len(list(self.photos_dir(job.id).glob("*.jpg")))
            job.step = f"{job.photos} foto ricevute"
            self._save(job)
            return job.photos

    def start(self, job: Job) -> Job:
        prov = self.providers[job.provider]
        if job.status != "uploading":
            raise ValueError("Il job è già stato avviato.")
        if job.photos < prov.min_photos:
            raise ValueError(f"Servono almeno {prov.min_photos} foto per “{prov.label}” (ne hai {job.photos}).")
        ok, why = prov.available()
        if not ok:
            raise ValueError(why)
        with self._lock:
            job.status, job.step, job.progress = "queued", "In coda", 0
            self._order.append(job.id)
            self._save(job)
        self._queue.put(job.id)
        return job

    def delete(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status in ("queued", "running"):
                self._cancel.add(job_id)  # il worker si ferma al prossimo controllo
            self._jobs.pop(job_id, None)
            if job_id in self._order:
                self._order.remove(job_id)
        if not job or job.status != "running":
            shutil.rmtree(self.job_dir(job_id), ignore_errors=True)

    # --- worker -------------------------------------------------------------------
    def _loop(self) -> None:
        while True:
            job_id = self._queue.get()
            with self._lock:
                if job_id in self._order:
                    self._order.remove(job_id)
                job = self._jobs.get(job_id)
            if not job or job_id in self._cancel:
                shutil.rmtree(self.job_dir(job_id), ignore_errors=True)
                self._cancel.discard(job_id)
                continue
            self._run(job)

    def _run(self, job: Job) -> None:
        prov = self.providers[job.provider]
        work = self.job_dir(job.id) / "work"
        work.mkdir(exist_ok=True)

        def report(pct: float, step: str):
            with self._lock:
                job.progress, job.step = round(pct, 1), step
                if time.time() - job.updated > 1.0:
                    self._save(job)

        ctx = RunContext(work_dir=work, report_progress=report,
                         is_cancelled=lambda: job.id in self._cancel, log_file=work / "pipeline.log")
        with self._lock:
            job.status, job.started = "running", time.time()
            self._save(job)
        try:
            photos = sorted(self.photos_dir(job.id).glob("*.jpg"))
            mesh, steps = prov.reconstruct(photos, ctx)
            ctx.progress(97, "Preparazione dell'anteprima")
            mesh.export(self.model_path(job.id))
            with self._lock:
                job.report, job.cleanup = printability(mesh), steps
                job.status, job.progress, job.step = "done", 100, "Completato"
        except JobCancelled:
            job.status, job.step = "cancelled", "Annullato"
        except ProviderError as e:
            job.status, job.error = "error", str(e)
        except (ImportError, OSError) as e:
            # tipicamente una libreria di sistema mancante sul server: il dettaglio serve a chi lo ripara
            (work / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            job.status, job.error = "error", (f"Il server non è configurato del tutto: {describe_import_error(e)}. "
                                              "Nel Codespace esegui: npm run doctor")
        except Exception as e:  # noqa: BLE001 - qualunque errore imprevisto va mostrato, non deve uccidere il worker
            (work / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            job.status, job.error = "error", f"Errore imprevisto durante l'elaborazione ({type(e).__name__}: {str(e)[:160]})."
        finally:
            job.finished = time.time()
            if job.id in self._cancel:
                self._cancel.discard(job.id)
                shutil.rmtree(self.job_dir(job.id), ignore_errors=True)
            else:
                with self._lock:
                    self._save(job)
                # le foto e i file intermedi non servono più (spazio disco), il log resta
                if job.status == "done":
                    shutil.rmtree(self.photos_dir(job.id), ignore_errors=True)
                    for p in work.iterdir():
                        if p.name != "pipeline.log":
                            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
