from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product_search.core.runtime_safety import (
    UnsafeRuntimeDirectoryError,
    is_loopback_host,
    validate_runtime_directory,
)
from product_search.infrastructure.image_storage import (
    LocalTemporaryImageStorage,
    TemporaryFileCleanupError,
)


class RuntimeSafetyTests(unittest.TestCase):
    def test_accepts_private_directory_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "mvp-data"
            data_dir.mkdir(mode=0o700)
            os.chmod(data_dir, 0o700)

            validate_runtime_directory(data_dir, repository_root=Path.cwd())

    def test_rejects_directory_inside_repository(self) -> None:
        with self.assertRaisesRegex(UnsafeRuntimeDirectoryError, "репозитори"):
            validate_runtime_directory(Path.cwd() / ".runtime-data", repository_root=Path.cwd())

    def test_rejects_relative_directory(self) -> None:
        with self.assertRaisesRegex(UnsafeRuntimeDirectoryError, "абсолютным"):
            validate_runtime_directory(Path("runtime-data"), repository_root=Path.cwd())

    def test_rejects_directory_with_group_or_other_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "mvp-data"
            data_dir.mkdir(mode=0o755)
            os.chmod(data_dir, 0o755)

            with self.assertRaisesRegex(UnsafeRuntimeDirectoryError, "права"):
                validate_runtime_directory(data_dir, repository_root=Path.cwd())

    def test_rejects_directory_owned_by_another_account(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "mvp-data"
            data_dir.mkdir(mode=0o700)
            os.chmod(data_dir, 0o700)

            with self.assertRaisesRegex(UnsafeRuntimeDirectoryError, "принадлежать"):
                validate_runtime_directory(
                    data_dir, repository_root=Path.cwd(), expected_uid=os.geteuid() + 1
                )

    def test_accepts_only_loopback_hosts(self) -> None:
        self.assertTrue(is_loopback_host("127.0.0.1"))
        self.assertTrue(is_loopback_host("::1"))
        self.assertFalse(is_loopback_host("0.0.0.0"))
        self.assertFalse(is_loopback_host("192.168.1.20"))


class TemporaryImageStorageTests(unittest.TestCase):
    def test_removes_temporary_file_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = LocalTemporaryImageStorage(Path(directory))

            with storage.temporary_file("query.jpg") as file_path:
                file_path.write_bytes(b"image")
                self.assertTrue(file_path.exists())

            self.assertFalse(file_path.exists())

    def test_removes_temporary_file_after_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = LocalTemporaryImageStorage(Path(directory))

            with self.assertRaisesRegex(RuntimeError, "simulated"), storage.temporary_file(
                "query.jpg"
            ) as file_path:
                file_path.write_bytes(b"image")
                raise RuntimeError("simulated failure")

            self.assertFalse(file_path.exists())

    def test_reports_failed_temporary_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = LocalTemporaryImageStorage(Path(directory))

            with (
                patch("product_search.infrastructure.image_storage.shutil.rmtree", side_effect=OSError),
                self.assertRaises(TemporaryFileCleanupError),
                storage.temporary_file("query.jpg") as file_path,
            ):
                file_path.write_bytes(b"image")
