# Price-List-Query-Backend
Backend for the price list web site

GOTO https://www.pythonguis.com/ to know about build process

## TODO
- add settings.json to edit dblocation
- add automatic sync settings
- add Number of items updated toast/info to be shown after updating.
- add option to enter custom time
- add option to update or rewrite whole db
- add option to image rewrite.

## SQL Express Backups

The desktop app has a separate **SQL Backups** tab. Refresh the database list to find
online user databases named `BusyCompNNNN_db1YYYY`. The company label comes from
`dbo.Company.Name` in the matching base database (`BusyCompNNNN_db`), falling back
to the year database if that base database is not present. The `YYYY` suffix
identifies a financial year from `YYYY` to `YYYY+1`. Companies appear as expandable
groups in the selector: selecting a company selects every year under it; expand it
to select individual years. A company with only some years selected shows a
partially-selected checkbox. Each selected year creates a full SQL Server `.bak`
file; every file contains the entire selected database.
The year row also shows the database's allocated SQL data-plus-log file size as
reported by SQL Server. This is a planning reference; the resulting `.bak` size
can differ.

SQL Server writes the `.bak` file to an absolute local folder on the same computer,
for example `C:\SQLBackups`. Create the folder first and grant the SQL Express
service account write access. Use **Check Folder** to confirm SQL Server can see
the destination. A successful backup and checksum verification confirms that SQL
Server could write and read the backup. If Cloudflare R2 uploads are enabled, the
app must also be able to read the completed backup at that path. The Windows
account used by the app must be allowed to enumerate SQL databases, read the
company metadata, and run SQL Server backups.

The daily backup schedule uses the computer's local time and runs while the app
process is running (it can remain minimized to the system tray). If the app is not
running at the scheduled time, that day's run is skipped. Use the existing
**Start on boot** setting if the app should launch minimized when Windows starts.

### Uploading backups to Cloudflare R2

The app can optionally upload SQL-verified backups to a private Cloudflare R2
bucket. It uses Cloudflare's S3-compatible API and multipart upload support. For
each upload session, it first prepares every selected backup locally and totals
their sizes. If the session alone would reach 10,000,000,000 bytes (10 GB
decimal), the session is canceled and the prepared local backups are retained.
The app then checks the whole bucket. If the session would make the bucket reach
10 GB, it clears existing objects under the configured SQL-backup prefix (default
`sql-backups/`) and verifies the remaining bucket has room. Objects outside that
prefix are never cleared. If the session still would not fit below 10 GB, it is
canceled. The bucket size is checked again after each upload; a newly uploaded
object is removed if a concurrent change causes the cap to be reached. A live
per-file progress bar is displayed during transfer.

1. In Cloudflare, create an R2 bucket and an R2 API token restricted to that bucket
   with permission to list the bucket and read/write objects (needed to total
   storage, upload backups, and remove a newly uploaded object if the cap is
   exceeded). Keep the token's secret private; do not put it in source code or
   send it in chat.
2. In the app's **Cloudflare R2 Upload** section, enter the Cloudflare Account ID,
   bucket name, Access Key ID, and Secret Access Key. Choose **Save R2 Settings**;
   the secret is saved in the current Windows user's Credential Manager, not in
   the app's JSON settings file.
3. Choose **Test R2 Connection**. After it succeeds, enable R2 upload. Each
   selected backup is written and verified locally before any file in the session
   is uploaded. After an individual upload succeeds and is verified, its local
   `.bak` is deleted. A failed upload keeps its local `.bak`; if a later upload
   fails, local files for earlier successful uploads have already been deleted.
   The error is shown in backup history.
4. The app process must be able to read each completed `.bak` file. Grant the app's
   Windows account read access to the configured backup folder, and grant the SQL
   Server service account write access.
5. Objects are stored under
   `sql-backups/BusyCompNNNN/FY<start year>-<end year>/<backup filename>` (for
   example, `FY2026-2027`). The R2 bucket remains private.

