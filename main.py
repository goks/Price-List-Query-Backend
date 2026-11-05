import json
import os
import re
import ssl
import sys
import tempfile
import threading
import traceback
import urllib.error
import urllib.request
import webbrowser
import winreg
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pytz
import certifi
from PySide6.QtCore import QObject, Property, QRunnable, QStandardPaths, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QFontDatabase, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from app_version import APP_VERSION
import core
import backup_service
import r2_service
import attendance_service

IST = pytz.timezone("Asia/Calcutta")
APP_NAME = "GA Price Uploader"
APP_RUN_KEY = "Price List Update"
LEGACY_RUN_KEYS = ("GA_Price_Uploader", APP_RUN_KEY)
GITHUB_REPO = "goks/Price-List-Query-Backend"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
DEFAULT_DB_SERVER = r"GASERVER\BUSYSTDSQL"
DEFAULT_DB_NAME = "BusyComp0004_db12025"
AUTOSTART_ARGUMENT = "--start-in-tray"


def get_base_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).parent


def get_settings_path() -> Path:
    config_root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    if not config_root:
        config_root = str(Path.home() / "AppData" / "Roaming" / "GA Price Uploader")
    settings_dir = Path(config_root)
    settings_dir.mkdir(parents=True, exist_ok=True)
    return settings_dir / "settings.json"


SETTINGS_FILE = get_settings_path()
LEGACY_SETTINGS_FILE = get_base_path() / "auto_update_settings.json"


def normalize_version(version: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", version or "")
    return tuple(int(part) for part in numbers) if numbers else (0,)


def load_latest_release() -> dict[str, Any]:
    request = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{APP_NAME}/{APP_VERSION}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20, context=get_ssl_context()) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError("No GitHub release is published yet for this repository.") from exc
        raise
    except ssl.SSLError as exc:
        raise RuntimeError("SSL certificate verification failed while contacting GitHub. Check system date/time, proxy, or CA certificates.") from exc


