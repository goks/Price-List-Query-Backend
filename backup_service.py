import ntpath
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional

import pyodbc


DATABASE_PATTERN = re.compile(
    r"^BusyComp(?P<company>\d{4})_db1(?P<year>\d{4})$",
    re.IGNORECASE,
)


class BackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackupDatabase:
    name: str
    company_code: str
    company_name: str
    financial_year: str
    size_mb: float = 0.0

    @property
    def key(self) -> str:
        return self.name

    def as_dict(self, selected: bool = False) -> dict[str, object]:
        return {
            "key": self.key,
            "name": self.name,
            "companyCode": self.company_code,
            "companyName": self.company_name,
            "financialYear": self.financial_year,
            "selected": selected,
        }


def group_databases(
    databases: list[BackupDatabase],
    selected_database_names: set[str],
) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    years_by_company: dict[str, list[dict[str, object]]] = {}
    for database in databases:
        years_by_company.setdefault(database.company_code, []).append(
            {
                "key": database.key,
                "name": database.name,
                "financialYear": database.financial_year,
                "size": format_database_size(database.size_mb),
                "selected": database.name in selected_database_names,
            }
        )

    for database in databases:
        if database.company_code in grouped:
            continue
        years = years_by_company[database.company_code]
        selected_count = sum(bool(year["selected"]) for year in years)
        grouped[database.company_code] = {
            "companyCode": database.company_code,
            "companyName": database.company_name,
            "selected": bool(years) and selected_count == len(years),
            "partiallySelected": 0 < selected_count < len(years),
            "financialYears": years,
        }
    return list(grouped.values())


def format_database_size(size_mb: float) -> str:
    if size_mb >= 1024:
        return f"{size_mb / 1024:.2f} GB"
    return f"{size_mb:.0f} MB"


def parse_database_name(database_name: str) -> Optional[tuple[str, int]]:
    match = DATABASE_PATTERN.fullmatch(database_name.strip())
    if not match:
        return None

    year = int(match.group("year"))
    if year >= 9999:
        return None
    return match.group("company"), year


def milliseconds_until_daily_time(now: datetime, schedule_time: str) -> int:
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", schedule_time):
        raise BackupError("Daily backup time must use 24-hour HH:mm format.")
    hour, minute = (int(part) for part in schedule_time.split(":"))
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return max(1, int((next_run - now).total_seconds() * 1000))


def connection_string(server: str) -> str:
    cleaned_server = server.strip()
    if not cleaned_server:
        raise BackupError("SQL Server name is required.")
    escaped_server = cleaned_server.replace("}", "}}")
    return (
        "Driver={SQL Server};"
        f"Server={{{escaped_server}}};"
        "Database=master;"
        "Trusted_Connection=yes;"
        "Connection Timeout=10;"
    )


def _connect(server: str, connect: Callable = pyodbc.connect):
    return connect(connection_string(server), timeout=10)


def discover_databases(
    server: str,
    connect: Callable = pyodbc.connect,
) -> tuple[list[BackupDatabase], list[str]]:
    connection = _connect(server, connect)
    databases: list[BackupDatabase] = []
    issues: list[str] = []

    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT d.name, COALESCE(SUM(mf.size), 0) * 8.0 / 1024 AS size_mb "
            "FROM sys.databases AS d "
            "LEFT JOIN sys.master_files AS mf ON mf.database_id = d.database_id "
            "WHERE d.database_id > 4 AND d.state_desc = N'ONLINE' "
            "AND d.source_database_id IS NULL "
            "GROUP BY d.name ORDER BY d.name"
        )
        database_rows = cursor.fetchall()
        database_names = [str(row[0]) for row in database_rows]
        database_sizes = {
            str(row[0]).casefold(): float(row[1] or 0)
            for row in database_rows
        }
        matching_names = [
            name for name in database_names
            if parse_database_name(name) is not None
        ]
        databases_by_folded_name = {
            name.casefold(): name for name in database_names
        }
        company_names: dict[str, Optional[str]] = {}

        for database_name in matching_names:
            parsed = parse_database_name(database_name)
            if parsed is None:
                continue
            company_code, start_year = parsed
            if company_code not in company_names:
                base_database = databases_by_folded_name.get(
                    f"BusyComp{company_code}_db".casefold()
                )
                metadata_database = base_database or database_name
                escaped_metadata_database = metadata_database.replace("]", "]]")
                try:
                    cursor.execute(
                        "SELECT DISTINCT TOP (2) "
                        "LTRIM(RTRIM(CONVERT(nvarchar(255), [Name]))) "
                        f"FROM [{escaped_metadata_database}].dbo.[Company] "
                        "WHERE [Name] IS NOT NULL "
                        "AND LTRIM(RTRIM(CONVERT(nvarchar(255), [Name]))) <> N''"
                    )
                    found_company_names = [
                        str(row[0]).strip() for row in cursor.fetchall()
                    ]
                    if len(found_company_names) != 1:
                        issues.append(
                            f"{database_name}: expected one company name in "
                            f"{metadata_database}.dbo.Company.Name; "
                            f"found {len(found_company_names)}."
                        )
                        company_names[company_code] = None
                    else:
                        company_names[company_code] = found_company_names[0]
                except Exception as exc:
                    issues.append(
                        f"{database_name}: could not read company metadata from "
                        f"{metadata_database}.dbo.Company.Name ({exc})."
                    )
                    company_names[company_code] = None

            company_name = company_names[company_code]
            if company_name is None:
                continue
            databases.append(
                BackupDatabase(
                    name=database_name,
                    company_code=company_code,
                    company_name=company_name,
                    financial_year=f"{start_year}-{start_year + 1}",
                    size_mb=database_sizes.get(database_name.casefold(), 0.0),
                )
            )

        if not matching_names:
            issues.append(
                "No online user databases match BusyCompNNNN_db1YYYY."
            )
        databases.sort(
            key=lambda item: (
                item.company_name.casefold(),
                item.company_code,
                item.financial_year,
            )
        )
        return databases, issues
    finally:
        connection.close()


