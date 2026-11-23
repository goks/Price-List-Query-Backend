import unittest
from unittest import mock

import backup_service


class BackupPathValidationTests(unittest.TestCase):
    def test_accepts_local_absolute_windows_path(self):
        self.assertEqual(
            backup_service._require_backup_directory("  C:/SQLBackups  "),
            "C:\\SQLBackups",
        )

    def test_accepts_unc_share_path(self):
        self.assertEqual(
            backup_service._require_backup_directory(
                "\\\\HomeServer\\SQLBackups"
            ),
            "\\\\HomeServer\\SQLBackups",
        )

    def test_rejects_relative_and_traversal_paths(self):
        for path in (
            "",
            "SQLBackups",
            "C:SQLBackups",
            "C:\\SQLBackups\\..\\Other",
            "\\\\HomeServer\\SQLBackups\\..\\Other",
            "\\\\HomeServer",
        ):
            with self.subTest(path=path):
                with self.assertRaises(backup_service.BackupError):
                    backup_service._require_backup_directory(path)


class BackupDestinationTests(unittest.TestCase):
    class Cursor:
        """Fake cursor whose canned responses are keyed by statement text."""

        def __init__(
            self,
            fetchone_results=None,
            message_results=None,
            execute_errors=None,
        ):
            self.executed = []
            self.fetchone_results = list(fetchone_results or [(0, 1, 0)])
            self.message_results = dict(message_results or {})
            self.execute_errors = dict(execute_errors or {})
            self.messages = []

        @staticmethod
        def _lookup(mapping, query, default):
            for needle, value in mapping.items():
                if needle in query:
                    return value
            return default

        def execute(self, query, *parameters):
            self.executed.append((query, parameters))
            self.messages = list(self._lookup(self.message_results, query, []))
            error = self._lookup(self.execute_errors, query, None)
            if isinstance(error, list):
                error = error.pop(0) if error else None
            if error is not None:
                raise error

        def fetchone(self):
            query = self.executed[-1][0]
            if "@@SPID" in query:
                return (55,)
            if "HAS_PERMS_BY_NAME" in query:
                return (1,)
            if "sys.dm_exec_requests" in query:
                return (0,)
            return self.fetchone_results.pop(0)

        def statements(self):
            return [query for query, _parameters in self.executed]

    class Connection:
        def __init__(
            self,
            fetchone_results=None,
            message_results=None,
            execute_errors=None,
        ):
            self.cursor_instance = BackupDestinationTests.Cursor(
                fetchone_results,
                message_results,
                execute_errors,
            )
            self.closed = False
            self.autocommit = False

        def cursor(self):
            return self.cursor_instance

        def close(self):
            self.closed = True

    @staticmethod
    def statement(statements, prefix):
        return next(query for query in statements if query.startswith(prefix))

    def test_check_accepts_local_path_on_sql_host(self):
        connection = self.Connection()

        message = backup_service.check_destination(
            ".\\SQLEXPRESS",
            "D:\\SQLBackups",
            connect=lambda *_args, **_kwargs: connection,
        )

        self.assertIn("SQL Server can see this folder", message)
        self.assertEqual(
            connection.cursor_instance.executed[0][1],
            ("D:\\SQLBackups",),
        )
        self.assertTrue(connection.closed)

    def test_backup_uses_local_server_path(self):
        connection = self.Connection()

        backup_path = backup_service.create_full_backup(
            ".\\SQLEXPRESS",
            "BusyComp0001_db12026",
            "D:\\SQLBackups",
            connect=lambda *_args, **_kwargs: connection,
        )

        self.assertTrue(backup_path.startswith("D:\\SQLBackups\\"))
        statements = connection.cursor_instance.statements()
        self.assertIn(
            ("D:\\SQLBackups",),
            [
                parameters for query, parameters in connection.cursor_instance.executed
                if query.startswith("EXEC master.dbo.xp_fileexist")
            ],
        )
        self.assertIn(
            f"TO DISK = N'{backup_path}'",
            self.statement(statements, "BACKUP DATABASE"),
        )
        self.assertIn(
            f"FROM DISK = N'{backup_path}'",
            self.statement(statements, "RESTORE VERIFYONLY"),
        )
        self.assertTrue(connection.closed)

    def test_backup_escapes_quotes_in_sql_path_literal(self):
        connection = self.Connection()

        backup_path = backup_service.create_full_backup(
            ".\\SQLEXPRESS",
            "BusyComp0001_db12026",
            "D:\\SQL's Backups",
            connect=lambda *_args, **_kwargs: connection,
        )

        escaped_literal = "N'" + backup_path.replace("'", "''") + "'"
        for query, parameters in connection.cursor_instance.executed:
            if not query.startswith(("BACKUP DATABASE", "RESTORE VERIFYONLY")):
                continue
            self.assertEqual(parameters, ())
            self.assertIn(escaped_literal, query)
        self.assertTrue(connection.closed)

    def test_backup_runs_each_command_as_its_own_batch(self):
        connection = self.Connection()

        backup_service.create_full_backup(
            ".\\SQLEXPRESS",
            "BusyComp0001_db12026",
            "D:\\SQLBackups",
            connect=lambda *_args, **_kwargs: connection,
        )

        statements = connection.cursor_instance.statements()
        for prefix in ("BACKUP DATABASE", "RESTORE VERIFYONLY"):
            query = self.statement(statements, prefix)
            # pyodbc frees the previous statement before the next execute(), which
            # cancels the still-running later statements of a batch.
            self.assertEqual(query.count(";"), 1, query)
            self.assertNotIn("DECLARE", query)
        self.assertTrue(connection.autocommit)

    def test_backup_verifies_on_a_second_connection_after_sql_server_finishes(self):
        connections = []

        def connect(*_args, **_kwargs):
            connections.append(self.Connection())
            return connections[-1]

        backup_service.create_full_backup(
            ".\\SQLEXPRESS",
            "BusyComp0001_db12026",
            "D:\\SQLBackups",
            connect=connect,
        )

        backup_connection, verify_connection = connections
        self.assertIsNot(backup_connection, verify_connection)
        self.assertTrue(
            backup_connection.cursor_instance.statements()[-1].startswith(
                "BACKUP DATABASE"
            )
        )
        # The backup statement must be left alone until SQL Server reports that
        # the session has no active request left.
        verify_statements = verify_connection.cursor_instance.statements()
        self.assertIn("HAS_PERMS_BY_NAME", verify_statements[0])
        self.assertIn("FROM sys.dm_exec_requests", verify_statements[1])
        self.assertTrue(verify_statements[-1].startswith("RESTORE VERIFYONLY"))
        self.assertTrue(backup_connection.closed)
        self.assertTrue(verify_connection.closed)

    def test_backup_reports_restore_verification_failure(self):
        connection = self.Connection(
            [(0, 1, 0)],
            execute_errors={
                "RESTORE VERIFYONLY": backup_service.pyodbc.Error(
                    "The backup set on file 1 is invalid."
                )
            },
        )

        with self.assertRaisesRegex(
            backup_service.BackupError,
            "RESTORE VERIFYONLY failed",
        ):
            backup_service.create_full_backup(
                ".\\SQLEXPRESS",
                "BusyComp0001_db12026",
                "D:\\SQLBackups",
                connect=lambda *_args, **_kwargs: connection,
            )

        statements = connection.cursor_instance.statements()
        self.assertEqual(
            sum(
                query.startswith("RESTORE VERIFYONLY")
                for query in statements
            ),
            1,
            "RESTORE VERIFYONLY should be the file existence/readability check.",
        )
        self.assertTrue(connection.closed)

    def test_backup_retries_verification_until_the_file_is_ready(self):
        connection = self.Connection(
            execute_errors={
                "RESTORE VERIFYONLY": [
                    backup_service.pyodbc.Error(
                        "Cannot open backup device. Operating system error 2."
                    ),
                    None,
                ]
            },
        )

        with mock.patch.object(backup_service.time, "sleep"):
            backup_path = backup_service.create_full_backup(
                ".\\SQLEXPRESS",
                "BusyComp0001_db12026",
                "D:\\SQLBackups",
                connect=lambda *_args, **_kwargs: connection,
            )

        self.assertTrue(backup_path.startswith("D:\\SQLBackups\\"))
        self.assertEqual(
            sum(
                query.startswith("RESTORE VERIFYONLY")
                for query in connection.cursor_instance.statements()
            ),
            2,
        )
        self.assertTrue(connection.closed)

    def test_backup_can_skip_verification(self):
        connection = self.Connection()

        backup_path = backup_service.create_full_backup(
            ".\\SQLEXPRESS",
            "BusyComp0001_db12026",
            "D:\\SQLBackups",
            connect=lambda *_args, **_kwargs: connection,
            verify=False,
            check_destination=False,
        )

        self.assertTrue(backup_path.startswith("D:\\SQLBackups\\"))
        statements = connection.cursor_instance.statements()
        self.assertTrue(statements[0].startswith("SELECT @@SPID"))
        self.assertTrue(
            any(query.startswith("BACKUP DATABASE") for query in statements)
        )
        self.assertFalse(
            any("xp_fileexist" in query for query in statements)
        )
        self.assertFalse(
            any("RESTORE VERIFYONLY" in query for query in statements)
        )
        self.assertTrue(connection.closed)

    def test_backup_reports_sql_server_messages(self):
        connection = self.Connection(
            message_results={
                "BACKUP DATABASE": [
                    ("01000", "Processed 3202 pages for database.")
                ],
                "RESTORE VERIFYONLY": [
                    ("01000", "The backup set on file 1 is valid.")
                ],
            }
        )
        messages = []

        backup_service.create_full_backup(
            ".\\SQLEXPRESS",
            "BusyComp0001_db12026",
            "D:\\SQLBackups",
            connect=lambda *_args, **_kwargs: connection,
            message_callback=messages.append,
        )

        self.assertEqual(
            messages,
            [
                "BACKUP DATABASE: Processed 3202 pages for database.",
                "RESTORE VERIFYONLY: The backup set on file 1 is valid.",
            ],
        )

    def test_backup_reports_sql_server_messages_when_backup_fails(self):
        connection = self.Connection(
            message_results={
                "BACKUP DATABASE": [
                    ("01000", "Error: 3201, Cannot open backup device.")
                ],
            },
            execute_errors={
                "BACKUP DATABASE": backup_service.pyodbc.Error(
                    "Operating system error 5."
                )
            },
        )
        messages = []

        with self.assertRaisesRegex(
            backup_service.BackupError,
            "BACKUP DATABASE failed",
        ):
            backup_service.create_full_backup(
                ".\\SQLEXPRESS",
                "BusyComp0001_db12026",
                "D:\\SQLBackups",
                connect=lambda *_args, **_kwargs: connection,
                message_callback=messages.append,
            )

        self.assertIn(
            "BACKUP DATABASE: Error: 3201, Cannot open backup device.",
            messages,
        )
        self.assertTrue(
            any("Operating system error 5." in message for message in messages)
        )


if __name__ == "__main__":
    unittest.main()
