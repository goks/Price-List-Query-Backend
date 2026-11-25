"""Publishes the progress of each background operation to Firestore.

Applies to every long-running operation the app performs:

* the price-list sync (``price_list``)
* SQL Server backups (``sql_backup``)
* the eTimeTrackLite attendance import (``attendance``)

Two documents are maintained so that both this desktop app and any other
consumer can follow along:

* ``DB_Service/sync_status`` - one document holding the latest run of every
  operation under ``latest.<kind>``. The document's top-level fields always
  describe the latest price-list sync, which keeps earlier consumers working.
* ``sync_runs/<runId>``      - one document per run, pruned to the last N per
  operation kind

Every write is best-effort: a Firestore problem must never abort an operation,
so failures are logged and swallowed. Because a single Firestore round trip can
take seconds on a slow link, writes happen on a background thread that
coalesces updates (latest state wins) instead of stalling the work itself.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

RUNNING = "running"
SUCCESS = "success"
FAILED = "failed"
CANCELLED = "cancelled"
TERMINAL_STATES = frozenset({SUCCESS, FAILED, CANCELLED})

KIND_PRICE_LIST = "price_list"
KIND_SQL_BACKUP = "sql_backup"
KIND_ATTENDANCE = "attendance"
OPERATION_KINDS = (KIND_PRICE_LIST, KIND_SQL_BACKUP, KIND_ATTENDANCE)
OPERATION_LABELS = {
    KIND_PRICE_LIST: "Price List",
    KIND_SQL_BACKUP: "SQL Backups",
    KIND_ATTENDANCE: "Attendance",
}
DEFAULT_COUNT_LABELS = {
    KIND_PRICE_LIST: {
        "items": "Items",
        "images": "Images",
        "deleted": "Deleted",
        "added": "Added",
    },
    KIND_SQL_BACKUP: {
        "databases": "Databases",
        "verified": "Verified",
        "uploaded": "Uploaded",
        "failed": "Failed",
    },
    KIND_ATTENDANCE: {
        "employees": "Employees",
        "attendance": "Attendance",
    },
}

SERVICE_COLLECTION = "DB_Service"
STATUS_DOCUMENT = "sync_status"
HISTORY_COLLECTION = "sync_runs"
LATEST_FIELD = "latest"

SCHEMA_VERSION = 2
DEFAULT_MIN_WRITE_INTERVAL = 2.0
DEFAULT_HISTORY_LIMIT = 50
STALE_AFTER_SECONDS = 300
NOTIFY_INTERVAL_SECONDS = 0.5

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_run_id(
    moment: Optional[datetime] = None,
    token: Optional[str] = None,
) -> str:
    stamp = (moment or utc_now()).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{token or secrets.token_hex(2)}"


def operation_label(kind: str) -> str:
    return OPERATION_LABELS.get(kind, kind.replace("_", " ").title() or "Operation")


def count_labels_for(kind: str, overrides: Optional[dict] = None) -> dict:
    labels = dict(DEFAULT_COUNT_LABELS.get(kind, {}))
    if overrides:
        labels.update(overrides)
    return labels


def _descending() -> Any:
    try:
        from google.cloud.firestore_v1 import Query
    except Exception:  # pragma: no cover - only when the SDK is unavailable
        return "DESCENDING"
    return Query.DESCENDING


class SyncReporter:
    """Records the progress of one sync run in Firestore.

    ``stage``, ``progress`` and ``count`` are cheap to call; writes are
    throttled to ``min_write_interval`` seconds while stage changes and the
    final state always write immediately.
    """

    def __init__(
        self,
        db,
        *,
        kind: str = KIND_PRICE_LIST,
        trigger: str = "manual",
        app_version: str = "",
        host: str = "",
        database: str = "",
        count_labels: Optional[dict] = None,
        on_update: Optional[Callable[[dict], None]] = None,
        min_write_interval: float = DEFAULT_MIN_WRITE_INTERVAL,
        history_limit: int = DEFAULT_HISTORY_LIMIT,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = utc_now,
        run_id: Optional[str] = None,
    ) -> None:
        self._db = db
        self._kind = kind
        self._trigger = trigger
        self._app_version = app_version
        self._host = host
        self._database = database
        self._count_labels = count_labels_for(kind, count_labels)
        self._on_update = on_update
        self._min_write_interval = min_write_interval
        self._history_limit = history_limit
        self._clock = clock
        self._now = now

        self._run_id: Optional[str] = run_id
        self._state = RUNNING
        self._stage: Optional[str] = None
        self._stage_index: Optional[int] = None
        self._stage_total: Optional[int] = None
        self._progress_done: Optional[int] = None
        self._progress_total: Optional[int] = None
        self._counts: dict[str, int] = {
            key: 0 for key in self._count_labels
        }
        self._started_at: Optional[datetime] = None
        self._finished_at: Optional[datetime] = None
        self._error: Optional[str] = None
        self._last_write_at = float("-inf")
        self._last_notify_at = float("-inf")
        self._write_failure: Optional[str] = None

        self._condition = threading.Condition()
        self._pending: Optional[dict] = None
        self._writing = False
        self._final = False
        self._writer: Optional[threading.Thread] = None

    @property
    def run_id(self) -> Optional[str]:
        return self._run_id

    @property
    def kind(self) -> str:
        return self._kind

    def _ready(self) -> bool:
        return self._started_at is not None and self._run_id is not None

    def start(self) -> str:
        self._started_at = self._now()
        if self._run_id is None:
            self._run_id = new_run_id(self._started_at)
        self._state = RUNNING
        self._write(force=True)
        return self._run_id

    def stage(
        self,
        name: str,
        index: Optional[int] = None,
        total: Optional[int] = None,
    ) -> None:
        if not self._ready():
            return
        self._stage = str(name)
        if index is not None:
            self._stage_index = int(index)
        if total is not None:
            self._stage_total = int(total)
        self._write(force=True)

    def progress(self, done: int, total: int) -> None:
        if not self._ready():
            return
        self._progress_done = int(done)
        self._progress_total = int(total)
        self._write()

    def count(self, key: str, value: Optional[int] = None) -> None:
        if not self._ready():
            return
        if value is None:
            self._counts[key] = self._counts.get(key, 0) + 1
        else:
            self._counts[key] = int(value)
        self._write()

    def finish(self, state: str, error: Optional[Any] = None) -> None:
        if state not in TERMINAL_STATES:
            raise ValueError(f"{state!r} is not a terminal sync state.")
        if not self._ready():
            return
        self._state = state
        self._error = None if state == SUCCESS else (str(error) if error else None)
        self._finished_at = self._now()
        self._write(force=True)
        with self._condition:
            self._final = True
            self._condition.notify_all()

    def snapshot(self) -> dict[str, Any]:
        duration = None
        if self._started_at is not None and self._finished_at is not None:
            duration = round(
                (self._finished_at - self._started_at).total_seconds(), 1
            )
        progress = None
        if self._progress_total is not None:
            progress = {
                "done": self._progress_done or 0,
                "total": self._progress_total,
            }
        return {
            "schemaVersion": SCHEMA_VERSION,
            "runId": self._run_id,
            "kind": self._kind,
            "kindLabel": operation_label(self._kind),
            "state": self._state,
            "trigger": self._trigger,
            "stage": self._stage,
            "stageIndex": self._stage_index,
            "stageTotal": self._stage_total,
            "progress": progress,
            "counts": dict(self._counts),
            "countLabels": dict(self._count_labels),
            "startedAt": self._started_at,
            "finishedAt": self._finished_at,
            "heartbeatAt": self._now(),
            "durationSeconds": duration,
            "error": self._error,
            "host": self._host,
            "database": self._database,
            "appVersion": self._app_version,
        }

    def _write(self, force: bool = False) -> None:
        if not self._ready() or self._final:
            return
        moment = self._clock()
        if not force and moment - self._last_write_at < self._min_write_interval:
            self._notify_if_due(moment)
            return
        self._last_write_at = moment
        payload = self.snapshot()
        self._queue_write(payload)
        self._notify(payload, moment)

    def _notify_if_due(self, moment: float) -> None:
        """Keeps in-app updates smooth while Firestore writes stay throttled."""
        if moment - self._last_notify_at < NOTIFY_INTERVAL_SECONDS:
            return
        self._notify(self.snapshot(), moment)

    def _notify(self, payload: dict, moment: float) -> None:
        self._last_notify_at = moment
        if self._on_update is None:
            return
        try:
            self._on_update(payload)
        except Exception:  # pragma: no cover - a broken listener must not matter
            logger.exception("Sync status listener failed.")

    def _queue_write(self, payload: dict) -> None:
        with self._condition:
            self._pending = payload
            self._condition.notify_all()
        self._ensure_writer()

    def _ensure_writer(self) -> None:
        if self._writer is not None:
            return
        self._writer = threading.Thread(
            target=self._writer_loop,
            name="sync-status-writer",
            daemon=True,
        )
        self._writer.start()

    def _writer_loop(self) -> None:
        while True:
            with self._condition:
                while self._pending is None and not self._final:
                    self._condition.wait()
                if self._pending is None and self._final:
                    break
                payload = self._pending
                self._pending = None
                self._writing = True
            try:
                self._publish(payload)
            except Exception:  # pragma: no cover - the writer must never die
                logger.exception("Unexpected error while publishing sync status.")
            finally:
                with self._condition:
                    self._writing = False
                    self._condition.notify_all()
        prune_history(self._db, keep=self._history_limit)

    def _publish(self, payload: dict) -> None:
        failures = 0
        writes = [(HISTORY_COLLECTION, self._run_id, payload, False)]
        if self._kind == KIND_PRICE_LIST:
            # Earlier consumers read these fields at the document root, so the
            # latest price-list run stays there as well as in latest.<kind>.
            document = dict(payload)
            document[LATEST_FIELD] = {self._kind: payload}
            writes.append((SERVICE_COLLECTION, STATUS_DOCUMENT, document, True))
        else:
            writes.append(
                (
                    SERVICE_COLLECTION,
                    STATUS_DOCUMENT,
                    {LATEST_FIELD: {self._kind: payload}},
                    True,
                )
            )
        for collection, document_id, data, merge in writes:
            try:
                try:
                    self._db.collection(collection).document(document_id).set(
                        data,
                        merge=merge,
                    )
                except TypeError:
                    # Test doubles may not accept the merge keyword.
                    self._db.collection(collection).document(document_id).set(data)
            except Exception as exc:  # pragma: no cover - depends on the network
                failures += 1
                self._note_write_failure(exc)
        if not failures:
            self._clear_write_failure()

    def flush(self, timeout: float = 15.0) -> bool:
        """Waits until every queued update has been written to Firestore."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._condition:
                if self._pending is None and not self._writing:
                    return True
            time.sleep(0.02)
        return False

    def _note_write_failure(self, exc: Exception) -> None:
        message = str(exc)
        if self._write_failure is None:
            logger.warning("Could not publish sync status to Firestore: %s", message)
        self._write_failure = message

    def _clear_write_failure(self) -> None:
        if self._write_failure is not None:
            logger.info("Sync status publishing recovered.")
            self._write_failure = None