def _require_backup_directory(path: str) -> str:
    cleaned_path = path.strip().replace("/", "\\")
    drive, tail = ntpath.splitdrive(cleaned_path)
    path_parts = cleaned_path.split("\\")
    is_unc_path = drive.startswith("\\\\")
    if is_unc_path:
        share_parts = drive[2:].split("\\")
        is_valid_path = (
            len(share_parts) == 2
            and bool(share_parts[0])
            and bool(share_parts[1])
            and (not tail or tail.startswith("\\"))
        )
    else:
        is_valid_path = (
            re.fullmatch(r"[A-Za-z]:", drive) is not None
            and tail.startswith("\\")
        )

    if not cleaned_path or not is_valid_path or ".." in path_parts:
        raise BackupError(
            "Enter an absolute path on the SQL Server host (for example "
            "C:\\SQLBackups) or a UNC share path (for example "
            "\\\\HomeServer\\SQLBackups)."
        )
    return ntpath.normpath(cleaned_path)


def _verify_server_directory(cursor, path: str) -> None:
    cursor.execute("EXEC master.dbo.xp_fileexist ?", path)
    result = cursor.fetchone()
    if result is None or len(result) < 2 or not bool(result[1]):
        raise BackupError(
            "SQL Server cannot see the destination folder. Confirm the path "
            "exists on the SQL Server host and that its service account can access it."
        )


def _report_sql_messages(
    cursor,
    message_callback: Optional[Callable[[str], None]],
    operation: str,
) -> None:
    if message_callback is None:
        return
    for message in getattr(cursor, "messages", ()) or ():
        if isinstance(message, tuple) and len(message) > 1:
            message_text = str(message[1]).strip()
        else:
            message_text = str(message).strip()
        if message_text:
            message_callback(f"{operation}: {message_text}")


def check_destination(
    server: str,
    destination: str,
    connect: Callable = pyodbc.connect,
) -> str:
    path = _require_backup_directory(destination)
    connection = _connect(server, connect)
    try:
        cursor = connection.cursor()
        _verify_server_directory(cursor, path)
        return (
            "SQL Server can see this folder. Write permission is confirmed "
            "when a backup completes."
        )
    finally:
        connection.close()


def create_full_backup(
    server: str,
    database_name: str,
    destination: str,
    now: Optional[datetime] = None,
    connect: Callable = pyodbc.connect,
    message_callback: Optional[Callable[[str], None]] = None,
) -> str:
    parsed = parse_database_name(database_name)
    if parsed is None:
        raise BackupError("The selected database name is not a supported company/year database.")

    path = _require_backup_directory(destination)
    company_code, start_year = parsed
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S_%f")
    filename = f"BusyComp{company_code}_FY{start_year}-{start_year + 1}_{timestamp}.bak"
    backup_path = ntpath.join(path, filename)
    escaped_name = database_name.replace("]", "]]")

    connection = _connect(server, connect)
    try:
        cursor = connection.cursor()
        _verify_server_directory(cursor, path)
        try:
            cursor.execute(
                "DECLARE @backupPath nvarchar(4000) = ?; "
                f"BACKUP DATABASE [{escaped_name}] TO DISK = @backupPath "
                "WITH COPY_ONLY, INIT, CHECKSUM;",
                backup_path,
            )
        except pyodbc.Error as exc:
            _report_sql_messages(cursor, message_callback, "BACKUP DATABASE")
            if message_callback is not None:
                message_callback(f"BACKUP DATABASE error: {exc}")
            raise BackupError(
                f"BACKUP DATABASE failed for {backup_path}: {exc}"
            ) from exc
        _report_sql_messages(cursor, message_callback, "BACKUP DATABASE")

        try:
            cursor.execute(
                "DECLARE @backupPath nvarchar(4000) = ?; "
                "RESTORE VERIFYONLY FROM DISK = @backupPath WITH CHECKSUM;",
                backup_path,
            )
        except pyodbc.Error as exc:
            _report_sql_messages(cursor, message_callback, "RESTORE VERIFYONLY")
            if message_callback is not None:
                message_callback(f"RESTORE VERIFYONLY error: {exc}")
            raise BackupError(
                "RESTORE VERIFYONLY failed for "
                f"{backup_path}: {exc}"
            ) from exc
        _report_sql_messages(cursor, message_callback, "RESTORE VERIFYONLY")
        return backup_path
    finally:
        connection.close()