def choose_release_asset(assets: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not assets:
        return None
    return sorted(
        assets,
        key=lambda asset: (
            0 if "installer" in str(asset.get("name", "")).lower() else 1,
            0 if str(asset.get("name", "")).lower().endswith(".exe") else 1,
            str(asset.get("name", "")).lower(),
        ),
    )[0]


def get_ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def get_pythonw_path() -> str:
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        return str(executable)
    pythonw_candidate = executable.with_name("pythonw.exe")
    if pythonw_candidate.exists():
        return str(pythonw_candidate)
    return str(executable)


class MainWindow(QObject):
    progressChanged = Signal(int, int)
    statusChanged = Signal()  # type: ignore
    isBusyChanged = Signal()  # type: ignore
    lastUpdatedChanged = Signal()  # type: ignore
    logChanged = Signal()  # type: ignore
    autoUpdateEnabledChanged = Signal()  # type: ignore
    autoUpdateIntervalChanged = Signal()  # type: ignore
    autostartEnabledChanged = Signal()  # type: ignore
    dbServerChanged = Signal()  # type: ignore
    dbNameChanged = Signal()  # type: ignore
    backupDatabasesChanged = Signal()  # type: ignore
    backupDestinationChanged = Signal()  # type: ignore
    backupScheduleEnabledChanged = Signal()  # type: ignore
    backupScheduleTimeChanged = Signal()  # type: ignore
    backupStatusChanged = Signal()  # type: ignore
    backupHistoryChanged = Signal()  # type: ignore
    r2SettingsChanged = Signal()  # type: ignore
    r2UploadEnabledChanged = Signal()  # type: ignore
    r2TransferChanged = Signal(float, float, float, str, bool)
    r2CancelRequestedChanged = Signal()
    attendanceConfigChanged = Signal()
    attendanceScheduleEnabledChanged = Signal()
    attendanceStatusChanged = Signal()
    attendanceHistoryChanged = Signal()
    attendanceTodayRowsChanged = Signal()
    attendanceProgressChanged = Signal(int, int, str, bool)
    appVersionChanged = Signal()  # type: ignore
    latestVersionChanged = Signal()  # type: ignore
    updateStatusChanged = Signal()  # type: ignore
    updateAvailableChanged = Signal()  # type: ignore

    def __init__(self):
        super().__init__()
        self._status = "Ready"
        self._isBusy = False
        self._lastUpdated = "Never"
        self._logs: list[str] = []
        self.progress = 0
        self.threadpool = QThreadPool()
        self.qmlWindow: Optional[Any] = None  # type: ignore
        self._wasVisible = True

        self._autoUpdateEnabled = True
        self._autoUpdateInterval = 4
        self._autostartEnabled = True
        self._dbServer = DEFAULT_DB_SERVER
        self._dbName = DEFAULT_DB_NAME
        self._backupDatabases: list[backup_service.BackupDatabase] = []
        self._selectedBackupDatabases: set[str] = set()
        self._backupDestination = ""
        self._backupScheduleEnabled = False
        self._backupScheduleTime = "02:00"
        self._backupStatus = "Refresh the database list to choose company years."
        self._backupHistory: list[str] = []
        self._backupPendingAfterDiscovery = False
        self._r2AccountId = ""
        self._r2BucketName = ""
        self._r2AccessKeyId = ""
        self._r2Prefix = "sql-backups"
        self._r2UploadEnabled = False
        self._r2CancelEvent = threading.Event()
        self._r2CancelRequested = False
        self._activeR2TransferFuture = None
        self._r2TransferFutureLock = threading.Lock()
        self._attendanceHost = "192.168.10.102"
        self._attendancePort = 4370
        self._attendanceScheduleEnabled = False
        self._attendanceStatus = "Configure the K90 Pro connection, then test it."
        self._attendanceHistory: list[str] = []
        self._attendanceTodayRows: list[dict[str, Any]] = []

        self._appVersion = APP_VERSION
        self._latestVersion = APP_VERSION
        self._updateStatus = "Ready"
        self._updateAvailable = False
        self._releasePageUrl = f"https://github.com/{GITHUB_REPO}/releases/latest"

        self.loadSettings()
        core.SERVERNAME = self._dbServer
        core.DATABASENAME = self._dbName

        self.autoUpdateTimer = QTimer()
        self.autoUpdateTimer.timeout.connect(self.onAutoUpdateTrigger)
        if self._autoUpdateEnabled:
            self.startAutoUpdate()
        self.backupScheduleTimer = QTimer()
        self.backupScheduleTimer.setSingleShot(True)
        self.backupScheduleTimer.timeout.connect(self.onScheduledBackupTrigger)
        self.startBackupSchedule()
        self.attendanceScheduleTimer = QTimer()
        self.attendanceScheduleTimer.setSingleShot(True)
        self.attendanceScheduleTimer.timeout.connect(self.onScheduledAttendanceImport)
        self.startAttendanceSchedule()

    def getAutostartCommand(self) -> str:
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}" {AUTOSTART_ARGUMENT}'
        return f'"{get_pythonw_path()}" "{os.path.abspath(__file__)}" {AUTOSTART_ARGUMENT}'

    def appendLog(self, message: str):
        self._logs.append(message)
        self.logChanged.emit()

    def setBusy(self, busy: bool):
        if self._isBusy != busy:
            self._isBusy = busy
            self.isBusyChanged.emit()

    def loadSettings(self):
        try:
            source_path = SETTINGS_FILE if SETTINGS_FILE.exists() else LEGACY_SETTINGS_FILE
            if source_path.exists():
                with open(source_path, "r", encoding="utf-8") as handle:
                    settings = json.load(handle)
                self._autoUpdateEnabled = bool(settings.get("enabled", True))
                self._autoUpdateInterval = int(settings.get("interval", 4))
                self._autostartEnabled = bool(settings.get("autostart", True))
                self._dbServer = str(settings.get("dbServer", DEFAULT_DB_SERVER))
                self._dbName = str(settings.get("dbName", DEFAULT_DB_NAME))
                self._backupDestination = str(settings.get("backupDestination", ""))
                self._backupScheduleEnabled = bool(settings.get("backupScheduleEnabled", False))
                self._r2AccountId = str(settings.get("r2AccountId", ""))
                self._r2BucketName = str(settings.get("r2BucketName", ""))
                self._r2AccessKeyId = str(settings.get("r2AccessKeyId", ""))
                self._r2Prefix = str(settings.get("r2Prefix", "sql-backups"))
                self._r2UploadEnabled = bool(settings.get("r2UploadEnabled", False))
                self._attendanceHost = str(
                    settings.get("attendanceHost", self._attendanceHost)
                )
                self._attendancePort = int(settings.get("attendancePort", 4370))
                self._attendanceScheduleEnabled = bool(
                    settings.get("attendanceScheduleEnabled", False)
                )
                schedule_time = str(settings.get("backupScheduleTime", "02:00"))
                if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", schedule_time):
                    self._backupScheduleTime = schedule_time
                selected_databases = settings.get("selectedBackupDatabases", [])
                if isinstance(selected_databases, list):
                    self._selectedBackupDatabases = {
                        str(name) for name in selected_databases if isinstance(name, str)
                    }
                if source_path == LEGACY_SETTINGS_FILE and source_path != SETTINGS_FILE:
                    self.saveSettings()
        except Exception as exc:
            print(f"Error loading settings: {exc}")

    def saveSettings(self) -> bool:
        try:
            settings = {
                "enabled": self._autoUpdateEnabled,
                "interval": self._autoUpdateInterval,
                "autostart": self._autostartEnabled,
                "dbServer": self._dbServer,
                "dbName": self._dbName,
                "backupDestination": self._backupDestination,
                "backupScheduleEnabled": self._backupScheduleEnabled,
                "backupScheduleTime": self._backupScheduleTime,
                "selectedBackupDatabases": sorted(self._selectedBackupDatabases),
                "r2AccountId": self._r2AccountId,
                "r2BucketName": self._r2BucketName,
                "r2AccessKeyId": self._r2AccessKeyId,
                "r2Prefix": self._r2Prefix,
                "r2UploadEnabled": self._r2UploadEnabled,
                "attendanceHost": self._attendanceHost,
                "attendancePort": self._attendancePort,
                "attendanceScheduleEnabled": self._attendanceScheduleEnabled,
            }
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as handle:
                json.dump(settings, handle, indent=2)
            return True
        except (OSError, TypeError, ValueError) as exc:
            message = f"Could not save settings: {exc}"
            self.appendLog(message)
            self.setBackupStatus(message)
            return False

    def setUpdateState(
        self,
        *,
        status: Optional[str] = None,
        latest_version: Optional[str] = None,
        update_available: Optional[bool] = None,
        release_url: Optional[str] = None,
    ):
        if status is not None and self._updateStatus != status:
            self._updateStatus = status
            self.updateStatusChanged.emit()
        if latest_version is not None and self._latestVersion != latest_version:
            self._latestVersion = latest_version
            self.latestVersionChanged.emit()
        if update_available is not None and self._updateAvailable != update_available:
            self._updateAvailable = update_available
            self.updateAvailableChanged.emit()
        if release_url:
            self._releasePageUrl = release_url

    def startAutoUpdate(self):
        if self._autoUpdateInterval > 0:
            interval_ms = self._autoUpdateInterval * 60 * 60 * 1000
            self.autoUpdateTimer.start(interval_ms)
            self.appendLog(f"Auto-sync enabled: every {self._autoUpdateInterval} hours")

    def stopAutoUpdate(self):
        self.autoUpdateTimer.stop()
        self.appendLog("Auto-sync disabled")

    def appendBackupLog(self, message: str):
        entry = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}"
        self._backupHistory.append(entry)
        self._backupHistory = self._backupHistory[-20:]
        self.backupHistoryChanged.emit()
        self.appendLog(f"Backup: {message}")

    def setBackupStatus(self, message: str):
        if self._backupStatus != message:
            self._backupStatus = message
            self.backupStatusChanged.emit()

    def startBackupSchedule(self):
        self.backupScheduleTimer.stop()
        if not self._backupScheduleEnabled:
            return

        try:
            interval_ms = backup_service.milliseconds_until_daily_time(
                datetime.now().astimezone(),
                self._backupScheduleTime,
            )
        except backup_service.BackupError as exc:
            self.setBackupStatus(str(exc))
            return

        self.backupScheduleTimer.start(interval_ms)

    @Slot()
    def onScheduledBackupTrigger(self):
        self.appendBackupLog(
            f"Daily backup schedule triggered at {datetime.now().astimezone().strftime('%H:%M')}."
        )
        if self._isBusy:
            self.appendBackupLog("Scheduled backup skipped because another operation is running.")
            self.setBackupStatus("Scheduled backup skipped because another operation is running.")
        else:
            self._backupPendingAfterDiscovery = True
            self.refreshBackupDatabases()
        self.startBackupSchedule()

    def appendAttendanceLog(self, message: str):
        entry = f"{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')} - {message}"
        self._attendanceHistory.append(entry)
        self._attendanceHistory = self._attendanceHistory[-20:]
        self.attendanceHistoryChanged.emit()
        self.appendLog(f"Attendance import: {message}")

    def setAttendanceStatus(self, message: str):
        if self._attendanceStatus != message:
            self._attendanceStatus = message
            self.attendanceStatusChanged.emit()

    def startAttendanceSchedule(self):
        self.attendanceScheduleTimer.stop()
        if not self._attendanceScheduleEnabled:
            return

        now = datetime.now().astimezone()
        next_run = attendance_service.next_scheduled_import(now)
        interval_ms = max(1, int((next_run - now).total_seconds() * 1000))
        self.attendanceScheduleTimer.start(interval_ms)

    @Slot()
    def onScheduledAttendanceImport(self):
        self.startAttendanceSchedule()
        if self._isBusy:
            self.appendAttendanceLog(
                "Scheduled import skipped because another operation is running."
            )
            return
        self.appendAttendanceLog("Scheduled import started.")
        self.runAttendanceImport()

    @Slot(str, str, str, result=bool)
    def saveAttendanceSettings(
        self,
        host: str,
        port_text: str,
        communication_key: str,
    ):
        try:
            settings = attendance_service.DeviceSettings(
                host=host.strip(),
                port=int(port_text),
            )
            attendance_service.validate_device_settings(settings)
            if communication_key:
                attendance_service.save_communication_key(
                    settings.host,
                    communication_key,
                )
        except (ValueError, attendance_service.AttendanceError) as exc:
            self.setAttendanceStatus(str(exc))
            self.appendAttendanceLog(f"Settings were not saved: {exc}")
            return False

        previous_config = (self._attendanceHost, self._attendancePort)
        self._attendanceHost = settings.host
        self._attendancePort = settings.port
        saved = self.saveSettings()
        if not saved:
            self._attendanceHost, self._attendancePort = previous_config
            self.setAttendanceStatus("Could not save attendance settings.")
            self.appendAttendanceLog("Device settings were not saved.")
            self.attendanceConfigChanged.emit()
            return False

        self.setAttendanceStatus(
            "Settings saved. The schedule runs every 10 minutes from 8:00 AM "
            "through 11:00 AM, then hourly on the hour. Test the connection "
            "before enabling automatic imports."
        )
        self.appendAttendanceLog(
            f"Device settings saved for {settings.host}:{settings.port}."
        )
        self.startAttendanceSchedule()
        self.attendanceConfigChanged.emit()
        return True

    @Slot(bool)
    def setAttendanceScheduleEnabled(self, enabled: bool):
        enabled = bool(enabled)
        if self._attendanceScheduleEnabled == enabled:
            return
        previous_enabled = self._attendanceScheduleEnabled
        self._attendanceScheduleEnabled = enabled
        if not self.saveSettings():
            self._attendanceScheduleEnabled = previous_enabled
            self.setAttendanceStatus(
                "Could not save the automatic attendance import setting."
            )
            self.appendAttendanceLog("Automatic import setting was not saved.")
            self.attendanceScheduleEnabledChanged.emit()
            return

        self.startAttendanceSchedule()
        if enabled:
            message = (
                "Automatic attendance import enabled: every 10 minutes from "
                "8:00 AM through 11:00 AM, then hourly on the hour (local time) "
                "while this app is running."
            )
        else:
            message = "Automatic attendance import disabled."
        self.setAttendanceStatus(message)
        self.appendAttendanceLog(message)
        self.attendanceScheduleEnabledChanged.emit()

    @Slot()
    def testAttendanceConnection(self):
        if self._isBusy:
            self.setAttendanceStatus("Wait for the current operation to finish.")
            return
        self.setBusy(True)
        self.setAttendanceStatus(
            f"Connecting to {self._attendanceHost}:{self._attendancePort}..."
        )
        self.threadpool.start(Worker(self.performAttendanceConnectionTest))

    def performAttendanceConnectionTest(self):
        try:
            settings = attendance_service.DeviceSettings(
                self._attendanceHost,
                self._attendancePort,
            )
            communication_key = attendance_service.get_communication_key(
                settings.host
            )
            details = attendance_service.test_device_connection(
                settings,
                communication_key,
            )
            description = details.get("device_name") or "K90 Pro"
            serial = details.get("serial_number")
            suffix = f" (serial {serial})" if serial else ""
            self.setAttendanceStatus(
                f"Connected to {description}{suffix} at "
                f"{settings.host}:{settings.port}."
            )
            self.appendAttendanceLog(
                f"Connection test succeeded for {settings.host}:{settings.port}."
            )
        except Exception as exc:
            self.setAttendanceStatus(f"Device connection failed: {exc}")
            self.appendAttendanceLog(f"Connection test failed: {exc}")
        finally:
            self.setBusy(False)

    @Slot()
    def runAttendanceImport(self):
        if self._isBusy:
            self.setAttendanceStatus("Wait for the current operation to finish.")
            return
        self.setBusy(True)
        self.setAttendanceStatus("Reading machine details, employees, and attendance...")
        self.attendanceProgressChanged.emit(
            5,
            100,
            "Reading device attendance and employee records",
            True,
        )
        self.threadpool.start(Worker(self.performAttendanceImport))

    def performAttendanceImport(self):
        try:
            settings = attendance_service.DeviceSettings(
                self._attendanceHost,
                self._attendancePort,
            )
            communication_key = attendance_service.get_communication_key(
                settings.host
            )
            snapshot = attendance_service.read_device_snapshot(
                settings,
                communication_key,
            )
            self.attendanceProgressChanged.emit(
                45,
                100,
                "Saving records to Firestore",
                True,
            )

            def report_upload_progress(done: int, total: int, stage: str):
                fraction = done / total if total else 1
                if stage.startswith("Saving employee"):
                    progress = 45 + round(fraction * 10)
                else:
                    progress = 55 + round(fraction * 44)
                self.attendanceProgressChanged.emit(
                    progress,
                    100,
                    stage,
                    True,
                )

            counts = attendance_service.upload_snapshot(
                snapshot,
                core.firestore_db,
                progress_callback=report_upload_progress,
            )
            self.setAttendanceTodayRows(snapshot)
            message = (
                f"Import complete: {counts['employees']} employee record(s) refreshed; "
                f"{counts['attendance']} new attendance record(s) imported."
            )
            if snapshot.warnings:
                self.appendAttendanceLog(
                    "Device info warnings: " + "; ".join(snapshot.warnings)
                )
            self.setAttendanceStatus(message)
            self.appendAttendanceLog(message)
        except Exception as exc:
            self.setAttendanceStatus(f"Attendance import failed: {exc}")
            self.appendAttendanceLog(f"Import failed: {exc}")
        finally:
            self.attendanceProgressChanged.emit(0, 0, "", False)
            self.setBusy(False)

    def setAttendanceTodayRows(
        self,
        snapshot: attendance_service.DeviceSnapshot,
    ):
        employee_names = {
            str(employee.get("employee_id", "")): str(employee.get("name", ""))
            for employee in snapshot.employees
        }
        today = datetime.now().astimezone().date()
        rows = []
        for record in snapshot.attendance:
            punch_time = record["punch_time"]
            local_time = (
                punch_time.astimezone()
                if punch_time.tzinfo is not None
                else punch_time.astimezone()
            )
            if local_time.date() != today:
                continue
            employee_id = str(record.get("employee_id", ""))
            rows.append(
                {
                    "time": local_time.isoformat(),
                    "employeeId": employee_id,
                    "name": employee_names.get(employee_id, ""),
                    "status": str(record.get("status", "")),
                    "punch": str(record.get("punch", "")),
                }
            )
        rows.sort(key=lambda row: row["time"], reverse=True)
        self._attendanceTodayRows = rows
        self.attendanceTodayRowsChanged.emit()

    @Slot()
    def refreshBackupDatabases(self):
        if self._isBusy:
            self.setBackupStatus("Wait for the current database operation to finish.")
            return
        self.setBackupStatus("Reading company/year databases...")
        self.setBusy(True)
        self.threadpool.start(Worker(self.performBackupDiscovery))

    def performBackupDiscovery(self):
        discovery_succeeded = False
        try:
            databases, issues = backup_service.discover_databases(self._dbServer)
            self._backupDatabases = databases
            discovery_succeeded = True
            self.backupDatabasesChanged.emit()
            if issues:
                self.setBackupStatus(
                    f"Found {len(databases)} backup database(s) with "
                    f"{len(issues)} discovery issue(s); see backup history."
                )
                for issue in issues:
                    self.appendBackupLog(f"Discovery warning: {issue}")
            else:
                self.setBackupStatus(
                    f"Found {len(databases)} company/year database(s)."
                )
            self.appendBackupLog(
                f"Database discovery completed: {len(databases)} candidate(s)."
            )
        except Exception as exc:
            self.setBackupStatus(f"Database discovery failed: {exc}")
            self.appendBackupLog(f"Database discovery failed: {exc}")
        finally:
            self.setBusy(False)
            if self._backupPendingAfterDiscovery:
                self._backupPendingAfterDiscovery = False
                if discovery_succeeded:
                    self.startBackupFromSelection()

    @Slot(str, bool)
    def setBackupDatabaseSelected(self, database_name: str, selected: bool):
        if not any(item.name == database_name for item in self._backupDatabases):
            self.setBackupStatus("Refresh the database list before changing selections.")
            return
        if selected:
            self._selectedBackupDatabases.add(database_name)
        else:
            self._selectedBackupDatabases.discard(database_name)
        self.saveSettings()
        self.backupDatabasesChanged.emit()

    @Slot(str, bool)
    def setBackupCompanySelected(self, company_code: str, selected: bool):
        company_databases = [
            item for item in self._backupDatabases
            if item.company_code == company_code
        ]
        if not company_databases:
            self.setBackupStatus("Refresh the database list before changing selections.")
            return
        for database in company_databases:
            if selected:
                self._selectedBackupDatabases.add(database.name)
            else:
                self._selectedBackupDatabases.discard(database.name)
        self.saveSettings()
        self.backupDatabasesChanged.emit()

    @Slot()
    def checkBackupDestination(self):
        if self._isBusy:
            self.setBackupStatus("Wait for the current database operation to finish.")
            return
        if not self._backupDestination.strip():
            self.setBackupStatus(
                "Enter an absolute folder path on the SQL Server host first."
            )
            return
        self.setBackupStatus("Checking destination from the SQL Server host...")
        self.setBusy(True)
        server = self._dbServer
        destination = self._backupDestination
        self.threadpool.start(
            Worker(lambda: self.performBackupDestinationCheck(server, destination))
        )

    def performBackupDestinationCheck(self, server: str, destination: str):
        try:
            message = backup_service.check_destination(server, destination)
            self.setBackupStatus(message)
            self.appendBackupLog(f"Destination check: {message}")
        except Exception as exc:
            self.setBackupStatus(f"Destination check failed: {exc}")
            self.appendBackupLog(f"Destination check failed: {exc}")
        finally:
            self.setBusy(False)

    def getR2Settings(self) -> r2_service.R2Settings:
        return r2_service.R2Settings(
            account_id=self._r2AccountId,
            bucket_name=self._r2BucketName,
            access_key_id=self._r2AccessKeyId,
            prefix=self._r2Prefix,
        )

    @Slot(str, str, str, str)
    def saveR2Settings(
        self,
        account_id: str,
        bucket_name: str,
        access_key_id: str,
        secret_access_key: str,
    ):
        account_id = str(account_id).strip()
        bucket_name = str(bucket_name).strip()
        access_key_id = str(access_key_id).strip()
        secret_access_key = str(secret_access_key)
        if not account_id or not bucket_name or not access_key_id:
            self.setBackupStatus("R2 account ID, bucket name, and access key ID are required.")
            return

        try:
            settings = r2_service.R2Settings(
                account_id=account_id,
                bucket_name=bucket_name,
                access_key_id=access_key_id,
                prefix=self._r2Prefix,
            )
            r2_service.validate_settings(settings)
            if secret_access_key:
                r2_service.save_secret(access_key_id, secret_access_key)
            else:
                r2_service.get_secret(access_key_id)
        except r2_service.R2Error as exc:
            self.setBackupStatus(str(exc))
            self.appendBackupLog(f"R2 settings were not saved: {exc}")
            return

        self._r2AccountId = account_id
        self._r2BucketName = bucket_name
        self._r2AccessKeyId = access_key_id
        saved = self.saveSettings()
        self.r2SettingsChanged.emit()
        if saved:
            self.setBackupStatus(
                "Cloudflare R2 settings saved. The secret is stored in Windows Credential Manager."
            )
            self.appendBackupLog("Cloudflare R2 settings saved.")

    @Slot()
    def testR2Connection(self):
        if self._isBusy:
            self.setBackupStatus("Wait for the current database operation to finish.")
            return
        try:
            settings = self.getR2Settings()
            secret = r2_service.get_secret(settings.access_key_id)
        except r2_service.R2Error as exc:
            self.setBackupStatus(str(exc))
            return

        self.setBackupStatus("Testing Cloudflare R2 connection...")
        self.setBusy(True)
        self.threadpool.start(
            Worker(lambda: self.performR2ConnectionTest(settings, secret))
        )

    def performR2ConnectionTest(
        self,
        settings: r2_service.R2Settings,
        secret_access_key: str,
    ):
        try:
            message = r2_service.test_connection(settings, secret_access_key)
            self.setBackupStatus(message)
            self.appendBackupLog(message)
        except Exception as exc:
            self.setBackupStatus(f"R2 connection test failed: {exc}")
            self.appendBackupLog(f"R2 connection test failed: {exc}")
        finally:
            self.setBusy(False)

    @Slot(bool)
    def setR2UploadEnabled(self, enabled: bool):
        enabled = bool(enabled)
        if self._r2UploadEnabled != enabled:
            self._r2UploadEnabled = enabled
            self.saveSettings()
            self.r2UploadEnabledChanged.emit()
            if not enabled:
                self.setBackupStatus("Cloudflare R2 uploads are disabled.")
                self.appendBackupLog("Cloudflare R2 upload disabled.")
                return

            try:
                settings = self.getR2Settings()
                r2_service.validate_settings(settings)
                r2_service.get_secret(settings.access_key_id)
            except r2_service.R2Error as exc:
                message = (
                    "Cloudflare R2 upload is switched on, but setup is incomplete: "
                    f"{exc} Save your R2 settings before starting a backup."
                )
                self.setBackupStatus(message)
                self.appendBackupLog(message)
                return

            self.setBackupStatus("Cloudflare R2 upload is enabled.")
            self.appendBackupLog("Cloudflare R2 upload enabled.")

    @Slot()
    def runBackupNow(self):
        if self._isBusy:
            self.setBackupStatus("Wait for the current database operation to finish.")
            return
        if not self._backupDestination.strip():
            self.setBackupStatus(
                "Enter an absolute folder path on the SQL Server host first."
            )
            return

        self._backupPendingAfterDiscovery = True
        self.setBackupStatus("Searching SQL Server for selected company/year databases...")
        self.refreshBackupDatabases()

    def startBackupFromSelection(self):
        selected = [
            item for item in self._backupDatabases
            if item.name in self._selectedBackupDatabases
        ]
        if not selected:
            message = (
                "No selected company/year databases were found. Select companies "
                "and financial years, then try again."
            )
            self.setBackupStatus(message)
            self.appendBackupLog(message)
            return
        if not self._backupDestination.strip():
            self.setBackupStatus(
                "Enter an absolute folder path on the SQL Server host first."
            )
            return

        r2_settings: Optional[r2_service.R2Settings] = None
        r2_secret: Optional[str] = None
        if self._r2UploadEnabled:
            try:
                r2_settings = self.getR2Settings()
                r2_secret = r2_service.get_secret(r2_settings.access_key_id)
                r2_service.validate_settings(r2_settings)
            except r2_service.R2Error as exc:
                self.setBackupStatus(f"R2 upload is enabled but not configured: {exc}")
                self.appendBackupLog(f"Backup not started: {exc}")
                return

        self.setBackupStatus(f"Backing up {len(selected)} database(s)...")
        self._r2CancelEvent.clear()
        self.setR2CancelRequested(False)
        self.setBusy(True)
        server = self._dbServer
        destination = self._backupDestination
        self.threadpool.start(
            Worker(
                lambda: self.performFullBackups(
                    selected,
                    server,
                    destination,
                    r2_settings,
                    r2_secret,
                )
            )
        )

    def performFullBackups(
        self,
        databases: list[backup_service.BackupDatabase],
        server: str,
        destination: str,
        r2_settings: Optional[r2_service.R2Settings] = None,
        r2_secret: Optional[str] = None,
    ):
        completed: list[str] = []
        failures: list[str] = []
        cloud_uploaded = 0
        cloud_failures: list[str] = []
        local_cleanup_failures: list[str] = []
        upload_cancelled = False
        prepared: list[tuple[backup_service.BackupDatabase, str]] = []
        try:
            for database in databases:
                try:
                    path = backup_service.create_full_backup(
                        server,
                        database.name,
                        destination,
                    )
                    completed.append(path)
                    prepared.append((database, path))
                    self.appendBackupLog(f"Created and verified {path}")

                except Exception as exc:
                    failure = f"{database.name}: {exc}"
                    failures.append(failure)
                    self.appendBackupLog(f"Backup failed: {failure}")

            if r2_settings is not None and r2_secret is not None and failures:
                message = (
                    "Upload session canceled because one or more selected SQL "
                    "backups could not be prepared. Prepared local backups were retained."
                )
                cloud_failures.append(message)
                self.appendBackupLog(message)
            elif r2_settings is not None and r2_secret is not None and prepared:
                try:
                    preflight = r2_service.prepare_upload_session(
                        [path for _database, path in prepared],
                        r2_settings,
                        r2_secret,
                    )
                    self.appendBackupLog(
                        "R2 upload session prepared: "
                        f"{len(prepared)} backup(s), "
                        f"{r2_service.format_storage_bytes(preflight.upload_bytes)} "
                        "to upload; bucket usage is "
                        f"{r2_service.format_storage_bytes(preflight.remaining_bucket_bytes)} "
                        "before upload."
                    )
                    if preflight.deleted_backup_objects:
                        self.appendBackupLog(
                            f"Cleared {preflight.deleted_backup_objects} existing "
                            f"R2 backup object(s) under "
                            f"'{r2_settings.prefix.strip().strip('/')}/' to stay "
                            "below the 10 GB limit. Other bucket objects were kept."
                        )
                except Exception as exc:
                    message = f"Upload session canceled: {exc}"
                    cloud_failures.append(message)
                    self.appendBackupLog(
                        f"R2 upload session canceled: {exc} "
                        f"Prepared local backup(s) retained: {len(prepared)}."
                    )
                else:
                    for database, path in prepared:
                        try:
                            file_size = Path(path).stat().st_size
                            self.r2TransferChanged.emit(
                                0,
                                file_size,
                                0,
                                database.name,
                                True,
                            )
                            object_key = r2_service.upload_backup(
                                path,
                                r2_settings,
                                r2_secret,
                                company_code=database.company_code,
                                financial_year=database.financial_year,
                                progress_callback=lambda done, total, speed, name=database.name: (
                                    self.r2TransferChanged.emit(
                                        done,
                                        total,
                                        speed,
                                        name,
                                        True,
                                    )
                                ),
                                cancel_event=self._r2CancelEvent,
                                transfer_future_callback=self.setActiveR2TransferFuture,
                            )
                            self.r2TransferChanged.emit(
                                1,
                                1,
                                0,
                                database.name,
                                False,
                            )
                            cloud_uploaded += 1
                            self.appendBackupLog(
                                f"Uploaded {database.name} to R2: "
                                f"{r2_settings.bucket_name}/{object_key}"
                            )
                            try:
                                Path(path).unlink()
                                self.appendBackupLog(
                                    f"Deleted local backup after verified upload: {path}"
                                )
                            except OSError as exc:
                                message = f"{database.name}: could not delete local backup {path}: {exc}"
                                local_cleanup_failures.append(message)
                                self.appendBackupLog(
                                    f"Local backup cleanup failed: {message}"
                                )
                        except r2_service.R2UploadCancelled as exc:
                            self.r2TransferChanged.emit(
                                0,
                                0,
                                0,
                                database.name,
                                False,
                            )
                            upload_cancelled = True
                            self.appendBackupLog(
                                f"R2 upload canceled by user for {database.name}; "
                                f"local backup retained: {path}."
                            )
                            break
                        except Exception as exc:
                            self.r2TransferChanged.emit(
                                0,
                                0,
                                0,
                                database.name,
                                False,
                            )
                            message = f"{database.name}: {exc}"
                            cloud_failures.append(message)
                            self.appendBackupLog(f"R2 upload failed: {message}")

            if upload_cancelled:
                message = (
                    f"R2 upload canceled. {cloud_uploaded} backup(s) uploaded "
                    "successfully; the in-progress and remaining local backups "
                    "were retained."
                )
                self.setBackupStatus(message)
            elif failures or cloud_failures or local_cleanup_failures:
                first_error = failures or cloud_failures or local_cleanup_failures
                self.setBackupStatus(
                    f"Backups: {len(completed)} succeeded, {len(failures)} failed. "
                    f"R2 uploads: {cloud_uploaded} succeeded, {len(cloud_failures)} failed."
                    f" Local cleanup: {len(local_cleanup_failures)} failed."
                    + (
                        f" First error: {first_error[0]}"
                        if first_error else ""
                    )
                )
            else:
                message = f"Backup complete: {len(completed)} database(s) verified."
                if r2_settings is not None:
                    message += f" R2 upload complete: {cloud_uploaded} object(s)."
                self.setBackupStatus(message)
        finally:
            self.setActiveR2TransferFuture(None)
            self.setR2CancelRequested(False)
            self.setBusy(False)

    def setActiveR2TransferFuture(self, transfer_future):
        with self._r2TransferFutureLock:
            self._activeR2TransferFuture = transfer_future
        if transfer_future is not None and self._r2CancelEvent.is_set():
            transfer_future.cancel()

    def setR2CancelRequested(self, requested: bool):
        if self._r2CancelRequested != requested:
            self._r2CancelRequested = requested
            self.r2CancelRequestedChanged.emit()

    @Slot()
    def cancelR2Upload(self):
        if not self._isBusy or not self._r2UploadEnabled:
            return
        self._r2CancelEvent.set()
        self.setR2CancelRequested(True)
        with self._r2TransferFutureLock:
            transfer_future = self._activeR2TransferFuture
        if transfer_future is not None:
            transfer_future.cancel()
        self.setBackupStatus("Stopping the current R2 upload...")
        self.appendBackupLog(
            "R2 upload cancellation requested. The current multipart transfer "
            "is stopping; local backup files will be retained."
        )

    @Slot()
    def onAutoUpdateTrigger(self):
        self.appendLog(f"Auto-sync triggered at {datetime.now(IST).strftime('%d-%m-%Y %H:%M')}")
        self.upload()

    @Slot()
    def checkDbConnection(self):
        if self._isBusy:
            return
        self._status = "Checking database connection..."
        self.setBusy(True)
        self.statusChanged.emit()
        self.threadpool.start(Worker(self.performDbConnectionCheck))

    def performDbConnectionCheck(self):
        try:
            if hasattr(core, "connect_to_sql"):
                conn = core.connect_to_sql()
                conn.close()
            self.appendLog("Database connection successful.")
            self._status = "Database connection successful."
        except Exception as exc:
            self._status = "Cannot connect to database."
            self.appendLog(f"Database connection failed: {exc}")
        finally:
            self.setBusy(False)
            self.statusChanged.emit()

    def loadLastUpdated(self):
        try:
            doc_ref = core.firestore_db.collection("DB_Service").document("serverSideData")
            doc_dict = doc_ref.get(timeout=10).to_dict()
            ts = doc_dict.get("latestImportFromServer", None) if doc_dict else None  # type: ignore

            if isinstance(ts, datetime):
                dt = ts.astimezone(IST)
            elif isinstance(ts, str):
                dt = datetime.fromisoformat(ts).replace(tzinfo=pytz.utc).astimezone(IST)
            elif isinstance(ts, (int, float)):
                dt = datetime.utcfromtimestamp(ts / 1000).replace(tzinfo=pytz.utc).astimezone(IST)
            else:
                dt = None

            self._lastUpdated = dt.strftime("%d-%m-%Y %H:%M") if dt else "Unknown"
        except Exception as exc:
            print("Error in loadLastUpdated:", exc)
            self._lastUpdated = "Unknown"
        finally:
            self.lastUpdatedChanged.emit()

    @Slot()
    def clearAndUploadAll(self):
        self._status = "Clearing and uploading..."
        self.setBusy(True)
        self.statusChanged.emit()
        self._logs = []
        self.logChanged.emit()
        self.progressChanged.emit(0, 1)
        self.threadpool.start(Worker(self.performClearAndUpload))

    def performClearAndUpload(self):
        try:
            def log(message: str):
                print(message)
                self.appendLog(message)

            def on_progress(done: int, total: int):
                self.progressChanged.emit(done, total if total > 0 else 1)

            item_count, _image_count, now, _ = core.clear_and_full_upload(
                log_func=log,
                on_progress=on_progress,
            )
            dt = now.replace(tzinfo=pytz.utc).astimezone(IST)
            self._status = f"Uploaded {item_count} items"
            self._lastUpdated = dt.strftime("%d-%m-%Y %H:%M")
        except (KeyboardInterrupt, TimeoutError) as exc:
            self._status = f"Cancelled or timed out: {exc}"
            self.appendLog(f"⚠️ Rebuild interrupted: {exc}")
        except Exception as exc:
            traceback.print_exc()
            self._status = f"Error: {exc}"
            self.appendLog(str(exc))
        finally:
            self.setBusy(False)
            self.statusChanged.emit()
            self.lastUpdatedChanged.emit()

    def getStatus(self):
        return self._status

    status = Property(str, getStatus, notify=statusChanged)  # type: ignore

    def getIsBusy(self):
        return self._isBusy

    isBusy = Property(bool, getIsBusy, notify=isBusyChanged)  # type: ignore

    def getR2CancelRequested(self):
        return self._r2CancelRequested

    r2CancelRequested = Property(
        bool,
        getR2CancelRequested,
        notify=r2CancelRequestedChanged,
    )

    def getLastUpdated(self):
        return self._lastUpdated

    lastUpdated = Property(str, getLastUpdated, notify=lastUpdatedChanged)  # type: ignore

    def getLogs(self):
        return "\n".join(self._logs)

    logs = Property(str, getLogs, notify=logChanged)  # type: ignore

    @Slot()
    def copyLogs(self):
        QApplication.clipboard().setText(self.getLogs())

    def getBackupDatabases(self):
        return [
            item.as_dict(item.name in self._selectedBackupDatabases)
            for item in self._backupDatabases
        ]

    backupDatabases = Property(
        "QVariantList",
        getBackupDatabases,
        notify=backupDatabasesChanged,
    )  # type: ignore

    def getBackupCompanies(self):
        return backup_service.group_databases(
            self._backupDatabases,
            self._selectedBackupDatabases,
        )

    backupCompanies = Property(
        "QVariantList",
        getBackupCompanies,
        notify=backupDatabasesChanged,
    )  # type: ignore

    def getBackupDestination(self):
        return self._backupDestination

    def setBackupDestination(self, destination):
        cleaned = str(destination).strip()
        if self._backupDestination != cleaned:
            self._backupDestination = cleaned
            self.saveSettings()
            self.backupDestinationChanged.emit()

    backupDestination = Property(
        str,
        getBackupDestination,
        setBackupDestination,
        notify=backupDestinationChanged,
    )  # type: ignore

    def getBackupScheduleEnabled(self):
        return self._backupScheduleEnabled

    def setBackupScheduleEnabled(self, enabled):
        enabled = bool(enabled)
        if self._backupScheduleEnabled != enabled:
            self._backupScheduleEnabled = enabled
            settings_saved = self.saveSettings()
            if enabled:
                self.startBackupSchedule()
                if settings_saved:
                    self.setBackupStatus(
                        f"Daily backups scheduled at {self._backupScheduleTime} local time "
                        "while this app is running."
                    )
                self.appendBackupLog(
                    f"Daily backup schedule enabled for {self._backupScheduleTime} local time."
                )
            else:
                self.backupScheduleTimer.stop()
                if settings_saved:
                    self.setBackupStatus("Daily backup schedule disabled.")
                self.appendBackupLog("Daily backup schedule disabled.")
            self.backupScheduleEnabledChanged.emit()

    backupScheduleEnabled = Property(
        bool,
        getBackupScheduleEnabled,
        setBackupScheduleEnabled,
        notify=backupScheduleEnabledChanged,
    )  # type: ignore

    def getBackupScheduleTime(self):
        return self._backupScheduleTime

    def setBackupScheduleTime(self, schedule_time):
        cleaned = str(schedule_time).strip()
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", cleaned):
            self.setBackupStatus("Enter the daily backup time in 24-hour HH:mm format.")
            return
        if self._backupScheduleTime != cleaned:
            self._backupScheduleTime = cleaned
            self.saveSettings()
            if self._backupScheduleEnabled:
                self.startBackupSchedule()
            self.backupScheduleTimeChanged.emit()

    backupScheduleTime = Property(
        str,
        getBackupScheduleTime,
        setBackupScheduleTime,
        notify=backupScheduleTimeChanged,
    )  # type: ignore

    def getBackupStatus(self):
        return self._backupStatus

    backupStatus = Property(str, getBackupStatus, notify=backupStatusChanged)  # type: ignore

    def getBackupHistory(self):
        return "\n".join(reversed(self._backupHistory))

    backupHistory = Property(str, getBackupHistory, notify=backupHistoryChanged)  # type: ignore

    def getAttendanceHost(self):
        return self._attendanceHost

    attendanceHost = Property(str, getAttendanceHost, notify=attendanceConfigChanged)  # type: ignore

    def getAttendancePort(self):
        return self._attendancePort

    attendancePort = Property(int, getAttendancePort, notify=attendanceConfigChanged)  # type: ignore

    def getAttendanceScheduleEnabled(self):
        return self._attendanceScheduleEnabled

    attendanceScheduleEnabled = Property(
        bool,
        getAttendanceScheduleEnabled,
        setAttendanceScheduleEnabled,
        notify=attendanceScheduleEnabledChanged,
    )  # type: ignore

    def getAttendanceStatus(self):
        return self._attendanceStatus

    attendanceStatus = Property(
        str,
        getAttendanceStatus,
        notify=attendanceStatusChanged,
    )  # type: ignore

    def getAttendanceHistory(self):
        return "\n".join(reversed(self._attendanceHistory))

    attendanceHistory = Property(
        str,
        getAttendanceHistory,
        notify=attendanceHistoryChanged,
    )  # type: ignore

    def getAttendanceTodayRows(self):
        return self._attendanceTodayRows

    attendanceTodayRows = Property(
        "QVariantList",
        getAttendanceTodayRows,
        notify=attendanceTodayRowsChanged,
    )  # type: ignore

    def getAttendanceTodayCount(self):
        return len(self._attendanceTodayRows)

    attendanceTodayCount = Property(
        int,
        getAttendanceTodayCount,
        notify=attendanceTodayRowsChanged,
    )  # type: ignore

    def getAttendanceKeySaved(self):
        return attendance_service.has_communication_key(self._attendanceHost)

    attendanceKeySaved = Property(
        bool,
        getAttendanceKeySaved,
        notify=attendanceConfigChanged,
    )  # type: ignore

    def getR2AccountId(self):
        return self._r2AccountId

    r2AccountId = Property(str, getR2AccountId, notify=r2SettingsChanged)  # type: ignore

    def getR2BucketName(self):
        return self._r2BucketName

    r2BucketName = Property(str, getR2BucketName, notify=r2SettingsChanged)  # type: ignore

    def getR2AccessKeyId(self):
        return self._r2AccessKeyId

    r2AccessKeyId = Property(str, getR2AccessKeyId, notify=r2SettingsChanged)  # type: ignore

    def getR2UploadEnabled(self):
        return self._r2UploadEnabled

    r2UploadEnabled = Property(
        bool,
        getR2UploadEnabled,
        setR2UploadEnabled,
        notify=r2UploadEnabledChanged,
    )  # type: ignore

    def getAutoUpdateEnabled(self):
        return self._autoUpdateEnabled

    def setAutoUpdateEnabled(self, enabled):
        enabled = bool(enabled)
        if self._autoUpdateEnabled != enabled:
            self._autoUpdateEnabled = enabled
            self.saveSettings()
            if enabled:
                self.startAutoUpdate()
            else:
                self.stopAutoUpdate()
            self.autoUpdateEnabledChanged.emit()

    autoUpdateEnabled = Property(bool, getAutoUpdateEnabled, setAutoUpdateEnabled, notify=autoUpdateEnabledChanged)  # type: ignore

    def getAutoUpdateInterval(self):
        return self._autoUpdateInterval

    def setAutoUpdateInterval(self, interval):
        interval = int(interval)
        if interval > 0 and self._autoUpdateInterval != interval:
            self._autoUpdateInterval = interval
            self.saveSettings()
            if self._autoUpdateEnabled:
                self.stopAutoUpdate()
                self.startAutoUpdate()
            self.autoUpdateIntervalChanged.emit()

    autoUpdateInterval = Property(int, getAutoUpdateInterval, setAutoUpdateInterval, notify=autoUpdateIntervalChanged)  # type: ignore

    def setWindowsAutostart(self, enable):
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)

            if enable:
                command = self.getAutostartCommand()
                for legacy_key in LEGACY_RUN_KEYS:
                    try:
                        winreg.DeleteValue(key, legacy_key)
                    except FileNotFoundError:
                        pass
                winreg.SetValueEx(key, APP_RUN_KEY, 0, winreg.REG_SZ, command)
                self.appendLog(f"Startup on boot enabled: {command}")
            else:
                for legacy_key in LEGACY_RUN_KEYS:
                    try:
                        winreg.DeleteValue(key, legacy_key)
                    except FileNotFoundError:
                        pass
                self.appendLog("Startup on boot disabled")

            winreg.CloseKey(key)
            return True
        except Exception as exc:
            self.appendLog(f"Failed to set autostart: {exc}")
            return False

    def checkWindowsAutostart(self):
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
            expected_command = self.getAutostartCommand()
            for run_key in LEGACY_RUN_KEYS:
                try:
                    current_value, _ = winreg.QueryValueEx(key, run_key)
                    if run_key == APP_RUN_KEY and current_value == expected_command:
                        winreg.CloseKey(key)
                        return True
                except FileNotFoundError:
                    continue
            winreg.CloseKey(key)
            return False
        except Exception:
            return False

    def getAutostartEnabled(self):
        return self._autostartEnabled

    def setAutostartEnabled(self, enabled):
        enabled = bool(enabled)
        if self._autostartEnabled != enabled:
            self._autostartEnabled = enabled
            self.saveSettings()
            self.setWindowsAutostart(enabled)
            self.autostartEnabledChanged.emit()

    autostartEnabled = Property(bool, getAutostartEnabled, setAutostartEnabled, notify=autostartEnabledChanged)  # type: ignore

    def getDbServer(self):
        return self._dbServer

    def setDbServer(self, server):
        cleaned = str(server).strip()
        if cleaned and self._dbServer != cleaned:
            self._dbServer = cleaned
            core.SERVERNAME = cleaned
            self.saveSettings()
            self.appendLog(f"Database server saved: {cleaned}")
            self.dbServerChanged.emit()

    dbServer = Property(str, getDbServer, setDbServer, notify=dbServerChanged)  # type: ignore

    def getDbName(self):
        return self._dbName

    def setDbName(self, dbName):
        cleaned = str(dbName).strip()
        if cleaned and self._dbName != cleaned:
            self._dbName = cleaned
            core.DATABASENAME = cleaned
            self.saveSettings()
            self.appendLog(f"Database name saved: {cleaned}")
            self.dbNameChanged.emit()

    dbName = Property(str, getDbName, setDbName, notify=dbNameChanged)  # type: ignore

    @Slot(str, str)
    def saveDatabaseSettings(self, server, dbName):
        server = str(server).strip()
        dbName = str(dbName).strip()
        if not server or not dbName:
            self._status = "Database server and database name are required."
            self.statusChanged.emit()
            return

        changed = False
        if self._dbServer != server:
            self._dbServer = server
            core.SERVERNAME = server
            self.dbServerChanged.emit()
            changed = True
        if self._dbName != dbName:
            self._dbName = dbName
            core.DATABASENAME = dbName
            self.dbNameChanged.emit()
            changed = True

        self.saveSettings()
        self._status = "Database settings saved."
        self.statusChanged.emit()
        if changed:
            self.appendLog(f"Database settings saved to {SETTINGS_FILE}")
        else:
            self.appendLog("Database settings were already current.")

    def getAppVersion(self):
        return self._appVersion

    appVersion = Property(str, getAppVersion, notify=appVersionChanged)  # type: ignore

    def getLatestVersion(self):
        return self._latestVersion

    latestVersion = Property(str, getLatestVersion, notify=latestVersionChanged)  # type: ignore

    def getUpdateStatus(self):
        return self._updateStatus

    updateStatus = Property(str, getUpdateStatus, notify=updateStatusChanged)  # type: ignore

    def getUpdateAvailable(self):
        return self._updateAvailable

    updateAvailable = Property(bool, getUpdateAvailable, notify=updateAvailableChanged)  # type: ignore

    def fetchLatestRelease(self) -> dict[str, Any]:
        release = load_latest_release()
        tag_name = str(release.get("tag_name") or "").strip()
        latest_version = tag_name.lstrip("v") or APP_VERSION
        release_url = str(release.get("html_url") or self._releasePageUrl)
        is_newer = normalize_version(latest_version) > normalize_version(self._appVersion)
        return {
            "release": release,
            "latest_version": latest_version,
            "release_url": release_url,
            "is_newer": is_newer,
        }

    @Slot()
    def checkForUpdates(self):
        self.setUpdateState(status="Checking for updates...")
        self.threadpool.start(Worker(self.performCheckForUpdates))

    def performCheckForUpdates(self):
        try:
            result = self.fetchLatestRelease()
            latest_version = result["latest_version"]
            is_newer = result["is_newer"]
            release_url = result["release_url"]

            if is_newer:
                self.appendLog(f"Found update v{latest_version} on GitHub Releases.")
                status = f"Update available: v{latest_version}"
            else:
                self.appendLog("No newer GitHub release was found.")
                status = "You are on the latest release."

            self.setUpdateState(
                status=status,
                latest_version=latest_version,
                update_available=is_newer,
                release_url=release_url,
            )
        except Exception as exc:
            self.setUpdateState(status=f"Update check failed: {exc}", update_available=False)
            self.appendLog(f"Update check failed: {exc}")

    @Slot()
    def downloadAndInstallUpdate(self):
        self.setUpdateState(status="Downloading update...")
        self.threadpool.start(Worker(self.performDownloadAndInstallUpdate))

    def performDownloadAndInstallUpdate(self):
        try:
            result = self.fetchLatestRelease()
            release = result["release"]
            latest_version = result["latest_version"]
            release_url = result["release_url"]
            asset = choose_release_asset(list(release.get("assets") or []))

            if not asset:
                raise RuntimeError("No installer asset was found in the latest GitHub release.")

            download_url = str(asset.get("browser_download_url") or "")
            asset_name = str(asset.get("name") or "update-installer.exe")
            if not download_url:
                raise RuntimeError("The latest release asset does not include a download URL.")

            temp_dir = Path(tempfile.gettempdir()) / "ga-price-uploader-updates"
            temp_dir.mkdir(parents=True, exist_ok=True)
            target_path = temp_dir / asset_name

            request = urllib.request.Request(
                download_url,
                headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"},
            )
            with urllib.request.urlopen(request, timeout=60, context=get_ssl_context()) as response, open(target_path, "wb") as output_file:
                output_file.write(response.read())

            self.setUpdateState(
                status=f"Downloaded v{latest_version}. Launching installer...",
                latest_version=latest_version,
                update_available=result["is_newer"],
                release_url=release_url,
            )
            self.appendLog(f"Downloaded update installer to {target_path}")
            os.startfile(target_path)  # type: ignore[attr-defined]
            app = QApplication.instance()
            if app:
                QTimer.singleShot(1500, app.quit)
        except Exception as exc:
            self.setUpdateState(status=f"Update download failed: {exc}")
            self.appendLog(f"Update download failed: {exc}")

    @Slot()
    def openReleasePage(self):
        webbrowser.open(self._releasePageUrl)

    @Slot()
    def showWindow(self):
        if self.qmlWindow:
            self.qmlWindow.show()
            self.qmlWindow.raise_()
            self.qmlWindow.requestActivate()

    @Slot()
    def hideWindow(self):
        if self.qmlWindow:
            self.qmlWindow.hide()

    @Slot()
    def toggleWindow(self):
        if self.qmlWindow:
            if self.qmlWindow.isVisible():
                self.hideWindow()
            else:
                self.showWindow()

    def setupTrayIcon(self, app):
        self.trayIcon = QSystemTrayIcon(app)
        base_path = get_base_path()
        icon_path = base_path / "icons" / "Price List Backend Quenry v2.ico"
        if icon_path.exists():
            self.trayIcon.setIcon(QIcon(str(icon_path)))
        else:
            self.trayIcon.setIcon(app.style().standardIcon(app.style().SP_ComputerIcon))

        tray_menu = QMenu()

        show_action = QAction("Show", app)
        show_action.triggered.connect(self.showWindow)
        tray_menu.addAction(show_action)

        sync_action = QAction("Sync Now", app)
        sync_action.triggered.connect(self.upload)
        tray_menu.addAction(sync_action)

        update_action = QAction("Check for Updates", app)
        update_action.triggered.connect(self.checkForUpdates)
        tray_menu.addAction(update_action)

        tray_menu.addSeparator()

        quit_action = QAction("Quit", app)
        quit_action.triggered.connect(app.quit)
        tray_menu.addAction(quit_action)

        self.trayIcon.setContextMenu(tray_menu)
        self.trayIcon.activated.connect(self.onTrayIconActivated)
        self.trayIcon.setToolTip(APP_NAME)
        self.trayIcon.show()

    def onTrayIconActivated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,  # type: ignore[attr-defined]
            QSystemTrayIcon.ActivationReason.Trigger,  # type: ignore[attr-defined]
        ):
            self.toggleWindow()

    @Slot()
    def upload(self):
        if self._isBusy:
            return
        self._status = "Uploading..."
        self.setBusy(True)
        self.progressChanged.emit(0, 0)
        self.statusChanged.emit()
        self.threadpool.start(Worker(self.performUpload))

    def performUpload(self):
        try:
            item_count, image_count, now, logs = core.run_sync()
            dt = now.replace(tzinfo=pytz.utc).astimezone(IST)
            self._status = f"Success: {item_count} items, {image_count} images"
            self._lastUpdated = dt.strftime("%d-%m-%Y %H:%M")
            self._logs = logs
        except (KeyboardInterrupt, TimeoutError) as exc:
            self._status = f"Cancelled or timed out: {exc}"
            self.appendLog(f"⚠️ Sync interrupted: {exc}")
        except Exception as exc:
            traceback.print_exc()
            self._status = f"Error: {exc}"
            self.appendLog(str(exc))
        finally:
            self.setBusy(False)
            self.statusChanged.emit()
            self.lastUpdatedChanged.emit()
            self.logChanged.emit()


