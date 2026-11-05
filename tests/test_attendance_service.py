import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import attendance_service


class FakeDocumentSnapshot:
    def __init__(self, value, document_id=None):
        self.value = value
        self.id = document_id
        self.exists = value is not None

    def to_dict(self):
        return dict(self.value) if self.value is not None else None


class FakeDocumentReference:
    def __init__(self, collection, document_id):
        self.collection = collection
        self.document_id = document_id

    def get(self):
        return FakeDocumentSnapshot(
            self.collection.documents.get(self.document_id),
            self.document_id,
        )

    def set(self, value, merge=False):
        if merge:
            current = self.collection.documents.get(self.document_id, {})
            self.collection.documents[self.document_id] = {**current, **value}
        else:
            self.collection.documents[self.document_id] = dict(value)


class FakeCollection:
    def __init__(self):
        self.documents = {}

    def document(self, document_id):
        return FakeDocumentReference(self, document_id)


class FakeBatch:
    def __init__(self):
        self.writes = []

    def set(self, reference, value, merge=False):
        self.writes.append((reference, value, merge))

    def commit(self):
        for reference, value, merge in self.writes:
            reference.set(value, merge=merge)


class FakeFirestore:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]

    def batch(self):
        return FakeBatch()

    def get_all(self, references):
        return [
            reference.get()
            for reference in references
        ]


