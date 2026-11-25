import unittest
from datetime import datetime, timedelta, timezone

import sync_status_service


class FakeSnapshot:
    def __init__(self, doc_id, data, reference=None):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        self.reference = reference or FakeDocRef({}, "", doc_id)

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


def _deep_merge(base, patch):
    result = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class FakeDocRef:
    def __init__(self, store, collection, doc_id):
        self._store = store
        self._collection = collection
        self.id = doc_id

    def set(self, payload, merge=False):
        documents = self._store.setdefault(self._collection, {})
        if merge:
            documents[self.id] = _deep_merge(documents.get(self.id, {}), payload)
        else:
            documents[self.id] = dict(payload)

    def get(self):
        return FakeSnapshot(self.id, self._store.get(self._collection, {}).get(self.id))

    def delete(self):
        self._store.get(self._collection, {}).pop(self.id, None)


class FakeQuery:
    def __init__(self, store, collection, field=None, descending=False, limit=None):
        self._store = store
        self._collection = collection
        self._field = field
        self._descending = descending
        self._limit = limit

    def order_by(self, field, direction=None):
        return FakeQuery(
            self._store,
            self._collection,
            field=field,
            descending=str(direction or "").upper().endswith("DESCENDING"),
            limit=self._limit,
        )

    def limit(self, count):
        return FakeQuery(
            self._store,
            self._collection,
            field=self._field,
            descending=self._descending,
            limit=count,
        )

    def stream(self):
        documents = list(self._store.get(self._collection, {}).items())
        if self._field:
            documents.sort(
                key=lambda item: item[1].get(self._field) or datetime.min,
                reverse=self._descending,
            )
        if self._limit is not None:
            documents = documents[: self._limit]
        return [
            FakeSnapshot(
                doc_id,
                data,
                reference=FakeDocRef(self._store, self._collection, doc_id),
            )
            for doc_id, data in documents
        ]


class FakeCollection:
    def __init__(self, store, name):
        self._store = store
        self._name = name

    def document(self, doc_id):
        return FakeDocRef(self._store, self._name, doc_id)

    def order_by(self, field, direction=None):
        return FakeQuery(self._store, self._name).order_by(field, direction)

    def stream(self):
        return FakeQuery(self._store, self._name).stream()


class FakeFirestore:
    def __init__(self):
        self.store: dict[str, dict[str, dict]] = {}

    def collection(self, name):
        return FakeCollection(self.store, name)

    def documents(self, name):
        return self.store.get(name, {})


class FailingFirestore:
    def collection(self, name):
        raise RuntimeError("firestore is unavailable")


class SyncReporterTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeFirestore()
        self.moment = datetime(2026, 11, 24, 11, 15, tzinfo=timezone.utc)
        self.elapsed = [0.0]
        self.updates = []
        self.reporter = sync_status_service.SyncReporter(
            self.db,
            trigger="manual",
            app_version="1.3.7",
            host="GASERVER",
            database="BusyComp0004_db12025",
            on_update=self.updates.append,
            clock=lambda: self.elapsed[0],
            now=lambda: self.moment + timedelta(seconds=self.elapsed[0]),
            run_id="20261124T111500Z-abcd",
        )

    def status(self):
        self.reporter.flush()
        return self.db.documents("DB_Service")["sync_status"]

    def test_start_publishes_running_state_to_both_documents(self):
        run_id = self.reporter.start()

        self.assertEqual(run_id, "20261124T111500Z-abcd")
        status = self.status()
        self.assertEqual(status["state"], "running")
        self.assertEqual(status["schemaVersion"], 2)
        self.assertEqual(status["kind"], "price_list")
        self.assertEqual(status["kindLabel"], "Price List")
        self.assertEqual(status["trigger"], "manual")
        self.assertEqual(status["database"], "BusyComp0004_db12025")
        self.assertEqual(
            status["counts"],
            {"items": 0, "images": 0, "deleted": 0, "added": 0},
        )
        self.assertEqual(
            status["countLabels"],
            {
                "items": "Items",
                "images": "Images",
                "deleted": "Deleted",
                "added": "Added",
            },
        )
        self.assertIsNone(status["progress"])
        self.assertEqual(
            self.db.documents("sync_runs")["20261124T111500Z-abcd"]["state"],
            "running",
        )
        self.assertEqual(len(self.updates), 1)

    def test_stage_changes_always_write(self):
        self.reporter.start()

        self.reporter.stage("Reading current stock", 2, 12)
        self.reporter.stage("Uploading items", 7, 12)

        status = self.status()
        self.assertEqual(status["stage"], "Uploading items")
        self.assertEqual(status["stageIndex"], 7)
        self.assertEqual(status["stageTotal"], 12)
        self.assertEqual(len(self.updates), 3)

    def test_progress_is_throttled_between_writes(self):
        self.reporter.start()

        for index in range(1, 51):
            self.elapsed[0] = index * 0.005
            self.reporter.progress(index, 50)

        # Only the "running" payload from start() reached Firestore.
        self.assertIsNone(self.status()["progress"])

    def test_listener_updates_faster_than_firestore_writes(self):
        self.reporter.start()
        updates_after_start = len(self.updates)

        self.elapsed[0] = 0.6
        self.reporter.progress(5, 50)
        self.assertEqual(len(self.updates), updates_after_start + 1)
        self.assertEqual(self.updates[-1]["progress"], {"done": 5, "total": 50})

        self.elapsed[0] = 0.8
        self.reporter.progress(6, 50)
        self.assertEqual(
            len(self.updates),
            updates_after_start + 1,
            "listener updates should respect their own interval",
        )

        self.elapsed[0] = 2.5
        self.reporter.progress(7, 50)
        self.assertEqual(self.status()["progress"], {"done": 7, "total": 50})

    def test_progress_writes_again_after_the_throttle_window(self):
        self.reporter.start()

        self.elapsed[0] = 5.0
        self.reporter.progress(10, 50)
        first = self.status()["progress"]
        self.elapsed[0] = 10.0
        self.reporter.progress(40, 50)

        self.assertEqual(first, {"done": 10, "total": 50})
        self.assertEqual(self.status()["progress"], {"done": 40, "total": 50})

    def test_counts_are_recorded(self):
        self.reporter.start()

        self.elapsed[0] = 3.0
        self.reporter.count("items", 12)
        self.elapsed[0] = 6.0
        self.reporter.count("images", 2)

        self.assertEqual(self.status()["counts"]["items"], 12)
        self.assertEqual(self.status()["counts"]["images"], 2)

    def test_finish_records_terminal_state_and_duration(self):
        self.reporter.start()
        self.elapsed[0] = 42.4

        self.reporter.finish(sync_status_service.SUCCESS)

        status = self.status()
        self.assertEqual(status["state"], "success")
        self.assertIsNone(status["error"])
        self.assertIsNotNone(status["finishedAt"])
        self.assertEqual(status["durationSeconds"], 42.4)
        self.assertEqual(
            self.db.documents("sync_runs")["20261124T111500Z-abcd"]["state"],
            "success",
        )

    def test_finish_records_failure_message(self):
        self.reporter.start()

        self.reporter.finish(sync_status_service.FAILED, RuntimeError("SQL is down"))

        status = self.status()
        self.assertEqual(status["state"], "failed")
        self.assertEqual(status["error"], "SQL is down")

    def test_finish_rejects_non_terminal_state(self):
        self.reporter.start()

        with self.assertRaises(ValueError):
            self.reporter.finish(sync_status_service.RUNNING)

    def test_writes_before_start_are_ignored(self):
        self.reporter.progress(1, 2)
        self.reporter.stage("Uploading items", 1, 2)
        self.reporter.count("items", 5)

        self.assertEqual(self.db.store, {})

    def test_firestore_failures_never_raise(self):
        reporter = sync_status_service.SyncReporter(
            FailingFirestore(),
            run_id="20261124T111500Z-abcd",
        )

        reporter.start()
        reporter.progress(1, 2)
        reporter.finish(sync_status_service.SUCCESS)

    def test_prune_history_keeps_newest_runs(self):
        base = datetime(2026, 11, 1, tzinfo=timezone.utc)
        for index in range(6):
            sync_status_service.SyncReporter(
                self.db,
                run_id=f"run-{index}",
                now=lambda index=index: base + timedelta(hours=index),
            ).start()

        deleted = sync_status_service.prune_history(self.db, keep=4)

        self.assertEqual(deleted, 2)
        remaining = set(self.db.documents("sync_runs"))
        self.assertEqual(remaining, {"run-2", "run-3", "run-4", "run-5"})


class MultiOperationTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeFirestore()
        self.base = datetime(2026, 11, 25, 9, 0, tzinfo=timezone.utc)

    def reporter(self, kind, run_id, minutes=0, **kwargs):
        return sync_status_service.SyncReporter(
            self.db,
            kind=kind,
            run_id=run_id,
            now=lambda: self.base + timedelta(minutes=minutes),
            **kwargs,
        )

    def status_doc(self):
        return self.db.documents("DB_Service")["sync_status"]

    def test_backup_run_only_updates_its_own_latest_entry(self):
        reporter = self.reporter(sync_status_service.KIND_SQL_BACKUP, "run-backup")
        reporter.start()
        reporter.stage("Backing up databases", 2, 3)
        reporter.progress(1, 4)
        reporter.count("databases", 1)
        reporter.finish(sync_status_service.SUCCESS)
        reporter.flush()

        doc = self.status_doc()
        self.assertNotIn("state", doc, "root fields stay owned by the price list")
        backup = doc["latest"]["sql_backup"]
        self.assertEqual(backup["state"], "success")
        self.assertEqual(backup["kindLabel"], "SQL Backups")
        self.assertEqual(backup["counts"]["databases"], 1)
        self.assertEqual(
            set(backup["countLabels"]), {"databases", "verified", "uploaded", "failed"}
        )

    def test_price_list_run_keeps_root_and_latest_in_sync(self):
        reporter = self.reporter(sync_status_service.KIND_PRICE_LIST, "run-price")
        reporter.start()
        reporter.finish(sync_status_service.SUCCESS)
        reporter.flush()

        doc = self.status_doc()
        self.assertEqual(doc["state"], "success")
        self.assertEqual(doc["latest"]["price_list"]["state"], "success")

    def test_each_kind_keeps_its_own_latest(self):
        price = self.reporter(sync_status_service.KIND_PRICE_LIST, "run-price", 0)
        price.start()
        price.finish(sync_status_service.SUCCESS)
        price.flush()

        backup = self.reporter(sync_status_service.KIND_SQL_BACKUP, "run-backup", 5)
        backup.start()
        backup.finish(sync_status_service.FAILED, RuntimeError("disk full"))
        backup.flush()

        attendance = self.reporter(sync_status_service.KIND_ATTENDANCE, "run-att", 10)
        attendance.start()
        attendance.count("employees", 12)
        attendance.finish(sync_status_service.SUCCESS)
        attendance.flush()

        doc = self.status_doc()
        self.assertEqual(doc["state"], "success", "root stays the price list")
        self.assertEqual(doc["latest"]["price_list"]["runId"], "run-price")
        self.assertEqual(doc["latest"]["sql_backup"]["state"], "failed")
        self.assertEqual(doc["latest"]["sql_backup"]["error"], "disk full")
        self.assertEqual(doc["latest"]["attendance"]["counts"]["employees"], 12)

    def test_read_latest_all_returns_every_kind(self):
        for kind, run_id, minutes in (
            (sync_status_service.KIND_PRICE_LIST, "r-price", 0),
            (sync_status_service.KIND_SQL_BACKUP, "r-backup", 3),
            (sync_status_service.KIND_ATTENDANCE, "r-att", 6),
        ):
            reporter = self.reporter(kind, run_id, minutes)
            reporter.start()
            reporter.finish(sync_status_service.SUCCESS)
            reporter.flush()

        latest = sync_status_service.read_latest_all(self.db)

        self.assertEqual(set(latest), set(sync_status_service.OPERATION_KINDS))
        self.assertEqual(latest["sql_backup"]["runId"], "r-backup")
        self.assertFalse(latest["attendance"]["stale"])
        self.assertEqual(
            sync_status_service.read_latest(self.db, sync_status_service.KIND_ATTENDANCE)[
                "runId"
            ],
            "r-att",
        )

    def test_read_latest_falls_back_to_root_fields(self):
        self.db.collection("DB_Service").document("sync_status").set(
            {
                "runId": "legacy",
                "state": "success",
                "startedAt": self.base,
                "heartbeatAt": self.base,
            }
        )

        latest = sync_status_service.read_latest_all(self.db)

        self.assertEqual(latest["price_list"]["runId"], "legacy")

    def test_history_filters_by_kind(self):
        for index in range(3):
            reporter = self.reporter(
                sync_status_service.KIND_SQL_BACKUP, f"backup-{index}", index
            )
            reporter.start()
            reporter.finish(sync_status_service.SUCCESS)
            reporter.flush()
        price = self.reporter(sync_status_service.KIND_PRICE_LIST, "price-0", 10)
        price.start()
        price.finish(sync_status_service.SUCCESS)
        price.flush()

        backups = sync_status_service.read_history(
            self.db, limit=5, kind=sync_status_service.KIND_SQL_BACKUP
        )
        everything = sync_status_service.read_history(self.db, limit=5)

        self.assertEqual([run["runId"] for run in backups], ["backup-2", "backup-1", "backup-0"])
        self.assertEqual(
            [run["runId"] for run in everything],
            ["price-0", "backup-2", "backup-1", "backup-0"],
        )

    def test_prune_keeps_the_newest_runs_of_each_kind(self):
        for index in range(4):
            for kind in sync_status_service.OPERATION_KINDS:
                reporter = self.reporter(kind, f"{kind}-{index}", index)
                reporter.start()
                reporter.finish(sync_status_service.SUCCESS)
                reporter.flush()

        deleted = sync_status_service.prune_history(self.db, keep=2)

        remaining = {
            document_id.rsplit("-", 1)[0]
            for document_id in self.db.documents("sync_runs")
        }
        self.assertEqual(deleted, 6)
        self.assertEqual(len(self.db.documents("sync_runs")), 6)
        for kind in sync_status_service.OPERATION_KINDS:
            kept = sorted(
                document_id
                for document_id in self.db.documents("sync_runs")
                if document_id.startswith(f"{kind}-")
            )
            self.assertEqual(kept, [f"{kind}-2", f"{kind}-3"])
        self.assertEqual(
            remaining, set(sync_status_service.OPERATION_KINDS)
        )


class SyncStatusReadTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeFirestore()
        self.base = datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)

    def seed(self, run_id, state, minutes):
        moment = self.base + timedelta(minutes=minutes)
        self.db.collection("sync_runs").document(run_id).set(
            {
                "runId": run_id,
                "state": state,
                "startedAt": moment,
                "heartbeatAt": moment,
            }
        )

    def test_read_history_returns_newest_first_with_iso_timestamps(self):
        self.seed("older", "success", 1)
        self.seed("newer", "failed", 5)

        history = sync_status_service.read_history(self.db, limit=10)

        self.assertEqual([item["runId"] for item in history], ["newer", "older"])
        self.assertIsInstance(history[0]["startedAt"], str)
        self.assertIn("2026-11-24T09:05:00", history[0]["startedAt"])

    def test_read_latest_returns_none_when_absent(self):
        self.assertIsNone(sync_status_service.read_latest(self.db))

    def test_read_latest_marks_stale_running_runs(self):
        moment = datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)
        self.db.collection("DB_Service").document("sync_status").set(
            {"runId": "r1", "state": "running", "startedAt": moment, "heartbeatAt": moment}
        )

        latest = sync_status_service.read_latest(self.db)

        self.assertTrue(latest["stale"])

    def test_is_stale_ignores_finished_runs(self):
        moment = datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)

        self.assertFalse(
            sync_status_service.is_stale(
                {"state": "success", "heartbeatAt": moment}, moment=moment
            )
        )
        self.assertTrue(
            sync_status_service.is_stale(
                {"state": "running", "heartbeatAt": moment},
                moment=moment + timedelta(minutes=10),
            )
        )


if __name__ == "__main__":
    unittest.main()
