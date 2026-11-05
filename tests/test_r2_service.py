import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import r2_service


class FakeTransferFuture:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def result(self):
        if self.cancelled:
            raise r2_service.CancelledError()


class FakeTransferManager:
    def __init__(self):
        self.future = FakeTransferFuture()
        self.shutdown_args = None

    def upload(self, file_path, bucket, key, extra_args, subscribers):
        size = Path(file_path).stat().st_size
        for subscriber in subscribers:
            subscriber.on_progress(
                future=self.future,
                bytes_transferred=size,
            )
        return self.future

    def shutdown(self, cancel=False, cancel_msg=""):
        self.shutdown_args = (cancel, cancel_msg)


class FakePaginator:
    def __init__(self, client):
        self.client = client

    def paginate(self, Bucket):
        yield {"Contents": [dict(item) for item in self.client.objects]}


class FakeR2Client:
    def __init__(self, objects):
        self.objects = [dict(item) for item in objects]
        self.deleted_keys = []

    def get_paginator(self, _operation):
        return FakePaginator(self)

    def delete_objects(self, Bucket, Delete):
        keys = [item["Key"] for item in Delete["Objects"]]
        self.deleted_keys.extend(keys)
        self.objects = [
            item for item in self.objects if item["Key"] not in keys
        ]
        return {"Deleted": [{"Key": key} for key in keys]}

    def head_object(self, Bucket, Key):
        return {"ContentLength": 2048}


class R2UploadSessionTests(unittest.TestCase):
    settings = r2_service.R2Settings(
        account_id="a" * 32,
        bucket_name="backup-bucket",
        access_key_id="access-key",
        prefix="sql-backups",
    )

    def prepare_with_size(self, client, size):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "prepared.bak"
            path.write_bytes(b"x" * size)
            with patch.object(r2_service, "MAX_BUCKET_BYTES", 100):
                return r2_service.prepare_upload_session(
                    [str(path)],
                    self.settings,
                    "secret",
                    client_factory=lambda *_args, **_kwargs: client,
                )

    def test_purges_only_configured_prefix_when_bucket_needs_room(self):
        client = FakeR2Client(
            [
                {"Key": "sql-backups/old.bak", "Size": 60},
                {"Key": "sql-backups-archive/keep.bak", "Size": 5},
                {"Key": "unrelated/keep.bak", "Size": 5},
            ]
        )

        result = self.prepare_with_size(client, 40)

        self.assertEqual(result.upload_bytes, 40)
        self.assertEqual(result.initial_bucket_bytes, 70)
        self.assertEqual(result.remaining_bucket_bytes, 10)
        self.assertEqual(result.deleted_backup_objects, 1)
        self.assertEqual(client.deleted_keys, ["sql-backups/old.bak"])
        self.assertEqual(
            {item["Key"] for item in client.objects},
            {"sql-backups-archive/keep.bak", "unrelated/keep.bak"},
        )

    def test_cancels_when_prepared_session_is_not_below_limit(self):
        client = FakeR2Client([{"Key": "sql-backups/old.bak", "Size": 10}])

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "prepared.bak"
            path.write_bytes(b"x" * 100)
            with patch.object(r2_service, "MAX_BUCKET_BYTES", 100):
                with self.assertRaisesRegex(r2_service.R2Error, "session was canceled"):
                    r2_service.prepare_upload_session(
                        [str(path)],
                        self.settings,
                        "secret",
                        client_factory=lambda *_args, **_kwargs: client,
                    )

        self.assertEqual(client.deleted_keys, [])

    def test_keeps_existing_backups_if_unrelated_objects_leave_no_room(self):
        client = FakeR2Client(
            [
                {"Key": "sql-backups/old.bak", "Size": 10},
                {"Key": "unrelated/keep.bak", "Size": 70},
            ]
        )

        with self.assertRaisesRegex(r2_service.R2Error, "No existing cloud backups were deleted"):
            self.prepare_with_size(client, 30)

        self.assertEqual(client.deleted_keys, [])
        self.assertEqual(len(client.objects), 2)

    def test_does_not_clear_prefix_when_session_fits_current_bucket(self):
        client = FakeR2Client([{"Key": "sql-backups/old.bak", "Size": 10}])

        result = self.prepare_with_size(client, 20)

        self.assertEqual(result.deleted_backup_objects, 0)
        self.assertEqual(result.remaining_bucket_bytes, 10)
        self.assertEqual(client.deleted_keys, [])

    def test_upload_progress_reports_average_speed(self):
        client = FakeR2Client([])
        manager = FakeTransferManager()
        progress = []

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "prepared.bak"
            path.write_bytes(b"x" * 2048)
            with patch.object(
                r2_service,
                "create_transfer_manager",
                return_value=manager,
            ):
                r2_service.upload_backup(
                    str(path),
                    self.settings,
                    "secret",
                    company_code="0001",
                    financial_year="2026-2027",
                    progress_callback=lambda done, total, speed: progress.append(
                        (done, total, speed)
                    ),
                    client_factory=lambda *_args, **_kwargs: client,
                )

        self.assertGreaterEqual(len(progress), 1)
        self.assertEqual(progress[-1][:2], (2048, 2048))
        self.assertGreater(progress[-1][2], 0)

    def test_user_cancellation_cancels_transfer_and_preserves_backup(self):
        client = FakeR2Client([])
        manager = FakeTransferManager()
        cancel_event = r2_service.threading.Event()

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "prepared.bak"
            path.write_bytes(b"x" * 2048)
            with patch.object(
                r2_service,
                "create_transfer_manager",
                return_value=manager,
            ):
                with self.assertRaises(r2_service.R2UploadCancelled):
                    r2_service.upload_backup(
                        str(path),
                        self.settings,
                        "secret",
                        company_code="0001",
                        financial_year="2026-2027",
                        cancel_event=cancel_event,
                        transfer_future_callback=lambda future: (
                            cancel_event.set(),
                            future.cancel() if future is not None else None,
                        ),
                        client_factory=lambda *_args, **_kwargs: client,
                    )

            self.assertTrue(path.exists())

        self.assertEqual(
            manager.shutdown_args,
            (True, "Upload canceled by user."),
        )
        self.assertEqual(client.deleted_keys, [])


if __name__ == "__main__":
    unittest.main()
