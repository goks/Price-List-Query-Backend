import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import boto3
import keyring
from botocore.config import Config
from keyring.backends.Windows import WinVaultKeyring


KEYRING_SERVICE = "GA Price Uploader Cloudflare R2"
MAX_BUCKET_BYTES = 10_000_000_000


class R2Error(RuntimeError):
    pass


@dataclass(frozen=True)
class R2Settings:
    account_id: str
    bucket_name: str
    access_key_id: str
    prefix: str = "sql-backups"

    @property
    def endpoint_url(self) -> str:
        return f"https://{self.account_id}.r2.cloudflarestorage.com"


@dataclass(frozen=True)
class UploadSessionPreflight:
    upload_bytes: int
    initial_bucket_bytes: int
    remaining_bucket_bytes: int
    deleted_backup_objects: int


def _windows_keyring():
    backend = keyring.get_keyring()
    if not isinstance(backend, WinVaultKeyring):
        raise R2Error(
            "Windows Credential Manager is unavailable; R2 secrets were not saved."
        )
    return backend


def save_secret(access_key_id: str, secret_access_key: str) -> None:
    if not access_key_id.strip() or not secret_access_key:
        raise R2Error("Access key ID and secret access key are required.")
    try:
        _windows_keyring().set_password(
            KEYRING_SERVICE,
            access_key_id.strip(),
            secret_access_key,
        )
    except R2Error:
        raise
    except Exception as exc:
        raise R2Error(f"Could not save the R2 secret in Windows Credential Manager: {exc}") from exc


def get_secret(access_key_id: str) -> str:
    try:
        secret = _windows_keyring().get_password(
            KEYRING_SERVICE,
            access_key_id.strip(),
        )
    except R2Error:
        raise
    except Exception as exc:
        raise R2Error(f"Could not read the R2 secret from Windows Credential Manager: {exc}") from exc
    if not secret:
        raise R2Error(
            "No saved R2 secret matches this access key ID. Save the secret before enabling uploads."
        )
    return secret


def has_secret(access_key_id: str) -> bool:
    if not access_key_id.strip():
        return False
    try:
        return bool(
            _windows_keyring().get_password(KEYRING_SERVICE, access_key_id.strip())
        )
    except R2Error:
        return False


def validate_settings(settings: R2Settings) -> None:
    if not settings.account_id.strip():
        raise R2Error("Cloudflare account ID is required.")
    if not re.fullmatch(r"[0-9a-fA-F]{32}", settings.account_id.strip()):
        raise R2Error("Cloudflare account ID must be the 32-character ID shown in your dashboard.")
    if not settings.bucket_name.strip():
        raise R2Error("R2 bucket name is required.")
    if not settings.access_key_id.strip():
        raise R2Error("R2 access key ID is required.")


def create_client(
    settings: R2Settings,
    secret_access_key: str,
    client_factory: Callable = boto3.client,
):
    validate_settings(settings)
    if not secret_access_key:
        raise R2Error("R2 secret access key is required.")

    return client_factory(
        "s3",
        endpoint_url=settings.endpoint_url,
        region_name="auto",
        aws_access_key_id=settings.access_key_id.strip(),
        aws_secret_access_key=secret_access_key,
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 5, "mode": "standard"},
        ),
    )


def format_storage_bytes(size_bytes: int) -> str:
    if size_bytes >= 1_000_000_000:
        return f"{size_bytes / 1_000_000_000:.2f} GB"
    return f"{size_bytes / 1_000_000:.1f} MB"


def list_bucket_objects(client, bucket_name: str) -> list[dict[str, Any]]:
    try:
        paginator = client.get_paginator("list_objects_v2")
        objects = []
        for page in paginator.paginate(Bucket=bucket_name):
            objects.extend(page.get("Contents", []))
        return objects
    except Exception as exc:
        raise R2Error(
            "Could not check current R2 bucket storage. The R2 token needs "
            f"bucket list/read permission: {exc}"
        ) from exc


def get_bucket_size(client, bucket_name: str) -> int:
    return sum(
        int(item.get("Size", 0))
        for item in list_bucket_objects(client, bucket_name)
    )


