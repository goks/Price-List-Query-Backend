import hashlib
import ipaddress
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import keyring
from keyring.backends.Windows import WinVaultKeyring


KEYRING_SERVICE = "GA Price Uploader eTimeTrackLite"
ATTENDANCE_OVERLAP = timedelta(days=1)
FIRESTORE_BATCH_SIZE = 400


class AttendanceError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeviceSettings:
    host: str
    port: int = 4370
    timeout: int = 10


@dataclass(frozen=True)
class DeviceSnapshot:
    device: dict[str, Any]
    employees: list[dict[str, Any]]
    attendance: list[dict[str, Any]]
    warnings: list[str]


def validate_device_settings(settings: DeviceSettings) -> None:
    host = settings.host.strip()
    if not host or len(host) > 253:
        raise AttendanceError("Enter the attendance machine's IP address or host name.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host):
            raise AttendanceError("Enter a valid attendance machine IP address or host name.")
    if not 1 <= settings.port <= 65535:
        raise AttendanceError("The machine TCP port must be between 1 and 65535.")


def _windows_keyring():
    backend = keyring.get_keyring()
    if not isinstance(backend, WinVaultKeyring):
        raise AttendanceError(
            "Windows Credential Manager is unavailable; the communication key was not saved."
        )
    return backend


def save_communication_key(host: str, communication_key: str) -> None:
    cleaned_host = host.strip().lower()
    if not cleaned_host:
        raise AttendanceError("Save the machine IP address before saving its communication key.")
    if not communication_key:
        raise AttendanceError("Enter the device communication key.")
    try:
        key_value = int(communication_key)
    except ValueError as exc:
        raise AttendanceError("The device communication key must be numeric.") from exc
    if key_value < 0:
        raise AttendanceError("The device communication key cannot be negative.")
    try:
        _windows_keyring().set_password(
            KEYRING_SERVICE,
            cleaned_host,
            str(key_value),
        )
    except AttendanceError:
        raise
    except Exception as exc:
        raise AttendanceError(
            f"Could not save the communication key in Windows Credential Manager: {exc}"
        ) from exc


def get_communication_key(host: str) -> str:
    cleaned_host = host.strip().lower()
    if not cleaned_host:
        return "0"
    try:
        key = _windows_keyring().get_password(KEYRING_SERVICE, cleaned_host)
    except AttendanceError:
        raise
    except Exception as exc:
        raise AttendanceError(
            f"Could not read the communication key from Windows Credential Manager: {exc}"
        ) from exc
    return key if key is not None else "0"


def has_communication_key(host: str) -> bool:
    if not host.strip():
        return False
    try:
        return bool(_windows_keyring().get_password(KEYRING_SERVICE, host.strip().lower()))
    except AttendanceError:
        return False


def _default_zk_factory():
    try:
        from zk import ZK
    except ImportError as exc:
        raise AttendanceError(
            "The PyZK device connector is not installed. Reinstall the app with its dependencies."
        ) from exc
    return ZK


def _optional_device_value(connection, method_name: str, warnings: list[str]):
    try:
        value = getattr(connection, method_name)()
        return str(value) if value is not None else ""
    except Exception as exc:
        warnings.append(f"Could not read optional device field {method_name}: {exc}")
        return ""


def _read_device_info(connection, settings: DeviceSettings) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    details = {
        "device_name": _optional_device_value(connection, "get_device_name", warnings),
        "serial_number": _optional_device_value(connection, "get_serialnumber", warnings),
        "firmware_version": _optional_device_value(connection, "get_firmware_version", warnings),
        "platform": _optional_device_value(connection, "get_platform", warnings),
        "mac_address": _optional_device_value(connection, "get_mac", warnings),
    }
    details["host"] = settings.host.strip()
    details["port"] = settings.port
    details["device_id"] = device_document_id(
        details["serial_number"] or f"{settings.host.strip()}:{settings.port}"
    )
    return details, warnings


def read_device_snapshot(
    settings: DeviceSettings,
    communication_key: str,
    *,
    zk_factory: Optional[Callable[..., Any]] = None,
) -> DeviceSnapshot:
    validate_device_settings(settings)
    try:
        numeric_key = int(communication_key or "0")
    except ValueError as exc:
        raise AttendanceError("The saved device communication key is not numeric.") from exc

    factory = zk_factory or _default_zk_factory()
    device = factory(
        settings.host.strip(),
        port=settings.port,
        timeout=settings.timeout,
        password=numeric_key,
        force_udp=False,
        ommit_ping=True,
    )
    connection = None
    try:
        connection = device.connect()
        device_info, warnings = _read_device_info(connection, settings)
        try:
            employees = [employee_to_record(user) for user in connection.get_users()]
            attendance = [
                attendance_to_record(record, sequence)
                for sequence, record in enumerate(connection.get_attendance())
            ]
        except Exception as exc:
            raise AttendanceError(f"Could not read employees or attendance from the device: {exc}") from exc
        return DeviceSnapshot(
            device=device_info,
            employees=employees,
            attendance=attendance,
            warnings=warnings,
        )
    except AttendanceError:
        raise
    except Exception as exc:
        raise AttendanceError(
            f"Could not connect to the attendance machine at "
            f"{settings.host.strip()}:{settings.port}: {exc}"
        ) from exc
    finally:
        if connection is not None:
            connection.disconnect()


def test_device_connection(
    settings: DeviceSettings,
    communication_key: str,
    *,
    zk_factory: Optional[Callable[..., Any]] = None,
) -> dict[str, Any]:
    validate_device_settings(settings)
    try:
        numeric_key = int(communication_key or "0")
    except ValueError as exc:
        raise AttendanceError("The saved device communication key is not numeric.") from exc
    factory = zk_factory or _default_zk_factory()
    device = factory(
        settings.host.strip(),
        port=settings.port,
        timeout=settings.timeout,
        password=numeric_key,
        force_udp=False,
        ommit_ping=True,
    )
    connection = None
    try:
        connection = device.connect()
        details, warnings = _read_device_info(connection, settings)
        if warnings:
            details["warning"] = "; ".join(warnings)
        return details
    except Exception as exc:
        raise AttendanceError(
            f"Could not connect to the attendance machine at "
            f"{settings.host.strip()}:{settings.port}: {exc}"
        ) from exc
    finally:
        if connection is not None:
            connection.disconnect()


def employee_to_record(user: Any) -> dict[str, Any]:
    return {
        "uid": _safe_value(getattr(user, "uid", None)),
        "employee_id": str(getattr(user, "user_id", "") or getattr(user, "uid", "")),
        "name": str(getattr(user, "name", "") or ""),
        "privilege": _safe_value(getattr(user, "privilege", None)),
        "group_id": _safe_value(getattr(user, "group_id", None)),
        "card_number": _safe_value(getattr(user, "card", None)),
    }


def attendance_to_record(record: Any, sequence: int = 0) -> dict[str, Any]:
    timestamp = getattr(record, "timestamp", None)
    if not isinstance(timestamp, datetime):
        raise AttendanceError("An attendance record has no valid timestamp.")
    local_timestamp = timestamp.astimezone()
    record_uid = getattr(record, "uid", None)
    if record_uid is None:
        record_uid = sequence
    return {
        "uid": _safe_value(record_uid),
        "employee_id": str(getattr(record, "user_id", "") or ""),
        "punch_time": local_timestamp,
        "punch_time_local": local_timestamp.isoformat(),
        "status": _safe_value(getattr(record, "status", None)),
        "punch": _safe_value(getattr(record, "punch", None)),
    }


def _safe_value(value: Any):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def device_document_id(device_identity: str) -> str:
    return hashlib.sha256(device_identity.encode("utf-8")).hexdigest()


def _attendance_document_id(device_id: str, record: dict[str, Any]) -> str:
    identity = "\x1f".join(
        (
            device_id,
            record["employee_id"],
            record["punch_time_local"],
            str(record["status"]),
            str(record["punch"]),
            str(record["uid"]),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _employee_document_id(device_id: str, employee_id: str) -> str:
    return hashlib.sha256(f"{device_id}\x1f{employee_id}".encode("utf-8")).hexdigest()


def _write_documents(
    firestore_db,
    collection,
    documents: list[tuple[str, dict[str, Any]]],
    *,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> int:
    written = 0
    total = len(documents)
    for offset in range(0, len(documents), FIRESTORE_BATCH_SIZE):
        batch = firestore_db.batch()
        chunk = documents[offset:offset + FIRESTORE_BATCH_SIZE]
        for document_id, data in chunk:
            batch.set(collection.document(document_id), data, merge=True)
        batch.commit()
        written += len(chunk)
        if progress_callback:
            progress_callback(written, total)
    if not documents and progress_callback:
        progress_callback(0, 0)
    return written


def _write_new_documents(
    firestore_db,
    collection,
    documents: list[tuple[str, dict[str, Any]]],
    *,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> int:
    written = 0
    checked = 0
    total = len(documents)
    for offset in range(0, len(documents), FIRESTORE_BATCH_SIZE):
        chunk = documents[offset:offset + FIRESTORE_BATCH_SIZE]
        references = [collection.document(document_id) for document_id, _ in chunk]
        existing_ids = {
            snapshot.id
            for snapshot in firestore_db.get_all(references)
            if snapshot.exists
        }
        checked += len(chunk)
        missing_documents = [
            (reference, data)
            for (document_id, data), reference in zip(chunk, references)
            if document_id not in existing_ids
        ]
        if missing_documents:
            batch = firestore_db.batch()
            for reference, data in missing_documents:
                batch.set(reference, data)
            batch.commit()
            written += len(missing_documents)
        if progress_callback:
            progress_callback(checked, total)
    if not documents and progress_callback:
        progress_callback(0, 0)
    return written


def upload_snapshot(
    snapshot: DeviceSnapshot,
    firestore_db,
    *,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> dict[str, int]:
    device = dict(snapshot.device)
    device_id = str(device.get("device_id") or "")
    if not device_id:
        raise AttendanceError("The device snapshot has no stable device identifier.")
    synced_at = datetime.now(timezone.utc)
    device["last_sync_at"] = synced_at

    state_ref = firestore_db.collection("attendance_sync_state").document(device_id)
    state_snapshot = state_ref.get()
    state_data = state_snapshot.to_dict() if state_snapshot.exists else {}
    previous_checkpoint = state_data.get("last_attendance_at")
    if isinstance(previous_checkpoint, str):
        try:
            previous_checkpoint = datetime.fromisoformat(previous_checkpoint)
        except ValueError:
            previous_checkpoint = None
    if previous_checkpoint is not None and previous_checkpoint.tzinfo is None:
        previous_checkpoint = previous_checkpoint.replace(tzinfo=timezone.utc)
    cutoff = (
        previous_checkpoint - ATTENDANCE_OVERLAP
        if isinstance(previous_checkpoint, datetime)
        else None
    )

    employee_documents = []
    for employee in snapshot.employees:
        employee_data = dict(employee)
        employee_data["device_id"] = device_id
        employee_data["last_sync_at"] = synced_at
        employee_documents.append(
            (
                _employee_document_id(device_id, str(employee_data["employee_id"])),
                employee_data,
            )
        )

    attendance_records = [
        record
        for record in snapshot.attendance
        if cutoff is None or record["punch_time"] >= cutoff
    ]
    attendance_documents = []
    for record in attendance_records:
        record_data = dict(record)
        record_data["device_id"] = device_id
        record_data["synced_at"] = synced_at
        attendance_documents.append(
            (_attendance_document_id(device_id, record_data), record_data)
        )

    devices_collection = firestore_db.collection("attendance_devices")
    employees_collection = firestore_db.collection("attendance_employees")
    logs_collection = firestore_db.collection("attendance_logs")
    _write_documents(firestore_db, devices_collection, [(device_id, device)])
    employee_count = _write_documents(
        firestore_db,
        employees_collection,
        employee_documents,
        progress_callback=(
            lambda done, total: progress_callback(
                done,
                total,
                "Saving employee records to Firestore",
            )
            if progress_callback
            else None
        ),
    )
    attendance_count = _write_new_documents(
        firestore_db,
        logs_collection,
        attendance_documents,
        progress_callback=(
            lambda done, total: progress_callback(
                done,
                total,
                "Checking and saving new attendance records",
            )
            if progress_callback
            else None
        ),
    )

    newest_attendance = max(
        (record["punch_time"] for record in snapshot.attendance),
        default=previous_checkpoint,
    )
    state_ref.set(
        {
            "device_id": device_id,
            "last_sync_at": synced_at,
            "last_attendance_at": newest_attendance,
            "employees_synced": employee_count,
            "attendance_records_synced": attendance_count,
        },
        merge=True,
    )
    return {
        "employees": employee_count,
        "attendance": attendance_count,
    }
