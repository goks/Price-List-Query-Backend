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

Enter the HomeServer destination as a UNC path, for example
`\\HomeServer\SQLBackups`, and use **Check Share** to confirm that the SQL Server
host can see the folder. The share and folder must already exist. Grant the SQL
Express service account on the database host write access to the share and its
folder; access available only to the desktop user's Windows account is not enough.
The Windows account used by the app must also be allowed to enumerate the SQL
databases, read the company metadata, and run SQL Server backups. The folder check
confirms visibility, while a successful backup and checksum verification confirms
that SQL Server could write and read the backup.

### Connecting a remote HomeServer over Tailscale

The SQL Server host performs the file write. Tailscale must therefore connect the
machine running SQL Express to the machine or VM that hosts the SMB share; having
Tailscale only on the desktop UI is not enough.

1. Install and sign in to Tailscale on the SQL Express host and on the Proxmox guest
   or NAS that serves SMB. Prefer installing Tailscale on the file-server guest,
   rather than exposing SMB on the Proxmox management host.
2. In your Tailscale admin console, allow those devices to reach each other on SMB
   (TCP port 445). Do not expose port 445 to the public internet.
3. Create an SMB share and folder on the HomeServer, and grant write/read access
   to an account that the SQL Server service can authenticate as. Tailscale gives
   the network route; it does not provide SMB credentials. The desktop user's
   mapped drive or login is not automatically used by SQL Server. Use an
   appropriate service/domain identity recognized by the file server, or configure
   credentials for the SQL Server service identity using your Windows/NAS account
   management policy.
4. From the SQL host, verify the share is reachable over Tailscale. Enter a UNC
   path in the app, such as `\\100.x.y.z\SQLBackups` using the HomeServer guest's
   Tailscale IP, or `\\<tailnet-device-name>\SQLBackups` if MagicDNS resolves that
   name on the SQL host.
5. In **SQL Backups**, choose **Check Share**. This checks the folder from SQL
   Server's point of view. Then run one manual backup and confirm the `.bak` file
   and checksum verification before relying on the daily schedule.

Cloudflare Tunnel is for supported web/HTTP or private-network access patterns;
it is not a direct SMB tunnel. For this app's UNC backup destination, use
Tailscale between the SQL host and the SMB file server. Do not publish SMB through
a public Cloudflare hostname or expose its port on the router.

The daily schedule uses the desktop's local time and runs while the app process is
running (it can remain minimized to the system tray). If the app is not running at
the scheduled time, that day's run is skipped. Use the existing **Start on boot**
setting if the app should launch minimized when Windows starts. No network
SMB credentials are stored by the app; configure share access through Windows.

### Uploading backups to Cloudflare R2

The app can optionally upload each completed and SQL-verified backup to a private
Cloudflare R2 bucket. It uses Cloudflare's S3-compatible API and multipart upload
support. The app checks total usage across the entire selected bucket before each
upload and blocks an upload if its projected total would exceed 10,000,000,000
bytes (10 GB decimal). It checks again after upload; if a race pushes usage above
the limit, it removes the newly uploaded object and reports failure. A live
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
3. Choose **Test R2 Connection**. After it succeeds, enable R2 upload. Each new
   backup is first written and verified at the configured backup destination,
   then uploaded. If an upload fails, the local `.bak` remains in place and the
   error is shown in backup history.
4. The app process must be able to read each completed `.bak` file. For testing,
   this means the desktop user needs read access to the configured share. In
   production, run the app under the intended Windows user on the SQL Server
   machine and configure a backup path that the app can read there. SQL Server
   still needs its own permission to write to the backup destination.
5. Objects are stored under
   `sql-backups/BusyCompNNNN/FY<start year>-<end year>/<backup filename>` (for
   example, `FY2026-2027`). The R2 bucket remains private.
   The HomeServer can pull these objects with an S3-compatible client such as
   `rclone`, using a separate bucket-restricted read-only token. For example,
   after configuring an `rclone` remote named `r2`, run
   `rclone copy r2:<bucket-name>/sql-backups /path/to/sql-backups` on the
   HomeServer. Protect that token and the rclone configuration on the HomeServer.

The uploader does not delete local backups or old R2 objects. Configure an
appropriate retention policy separately after validating your restore process.
R2 account storage and operation quotas/pricing are set by Cloudflare; monitor
usage in the Cloudflare dashboard. The app enforces a 10 GB current bucket-size
ceiling for its uploads; this is not a calculation of Cloudflare's monthly
average storage usage or a guarantee about billing/free-tier eligibility.

R2 account ID, bucket, access key ID, and upload preference are per-user app
settings. The secret lives in that Windows user's Credential Manager; production
must run under the same Windows account that saved the R2 secret. If the Windows
user changes, save the R2 secret again under the production account.

Run the focused backup tests with `python -m unittest discover -s tests -v`.

## Release Flow
- Trigger the `Version Bump` GitHub Actions workflow.
- That workflow updates `app_version.py` and `installer.nsi`, commits the change, and creates the matching `vX.Y.Z` tag.
- Pushing that tag automatically triggers `Build Windows Release`.
- `Build Windows Release` builds `dist/Price List Update.exe` and `Price List Update-installer.exe`, then uploads them to the GitHub release for that tag.
