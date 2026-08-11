"""Tests for the PyCMD 4.0 behaviour.

The original suite in test_pythoncmd.py is deliberately left untouched: it is
the regression contract for 3.0 behaviour that 4.0 promises to keep.
"""

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import PythonCMD
from PythonCMD import CMDEmulator


MODULE_PATH = Path(PythonCMD.__file__).resolve()


class EmulatorTestCase(unittest.TestCase):
    """Builds an emulator that never touches the real home directory."""

    def setUp(self):
        self.original_cwd = os.getcwd()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.emulator = self.make_emulator()

    def tearDown(self):
        os.chdir(self.original_cwd)
        self.temp_dir.cleanup()

    def make_emulator(self, **kwargs):
        options = {
            "history_file": None,
            "config_file": str(self.root / "config.json"),
            "record_file": str(self.root / "history.jsonl"),
            "auto_persist_history": False,
            "interactive": False,
            "show_banner": False,
        }
        options.update(kwargs)
        return CMDEmulator(**options)

    def run_command(self, command, emulator=None):
        emulator = emulator or self.emulator
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            result = emulator.execute_line(command)
        return result, output.getvalue(), errors.getvalue()


class RegistryAndSourceTests(EmulatorTestCase):
    def test_command_registry_is_consistent(self):
        self.assertEqual(set(self.emulator.commands), set(self.emulator.COMMAND_INFO))
        self.assertTrue(self.emulator.check_command_registry())

    def test_featured_help_entries_all_exist(self):
        for key in self.emulator.FEATURED:
            self.assertIn(key, self.emulator.COMMAND_INFO)

    def test_no_bare_print_inside_class(self):
        """Every message must go through emit/emit_error or redirection leaks."""
        source = MODULE_PATH.read_text(encoding="utf-8")
        body = source.split("class CMDEmulator:", 1)[1]
        offenders = [
            line.strip()
            for line in body.splitlines()
            if re.search(r"(?<![.\w])print\(", line)
        ]
        self.assertEqual(offenders, [])

    @unittest.skipUnless(hasattr(sys, "stdlib_module_names"), "needs Python 3.10+")
    def test_module_uses_only_the_standard_library(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        imported = re.findall(r"^\s*import (\w+)", source, re.MULTILINE)
        for name in imported:
            self.assertIn(name, sys.stdlib_module_names, "%s is not stdlib" % name)

    def test_module_parses_under_the_oldest_supported_grammar(self):
        """pyproject declares requires-python >= 3.9; keep that honest."""
        import ast

        ast.parse(MODULE_PATH.read_text(encoding="utf-8"), feature_version=(3, 9))


class OutputPlumbingTests(EmulatorTestCase):
    def test_emit_resolves_stdout_lazily(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.emulator.emit("late bound")
        self.assertEqual(buffer.getvalue(), "late bound\n")

    def test_injected_stdout_receives_output(self):
        buffer = io.StringIO()
        emulator = self.make_emulator(stdout=buffer)
        emulator.execute_line("ECHO injected")
        self.assertIn("injected", buffer.getvalue())

    def test_errors_go_to_stderr(self):
        _, output, errors = self.run_command("WHICH")
        self.assertIn("Usage: WHICH", errors)
        self.assertNotIn("Usage: WHICH", output)


class StatusModelTests(EmulatorTestCase):
    def test_coerce_status_maps_booleans_and_codes(self):
        self.assertEqual(self.emulator.coerce_status(True), 0)
        self.assertEqual(self.emulator.coerce_status(None), 0)
        self.assertEqual(self.emulator.coerce_status(False), 1)
        # The 3.0 trap: `0 is not False` is True, so a zero returncode used to
        # be scored as a failure-free success by accident and 1 as success too.
        self.assertEqual(self.emulator.coerce_status(0), 0)
        self.assertEqual(self.emulator.coerce_status(3), 3)

    def test_process_input_returns_status(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(self.emulator.process_input("ECHO ok"))
        self.assertEqual(self.emulator.last_status, 0)

    def test_last_status_tracks_failures(self):
        self.run_command("ECHO fine")
        self.assertEqual(self.emulator.last_status, 0)
        self.run_command("JUMP nowhere")
        self.assertNotEqual(self.emulator.last_status, 0)


class ParsingTests(EmulatorTestCase):
    def test_split_first_token_handles_quotes(self):
        self.assertEqual(
            self.emulator.split_first_token('"my alias" ECHO hi'),
            ("my alias", "ECHO hi"),
        )
        self.assertEqual(self.emulator.split_first_token("plain rest here"), ("plain", "rest here"))
        self.assertEqual(self.emulator.split_first_token(""), ("", ""))

    def test_split_operators_table(self):
        cases = [
            ("ECHO a && ECHO b", [(None, "ECHO a "), ("&&", " ECHO b")]),
            ("ECHO a || ECHO b", [(None, "ECHO a "), ("||", " ECHO b")]),
            ("ECHO a; ECHO b", [(None, "ECHO a"), (";", " ECHO b")]),
            ("DIR | findstr x", [(None, "DIR "), ("|", " findstr x")]),
            # A single ampersand is literal, so A&B.txt survives.
            ("DEL A&B.txt", [(None, "DEL A&B.txt")]),
            # Operators inside quotes are data.
            ('ECHO "a && b"', [(None, 'ECHO "a && b"')]),
            ("ECHO 'a; b'", [(None, "ECHO 'a; b'")]),
        ]
        for line, expected in cases:
            with self.subTest(line=line):
                self.assertEqual(self.emulator.split_operators(line), expected)

    def test_split_operators_rejects_unbalanced_quotes(self):
        with self.assertRaises(ValueError):
            self.emulator.split_operators('ECHO "unterminated')

    def test_parse_redirections_extracts_targets(self):
        cases = [
            ("ECHO hi > out.txt", "ECHO hi", [(1, "w", "out.txt")]),
            ("ECHO hi>>out.txt", "ECHO hi", [(1, "a", "out.txt")]),
            ("DIR 2> err.txt", "DIR", [(2, "w", "err.txt")]),
            ("SORT < in.txt", "SORT", [(0, "r", "in.txt")]),
            ('ECHO hi > "a b.txt"', "ECHO hi", [(1, "w", "a b.txt")]),
            ("ECHO no redirect here", "ECHO no redirect here", []),
        ]
        for line, expected_text, expected_redirections in cases:
            with self.subTest(line=line):
                text, redirections = self.emulator.parse_redirections(line)
                self.assertEqual(text, expected_text)
                self.assertEqual(redirections, expected_redirections)

    def test_parse_redirections_requires_a_target(self):
        with self.assertRaises(ValueError):
            self.emulator.parse_redirections("ECHO hi >")

    def test_definition_commands_keep_their_own_operators(self):
        """MACRO/ALIAS bodies must not be eaten by the operator parser."""
        self.run_command("MACRO chain ECHO one; ECHO two")
        self.assertEqual(self.emulator.macros["chain"], "ECHO one; ECHO two")
        self.run_command("ALIAS both ECHO a && ECHO b")
        self.assertEqual(self.emulator.aliases["both"], "ECHO a && ECHO b")


class TableTests(EmulatorTestCase):
    def test_render_table_handles_ragged_rows(self):
        lines = self.emulator.render_table([("a", "b", "c"), ("d",)], headers=("1", "2", "3"))
        self.assertTrue(lines)
        self.assertIn("d", lines[-1])

    def test_render_table_empty_rows_render_nothing(self):
        self.assertEqual(self.emulator.render_table([], headers=("A", "B")), [])

    def test_render_table_fits_the_width_budget(self):
        rows = [("x" * 200, "y" * 200)]
        lines = self.emulator.render_table(rows, headers=("A", "B"), max_width=40)
        for line in lines:
            self.assertLessEqual(len(line), 40)

    def test_render_table_has_no_trailing_padding(self):
        lines = self.emulator.render_table([("a", "b")], headers=("A", "B"))
        for line in lines:
            self.assertEqual(line, line.rstrip())


class ConfigTests(EmulatorTestCase):
    def test_config_round_trips_through_a_second_emulator(self):
        self.run_command("ALIAS gs ECHO status")
        self.run_command("BOOKMARK here %s" % self.root)
        reloaded = self.make_emulator()
        self.assertEqual(reloaded.aliases.get("gs"), "ECHO status")
        self.assertIn("here", reloaded.bookmarks)

    def test_config_with_a_byte_order_mark_still_loads(self):
        path = self.root / "bom.json"
        payload = {"version": 2, "aliases": {"bom": "ECHO ok"}, "macros": {}, "bookmarks": {}}
        path.write_text(json.dumps(payload), encoding="utf-8-sig")
        emulator = self.make_emulator(config_file=str(path))
        self.assertEqual(emulator.aliases.get("bom"), "ECHO ok")

    def test_unreadable_config_is_backed_up_not_clobbered(self):
        path = self.root / "broken.json"
        path.write_text("{ this is not json", encoding="utf-8")
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            emulator = self.make_emulator(config_file=str(path))
        self.assertFalse(emulator.config_loaded)

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            emulator.execute_line("ALIAS fresh ECHO hi")

        self.assertTrue((self.root / "broken.json.bak").exists(), "original config must be preserved")
        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8"))["aliases"]["fresh"], "ECHO hi"
        )

    def test_atomic_write_leaves_no_temporary_file(self):
        self.run_command("ALIAS a ECHO a")
        leftovers = list(self.root.glob("*.tmp"))
        self.assertEqual(leftovers, [])

    def test_config_entries_that_shadow_builtins_are_dropped_on_load(self):
        path = self.root / "shadow.json"
        payload = {"version": 2, "aliases": {"DIR": "ECHO gotcha"}, "macros": {}, "bookmarks": {}}
        path.write_text(json.dumps(payload), encoding="utf-8")
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            emulator = self.make_emulator(config_file=str(path))
        self.assertNotIn("DIR", emulator.aliases)
        self.assertIn("built-in", errors.getvalue())


class NameAndLookupTests(EmulatorTestCase):
    def test_alias_with_a_quoted_name_is_refused(self):
        result, _, errors = self.run_command('ALIAS "my alias" ECHO hi')
        self.assertFalse(result)
        self.assertEqual(self.emulator.aliases, {})
        self.assertIn("whitespace", errors)

    def test_alias_cannot_shadow_a_builtin(self):
        result, _, _ = self.run_command("ALIAS DIR ECHO gotcha")
        self.assertFalse(result)
        _, output, _ = self.run_command("DIR %s" % self.root)
        self.assertNotIn("gotcha", output)

    def test_alias_lookup_is_case_insensitive(self):
        self.run_command("ALIAS greet ECHO hello")
        result, output, _ = self.run_command("GREET world")
        self.assertTrue(result)
        self.assertIn("hello world", output)

    def test_alias_keys_keep_the_users_spelling(self):
        self.run_command("ALIAS MixedCase ECHO x")
        self.assertIn("MixedCase", self.emulator.aliases)

    def test_bookmark_and_macro_lookup_are_case_insensitive(self):
        target = self.root / "place"
        target.mkdir()
        self.run_command('BOOKMARK spot "%s"' % target)
        result, _, _ = self.run_command("JUMP SPOT")
        self.assertTrue(result)
        self.assertEqual(os.getcwd(), str(target))


class ExecutionPolicyTests(EmulatorTestCase):
    def test_unknown_command_does_not_reach_the_shell_by_default(self):
        with mock.patch("PythonCMD.os.system") as system, mock.patch("PythonCMD.subprocess.run") as run:
            result, _, errors = self.run_command("definitelynotacommand")
        self.assertFalse(result)
        system.assert_not_called()
        run.assert_not_called()
        self.assertIn("Not run.", errors)

    def test_typo_does_not_truncate_a_redirection_target(self):
        """The headline 4.0 fix: `dur > notes.txt` must leave notes.txt alone."""
        notes = self.root / "notes.txt"
        notes.write_text("important data", encoding="utf-8")
        os.chdir(self.root)
        with mock.patch("PythonCMD.os.system") as system:
            result, _, _ = self.run_command("dur > notes.txt")
        self.assertFalse(result)
        system.assert_not_called()
        self.assertEqual(notes.read_text(encoding="utf-8"), "important data")

    def test_shell_fallback_refused_when_the_user_declines(self):
        self.emulator.interactive = True
        with mock.patch("builtins.input", return_value="n"), mock.patch("PythonCMD.os.system") as system:
            result, _, _ = self.run_command("definitelynotacommand")
        self.assertFalse(result)
        system.assert_not_called()

    def test_shell_fallback_runs_when_the_user_accepts(self):
        self.emulator.interactive = True
        with mock.patch("builtins.input", return_value="y"), mock.patch(
            "PythonCMD.os.system", return_value=0
        ) as system:
            result, _, _ = self.run_command("definitelynotacommand")
        self.assertTrue(result)
        system.assert_called_once()

    def test_shell_fallback_never_prompts_inside_a_macro(self):
        self.emulator.interactive = True
        self.run_command("MACRO risky definitelynotacommand")
        with mock.patch("builtins.input") as prompt, mock.patch("PythonCMD.os.system") as system:
            self.run_command("RUNMACRO risky")
        prompt.assert_not_called()
        system.assert_not_called()

    def test_policy_always_restores_legacy_behaviour(self):
        self.run_command("POLICY shell_fallback always")
        with mock.patch("PythonCMD.os.system", return_value=0) as system:
            result, _, _ = self.run_command("definitelynotacommand")
        self.assertTrue(result)
        system.assert_called_once()

    def test_policy_rejects_unknown_settings_and_values(self):
        self.assertFalse(self.run_command("POLICY nosuchkey on")[0])
        self.assertFalse(self.run_command("POLICY shell_fallback maybe")[0])

    def test_policy_persists(self):
        self.run_command("POLICY shell_fallback off")
        self.assertEqual(self.make_emulator().policy["shell_fallback"], "off")

    def test_a_program_on_path_is_not_treated_as_a_typo(self):
        self.assertIsNotNone(self.emulator.resolve_program(os.path.basename(sys.executable)))
        self.assertIsNone(self.emulator.resolve_program("definitelynotacommand"))

    def test_path_programs_can_be_disabled(self):
        self.emulator.policy["path_programs"] = False
        self.assertIsNone(self.emulator.resolve_program(os.path.basename(sys.executable)))


class RedirectionAndPipeTests(EmulatorTestCase):
    def setUp(self):
        super().setUp()
        os.chdir(self.root)

    def test_builtin_output_redirects_to_a_file(self):
        result, output, _ = self.run_command("ECHO written by a builtin > out.txt")
        self.assertTrue(result)
        self.assertEqual((self.root / "out.txt").read_text(encoding="utf-8"), "written by a builtin\n")
        self.assertNotIn("written by a builtin", output)

    def test_append_redirection_keeps_existing_content(self):
        self.run_command("ECHO first > out.txt")
        self.run_command("ECHO second >> out.txt")
        self.assertEqual(
            (self.root / "out.txt").read_text(encoding="utf-8"), "first\nsecond\n"
        )

    def test_stderr_redirection_is_separate_from_stdout(self):
        self.run_command("WHICH 2> err.txt")
        self.assertIn("Usage: WHICH", (self.root / "err.txt").read_text(encoding="utf-8"))

    def test_redirection_failure_does_not_run_the_command(self):
        blocked = self.root / "blocked"
        blocked.mkdir()
        result, _, errors = self.run_command("ECHO nope > blocked")
        self.assertFalse(result)
        self.assertIn("Redirection error", errors)

    def test_operators_short_circuit(self):
        _, output, _ = self.run_command("ECHO one && ECHO two")
        self.assertIn("one", output)
        self.assertIn("two", output)

        _, output, _ = self.run_command("JUMP nowhere && ECHO unreachable")
        self.assertNotIn("unreachable", output)

        _, output, _ = self.run_command("JUMP nowhere || ECHO recovered")
        self.assertIn("recovered", output)

        _, output, _ = self.run_command("JUMP nowhere; ECHO always")
        self.assertIn("always", output)

    def test_pipe_feeds_builtin_output_into_a_program(self):
        helper = self.root / "upper.py"
        helper.write_text("import sys; sys.stdout.write(sys.stdin.read().upper())", encoding="utf-8")
        interpreter = os.path.basename(sys.executable)
        _, output, errors = self.run_command('ECHO piped | %s "%s"' % (interpreter, helper))
        self.assertIn("PIPED", output, errors)

    def test_operator_parsing_can_be_switched_off(self):
        self.emulator.policy["operators"] = False
        _, output, _ = self.run_command("ECHO a && ECHO b")
        self.assertIn("a && ECHO b", output)


class HandlerTests(EmulatorTestCase):
    def setUp(self):
        super().setUp()
        os.chdir(self.root)

    def test_del_removes_each_operand(self):
        for name in ("a.txt", "b.txt"):
            (self.root / name).write_text("x", encoding="utf-8")
        result, _, _ = self.run_command("DEL --force a.txt b.txt")
        self.assertTrue(result)
        self.assertFalse((self.root / "a.txt").exists())
        self.assertFalse((self.root / "b.txt").exists())

    def test_del_expands_wildcards(self):
        for name in ("one.log", "two.log", "keep.txt"):
            (self.root / name).write_text("x", encoding="utf-8")
        result, _, _ = self.run_command("DEL --force *.log")
        self.assertTrue(result)
        self.assertFalse((self.root / "one.log").exists())
        self.assertTrue((self.root / "keep.txt").exists())

    def test_del_asks_before_removing_several_files(self):
        for name in ("x.log", "y.log"):
            (self.root / name).write_text("x", encoding="utf-8")
        self.emulator.interactive = True
        with mock.patch("builtins.input", return_value="n"):
            result, _, _ = self.run_command("DEL *.log")
        self.assertFalse(result)
        self.assertTrue((self.root / "x.log").exists())

    def test_del_dry_run_reports_missing_targets(self):
        result, _, _ = self.run_command("DEL --dry-run nosuchfile.txt")
        self.assertFalse(result)

    def test_mkdir_creates_each_operand(self):
        result, _, _ = self.run_command("MKDIR alpha beta")
        self.assertTrue(result)
        self.assertTrue((self.root / "alpha").is_dir())
        self.assertTrue((self.root / "beta").is_dir())

    def test_cwd_accepts_the_slash_d_flag(self):
        target = self.root / "sub"
        target.mkdir()
        result, _, _ = self.run_command("CWD /d %s" % target)
        self.assertTrue(result)
        self.assertEqual(os.getcwd(), str(target))

    def test_cwd_without_arguments_does_not_prompt(self):
        with mock.patch("builtins.input") as prompt:
            result, _, errors = self.run_command("CWD")
        prompt.assert_not_called()
        self.assertFalse(result)
        self.assertIn("Usage: CWD", errors)

    def test_legacy_without_arguments_does_not_prompt(self):
        with mock.patch("builtins.input") as prompt:
            result, _, errors = self.run_command("LEGACY")
        prompt.assert_not_called()
        self.assertFalse(result)
        self.assertIn("Usage: LEGACY", errors)

    def test_cwd_handles_unquoted_paths_with_spaces(self):
        target = self.root / "two words"
        target.mkdir()
        result, _, _ = self.run_command("CWD %s" % target)
        self.assertTrue(result)
        self.assertEqual(os.getcwd(), str(target))

    def test_history_rejects_useless_limits(self):
        self.run_command("ECHO a")
        self.assertFalse(self.run_command("HISTORY 0")[0])
        self.assertFalse(self.run_command("HISTORY -2")[0])
        self.assertFalse(self.run_command("HISTORY last 0")[0])

    def test_history_search_excludes_the_searching_line(self):
        result, output, _ = self.run_command("HISTORY search uniquetokenxyz")
        self.assertTrue(result)
        self.assertIn("No history matches", output)

    def test_history_clear_is_honest_about_disk_records(self):
        self.run_command("ECHO recorded")
        _, output, _ = self.run_command("HISTORY --clear")
        self.assertIn("HISTORY --purge", output)
        self.assertEqual(self.emulator.history, [])

    def test_color_rejects_a_non_hexadecimal_code(self):
        with mock.patch("PythonCMD.platform.system", return_value="Windows"), mock.patch(
            "PythonCMD.subprocess.call"
        ) as call:
            result, _, errors = self.run_command('COLOR "0A & echo PWNED"')
        self.assertFalse(result)
        call.assert_not_called()
        self.assertIn("hexadecimal", errors)

    def test_dir_details_survives_a_failing_stat(self):
        (self.root / "sample.txt").write_text("x", encoding="utf-8")
        real_stat = os.stat

        def flaky(path, *args, **kwargs):
            if str(path).endswith("sample.txt"):
                raise OSError("nope")
            return real_stat(path, *args, **kwargs)

        with mock.patch("PythonCMD.os.stat", side_effect=flaky):
            result, output, _ = self.run_command("DIR %s --details" % self.root)
        self.assertTrue(result)
        self.assertIn("sample.txt", output)

    def test_dir_rejects_several_paths(self):
        result, _, errors = self.run_command("DIR nosuchdir1 nosuchdir2")
        self.assertFalse(result)
        self.assertIn("single path", errors)


class MacroTests(EmulatorTestCase):
    def test_macro_stops_after_exit(self):
        self.run_command("MACRO bye EXIT; ECHO still running")
        _, output, _ = self.run_command("RUNMACRO bye")
        self.assertNotIn("still running", output)
        self.assertFalse(self.emulator.running)

    def test_macro_placeholders_are_not_substituted_twice(self):
        self.run_command("MACRO m ECHO [{1}] [{2}]")
        _, output, _ = self.run_command('RUNMACRO m "{2}" hello')
        self.assertIn("[{2}] [hello]", output)

    def test_macro_dry_run_does_not_execute(self):
        self.run_command("MACRO m MKDIR should-not-exist")
        os.chdir(self.root)
        _, output, _ = self.run_command("RUNMACRO --dry-run m")
        self.assertIn(">> MKDIR should-not-exist", output)
        self.assertFalse((self.root / "should-not-exist").exists())

    def test_macro_stop_flag_halts_on_failure(self):
        self.run_command("MACRO m JUMP nowhere; ECHO after")
        _, output, _ = self.run_command("RUNMACRO --stop m")
        self.assertNotIn("after", output)

    def test_macro_loop_is_bounded(self):
        self.emulator.macros["loop"] = "RUNMACRO loop"
        self.emulator.rebuild_indexes()
        result, _, errors = self.run_command("RUNMACRO loop")
        self.assertFalse(result)
        self.assertIn("loop", errors.lower())


class ExplainTests(EmulatorTestCase):
    def test_explain_reports_the_alias_chain(self):
        self.run_command("ALIAS ll DIR --details")
        result, output, _ = self.run_command("EXPLAIN ll")
        self.assertTrue(result)
        self.assertIn("alias ll", output)
        self.assertIn("builtin DIR", output)

    def test_explain_flags_a_command_that_would_reach_the_shell(self):
        _, output, errors = self.run_command("EXPLAIN definitelynotacommand")
        self.assertIn("UNKNOWN", output)
        self.assertIn("Warning", errors)

    def test_explain_shows_redirection_and_operators(self):
        _, output, _ = self.run_command("EXPLAIN ECHO hi > out.txt && PWD")
        self.assertIn("out.txt", output)
        self.assertIn("on success", output)

    def test_explain_does_not_execute_anything(self):
        os.chdir(self.root)
        self.run_command("EXPLAIN MKDIR untouched")
        self.assertFalse((self.root / "untouched").exists())


class RecordTests(EmulatorTestCase):
    def test_records_capture_the_typed_line_not_the_expansion(self):
        self.run_command("ALIAS hi ECHO hello")
        self.run_command("hi there")
        commands = [item["command"] for item in self.emulator.command_stats]
        self.assertIn("hi there", commands)

    def test_record_can_be_switched_off(self):
        self.run_command("ECHO recorded")
        self.run_command("RECORD off")
        before = self.emulator.record_file_size()
        self.assertGreater(before, 0)
        self.run_command("ECHO quiet")
        self.assertEqual(self.emulator.record_file_size(), before)

    def test_record_file_rotates_when_it_grows(self):
        path = Path(self.emulator.record_file)
        path.write_text("x" * (PythonCMD.RECORD_MAX_BYTES + 1), encoding="utf-8")
        self.run_command("ECHO trigger")
        self.assertTrue(Path(str(path) + ".1").exists())

    def test_history_search_reads_only_the_tail(self):
        path = Path(self.emulator.record_file)
        with path.open("w", encoding="utf-8") as stream:
            for index in range(5000):
                stream.write(json.dumps({"command": "ECHO %d" % index, "cwd": "", "time": ""}) + "\n")
        records = self.emulator.iter_history_records(limit=10)
        self.assertLessEqual(len(records), 10)


class CommandLineTests(unittest.TestCase):
    """End-to-end coverage of main(), which nothing exercised before 4.0."""

    def run_pycmd(self, *arguments, **kwargs):
        return subprocess.run(
            [sys.executable, str(MODULE_PATH), "--no-config", "--no-record"] + list(arguments),
            capture_output=True,
            text=True,
            timeout=30,
            **kwargs
        )

    def test_dash_c_runs_and_exits_cleanly(self):
        completed = self.run_pycmd("-c", "ECHO hello from the cli")
        self.assertEqual(completed.returncode, 0)
        self.assertIn("hello from the cli", completed.stdout)

    def test_dash_c_reports_a_failure_status(self):
        completed = self.run_pycmd("-c", "JUMP nowhere")
        self.assertNotEqual(completed.returncode, 0)

    def test_eof_terminates_the_repl(self):
        """3.0 spun forever on Ctrl+Z / piped stdin; 4.0 must exit."""
        completed = self.run_pycmd(input="ECHO alive\n")
        self.assertEqual(completed.returncode, 0)
        self.assertIn("alive", completed.stdout)
        self.assertLess(len(completed.stdout.splitlines()), 100)

    def test_version_flag(self):
        completed = self.run_pycmd("--version")
        self.assertIn(PythonCMD.__version__, completed.stdout)

    def test_script_mode_runs_each_line(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "demo.pycmd"
            script.write_text("# a comment\nECHO from script\nREM ignored\nPWD\n", encoding="utf-8")
            completed = self.run_pycmd(str(script))
        self.assertEqual(completed.returncode, 0)
        self.assertIn("from script", completed.stdout)
        self.assertNotIn("ignored", completed.stdout)

    def test_one_shot_mode_refuses_the_shell_fallback(self):
        completed = self.run_pycmd("-c", "definitelynotacommand")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Not run.", completed.stderr)

    def test_safe_mode_blocks_every_route_to_the_shell(self):
        completed = self.run_pycmd("--safe-mode", "-c", "!echo hello")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("disabled by policy", completed.stderr)


if __name__ == "__main__":
    unittest.main()
