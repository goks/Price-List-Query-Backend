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
        def __init__(self):
            self.executed = []

        def execute(self, query, *parameters):
            self.executed.append((query, parameters))

        def fetchone(self):
            return (0, 1, 0)

    class Connection:
        def __init__(self):
            self.cursor_instance = BackupDestinationTests.Cursor()
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
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
