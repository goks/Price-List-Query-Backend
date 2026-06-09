import json
import os
import re
import ssl
import sys
import tempfile
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
                if source_path == LEGACY_SETTINGS_FILE and source_path != SETTINGS_FILE:
                    self.saveSettings()
        except Exception as exc:
            print(f"Error loading settings: {exc}")

    def saveSettings(self):
        try:
            settings = {
                "enabled": self._autoUpdateEnabled,
                "interval": self._autoUpdateInterval,
                "autostart": self._autostartEnabled,
                "dbServer": self._dbServer,
                "dbName": self._dbName,
            }
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as handle:
                json.dump(settings, handle, indent=2)
        except Exception as exc:
            print(f"Error saving settings: {exc}")

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

    def getLastUpdated(self):
        return self._lastUpdated

    lastUpdated = Property(str, getLastUpdated, notify=lastUpdatedChanged)  # type: ignore

    def getLogs(self):
        return "\n".join(self._logs)

    logs = Property(str, getLogs, notify=logChanged)  # type: ignore

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
