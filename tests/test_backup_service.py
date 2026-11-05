import unittest

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
        def __init__(
            self,
            fetchone_results=None,
            message_results=None,
            execute_errors=None,
        ):
            self.executed = []
            self.fetchone_results = list(
                fetchone_results or [(0, 1, 0), (1, 0, 1)]
            )
            self.message_results = list(message_results or [])
            self.execute_errors = execute_errors or {}
            self.messages = []

        def execute(self, query, *parameters):
            self.executed.append((query, parameters))
            execute_index = len(self.executed)
            self.messages = (
                self.message_results[execute_index - 1]
                if execute_index <= len(self.message_results)
                else []
            )
            if execute_index in self.execute_errors:
                raise self.execute_errors[execute_index]

        def fetchone(self):
            return self.fetchone_results.pop(0)

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

        def cursor(self):
            return self.cursor_instance

        def close(self):
            self.closed = True

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
        self.assertEqual(
            connection.cursor_instance.executed[0][1],
            ("D:\\SQLBackups",),
        )
        self.assertEqual(
            connection.cursor_instance.executed[-1][1],
            (backup_path,),
        )
        self.assertIn(
            "xp_fileexist",
            connection.cursor_instance.executed[-2][0],
        )
        self.assertTrue(connection.closed)

    def test_backup_reports_when_sql_server_cannot_find_created_file(self):
        connection = self.Connection([(0, 1, 0), (0, 0, 1)])

        with self.assertRaisesRegex(
            backup_service.BackupError,
            "completed BACKUP DATABASE but cannot find the backup file",
        ):
            backup_service.create_full_backup(
                ".\\SQLEXPRESS",
                "BusyComp0001_db12026",
                "D:\\SQLBackups",
                connect=lambda *_args, **_kwargs: connection,
            )

        self.assertEqual(
            len(connection.cursor_instance.executed),
            3,
            "Verification should not run when SQL Server cannot see the file.",
        )
        self.assertTrue(connection.closed)

    def test_backup_reports_sql_server_messages(self):
        connection = self.Connection(
            message_results=[
                [],
                [("01000", "Processed 3202 pages for database.")],
                [],
                [("01000", "The backup set on file 1 is valid.")],
            ]
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
            message_results=[
                [],
                [("01000", "Error: 3201, Cannot open backup device.")],
            ],
            execute_errors={
                2: backup_service.pyodbc.Error("Operating system error 5.")
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
