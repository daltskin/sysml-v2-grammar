"""Verify conformance downloads use the configured release and one archive."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

import conformance


class ConformanceFetchTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.workspace = Path(directory.name)
        self.config_path = self.workspace / "config.json"
        self.config = {
            "release_repo": "Systems-Modeling/SysML-v2-Release",
            "release_tag": "2026-09.1",
        }
        self.write_config()
        self.fixtures = self.workspace / "fixtures"
        self.library = self.workspace / "sysml.library"
        self.fixtures.mkdir()
        self.library.mkdir()
        (self.fixtures / "old.sysml").write_text("old fixtures")
        for name in ("Domain Libraries", "Kernel Libraries", "Systems Library"):
            directory = self.library / name
            directory.mkdir()
            (directory / "old.sysml").write_text("old library")

        self.archive_files = {
            f"sysml/src/{suite}/Model.sysml": f"package {suite};\n"
            for suite in ("training", "validation", "examples")
        }
        self.archive_files.update(
            {
                "sysml.library/Domain Libraries/Domain.sysml": "package Domain;\n",
                "sysml.library/Kernel Libraries/Kernel.kerml": "package Kernel;\n",
                "sysml.library/Systems Library/Systems.sysml": "package Systems;\n",
            }
        )
        self.stderr = io.StringIO()
        contexts = ExitStack()
        self.addCleanup(contexts.close)
        contexts.enter_context(redirect_stdout(io.StringIO()))
        contexts.enter_context(redirect_stderr(self.stderr))
        contexts.enter_context(
            patch.object(conformance, "CONFIG_PATH", self.config_path, create=True)
        )
        contexts.enter_context(patch.object(conformance, "FIXTURES_DIR", self.fixtures))
        contexts.enter_context(patch.object(conformance, "LIBRARY_DIR", self.library))
        self.download = contexts.enter_context(
            patch.object(
                conformance.urllib.request,
                "urlretrieve",
                side_effect=self.download_archive,
            )
        )

    def write_config(self):
        self.config_path.write_text(json.dumps(self.config))

    def download_archive(self, url, filename):
        with tarfile.open(filename, "w:gz") as archive:
            for path, content in self.archive_files.items():
                data = content.encode()
                member = tarfile.TarInfo(f"SysML-v2-Release-fixture/{path}")
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))

    def assert_existing_data_preserved(self):
        self.assertEqual((self.fixtures / "old.sysml").read_text(), "old fixtures")
        for directory in self.library.iterdir():
            self.assertEqual((directory / "old.sysml").read_text(), "old library")

    def test_fetches_configured_tag_once_and_refreshes_all_sources(self):
        conformance.fetch_fixtures()
        self.download.assert_called_once()
        self.assertEqual(
            self.download.call_args.args[0],
            "https://github.com/Systems-Modeling/SysML-v2-Release/archive/refs/tags/2026-09.1.tar.gz",
        )
        self.assertFalse((self.fixtures / "old.sysml").exists())
        for suite in ("training", "validation", "examples"):
            self.assertEqual(
                (self.fixtures / suite / "Model.sysml").read_text(),
                f"package {suite};\n",
            )
        for directory in self.library.iterdir():
            self.assertFalse((directory / "old.sysml").exists())
        for path, content in self.archive_files.items():
            if path.startswith("sysml.library/"):
                self.assertEqual(
                    (
                        self.library / Path(path).relative_to("sysml.library")
                    ).read_text(),
                    content,
                )

    def test_reads_repository_and_tag_from_config_on_each_fetch(self):
        for repo, tag in (
            ("Systems-Modeling/SysML-v2-Release", "2026-09"),
            ("Example/Other-Release", "2026-09.2"),
        ):
            self.config.update(release_repo=repo, release_tag=tag)
            self.write_config()
            conformance.fetch_fixtures()
            self.assertEqual(
                self.download.call_args.args[0],
                f"https://github.com/{repo}/archive/refs/tags/{tag}.tar.gz",
            )
        self.assertEqual(self.download.call_count, 2)

    def test_rejects_missing_or_empty_fixture_suites_before_replacing_data(self):
        original = self.archive_files.copy()
        for suite in ("training", "validation", "examples"):
            for empty in (False, True):
                with self.subTest(suite=suite, empty=empty):
                    self.archive_files = {
                        path: content
                        for path, content in original.items()
                        if not path.startswith(f"sysml/src/{suite}/")
                    }
                    if empty:
                        self.archive_files[f"sysml/src/{suite}/README.txt"] = "empty"
                    with self.assertRaises(SystemExit) as error:
                        conformance.fetch_fixtures()
                    self.assertEqual(error.exception.code, 1)
                    self.assertIn(suite, self.stderr.getvalue())
                    self.assert_existing_data_preserved()

    def test_rejects_missing_library_directories_before_replacing_data(self):
        original = self.archive_files.copy()
        for name in ("Domain Libraries", "Kernel Libraries", "Systems Library"):
            with self.subTest(directory=name):
                self.archive_files = {
                    path: content
                    for path, content in original.items()
                    if not path.startswith(f"sysml.library/{name}/")
                }
                with self.assertRaises(SystemExit) as error:
                    conformance.fetch_fixtures()
                self.assertEqual(error.exception.code, 1)
                self.assertIn(name, self.stderr.getvalue())
                self.assert_existing_data_preserved()

    def test_rejects_invalid_config_before_downloading(self):
        original = self.config.copy()
        for field, value in (
            ("release_tag", ""),
            ("release_tag", "../2026-09.1"),
            ("release_tag", None),
            ("release_repo", "not-a-repository"),
            ("release_repo", "Example/Repo?ref=master"),
            ("release_repo", None),
        ):
            with self.subTest(field=field, value=value):
                self.config = {**original, field: value}
                self.write_config()
                with self.assertRaises(SystemExit) as error:
                    conformance.fetch_fixtures()
                self.assertEqual(error.exception.code, 1)
                self.assert_existing_data_preserved()
        self.download.assert_not_called()

    def test_download_errors_preserve_existing_data(self):
        self.download.side_effect = URLError("download failed")
        with self.assertRaises(URLError):
            conformance.fetch_fixtures()
        self.assert_existing_data_preserved()


if __name__ == "__main__":
    unittest.main()
