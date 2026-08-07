import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.ticket.factory import _create_mysql_repository


class MySQLTicketFactoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_creates_repository_from_mysql_dsn(self):
        dsn = (
            "mysql+asyncmy://scrm_reader:test_password@"
            "127.0.0.1:3306/scrm?charset=utf8mb4"
        )
        with patch.dict(os.environ, {"MYSQL_DSN": dsn}):
            repository = _create_mysql_repository()

        self.assertEqual(repository.engine.url.drivername, "mysql+asyncmy")
        self.assertEqual(repository.engine.url.host, "127.0.0.1")
        self.assertEqual(repository.engine.url.database, "scrm")
        await repository.close()

    def test_rejects_non_mysql_asyncmy_dsn(self):
        dsn = "postgresql://user:password@127.0.0.1:5432/database"
        with patch.dict(os.environ, {"MYSQL_DSN": dsn}):
            with self.assertRaisesRegex(RuntimeError, "mysql\\+asyncmy"):
                _create_mysql_repository()

    def test_requires_mysql_dsn(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "MYSQL_DSN"):
                _create_mysql_repository()


if __name__ == "__main__":
    unittest.main()