class AttendanceServiceTests(unittest.TestCase):
    def test_fixed_schedule_next_run_boundaries(self):
        test_cases = (
            (datetime(2026, 11, 5, 7, 59), datetime(2026, 11, 5, 8, 0)),
            (datetime(2026, 11, 5, 8, 0), datetime(2026, 11, 5, 8, 10)),
            (datetime(2026, 11, 5, 8, 1), datetime(2026, 11, 5, 8, 10)),
            (datetime(2026, 11, 5, 10, 55), datetime(2026, 11, 5, 11, 0)),
            (datetime(2026, 11, 5, 11, 0), datetime(2026, 11, 5, 12, 0)),
            (datetime(2026, 11, 5, 14, 35), datetime(2026, 11, 5, 15, 0)),
            (datetime(2026, 11, 5, 23, 35), datetime(2026, 11, 6, 0, 0)),
        )
        for current, expected in test_cases:
            with self.subTest(current=current):
                self.assertEqual(
                    attendance_service.next_scheduled_import(current),
                    expected,
                )

    def test_device_settings_validation(self):
        attendance_service.validate_device_settings(
            attendance_service.DeviceSettings("192.168.10.102", 4370)
        )
        with self.assertRaises(attendance_service.AttendanceError):
            attendance_service.validate_device_settings(
                attendance_service.DeviceSettings("not an ip!", 4370)
            )
        with self.assertRaises(attendance_service.AttendanceError):
            attendance_service.validate_device_settings(
                attendance_service.DeviceSettings("192.168.10.102", 70000)
            )

    def test_snapshot_reads_supported_records_and_disconnects(self):
        local_time = datetime.now().replace(microsecond=0)

        class FakeConnection:
            disconnected = False

            def get_device_name(self):
                return "K90 Pro"

            def get_serialnumber(self):
                return "serial-01"

            def get_firmware_version(self):
                return "1.0"

            def get_platform(self):
                return "ZK"

            def get_mac(self):
                return "00:11:22:33:44:55"

            def get_users(self):
                return [
                    SimpleNamespace(
                        uid=1,
                        user_id="EMP001",
                        name="Example Employee",
                        privilege=0,
                        group_id="",
                        card=123,
                        password="must-not-upload",
                    )
                ]

            def get_attendance(self):
                return [
                    SimpleNamespace(
                        uid=5,
                        user_id="EMP001",
                        timestamp=local_time,
                        status=0,
                        punch=0,
                    ),
                    SimpleNamespace(
                        uid=6,
                        user_id="EMP001",
                        timestamp=datetime.now() + timedelta(days=365 * 93),
                        status=0,
                        punch=0,
                    ),
                    SimpleNamespace(
                        uid=7,
                        user_id="EMP001",
                        timestamp=datetime.now() - timedelta(days=366),
                        status=0,
                        punch=0,
                    ),
                ]

            def disconnect(self):
                self.disconnected = True

        connection = FakeConnection()
        factory_calls = {}

        class FakeDevice:
            def connect(self):
                return connection

        def fake_factory(host, **kwargs):
            factory_calls["host"] = host
            factory_calls.update(kwargs)
            return FakeDevice()

        snapshot = attendance_service.read_device_snapshot(
            attendance_service.DeviceSettings("192.168.10.102", 4370),
            "123456",
            zk_factory=fake_factory,
        )

        self.assertEqual(factory_calls["host"], "192.168.10.102")
        self.assertEqual(factory_calls["password"], 123456)
        self.assertEqual(snapshot.device["serial_number"], "serial-01")
        self.assertEqual(snapshot.employees[0]["employee_id"], "EMP001")
        self.assertNotIn("password", snapshot.employees[0])
        self.assertEqual(len(snapshot.attendance), 1)
        self.assertEqual(snapshot.attendance[0]["employee_id"], "EMP001")
        self.assertTrue(any("Ignored 2 attendance record(s)" in warning for warning in snapshot.warnings))
        self.assertTrue(connection.disconnected)

    def test_import_uses_dedicated_collections_and_is_idempotent(self):
        firestore_db = FakeFirestore()
        progress = []
        snapshot = attendance_service.DeviceSnapshot(
            device={
                "device_id": attendance_service.device_document_id("serial-01"),
                "serial_number": "serial-01",
                "host": "192.168.10.102",
                "port": 4370,
            },
            employees=[
                {
                    "employee_id": "EMP001",
                    "uid": 1,
                    "name": "Example Employee",
                }
            ],
            attendance=[
                {
                    "employee_id": "EMP001",
                    "uid": 5,
                    "punch_time": datetime(2026, 11, 2, 9, 15, tzinfo=timezone.utc),
                    "punch_time_local": "2026-11-02T09:15:00+00:00",
                    "status": 0,
                    "punch": 0,
                }
            ],
            warnings=[],
        )

        counts = attendance_service.upload_snapshot(
            snapshot,
            firestore_db,
            progress_callback=lambda done, total, stage: progress.append(
                (done, total, stage)
            ),
        )
        second_counts = attendance_service.upload_snapshot(snapshot, firestore_db)

        self.assertEqual(counts, {"employees": 1, "attendance": 1})
        self.assertEqual(second_counts, {"employees": 1, "attendance": 0})
        self.assertIn(
            (1, 1, "Saving employee records to Firestore"),
            progress,
        )
        self.assertIn(
            (1, 1, "Checking and saving new attendance records"),
            progress,
        )
        self.assertEqual(
            len(firestore_db.collection("attendance_devices").documents),
            1,
        )
        self.assertEqual(
            len(firestore_db.collection("attendance_employees").documents),
            1,
        )
        self.assertEqual(
            len(firestore_db.collection("attendance_logs").documents),
            1,
        )
        self.assertEqual(
            len(firestore_db.collection("attendance_sync_state").documents),
            1,
        )

    def test_incremental_import_keeps_one_day_overlap(self):
        firestore_db = FakeFirestore()
        device_id = attendance_service.device_document_id("serial-02")
        now = datetime.now(timezone.utc)
        state = firestore_db.collection("attendance_sync_state")
        state.document(device_id).set(
            {
                "last_attendance_at": now - timedelta(hours=1)
            }
        )
        records = []
        for hours_ago in (72, 12, 1):
            punch_time = now - timedelta(hours=hours_ago)
            records.append(
                {
                    "employee_id": "EMP001",
                    "uid": hours_ago,
                    "punch_time": punch_time,
                    "punch_time_local": punch_time.isoformat(),
                    "status": 0,
                    "punch": 0,
                }
            )
        snapshot = attendance_service.DeviceSnapshot(
            device={"device_id": device_id},
            employees=[],
            attendance=records,
            warnings=[],
        )

        counts = attendance_service.upload_snapshot(snapshot, firestore_db)

        self.assertEqual(counts["attendance"], 2)

    def test_invalid_attendance_dates_do_not_poison_sync_checkpoint(self):
        firestore_db = FakeFirestore()
        device_id = attendance_service.device_document_id("serial-03")
        firestore_db.collection("attendance_sync_state").document(device_id).set(
            {"last_attendance_at": datetime(2119, 1, 1, tzinfo=timezone.utc)}
        )
        now = datetime.now(timezone.utc)
        recent_punch = now - timedelta(hours=1)
        snapshot = attendance_service.DeviceSnapshot(
            device={"device_id": device_id},
            employees=[],
            attendance=[
                {
                    "employee_id": "EMP001",
                    "uid": 1,
                    "punch_time": recent_punch,
                    "punch_time_local": recent_punch.isoformat(),
                    "status": 0,
                    "punch": 0,
                },
                {
                    "employee_id": "EMP001",
                    "uid": 2,
                    "punch_time": now - timedelta(days=366),
                    "punch_time_local": (now - timedelta(days=366)).isoformat(),
                    "status": 0,
                    "punch": 0,
                },
                {
                    "employee_id": "EMP001",
                    "uid": 3,
                    "punch_time": datetime(2119, 1, 1, tzinfo=timezone.utc),
                    "punch_time_local": "2119-01-01T00:00:00+00:00",
                    "status": 0,
                    "punch": 0,
                },
            ],
            warnings=[],
        )

        counts = attendance_service.upload_snapshot(snapshot, firestore_db)

        self.assertEqual(counts["attendance"], 1)
        self.assertEqual(
            len(firestore_db.collection("attendance_logs").documents),
            1,
        )
        checkpoint = firestore_db.collection("attendance_sync_state").documents[device_id][
            "last_attendance_at"
        ]
        self.assertEqual(checkpoint, recent_punch)

    def test_communication_key_is_stored_in_keyring(self):
        keyring = SimpleNamespace(values={})

        class FakeWindowsKeyring:
            pass

        class FakeBackend(FakeWindowsKeyring):
            def set_password(self, service, username, password):
                keyring.values[(service, username)] = password

            def get_password(self, service, username):
                return keyring.values.get((service, username))

        with patch.object(attendance_service, "WinVaultKeyring", FakeWindowsKeyring), patch.object(
            attendance_service,
            "_windows_keyring",
            return_value=FakeBackend(),
        ):
            attendance_service.save_communication_key(
                "192.168.10.102",
                "000123",
            )
            self.assertEqual(
                attendance_service.get_communication_key("192.168.10.102"),
                "123",
            )
            self.assertTrue(
                attendance_service.has_communication_key("192.168.10.102")
            )


if __name__ == "__main__":
    unittest.main()