def prune_history(db, keep: int = DEFAULT_HISTORY_LIMIT) -> int:
    """Deletes all but the newest ``keep`` runs of each operation kind.

    Returns the number of documents deleted. The newest
    ``keep * len(OPERATION_KINDS) + 20`` runs are read so that a single fetch
    covers every kind without needing a composite index.
    """
    if keep < 0:
        return 0
    fetch_limit = keep * len(OPERATION_KINDS) + 20
    try:
        runs = list(
            db.collection(HISTORY_COLLECTION)
            .order_by("startedAt", direction=_descending())
            .limit(fetch_limit)
            .stream()
        )
    except Exception as exc:  # pragma: no cover - depends on the network
        logger.warning("Could not read sync history for pruning: %s", exc)
        return 0

    by_kind: dict[str, list] = {}
    for document in runs:
        data = document.to_dict() or {}
        by_kind.setdefault(str(data.get("kind") or KIND_PRICE_LIST), []).append(
            document
        )

    deleted = 0
    for documents in by_kind.values():
        for document in documents[keep:]:
            try:
                document.reference.delete()
                deleted += 1
            except Exception as exc:  # pragma: no cover - depends on the network
                logger.warning("Could not prune sync run %s: %s", document.id, exc)
    return deleted


def read_latest_all(db) -> dict[str, dict]:
    """Returns the latest run of every operation kind, keyed by kind."""
    try:
        snapshot = (
            db.collection(SERVICE_COLLECTION).document(STATUS_DOCUMENT).get()
        )
    except Exception as exc:  # pragma: no cover - depends on the network
        logger.warning("Could not read the latest sync status: %s", exc)
        return {}
    if not snapshot.exists:
        return {}

    data = snapshot.to_dict() or {}
    latest = data.get(LATEST_FIELD) or {}
    result = {
        str(kind): _normalize(payload)
        for kind, payload in latest.items()
        if isinstance(payload, dict)
    }
    if KIND_PRICE_LIST not in result and data.get("runId"):
        # Document written before per-kind statuses were introduced.
        root = {key: value for key, value in data.items() if key != LATEST_FIELD}
        result[KIND_PRICE_LIST] = _normalize(root)
    return result