def prepare_upload_session(
    file_paths: list[str],
    settings: R2Settings,
    secret_access_key: str,
    client_factory: Callable = boto3.client,
) -> UploadSessionPreflight:
    if not file_paths:
        raise R2Error("No prepared SQL backup files were provided for upload.")

    backup_files = [Path(file_path) for file_path in file_paths]
    sizes = []
    for backup_file in backup_files:
        if not backup_file.is_file():
            raise R2Error(
                f"Backup file is not readable from this computer: {backup_file}. "
                "Ensure the app process can read the SQL Server backup folder."
            )
        try:
            sizes.append(backup_file.stat().st_size)
        except OSError as exc:
            raise R2Error(
                f"Could not determine the size of prepared backup "
                f"{backup_file}: {exc}"
            ) from exc

    upload_bytes = sum(sizes)
    if upload_bytes >= MAX_BUCKET_BYTES:
        raise R2Error(
            "The prepared SQL backups total "
            f"{format_storage_bytes(upload_bytes)}, which is not below the "
            "10 GB R2 limit. The upload session was canceled."
        )

    client = create_client(settings, secret_access_key, client_factory)
    bucket_name = settings.bucket_name.strip()
    objects = list_bucket_objects(client, bucket_name)
    initial_bucket_bytes = sum(int(item.get("Size", 0)) for item in objects)
    projected_bytes = initial_bucket_bytes + upload_bytes
    if projected_bytes < MAX_BUCKET_BYTES:
        return UploadSessionPreflight(
            upload_bytes=upload_bytes,
            initial_bucket_bytes=initial_bucket_bytes,
            remaining_bucket_bytes=initial_bucket_bytes,
            deleted_backup_objects=0,
        )

    prefix = settings.prefix.strip().strip("/")
    if not prefix:
        raise R2Error(
            "The R2 bucket would exceed 10 GB, and no SQL-backup prefix is "
            "configured for safe cleanup. No cloud backups were deleted."
        )

    managed_prefix = f"{prefix}/"
    backup_objects = [
        item for item in objects
        if str(item.get("Key", "")).startswith(managed_prefix)
    ]
    backup_bytes = sum(int(item.get("Size", 0)) for item in backup_objects)
    non_backup_bytes = initial_bucket_bytes - backup_bytes
    if non_backup_bytes + upload_bytes >= MAX_BUCKET_BYTES:
        raise R2Error(
            "The prepared SQL backups plus bucket objects outside the configured "
            f"'{managed_prefix}' prefix would use "
            f"{format_storage_bytes(non_backup_bytes + upload_bytes)}, which is "
            "not below the 10 GB limit. No existing cloud backups were deleted."
        )
    if not backup_objects:
        raise R2Error(
            "The R2 bucket would exceed 10 GB, but there are no existing objects "
            f"under '{managed_prefix}' to clear. No cloud backups were deleted."
        )

    try:
        for offset in range(0, len(backup_objects), 1000):
            batch = backup_objects[offset:offset + 1000]
            response = client.delete_objects(
                Bucket=bucket_name,
                Delete={
                    "Objects": [{"Key": item["Key"]} for item in batch],
                    "Quiet": True,
                },
            )
            deletion_errors = response.get("Errors", [])
            if deletion_errors:
                details = "; ".join(
                    f"{item.get('Key', '<unknown key>')}: "
                    f"{item.get('Message', 'delete failed')}"
                    for item in deletion_errors[:5]
                )
                raise R2Error(
                    f"Could not clear all SQL backups under '{managed_prefix}': "
                    f"{details}. Some objects may already have been deleted."
                )
    except R2Error:
        raise
    except Exception as exc:
        raise R2Error(
            f"Could not clear SQL backups under '{managed_prefix}'. "
            f"Some objects may already have been deleted: {exc}"
        ) from exc

    remaining_objects = list_bucket_objects(client, bucket_name)
    remaining_bucket_bytes = sum(
        int(item.get("Size", 0)) for item in remaining_objects
    )
    if any(
        str(item.get("Key", "")).startswith(managed_prefix)
        for item in remaining_objects
    ):
        raise R2Error(
            f"Not all objects under '{managed_prefix}' were removed. "
            "The upload session was canceled."
        )
    if remaining_bucket_bytes + upload_bytes >= MAX_BUCKET_BYTES:
        raise R2Error(
            "The bucket would still reach or exceed 10 GB after clearing "
            f"'{managed_prefix}'. The upload session was canceled."
        )

    return UploadSessionPreflight(
        upload_bytes=upload_bytes,
        initial_bucket_bytes=initial_bucket_bytes,
        remaining_bucket_bytes=remaining_bucket_bytes,
        deleted_backup_objects=len(backup_objects),
    )


