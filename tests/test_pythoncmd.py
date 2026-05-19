import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PythonCMD import CMDEmulator


class CMDEmulatorTests(unittest.TestCase):
    def setUp(self):
        self.original_cwd = os.getcwd()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.emulator = CMDEmulator(
            history_file=None,
            config_file=str(self.root / "config.json"),
            record_file=str(self.root / "history.jsonl"),
            auto_persist_history=False,
        )

    def tearDown(self):
        os.chdir(self.original_cwd)
        self.temp_dir.cleanup()

    def run_command(self, command):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = self.emulator.execute_line(command)
        return result, output.getvalue()

    def test_unknown_command_suggests_close_match(self):
        suggestions = self.emulator.get_suggestions("histroy")
        self.assertIn("HISTORY", suggestions)

    def test_alias_persists_and_expands_with_extra_args(self):
        self.run_command("ALIAS hi ECHO hello")
        result, output = self.run_command("hi there")

        self.assertTrue(result)
        self.assertIn("hello there", output)
        self.assertIn("hi", self.emulator.aliases)
        self.assertTrue((self.root / "config.json").exists())

    def test_bookmark_jump_supports_quoted_paths(self):
        target = self.root / "folder with spaces"
        target.mkdir()

        self.run_command(f'BOOKMARK work "{target}"')
        os.chdir(self.root)
        result, output = self.run_command("JUMP work")

        self.assertTrue(result)
        self.assertEqual(os.getcwd(), str(target))
        self.assertIn("Current Directory:", output)

    def test_run_safe_uses_shell_false(self):
        completed = subprocess.CompletedProcess(args=["python"], returncode=0)
        with mock.patch("PythonCMD.subprocess.run", return_value=completed) as run:
            result, _ = self.run_command('RUN --safe python -c "print(1)"')

        self.assertTrue(result)
        run.assert_called_once_with(["python", "-c", "print(1)"], shell=False)

    def test_del_dry_run_does_not_remove_file(self):
        target = self.root / "sample.txt"
        target.write_text("sample", encoding="utf-8")

        result, output = self.run_command(f"DEL --dry-run {target}")

        self.assertTrue(result)
        self.assertTrue(target.exists())
        self.assertIn("Would delete:", output)

    def test_history_search_finds_session_command(self):
        self.run_command("ECHO searchable")
        result, output = self.run_command("HISTORY search searchable")

        self.assertTrue(result)
        self.assertIn("ECHO searchable", output)

    def test_help_shortcut_dispatches_to_help(self):
        result, output = self.run_command("? RUN")

        self.assertTrue(result)
        self.assertIn("Usage: RUN [--safe] <command>", output)

    def test_legacy_shortcut_dispatches_to_shell(self):
        with mock.patch("PythonCMD.os.system", return_value=0) as system:
            result, _ = self.run_command("!echo hello")

        self.assertTrue(result)
        system.assert_called_once_with("echo hello")

    def test_macro_runs_multiple_commands_with_placeholders(self):
        self.run_command("MACRO greet ECHO hello {1}; ECHO all {*}")
        result, output = self.run_command("RUNMACRO greet world wide")

        self.assertTrue(result)
        self.assertIn(">> ECHO hello world", output)
        self.assertIn("hello world", output)
        self.assertIn("all world wide", output)

    def test_direct_macro_invocation(self):
        self.run_command("MACRO greet ECHO direct")
        result, output = self.run_command("greet")

        self.assertTrue(result)
        self.assertIn("direct", output)

    def test_path_suggestions_include_local_files(self):
        os.chdir(self.root)
        (self.root / "alpha.txt").write_text("sample", encoding="utf-8")

        suggestions = self.emulator.get_suggestions("alp")

        self.assertIn("alpha.txt", suggestions)

    def test_tree_lists_nested_entries(self):
        nested = self.root / "nested"
        nested.mkdir()
        (nested / "leaf.txt").write_text("sample", encoding="utf-8")

        result, output = self.run_command(f"TREE {self.root} 2")

        self.assertTrue(result)
        self.assertIn("nested", output)
        self.assertIn("leaf.txt", output)


if __name__ == "__main__":
    unittest.main()