def read_latest(db, kind: str = KIND_PRICE_LIST) -> Optional[dict]:
    return read_latest_all(db).get(kind)


def read_history(
    db,
    limit: int = 10,
    kind: Optional[str] = None,
) -> list[dict]:
    """Returns the newest runs, filtered to ``kind`` when one is given."""
    fetch_limit = limit if kind is None else max(limit * len(OPERATION_KINDS), limit)
    try:
        documents = list(
            db.collection(HISTORY_COLLECTION)
            .order_by("startedAt", direction=_descending())
            .limit(fetch_limit)
            .stream()
        )
    except Exception as exc:  # pragma: no cover - depends on the network
        logger.warning("Could not read sync history: %s", exc)
        return []
    runs = [_normalize(document.to_dict() or {}) for document in documents]
    if kind is not None:
        runs = [
            run
            for run in runs
            if str(run.get("kind") or KIND_PRICE_LIST) == kind
        ]
    return runs[:limit]


def is_stale(payload: dict, moment: Optional[datetime] = None) -> bool:
    """True when a run still says "running" but its heartbeat stopped."""
    if payload.get("state") != RUNNING:
        return False
    heartbeat = _as_datetime(payload.get("heartbeatAt") or payload.get("startedAt"))
    if heartbeat is None:
        return True
    now = (moment or utc_now()).astimezone(timezone.utc)
    return (now - heartbeat).total_seconds() > STALE_AFTER_SECONDS


def _as_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _normalize(data: dict) -> dict:
    result = dict(data)
    for key in ("startedAt", "finishedAt", "heartbeatAt"):
        value = _as_datetime(result.get(key))
        if value is not None:
            result[key] = value.isoformat()
    result["stale"] = is_stale(result)
    return result