def test_connection(
    settings: R2Settings,
    secret_access_key: str,
    client_factory: Callable = boto3.client,
) -> str:
    client = create_client(settings, secret_access_key, client_factory)
    try:
        client.head_bucket(Bucket=settings.bucket_name.strip())
    except Exception as exc:
        raise R2Error(
            "Could not access the R2 bucket. Check the account ID, bucket name, "
            f"and token permissions: {exc}"
        ) from exc
    try:
        bucket_size = get_bucket_size(client, settings.bucket_name.strip())
    except R2Error as exc:
        raise R2Error(
            "The R2 token can access the bucket but cannot check bucket storage. "
            f"Grant bucket object-list permission: {exc}"
        ) from exc
    return (
        "Cloudflare R2 connection successful. Bucket storage: "
        f"{format_storage_bytes(bucket_size)} of 10.00 GB."
    )


def upload_backup(
    file_path: str,
    settings: R2Settings,
    secret_access_key: str,
    *,
    company_code: str,
    financial_year: str,
    progress_callback: Optional[Callable[[int, int, float], None]] = None,
    client_factory: Callable = boto3.client,
) -> str:
    backup_file = Path(file_path)
    if not backup_file.is_file():
        raise R2Error(
            f"Backup file is not readable from this computer: {file_path}. "
            "Ensure the app process can read the SQL Server backup share."
        )

    prefix = settings.prefix.strip().strip("/")
    object_key_parts = [
        part for part in (prefix, f"BusyComp{company_code}", f"FY{financial_year}", backup_file.name)
        if part
    ]
    object_key = "/".join(object_key_parts)
    client = create_client(settings, secret_access_key, client_factory)
    bucket_name = settings.bucket_name.strip()
    file_size = backup_file.stat().st_size
    current_size = get_bucket_size(client, bucket_name)
    projected_size = current_size + file_size
    if current_size >= MAX_BUCKET_BYTES or projected_size >= MAX_BUCKET_BYTES:
        raise R2Error(
            "R2 10 GB bucket limit would be reached or exceeded: currently using "
            f"{format_storage_bytes(current_size)}, this backup is "
            f"{format_storage_bytes(file_size)}, projected total is "
            f"{format_storage_bytes(projected_size)}. The backup was not uploaded."
        )

    transferred = 0
    upload_started_at = time.monotonic()
    progress_lock = threading.Lock()

    def report_progress(increment: int) -> None:
        nonlocal transferred
        if progress_callback is None:
            return
        with progress_lock:
            transferred = min(file_size, transferred + int(increment))
            elapsed = max(time.monotonic() - upload_started_at, 0.25)
            average_speed = transferred / elapsed
            progress_callback(transferred, file_size, average_speed)

    object_uploaded = False
    try:
        client.upload_file(
            os.fspath(backup_file),
            bucket_name,
            object_key,
            ExtraArgs={
                "Metadata": {
                    "company-code": company_code,
                    "financial-year": financial_year,
                }
            },
            Callback=report_progress,
        )
        object_uploaded = True
        response = client.head_object(
            Bucket=bucket_name,
            Key=object_key,
        )
        if int(response.get("ContentLength", -1)) != file_size:
            raise R2Error(
                f"R2 object size verification failed for {backup_file.name}."
            )

        updated_size = get_bucket_size(client, bucket_name)
        if updated_size >= MAX_BUCKET_BYTES:
            raise R2Error(
                "R2 bucket usage reached or exceeded 10 GB after upload: "
                f"{format_storage_bytes(updated_size)} in use. "
                "Removing the newly uploaded backup."
            )
    except R2Error:
        if object_uploaded:
            _delete_uploaded_object(client, bucket_name, object_key)
        raise
    except Exception as exc:
        if object_uploaded:
            _delete_uploaded_object(client, bucket_name, object_key)
        raise R2Error(f"R2 upload failed for {backup_file.name}: {exc}") from exc
    if progress_callback is not None and transferred != file_size:
        elapsed = max(time.monotonic() - upload_started_at, 0.25)
        progress_callback(file_size, file_size, file_size / elapsed)
    return object_key


def _delete_uploaded_object(client, bucket_name: str, object_key: str) -> None:
    try:
        client.delete_object(Bucket=bucket_name, Key=object_key)
    except Exception as delete_exc:
        raise R2Error(
            f"The new R2 object could not be removed ({object_key}): {delete_exc}"
        ) from delete_exc