When the bucket needs space, the app deletes all existing objects under the
configured SQL-backup prefix before uploading the new session; keep copies of
older backups elsewhere if they must be retained. R2 account storage and operation
quotas/pricing are set by Cloudflare; monitor usage in the Cloudflare dashboard.
The app enforces a strict below-10-GB current bucket-size ceiling for its uploads;
this is not a calculation of Cloudflare's monthly average storage usage or a
guarantee about billing/free-tier eligibility.

R2 account ID, bucket, access key ID, and upload preference are per-user app
settings. The secret lives in that Windows user's Credential Manager; production
must run under the same Windows account that saved the R2 secret. If the Windows
user changes, save the R2 secret again under the production account.

## eTimeTrackLite K90 Pro attendance import

The **Attendance Import** tab connects directly from the Windows app computer to
the K90 Pro over the local TCP/IP network. Keep the machine reachable on the same
LAN and allow the configured TCP port (default `4370`) between that computer and
the terminal. The port and communication key must match the machine's network
settings.

Enter the machine IP address and port, optionally enter its numeric communication
key, and save. The fixed automatic schedule runs every 10 minutes from 8:00 AM
through 11:00 AM, then every hour on the hour, using the computer's local time.
The communication key is stored in the current Windows user's Credential Manager;
only the address, port, and schedule preference are stored in app settings. Test
the connection before enabling the schedule. Automatic imports run only while the
app process is running and are independent of price-list sync.
The Attendance Import tab keeps device/schedule fields under a collapsible
Settings control, shows transfer progress during imports, and displays the
current local day's imported attendance rows after a successful import.

The importer reads device name/serial/firmware/network metadata, user IDs and
basic employee fields, and attendance timestamps/status/punch values. It does
not change the machine, upload passwords, or read/upload fingerprint templates.
Records are written to the existing Firestore project in:

- `attendance_devices` — one document per device
- `attendance_employees` — device-scoped employee records
- `attendance_logs` — device-scoped attendance records
- `attendance_sync_state` — incremental import checkpoint and last-run metadata

Attendance document IDs are deterministic. Each import rechecks a 24-hour overlap
before the last successful attendance timestamp, checks those IDs in Firestore,
and writes only attendance documents that do not already exist. The checkpoint
advances only after all data writes succeed. Employee records are refreshed to
pick up changes; device metadata is also updated. Attendance older than 365 days
or dated in the future is ignored, so an invalid device clock cannot advance the
checkpoint beyond current records.

The PyZK `get_attendance()` API reads the terminal's attendance list as a whole;
it does not expose a server-side cursor for fetching only records after a
checkpoint. The importer filters to the checkpoint overlap and prevents
re-uploading existing attendance documents, but the device protocol/library still
transfers the stored attendance list to the app on each run. Keep the terminal's
retained-log volume in mind if network read time becomes an issue.

This feature uses PyZK, an unofficial GPL-2.0 library for ZK-family attendance
devices, rather than an official K90 Pro SDK. Its documented API includes device
information, users, and attendance reads, but this exact K90 Pro firmware has
not been tested from this app. Use **Test Connection** and confirm the imported
records before relying on automatic sync. Do not expose the device's TCP port to
the public internet. See [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) and
review the GPL-2.0 source and redistribution obligations before distributing a
bundled application.

Run the focused tests with `python -m unittest discover -s tests -v`.

## Release Flow
- Trigger the `Version Bump` GitHub Actions workflow.
- That workflow updates `app_version.py` and `installer.nsi`, commits the change, and creates the matching `vX.Y.Z` tag.
- Pushing that tag automatically triggers `Build Windows Release`.
- `Build Windows Release` builds versioned portable and installer files (for example, `Price List Update v1.2.3.exe` and `Price List Update v1.2.3-installer.exe`), then uploads them to the GitHub release for that tag. The installed application filename remains `Price List Update.exe` across releases. The installer requests administrator elevation when launched; the portable executable does not require installation.