class Worker(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        self.fn()


if __name__ == "__main__":
    start_in_tray = AUTOSTART_ARGUMENT in sys.argv
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    base_path = get_base_path()
    font_dir = base_path / "fonts"
    if font_dir.exists():
        for font_file in [
            "Poppins-Regular.ttf",
            "Poppins-Medium.ttf",
            "Poppins-SemiBold.ttf",
            "Poppins-Bold.ttf",
        ]:
            font_path = font_dir / font_file
            if font_path.exists():
                QFontDatabase.addApplicationFont(str(font_path))

    app.setWindowIcon(QIcon(str(base_path / "icons" / "Price List Backend Quenry v2.ico")))

    engine = QQmlApplicationEngine()
    win = MainWindow()
    engine.rootContext().setContextProperty("backend", win)
    engine.load((base_path / "GUI" / "main.qml").as_posix())

    if not engine.rootObjects():
        sys.exit(-1)

    win.qmlWindow = engine.rootObjects()[0]
    if start_in_tray and win.qmlWindow:
        win.qmlWindow.hide()
        win._wasVisible = False

    def on_progress_changed(done, total):
        if win.qmlWindow:
            win.qmlWindow.setProperty("currentValue", done)
            win.qmlWindow.setProperty("maxValue", total)

    win.progressChanged.connect(on_progress_changed)
    win.setupTrayIcon(app)

    def on_visibility_changed():
        is_visible = win.qmlWindow.isVisible()  # type: ignore[union-attr]
        if win._wasVisible and not is_visible:
            win.trayIcon.showMessage(
                APP_NAME,
                "App minimized to system tray",
                QSystemTrayIcon.MessageIcon.Information,  # type: ignore[attr-defined]
                2000,
            )
        win._wasVisible = is_visible

    win.qmlWindow.visibilityChanged.connect(on_visibility_changed)  # type: ignore[union-attr]

    def delayed_setup():
        core.SERVERNAME = win._dbServer
        core.DATABASENAME = win._dbName
        win.threadpool.start(Worker(win.loadLastUpdated))
        win.checkDbConnection()
        win.checkForUpdates()
        if win._autostartEnabled != win.checkWindowsAutostart():
            win.setWindowsAutostart(win._autostartEnabled)

    QTimer.singleShot(500, delayed_setup)
    sys.exit(app.exec())
