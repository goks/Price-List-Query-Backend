import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import r2_service


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


if __name__ == "__main__":
    unittest.main()
