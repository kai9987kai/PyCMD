#!/usr/bin/env python3
"""
Advanced CMD Emulator for Windows [Version 4.0 - Enhanced 2026]
By Jared/kai9987kai (C)03/2019 - Enhanced 2026
Contribution credits
kai9987kai

PyCMD keeps the original simple command surface and adds the things a shell
needs to be predictable: an execution policy so a typo can never reach the OS
shell unannounced, real operators (``&&``, ``||``, ``;``), redirection and
pipes that work for PyCMD's own builtins, persistent aliases, macros and
bookmarks, and a non-interactive mode so the shell can be scripted.

For best functionality, run this on the Python command line.
Visit the GitHub: http://www.github.com/Kai9987kai/PyCMD
"""

import argparse
import atexit
import collections
import contextlib
import difflib
import fnmatch
import getpass
import glob
import io
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time

try:
    import readline
except ImportError:  # pragma: no cover - depends on the host Python build
    readline = None


__version__ = "4.0.0"

HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".cmd_emulator_history")
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".pycmd_config.json")
RECORD_FILE = os.path.join(os.path.expanduser("~"), ".pycmd_history.jsonl")

CONFIG_VERSION = 2
RECORD_MAX_BYTES = 2 * 1024 * 1024
RECORD_WINDOW_BYTES = 256 * 1024
READLINE_HISTORY_LENGTH = 2000

SCRIPT_PATH = os.path.abspath(sys.argv[0])
# RESTART re-execs in whatever directory the user has since cd'd into, so any
# relative path on the original command line has to be pinned down now.
LAUNCH_ARGV = [
    os.path.abspath(argument) if os.path.exists(argument) else argument
    for argument in sys.argv[1:]
]

DEFAULT_POLICY = {
    "shell_fallback": "confirm",
    "expand_variables": True,
    "path_programs": True,
    "legacy": True,
    "run_shell": True,
    "operators": True,
    "record": True,
    "stop_on_error": False,
}

POLICY_CHOICES = {"shell_fallback": ("off", "confirm", "always")}

TRUE_WORDS = ("on", "true", "yes", "1", "enabled")
FALSE_WORDS = ("off", "false", "no", "0", "disabled")


class CMDEmulator:
    COMMAND_INFO = {
        "CWD": ("Navigation", "CWD <directory>", "Change working directory."),
        "CD": ("Navigation", "CD <directory>", "Alias for CWD."),
        "PWD": ("Navigation", "PWD", "Display the current working directory."),
        "PUSHD": ("Navigation", "PUSHD [directory]", "Remember this directory, then change to another."),
        "POPD": ("Navigation", "POPD", "Return to the directory PUSHD remembered."),
        "DIRS": ("Navigation", "DIRS", "Show the directory stack."),
        "IF": ("Control", "IF <condition> THEN <command> [ELSE <command>]", "Run a command conditionally."),
        "FOR": ("Control", "FOR <name> IN <item> [more...] DO <command>", "Run a command once per item."),
        "SEARCH": ("Files", "SEARCH [pattern] [--in root] [--containing text] [--limit n]", "Find files recursively."),
        "DIFF": ("Text", "DIFF <left> <right>", "Show differences between two files."),
        "REPLACE": ("Text", "REPLACE [--regex] [--case] [--in-place] <search> <new> [file...]", "Substitute text."),
        "DIR": ("Files", "DIR [path] [--details]", "List directory contents."),
        "MKDIR": ("Files", "MKDIR <directory> [more...]", "Create one or more directories."),
        "DEL": ("Files", "DEL [--dry-run] [--force] <file> [more...]", "Delete files; wildcards are expanded."),
        "ERASE": ("Files", "ERASE [--dry-run] [--force] <file> [more...]", "Alias for DEL."),
        "TREE": ("Files", "TREE [path] [depth]", "Show a compact directory tree."),
        "COPY": ("Files", "COPY <source> [more...] <destination>", "Copy files; wildcards are expanded."),
        "MOVE": ("Files", "MOVE <source> [more...] <destination>", "Move files; wildcards are expanded."),
        "RENAME": ("Files", "RENAME <old> <new>", "Rename a single file or directory."),
        "RMDIR": ("Files", "RMDIR [--recurse] [--force] <directory> [more...]", "Remove directories."),
        "TOUCH": ("Files", "TOUCH <file> [more...]", "Create a file, or update its timestamp."),
        "TYPE": ("Text", "TYPE <file> [more...]", "Print file contents; reads piped input too."),
        "GREP": ("Text", "GREP [--regex] [--case] [--invert] [--count] [-n] <pattern> [file...]", "Show matching lines."),
        "SORT": ("Text", "SORT [--reverse] [--unique] [--numeric] [file...]", "Sort lines."),
        "HEAD": ("Text", "HEAD [-n count] [file...]", "Show the first lines."),
        "TAIL": ("Text", "TAIL [-n count] [file...]", "Show the last lines."),
        "COUNT": ("Text", "COUNT [--lines|--words|--chars] [file...]", "Count lines, words and characters."),
        "SET": ("Environment", "SET [name=value]", "Show or set a session variable."),
        "UNSET": ("Environment", "UNSET <name>", "Remove a session variable."),
        "ENV": ("Environment", "ENV [filter]", "Show environment and session variables."),
        "ECHO": ("Basic", "ECHO <text>", "Display the given text."),
        "CLS": ("Basic", "CLS", "Clear the screen."),
        "COLOR": ("Basic", "COLOR <code>", "Change Windows console color."),
        "TIME": ("Basic", "TIME", "Display the current system time."),
        "DATE": ("Basic", "DATE", "Display the current system date."),
        "RUN": ("Execution", "RUN [--safe] <command>", "Execute an external command/program."),
        "LEGACY": ("Execution", "LEGACY [command]", "Execute a command through the OS shell."),
        "!": ("Execution", "!<command>", "Shortcut for LEGACY."),
        "SHELL": ("Execution", "SHELL", "Launch an external interactive shell."),
        "WHICH": ("Execution", "WHICH <program>", "Show the executable path for a program."),
        "ALIAS": ("Productivity", "ALIAS <name> <command>", "Create and save an alias."),
        "UNALIAS": ("Productivity", "UNALIAS <name>", "Remove an alias."),
        "LISTALIASES": ("Productivity", "LISTALIASES", "List all aliases."),
        "MACRO": ("Productivity", "MACRO <name> <cmd>; <cmd>", "Save a multi-command workflow."),
        "RUNMACRO": ("Productivity", "RUNMACRO [--dry-run] [--stop] <name> [args]", "Run a saved macro."),
        "UNMACRO": ("Productivity", "UNMACRO <name>", "Remove a saved macro."),
        "LISTMACROS": ("Productivity", "LISTMACROS", "List all saved macros."),
        "BOOKMARK": ("Productivity", "BOOKMARK <name> [path]", "Save a directory bookmark."),
        "JUMP": ("Productivity", "JUMP <name>", "Change to a saved bookmark."),
        "UNBOOKMARK": ("Productivity", "UNBOOKMARK <name>", "Remove a directory bookmark."),
        "LISTBOOKMARKS": ("Productivity", "LISTBOOKMARKS", "List directory bookmarks."),
        "HISTORY": ("Insight", "HISTORY [limit|last n|search text|--clear|--purge]", "Show, search, or clear history."),
        "STATS": ("Insight", "STATS", "Show command counts, failures, and slow commands."),
        "SUGGEST": ("Insight", "SUGGEST <text>", "Show command and alias suggestions."),
        "EXPLAIN": ("Insight", "EXPLAIN <command line>", "Show how PyCMD will interpret a line."),
        "POLICY": ("Safety", "POLICY [key value]", "Show or change execution policy."),
        "RECORD": ("Safety", "RECORD [on|off]", "Show or change on-disk command recording."),
        "COMMANDS": ("Help", "COMMANDS [category]", "List commands grouped by category."),
        "HELP": ("Help", "HELP [command]", "Show general or command-specific help."),
        "_HELP": ("Help", "_HELP [command]", "Alias for HELP."),
        "?": ("Help", "? [command]", "Shortcut for HELP."),
        "??": ("Help", "?? [category]", "Shortcut for COMMANDS."),
        "CONFIG": ("Help", "CONFIG", "Show PyCMD config and history locations."),
        "RESTART": ("Session", "RESTART", "Restart the CMD Emulator session."),
        "EXIT": ("Session", "EXIT", "Exit the emulator."),
    }

    FEATURED = (
        "CWD",
        "DIR",
        "COPY",
        "TYPE",
        "GREP",
        "SET",
        "RUN",
        "!",
        "ALIAS",
        "MACRO",
        "BOOKMARK",
        "HISTORY",
        "STATS",
        "EXPLAIN",
        "POLICY",
        "EXIT",
    )

    # Commands whose tail is data, not a command line: either the OS shell owns
    # it verbatim, or it is a definition body that must keep its own operators.
    RAW_TAIL_COMMANDS = ("!", "LEGACY", "RUN", "ALIAS", "MACRO", "EXPLAIN", "IF", "FOR")
    OPERATORS = ("&&", "||", "|", ";")
    NAME_FORBIDDEN = set(" \t\"'`;|&<>()")
    MAX_EXPANSION_DEPTH = 10

    def __init__(
        self,
        history_file=HISTORY_FILE,
        config_file=CONFIG_FILE,
        record_file=RECORD_FILE,
        auto_persist_history=True,
        stdout=None,
        stderr=None,
        interactive=None,
        show_banner=True,
    ):
        self.prompt = ""
        self.history = []
        self.aliases = {}
        self.macros = {}
        self.bookmarks = {}
        # self.policy is what this session enforces; self.stored_policy is what
        # gets written back. A transient CLI override (--safe-mode, one-shot
        # lockdown) changes only the former, so running `pycmd --safe-mode -c
        # "ALIAS ..."` once cannot silently lock down every later session.
        self.policy = dict(DEFAULT_POLICY)
        self.stored_policy = dict(DEFAULT_POLICY)
        self.quarantined = {}
        self.variables = {}
        self.command_stats = collections.deque(maxlen=200)
        self.history_file = history_file
        self.config_file = config_file
        self.record_file = record_file
        self.record_write_failed = False
        self.config_loaded = True
        self.running = True
        self.last_status = 0
        self.readline_backend = None
        self.show_banner = show_banner

        # Output plumbing. These stay None unless a caller (or a redirection)
        # diverts them, so `self.out` resolves lazily against the live
        # sys.stdout and contextlib.redirect_stdout keeps working.
        self._stdout = stdout
        self._stderr = stderr
        self._pipe_input = None
        self._capture_depth = 0
        # Authoritative macro nesting counter. RUNMACRO is a normal handler and
        # cannot receive a depth argument, so the guard has to live on self or a
        # macro that invokes itself by name recurses until Python's stack gives.
        self._macro_depth = 0
        self._substitution_depth = 0
        self._loop_depth = 0
        self.directory_stack = []
        self._executing_line = None
        self._completion_cache = (None, [])

        if interactive is None:
            try:
                interactive = bool(sys.stdin) and sys.stdin.isatty()
            except (AttributeError, ValueError, OSError):
                interactive = False
        self.interactive = interactive

        self.commands = {
            "CWD": self.cmd_cwd,
            "CD": self.cmd_cwd,
            "CLS": self.cmd_cls,
            "COLOR": self.cmd_color,
            "_HELP": self.cmd_help,
            "HELP": self.cmd_help,
            "?": self.cmd_help,
            "??": self.cmd_commands,
            "COMMANDS": self.cmd_commands,
            "CONFIG": self.cmd_config,
            "LEGACY": self.cmd_legacy,
            "!": self.cmd_legacy,
            "DIR": self.cmd_dir,
            "TREE": self.cmd_tree,
            "MKDIR": self.cmd_mkdir,
            "DEL": self.cmd_del,
            "ERASE": self.cmd_del,
            "COPY": self.cmd_copy,
            "MOVE": self.cmd_move,
            "RENAME": self.cmd_rename,
            "RMDIR": self.cmd_rmdir,
            "TOUCH": self.cmd_touch,
            "TYPE": self.cmd_type,
            "GREP": self.cmd_grep,
            "SORT": self.cmd_sort,
            "HEAD": self.cmd_head,
            "TAIL": self.cmd_tail,
            "COUNT": self.cmd_count,
            "SET": self.cmd_set,
            "UNSET": self.cmd_unset,
            "ENV": self.cmd_env,
            "PWD": self.cmd_pwd,
            "PUSHD": self.cmd_pushd,
            "POPD": self.cmd_popd,
            "DIRS": self.cmd_dirs,
            "IF": self.cmd_if,
            "FOR": self.cmd_for,
            "SEARCH": self.cmd_search,
            "DIFF": self.cmd_diff,
            "REPLACE": self.cmd_replace,
            "ECHO": self.cmd_echo,
            "RUN": self.cmd_run,
            "TIME": self.cmd_time,
            "DATE": self.cmd_date,
            "HISTORY": self.cmd_history,
            "STATS": self.cmd_stats,
            "SUGGEST": self.cmd_suggest,
            "EXPLAIN": self.cmd_explain,
            "POLICY": self.cmd_policy,
            "RECORD": self.cmd_record,
            "ALIAS": self.cmd_alias,
            "UNALIAS": self.cmd_unalias,
            "LISTALIASES": self.cmd_listaliases,
            "MACRO": self.cmd_macro,
            "RUNMACRO": self.cmd_runmacro,
            "UNMACRO": self.cmd_unmacro,
            "LISTMACROS": self.cmd_listmacros,
            "BOOKMARK": self.cmd_bookmark,
            "JUMP": self.cmd_jump,
            "UNBOOKMARK": self.cmd_unbookmark,
            "LISTBOOKMARKS": self.cmd_listbookmarks,
            "SHELL": self.cmd_shell,
            "WHICH": self.cmd_which,
            "RESTART": self.cmd_restart,
            "EXIT": self.cmd_exit,
        }

        # Which candidate set completes the operands of each command.
        self.command_completers = {
            "JUMP": "bookmarks",
            "UNBOOKMARK": "bookmarks",
            "RUNMACRO": "macros",
            "UNMACRO": "macros",
            "UNALIAS": "aliases",
            "HELP": "topics",
            "_HELP": "topics",
            "?": "topics",
            "CWD": "directories",
            "CD": "directories",
            "TREE": "directories",
            "MKDIR": "directories",
            "BOOKMARK": "directories",
            "POLICY": "policy",
        }

        self.rebuild_indexes()
        self.load_config()
        self.configure_readline(auto_persist_history)
        self.update_prompt()
        self.check_command_registry()

    # ------------------------------------------------------------------
    # Output plumbing
    # ------------------------------------------------------------------

    @property
    def out(self):
        return self._stdout if self._stdout is not None else sys.stdout

    @property
    def err(self):
        # Diagnostics follow 2> only. When stdout alone is diverted they stay on
        # the console, so `DIR nosuch > out.txt` reports the error to the user
        # rather than folding it silently into the file.
        return self._stderr if self._stderr is not None else sys.stderr

    @property
    def diverted(self):
        """True when normal output is going somewhere other than the console."""
        return self._stdout is not None

    @property
    def redirected(self):
        """True when either stream is diverted.

        External programs inherit real OS handles, so they must take the
        capturing path whenever *any* stream has been redirected. Testing only
        stdout would open (and truncate) the target of a bare `2>` and then let
        the child write past it to the console.
        """
        return self._stdout is not None or self._stderr is not None

    def emit(self, *values, **kwargs):
        separator = kwargs.pop("sep", " ")
        end = kwargs.pop("end", "\n")
        if kwargs:
            raise TypeError("emit() got unexpected keyword arguments: %s" % sorted(kwargs))
        self.write_to(self.out, separator.join(str(value) for value in values) + end)

    def emit_error(self, *values):
        self.write_to(self.err, " ".join(str(value) for value in values) + "\n")

    @staticmethod
    def write_to(stream, text):
        """Write text, degrading rather than dropping it.

        A console code page that cannot represent a character raises
        UnicodeEncodeError; swallowing that would silently delete whole lines of
        a DIR listing, so transliterate instead. Only a closed pipe is ignored.
        """
        try:
            stream.write(text)
        except UnicodeEncodeError:
            encoding = getattr(stream, "encoding", None) or "ascii"
            stream.write(text.encode(encoding, "backslashreplace").decode(encoding, "replace"))
        except BrokenPipeError:
            pass

    def ask(self, question):
        """Prompt the user. Returns '' when there is nobody to answer."""
        if not self.interactive:
            return ""
        try:
            return input(question)
        except (EOFError, KeyboardInterrupt):
            self.emit("")
            return ""

    def confirm(self, question):
        return self.ask(question).strip().lower() in ("y", "yes")

    # ------------------------------------------------------------------
    # Prompt
    # ------------------------------------------------------------------

    def update_prompt(self):
        self.prompt = self.shorten_path(os.getcwd()) + "> "

    def shorten_path(self, path, budget=None):
        """Keep the prompt narrow enough to leave room for typing."""
        home = os.path.expanduser("~")
        if home and path.startswith(home):
            path = "~" + path[len(home):]
        if budget is None:
            budget = max(20, self.terminal_width() // 3)
        if len(path) <= budget:
            return path
        parts = [part for part in path.replace("\\", "/").split("/") if part]
        if len(parts) <= 2:
            return path[-budget:]
        shortened = parts[0] + "/.../" + "/".join(parts[-2:])
        if len(shortened) > budget:
            shortened = ".../" + parts[-1]
        return shortened

    @staticmethod
    def terminal_width(default=80):
        try:
            return shutil.get_terminal_size((default, 24)).columns
        except (OSError, ValueError):
            return default

    # ------------------------------------------------------------------
    # readline
    # ------------------------------------------------------------------

    def detect_readline_backend(self):
        if readline is None:
            return None
        documentation = getattr(readline, "__doc__", "") or ""
        location = getattr(readline, "__file__", "") or ""
        if "libedit" in documentation:
            return "libedit"
        if "pyreadline" in documentation.lower() or "site-packages" in location:
            return "pyreadline3"
        return "GNU readline"

    def configure_readline(self, auto_persist_history):
        self.readline_backend = self.detect_readline_backend()
        if readline is None:
            return

        if self.history_file:
            try:
                readline.read_history_file(self.history_file)
            except FileNotFoundError:
                pass
            except OSError as err:
                self.emit_error("Warning: could not read history file:", err)

        try:
            existing = readline.get_current_history_length()
        except Exception:  # pragma: no cover - backend dependent
            existing = 0
        try:
            readline.set_history_length(max(READLINE_HISTORY_LENGTH, existing))
        except Exception:  # pragma: no cover - backend dependent
            pass

        try:
            readline.set_completer_delims(" \t\n")
            readline.set_completer(self.complete)
            if self.readline_backend == "libedit":
                readline.parse_and_bind("bind ^I rl_complete")
            else:
                readline.parse_and_bind("tab: complete")
        except Exception as err:
            self.emit_error("Warning: command completion is unavailable:", err)

        if auto_persist_history and self.history_file:
            atexit.register(self.save_readline_history)

    def save_readline_history(self):
        if readline is None or not self.history_file:
            return
        try:
            readline.write_history_file(self.history_file)
        except OSError as err:
            self.emit_error("Warning: could not save history file:", err)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def load_config(self):
        if not self.config_file:
            return
        try:
            with open(self.config_file, "r", encoding="utf-8-sig") as config_stream:
                config = json.load(config_stream)
        except FileNotFoundError:
            self.config_loaded = True
            return
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as err:
            self.config_loaded = False
            self.emit_error("Warning: could not load config:", err)
            return

        if not isinstance(config, dict):
            self.config_loaded = False
            self.emit_error("Warning: config file is not a JSON object; ignoring it.")
            return

        self.config_loaded = True
        self.aliases = self.load_name_map(config.get("aliases"), "alias")
        self.macros = self.load_name_map(config.get("macros"), "macro")
        self.bookmarks = self.load_name_map(config.get("bookmarks"), "bookmark")

        policy = config.get("policy")
        if isinstance(policy, dict):
            for key, value in policy.items():
                if key in DEFAULT_POLICY:
                    self.policy[key] = value
        self.normalise_policy()
        self.stored_policy = dict(self.policy)
        self.rebuild_indexes()

    def load_name_map(self, raw, kind):
        """Validate a persisted name -> text mapping, reporting what is dropped."""
        if not isinstance(raw, dict):
            return {}
        cleaned = {}
        # Entries this session refuses are kept aside and written back on save.
        # Ignoring an entry is fine; deleting the user's definition is not.
        quarantine = self.quarantined.setdefault(kind, {})
        for name, value in raw.items():
            if not isinstance(name, str) or not isinstance(value, str):
                self.emit_error("Warning: ignoring non-text %s entry: %r" % (kind, name))
                continue
            ok, reason = self.validate_name(name, kind)
            if not ok:
                quarantine[name] = value
                self.emit_error(
                    "Warning: ignoring %s '%s': %s (kept in the config, unused)" % (kind, name, reason)
                )
                continue
            key = self.normalise_command(name)
            duplicate = next((existing for existing in cleaned if self.normalise_command(existing) == key), None)
            if duplicate is not None:
                self.emit_error(
                    "Warning: %s '%s' collides with '%s'; keeping the first." % (kind, name, duplicate)
                )
                continue
            cleaned[name] = value
        return cleaned

    def normalise_policy(self):
        for key, default in DEFAULT_POLICY.items():
            value = self.policy.get(key, default)
            if isinstance(default, bool):
                self.policy[key] = self.coerce_bool(value, default)
            else:
                choices = POLICY_CHOICES.get(key, ())
                text = str(value).strip().lower()
                self.policy[key] = text if text in choices else default

    @staticmethod
    def coerce_bool(value, default=False):
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in TRUE_WORDS:
            return True
        if text in FALSE_WORDS:
            return False
        return default

    def atomic_write_json(self, path, payload):
        directory = os.path.dirname(os.path.abspath(path)) or "."
        temporary = os.path.join(directory, os.path.basename(path) + ".tmp")
        try:
            with open(temporary, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except BaseException:
            # Never leave a stray copy of the config next to the real one.
            with contextlib.suppress(OSError):
                os.remove(temporary)
            raise

    def save_config(self):
        if not self.config_file:
            return False

        if not self.config_loaded and os.path.exists(self.config_file):
            backup = self.config_file + ".bak"
            try:
                os.replace(self.config_file, backup)
            except OSError as err:
                self.emit_error("Refusing to overwrite an unreadable config:", err)
                return False
            self.emit_error("Unreadable config moved to", backup + "; starting a fresh one.")
            self.config_loaded = True

        def merged(active, kind):
            combined = dict(self.quarantined.get(kind, {}))
            combined.update(active)
            return combined

        config = {
            "version": CONFIG_VERSION,
            "aliases": merged(self.aliases, "alias"),
            "macros": merged(self.macros, "macro"),
            "bookmarks": merged(self.bookmarks, "bookmark"),
            "policy": self.stored_policy,
        }
        try:
            self.atomic_write_json(self.config_file, config)
            return True
        except (OSError, TypeError, ValueError) as err:
            self.emit_error("Warning: could not save config:", err)
            return False

    def persist(self, message, failure_note):
        """Save the config and tell the truth about whether it stuck."""
        saved = self.save_config()
        if saved:
            self.emit(message)
        else:
            self.emit(message + " " + failure_note)
        return saved

    # ------------------------------------------------------------------
    # Names and lookup indexes
    # ------------------------------------------------------------------

    @staticmethod
    def normalise_command(name):
        return str(name).upper()

    def validate_name(self, name, kind="alias"):
        if not name:
            return False, "the name is empty"
        if any(char in self.NAME_FORBIDDEN for char in name):
            return False, "names cannot contain whitespace, quotes or shell operators"
        if name[0] in ("!", "?", "-", "/"):
            return False, "names cannot start with '%s'" % name[0]
        if self.normalise_command(name) in self.commands:
            return False, "'%s' is a built-in command; PyCMD does not allow shadowing builtins" % name
        return True, ""

    def rebuild_indexes(self):
        self.alias_index = {self.normalise_command(name): name for name in self.aliases}
        self.macro_index = {self.normalise_command(name): name for name in self.macros}
        self.bookmark_index = {self.normalise_command(name): name for name in self.bookmarks}
        self._completion_cache = (None, [])

    def check_command_registry(self):
        missing_info = sorted(set(self.commands) - set(self.COMMAND_INFO))
        missing_handler = sorted(set(self.COMMAND_INFO) - set(self.commands))
        if missing_info:
            self.emit_error("Internal warning: commands without help entries:", ", ".join(missing_info))
        if missing_handler:
            self.emit_error("Internal warning: help entries without handlers:", ", ".join(missing_handler))
        return not (missing_info or missing_handler)

    def classify_command(self, command):
        """Resolve a command word the same way execute_line does."""
        key = self.normalise_command(command)
        if key in self.alias_index:
            name = self.alias_index[key]
            return "alias", name, self.aliases[name]
        if key in self.macro_index:
            name = self.macro_index[key]
            return "macro", name, self.macros[name]
        if key in self.commands:
            return "builtin", key, self.commands[key]
        return "unknown", command, None

    # ------------------------------------------------------------------
    # Completion
    # ------------------------------------------------------------------

    def complete(self, text, state):
        if state == 0 or self._completion_cache[0] != text:
            self._completion_cache = (text, self.complete_candidates(text))
        options = self._completion_cache[1]
        if state < len(options):
            return options[state]
        return None

    def complete_candidates(self, text):
        """Prefix-only completion. Never substitutes a non-matching candidate."""
        line = ""
        if readline is not None:
            try:
                line = readline.get_line_buffer()[: readline.get_endidx()]
            except Exception:  # pragma: no cover - backend dependent
                line = text
        before = line[: len(line) - len(text)] if text and line.endswith(text) else line
        first_token = before.strip().split(" ", 1)[0] if before.strip() else ""

        if not first_token:
            pool = sorted(set(self.commands) | set(self.aliases) | set(self.macros))
            return [name for name in pool if name.upper().startswith(text.upper())]

        kind = self.command_completers.get(self.normalise_command(first_token), "paths")
        if text.startswith("-"):
            return self.complete_flags(first_token, text)
        if kind == "bookmarks":
            pool = sorted(self.bookmarks)
        elif kind == "macros":
            pool = sorted(self.macros)
        elif kind == "aliases":
            pool = sorted(self.aliases)
        elif kind == "topics":
            pool = sorted(self.COMMAND_INFO)
        elif kind == "policy":
            pool = sorted(DEFAULT_POLICY)
        elif kind == "directories":
            return self.get_path_suggestions(text, limit=100, directories_only=True)
        else:
            return self.get_path_suggestions(text, limit=100)
        return [name for name in pool if name.upper().startswith(text.upper())]

    def complete_flags(self, command, text):
        info = self.COMMAND_INFO.get(self.normalise_command(command))
        if not info:
            return []
        flags = sorted(set(re.findall(r"--[a-z-]+", info[1])))
        return [flag for flag in flags if flag.startswith(text)]

    def get_suggestions(self, text, limit=6):
        """Fuzzy 'did you mean' suggestions. Also used by SUGGEST."""
        text = text or ""
        candidates = sorted(
            set(self.commands) | set(self.aliases) | set(self.macros) | set(self.bookmarks)
        )
        if not text:
            return candidates[:limit]

        upper_text = text.upper()
        prefix_matches = [
            candidate
            for candidate in candidates
            if candidate.upper().startswith(upper_text)
        ]
        close_matches = difflib.get_close_matches(
            upper_text,
            [candidate.upper() for candidate in candidates],
            n=limit,
            cutoff=0.45,
        )
        lookup = {candidate.upper(): candidate for candidate in candidates}
        suggestions = prefix_matches + [
            lookup[match] for match in close_matches if lookup[match] not in prefix_matches
        ]
        for match in self.get_path_suggestions(text, limit=limit):
            if match not in suggestions:
                suggestions.append(match)
        return suggestions[:limit]

    def get_path_suggestions(self, text, limit=6, directories_only=False):
        if not text:
            return []

        expanded = os.path.expanduser(text)
        directory, prefix = os.path.split(expanded)
        display_directory, _ = os.path.split(text)
        directory = directory or "."

        if not os.path.isdir(directory):
            return []

        suggestions = []
        try:
            names = sorted(os.listdir(directory), key=str.lower)
        except OSError:
            return []

        for name in names:
            if not name.lower().startswith(prefix.lower()):
                continue
            candidate_path = os.path.join(directory, name)
            is_directory = os.path.isdir(candidate_path)
            if directories_only and not is_directory:
                continue
            display_value = os.path.join(display_directory, name) if display_directory else name
            if is_directory:
                display_value += os.sep
            suggestions.append(display_value)
            if len(suggestions) >= limit:
                break
        return suggestions

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def split_input(self, user_input):
        command_line = user_input.strip()
        if not command_line:
            return "", ""
        if command_line.startswith("??"):
            return "??", command_line[2:].strip()
        if command_line.startswith("?"):
            return "?", command_line[1:].strip()
        if command_line.startswith("!"):
            return "!", command_line[1:].strip()
        parts = command_line.split(maxsplit=1)
        command = parts[0]
        arg_string = parts[1] if len(parts) > 1 else ""
        return command, arg_string

    def tokenise_args(self, arg_string):
        if not arg_string:
            return []
        try:
            lexer = shlex.shlex(arg_string, posix=False)
            lexer.whitespace_split = True
            lexer.commenters = ""
            return [self.strip_wrapping_quotes(token) for token in lexer]
        except ValueError as err:
            self.emit_error("Input parse error:", err)
            return arg_string.split()

    @staticmethod
    def strip_wrapping_quotes(value):
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            return value[1:-1]
        return value

    @staticmethod
    def skip_substitution(text, index):
        """Index just past the ')' closing a '$(' at index, or -1 if unbalanced.

        The operator and redirection scanners use this to step over a whole
        $(...) region, so a '|' or '>' inside a substitution belongs to the
        inner command rather than splitting the outer line.
        """
        level = 1
        cursor = index + 2
        while cursor < len(text) and level:
            if text[cursor] == "(":
                level += 1
            elif text[cursor] == ")":
                level -= 1
            cursor += 1
        return -1 if level else cursor

    @staticmethod
    def read_token(text, index):
        """Read one quote-aware token starting at index. Returns (token, index)."""
        length = len(text)
        while index < length and text[index].isspace():
            index += 1
        chars = []
        quote = None
        while index < length:
            char = text[index]
            if quote:
                if char == quote:
                    quote = None
                else:
                    chars.append(char)
                index += 1
                continue
            if char in ("'", '"'):
                quote = char
                index += 1
                continue
            if char.isspace():
                break
            chars.append(char)
            index += 1
        return "".join(chars), index

    def split_first_token(self, text):
        """Split a raw string into (first token, remainder), honouring quotes."""
        token, index = self.read_token(text, 0)
        return token, text[index:].strip()

    def split_operators(self, line, operators=None):
        """Split a line on shell operators, ignoring anything inside quotes.

        Returns a list of (operator_before_segment, text) pairs. The first
        segment always carries None. A single '&' stays literal so that
        filenames such as A&B.txt keep working.
        """
        operators = self.OPERATORS if operators is None else operators
        segments = []
        pending = []
        operator = None
        quote = None
        index = 0
        length = len(line)

        while index < length:
            char = line[index]
            if quote:
                pending.append(char)
                if char == quote:
                    quote = None
                index += 1
                continue
            if char in ("'", '"'):
                quote = char
                pending.append(char)
                index += 1
                continue
            if line.startswith("$(", index):
                end = self.skip_substitution(line, index)
                if end > 0:
                    pending.append(line[index:end])
                    index = end
                    continue
            matched = None
            for candidate in operators:
                if line.startswith(candidate, index):
                    matched = candidate
                    break
            if matched:
                segments.append((operator, "".join(pending)))
                pending = []
                operator = matched
                index += len(matched)
                continue
            pending.append(char)
            index += 1

        if quote:
            raise ValueError("unbalanced %s quote" % quote)
        segments.append((operator, "".join(pending)))
        return segments

    def split_macro_commands(self, macro_text):
        try:
            segments = self.split_operators(macro_text, operators=(";",))
        except ValueError as err:
            self.emit_error("Macro parse error:", err)
            return []
        return [text.strip() for _, text in segments if text.strip()]

    def parse_redirections(self, text):
        """Pull >, >>, <, 2> and 2>> out of a stage, leaving the command text."""
        clean = []
        redirections = []
        quote = None
        index = 0
        length = len(text)

        while index < length:
            char = text[index]
            if quote:
                clean.append(char)
                if char == quote:
                    quote = None
                index += 1
                continue
            if char in ("'", '"'):
                quote = char
                clean.append(char)
                index += 1
                continue
            if text.startswith("$(", index):
                end = self.skip_substitution(text, index)
                if end > 0:
                    clean.append(text[index:end])
                    index = end
                    continue
            if char in (">", "<"):
                descriptor = 1 if char == ">" else 0
                if char == ">" and clean and clean[-1] in ("1", "2"):
                    if len(clean) == 1 or clean[-2].isspace():
                        descriptor = int(clean.pop())
                index += 1
                mode = "w"
                if char == ">" and index < length and text[index] == ">":
                    mode = "a"
                    index += 1
                target, index = self.read_token(text, index)
                if not target:
                    raise ValueError("missing target after '%s'" % char)
                # 2>&1 duplicates a descriptor rather than naming a file. Without
                # this, PyCMD would create a file literally called "&1".
                if char == ">" and re.fullmatch(r"&[0-2]", target):
                    redirections.append((descriptor, "dup", int(target[1:])))
                    continue
                redirections.append((descriptor, "r" if char == "<" else mode, target))
                continue
            clean.append(char)
            index += 1

        if quote:
            # An apostrophe in a filename (it's.txt, don't stop) is far commoner
            # than deliberate quoting, and a half-parsed line cannot be trusted
            # to say where a redirect begins. Treat the whole line literally.
            return text.strip(), []
        return "".join(clean).strip(), redirections

    @contextlib.contextmanager
    def apply_redirections(self, redirections):
        opened = []
        saved = (self._stdout, self._stderr, self._pipe_input)
        try:
            for descriptor, mode, target in redirections:
                if mode == "dup":
                    # 2>&1 points stderr at wherever stdout currently goes, so
                    # ordering matters exactly as it does in a real shell.
                    if target == 1:
                        source = self._stdout if self._stdout is not None else sys.stdout
                    else:
                        source = self._stderr if self._stderr is not None else sys.stderr
                    if descriptor == 2:
                        self._stderr = source
                    else:
                        self._stdout = source
                    continue
                path = os.path.expanduser(target)
                if mode == "r":
                    with open(path, "r", encoding="utf-8", errors="replace") as stream:
                        self._pipe_input = stream.read()
                    continue
                handle = open(path, mode, encoding="utf-8")
                opened.append(handle)
                if descriptor == 2:
                    self._stderr = handle
                else:
                    self._stdout = handle
            yield
        finally:
            self._stdout, self._stderr, self._pipe_input = saved
            for handle in opened:
                try:
                    handle.close()
                except OSError:
                    pass

    def expand_substitutions(self, text):
        """Replace $(command) with that command's output.

        Like variable expansion this runs after the line has been parsed, so
        output containing ';' or '|' is inserted as text and can never become a
        command of its own. Newlines collapse to spaces, as in other shells.
        """
        if "$(" not in text or not self.policy.get("expand_variables", True):
            return text
        if self._substitution_depth >= self.MAX_EXPANSION_DEPTH:
            self.emit_error("Command substitution stopped: nested too deeply.")
            return text

        pieces = []
        index = 0
        while index < len(text):
            start = text.find("$(", index)
            if start < 0:
                pieces.append(text[index:])
                break
            pieces.append(text[index:start])
            level = 1
            cursor = start + 2
            while cursor < len(text) and level:
                if text[cursor] == "(":
                    level += 1
                elif text[cursor] == ")":
                    level -= 1
                cursor += 1
            if level:
                # Unbalanced: leave it exactly as typed rather than guessing.
                pieces.append(text[start:])
                break
            pieces.append(self.capture_output(text[start + 2:cursor - 1]))
            index = cursor
        return "".join(pieces)

    def capture_output(self, command_line):
        buffer = io.StringIO()
        saved_out = self._stdout
        self._stdout = buffer
        self._capture_depth += 1
        self._substitution_depth += 1
        try:
            self.run_line(command_line)
        finally:
            self._substitution_depth -= 1
            self._capture_depth -= 1
            self._stdout = saved_out
        return " ".join(buffer.getvalue().split())

    VARIABLE_PATTERN = re.compile(r"\$(\?|\{\w+\}|\w+)")

    def expand_variables(self, text):
        """Substitute $NAME, ${NAME} and $? .

        Deliberately applied *after* operators and redirection have been parsed,
        so a variable holding '; DEL x' can never become a second command. An
        unknown name is left alone rather than blanked, so a literal $ survives.
        """
        if not text or "$" not in text or not self.policy.get("expand_variables", True):
            return text

        def replace(match):
            name = match.group(1)
            if name == "?":
                return str(self.last_status)
            if name.startswith("{"):
                name = name[1:-1]
            if name in self.variables:
                return self.variables[name]
            value = os.environ.get(name)
            return value if value is not None else match.group(0)

        return self.VARIABLE_PATTERN.sub(replace, text)

    def is_raw_tail(self, command_line):
        """True for commands whose tail belongs to the OS shell verbatim."""
        command, _ = self.split_input(command_line)
        return self.normalise_command(command) in self.RAW_TAIL_COMMANDS

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------

    def render_table(self, rows, headers=None, max_width=None, minimum=8, truncate=True):
        rows = [list(row) for row in rows]
        if not rows:
            return []
        if headers:
            rows = [list(headers)] + rows

        columns = max(len(row) for row in rows)
        for row in rows:
            while len(row) < columns:
                row.append("")

        widths = [max(len(str(row[index])) for row in rows) for index in range(columns)]
        if max_width is None:
            max_width = self.terminal_width()

        def total():
            return sum(widths) + 2 * (columns - 1)

        while truncate and total() > max_width:
            widest = max(range(columns), key=lambda index: widths[index])
            if widths[widest] <= minimum:
                break
            widths[widest] = max(minimum, widths[widest] - (total() - max_width))

        lines = []
        for row_index, row in enumerate(rows):
            cells = []
            for index, value in enumerate(row):
                text = str(value)
                if len(text) > widths[index]:
                    text = text[: max(1, widths[index] - 1)] + "…"
                cells.append(text.ljust(widths[index]))
            lines.append("  ".join(cells).rstrip())
            if headers and row_index == 0:
                lines.append("  ".join("-" * width for width in widths).rstrip())
        return lines

    def print_table(self, rows, headers=None, truncate=True):
        for line in self.render_table(rows, headers=headers, truncate=truncate):
            self.emit(line)

    # ------------------------------------------------------------------
    # Statistics and on-disk records
    # ------------------------------------------------------------------

    def record_stat(self, command_line, success, duration, status=None, resolved=None):
        record = {
            "command": command_line,
            "success": success,
            "status": self.last_status if status is None else status,
            "duration": duration,
            "time": time.strftime("%H:%M:%S"),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "cwd": os.getcwd(),
        }
        if resolved and resolved != command_line:
            record["resolved"] = resolved
        self.command_stats.append(record)
        self.append_history_record(record)

    def append_history_record(self, record):
        if not self.record_file or self.record_write_failed or not self.policy.get("record", True):
            return
        try:
            with open(self.record_file, "a", encoding="utf-8") as record_stream:
                json.dump(record, record_stream, sort_keys=True)
                record_stream.write("\n")
        except OSError as err:
            self.record_write_failed = True
            self.emit_error("Warning: could not save history record:", err)
            return
        self.rotate_record_file()

    def rotate_record_file(self):
        try:
            if os.path.getsize(self.record_file) <= RECORD_MAX_BYTES:
                return
            os.replace(self.record_file, self.record_file + ".1")
        except OSError as err:
            self.emit_error("Warning: could not rotate history records:", err)

    def iter_history_records(self, limit=200, window=RECORD_WINDOW_BYTES):
        """Read only the tail of the record file, so search stays bounded."""
        if not self.record_file or not os.path.exists(self.record_file):
            return []
        records = []
        try:
            size = os.path.getsize(self.record_file)
            with open(self.record_file, "rb") as record_stream:
                if size > window:
                    record_stream.seek(size - window)
                    record_stream.readline()  # discard the partial first line
                for raw in record_stream:
                    try:
                        records.append(json.loads(raw.decode("utf-8", "replace")))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
        except OSError as err:
            self.emit_error("Warning: could not read history records:", err)
        return records[-limit:]

    def record_file_size(self):
        try:
            return os.path.getsize(self.record_file)
        except (OSError, TypeError):
            return 0

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    @staticmethod
    def coerce_status(result):
        """Map a handler's return value onto a process-style status code."""
        if result is None or result is True:
            return 0
        if result is False:
            return 1
        try:
            return int(result)
        except (TypeError, ValueError):
            return 0

    def resolve_program(self, command):
        """Return the executable a bare word names on PATH, or None.

        This is what separates 'findstr' from 'dur': a word that resolves to a
        real program is not a typo, so it can run directly through argv with no
        shell involved. A word that resolves to nothing is the dangerous case.
        """
        if not command or not self.policy.get("path_programs", True):
            return None
        if any(char in command for char in "\"'*?"):
            return None
        try:
            found = shutil.which(os.path.expanduser(command))
        except (OSError, TypeError):
            return None
        if not found:
            return None
        # On Windows shutil.which searches the current directory first. A bare
        # word must never pick up a binary that merely happens to sit in the
        # directory you cd'd into; require an explicit ./ or a path for that.
        explicit = os.sep in command or (os.altsep and os.altsep in command)
        if not explicit and os.path.dirname(os.path.abspath(found)) == os.getcwd():
            return None
        return found

    def check_unknown(self, command_line, alias_depth=0, macro_depth=0):
        """Vet an unrecognised command *before* anything irreversible happens.

        Returns None when the line may proceed, or a status code when it is
        refused. Running this ahead of redirection is what stops a typo such as
        'dur > notes.txt' from truncating notes.txt on its way to being refused.
        """
        # Follow aliases to the word that will actually execute. A single-level
        # check would let `boom > notes.txt` (alias boom -> a typo) open and
        # truncate notes.txt before the expansion is refused.
        command, _ = self.split_input(command_line)
        seen = set()
        for _ in range(self.MAX_EXPANSION_DEPTH):
            kind, name, payload = self.classify_command(command)
            if kind != "alias" or name in seen:
                break
            seen.add(name)
            command, _ = self.split_input(payload)

        if kind != "unknown":
            return None
        if self.resolve_program(command):
            return None

        self.emit_error("Command not recognized.")
        self.print_suggestions(command, to_error=True)
        if self.authorise_shell(command_line, "fallback", bool(alias_depth or macro_depth)):
            return None
        self.emit_error(
            "Not run. Use !<command>, LEGACY or RUN to reach the OS shell,"
            " or POLICY shell_fallback always to restore 3.0 behaviour."
        )
        return 127

    def authorise_shell(self, command_line, source="fallback", in_expansion=False):
        if source == "legacy":
            return bool(self.policy.get("legacy", True))
        if source == "run":
            return bool(self.policy.get("run_shell", True))

        mode = self.policy.get("shell_fallback", "confirm")
        if mode == "always":
            return True
        if mode == "off":
            return False
        if in_expansion or not self.interactive:
            return False
        return self.confirm("Run '%s' through the OS shell? [y/N] " % command_line)

    def run_external(self, command_line, argv=None):
        """Run an external command, honouring any active capture or redirect."""
        if not self.redirected and self._pipe_input is None:
            if argv is not None:
                return subprocess.run(argv, shell=False).returncode
            raw = os.system(command_line)
            if raw and os.name != "nt" and hasattr(os, "waitstatus_to_exitcode"):
                try:
                    return os.waitstatus_to_exitcode(raw)
                except ValueError:
                    return 1
            return raw

        completed = subprocess.run(
            argv if argv is not None else command_line,
            shell=argv is None,
            input=self._pipe_input,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if completed.stdout:
            self.emit(completed.stdout, end="")
        if completed.stderr:
            self.emit_error(completed.stderr.rstrip("\n"))
        return completed.returncode

    def process_input(self, user_input):
        return self.execute_line(user_input, record_history=True)

    def execute_line(self, user_input, record_history=True, alias_depth=0, macro_depth=0, display_line=None):
        command_line = user_input.strip()
        if not command_line:
            return True

        if record_history:
            self.history.append(command_line)
            self._executing_line = command_line

        started = time.perf_counter()
        try:
            status = self.run_line(command_line, alias_depth=alias_depth, macro_depth=macro_depth)
        except KeyboardInterrupt:
            self.emit_error("Interrupted.")
            status = 130
        except Exception as err:
            self.emit_error("Error executing command:", err)
            status = 1
        duration = time.perf_counter() - started

        self.last_status = status
        if record_history:
            self.record_stat(display_line or command_line, status == 0, duration, status)
        return status == 0

    def run_line(self, command_line, alias_depth=0, macro_depth=0):
        """Split a line into operator-separated groups and run them in order."""
        if self.policy.get("operators", True) and not self.is_raw_tail(command_line):
            try:
                segments = self.split_operators(command_line)
            except ValueError:
                # An unpaired quote is far more often a filename like it's.txt
                # than an attempt at quoting, so treat the line as one command
                # rather than refusing it outright.
                segments = [(None, command_line)]
        else:
            segments = [(None, command_line)]

        groups = []
        for operator, text in segments:
            if operator == "|" and groups:
                if not text.strip():
                    self.emit_error("Syntax error: '|' must be followed by a command.")
                    return 1
                groups[-1][1].append(text)
            else:
                groups.append((operator, [text]))

        status = self.last_status
        for index, (operator, stages) in enumerate(groups):
            if index:
                if operator == "&&" and status != 0:
                    continue
                if operator == "||" and status == 0:
                    continue
            if len(stages) == 1:
                status = self.run_stage(stages[0], alias_depth, macro_depth)
            else:
                status = self.run_pipeline(stages, alias_depth, macro_depth)
            self.last_status = status
        return status

    def run_pipeline(self, stages, alias_depth=0, macro_depth=0):
        data = None
        status = 0
        for index, stage in enumerate(stages):
            if index == len(stages) - 1:
                saved_input = self._pipe_input
                self._pipe_input = data
                try:
                    status = self.run_stage(stage, alias_depth, macro_depth)
                finally:
                    self._pipe_input = saved_input
                continue

            buffer = io.StringIO()
            saved_out, saved_input = self._stdout, self._pipe_input
            self._stdout, self._pipe_input = buffer, data
            self._capture_depth += 1
            try:
                status = self.run_stage(stage, alias_depth, macro_depth)
            finally:
                self._capture_depth -= 1
                self._stdout, self._pipe_input = saved_out, saved_input
            data = buffer.getvalue()
        return status

    def run_stage(self, text, alias_depth=0, macro_depth=0):
        stage_text = text.strip()
        if not stage_text:
            self.emit_error("Syntax error: empty command segment.")
            return 1

        redirections = []
        if self.policy.get("operators", True) and not self.is_raw_tail(stage_text):
            try:
                stage_text, redirections = self.parse_redirections(stage_text)
            except ValueError as err:
                self.emit_error("Redirection error:", err)
                return 1
            if not stage_text:
                self.emit_error("Syntax error: redirection without a command.")
                return 1
            redirections = [
                (descriptor, mode, target if mode == "dup" else self.expand_variables(target))
                for descriptor, mode, target in redirections
            ]

        # Vet the command before opening any redirection target, so a refused
        # command never truncates a file on its way to being refused.
        refusal = self.check_unknown(stage_text, alias_depth, macro_depth)
        if refusal is not None:
            return refusal

        if not redirections:
            return self.dispatch(stage_text, alias_depth, macro_depth)

        try:
            with self.apply_redirections(redirections):
                return self.dispatch(stage_text, alias_depth, macro_depth)
        except OSError as err:
            self.emit_error("Redirection error:", err)
            return 1

    def dispatch(self, command_line, alias_depth=0, macro_depth=0):
        command_line = self.expand_variables(self.expand_substitutions(command_line))
        command, arg_string = self.split_input(command_line)
        args = self.tokenise_args(arg_string)
        kind, name, payload = self.classify_command(command)

        if kind == "alias":
            if alias_depth >= self.MAX_EXPANSION_DEPTH:
                self.emit_error("Alias expansion stopped: possible alias loop.")
                return 1
            expanded = payload + (" " + arg_string if arg_string else "")
            return self.run_line(expanded, alias_depth=alias_depth + 1, macro_depth=macro_depth)

        if kind == "macro":
            succeeded = self.run_macro(name, args, arg_string, macro_depth=macro_depth, alias_depth=alias_depth)
            return 0 if succeeded else 1

        if kind == "builtin":
            return self.coerce_status(payload(args, arg_string))

        # Unknown commands have already been vetted by run_stage.check_unknown.
        program = self.resolve_program(command)
        if program:
            return self.run_external(command_line, argv=[program] + args)
        return self.run_external(command_line)

    # ------------------------------------------------------------------
    # Commands: navigation and files
    # ------------------------------------------------------------------

    def path_operand(self, operands):
        """Resolve operands into one path, tolerating unquoted spaces."""
        if not operands:
            return ""
        if len(operands) == 1:
            return operands[0]
        joined = " ".join(operands)
        if os.path.exists(os.path.expanduser(joined)):
            return joined
        return None

    def expand_globs(self, operands, keep_unmatched=True):
        """Expand wildcards.

        keep_unmatched follows cmd.exe: a pattern that matches nothing is passed
        through so the command can report it. FOR passes False instead, because
        looping once over the literal text '*.py' is never what anyone means.
        """
        expanded = []
        for operand in operands:
            if any(char in operand for char in "*?["):
                matches = sorted(glob.glob(os.path.expanduser(operand)), key=str.lower)
                if matches:
                    expanded.extend(matches)
                    continue
                if not keep_unmatched:
                    continue
            expanded.append(operand)
        return expanded

    def cmd_cwd(self, args, arg_string=""):
        operands = [arg for arg in args if arg.lower() not in ("/d", "-d")]
        if not operands:
            self.emit_error("Usage: CWD <directory>")
            return False
        dir_path = self.path_operand(operands)
        if dir_path is None:
            self.emit_error("CWD accepts a single directory; quote paths containing spaces.")
            return False
        try:
            os.chdir(os.path.expanduser(dir_path))
            self.update_prompt()
            return True
        except OSError as err:
            self.emit_error("Error changing directory:", err)
            return False

    def cmd_pwd(self, args, arg_string=""):
        self.emit("Current Directory:", os.getcwd())
        return True

    def cmd_dir(self, args, arg_string=""):
        details = False
        operands = []
        for arg in args:
            if arg.lower() in ("--details", "/details"):
                details = True
            else:
                operands.append(arg)

        target = os.getcwd()
        if operands:
            resolved = self.path_operand(operands)
            if resolved is None:
                self.emit_error("DIR accepts a single path; quote paths containing spaces.")
                return False
            target = resolved

        target = os.path.expanduser(target)
        try:
            if os.path.isdir(target):
                names = sorted(os.listdir(target), key=str.lower)
                base = target
            elif any(char in target for char in "*?["):
                matches = sorted(glob.glob(target), key=str.lower)
                if not matches:
                    self.emit_error("No matches for:", target)
                    return False
                base = os.path.dirname(matches[0]) or "."
                names = [os.path.basename(match) for match in matches]
            elif os.path.exists(target):
                base = os.path.dirname(target) or "."
                names = [os.path.basename(target)]
            else:
                self.emit_error("Error listing directory: no such path:", target)
                return False
        except OSError as err:
            self.emit_error("Error listing directory:", err)
            return False

        if not details:
            for name in names:
                self.emit(name)
            return True

        rows = []
        for name in names:
            item_path = os.path.join(base, name)
            try:
                stat = os.stat(item_path)
                is_directory = os.path.isdir(item_path)
                item_type = "<DIR>" if is_directory else "file"
                size = "" if is_directory else str(stat.st_size)
                modified = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
            except OSError:
                item_type, size, modified = "?", "?", "?"
            rows.append((item_type, size, modified, name))
        self.print_table(rows, headers=("Type", "Size", "Modified", "Name"))
        return True

    def cmd_tree(self, args, arg_string=""):
        target = os.path.expanduser(args[0]) if args else os.getcwd()
        try:
            depth = int(args[1]) if len(args) > 1 else 2
        except ValueError:
            self.emit_error("Usage: TREE [path] [depth]")
            return False

        if depth < 0:
            self.emit_error("Depth must be 0 or greater.")
            return False
        if not os.path.isdir(target):
            self.emit_error("Tree path is not a directory:", target)
            return False

        target = os.path.abspath(target)
        self.emit(target)
        self.print_tree(target, depth)
        return True

    def print_tree(self, root, max_depth, prefix="", current_depth=0):
        if current_depth >= max_depth:
            return
        try:
            entries = sorted(os.listdir(root), key=str.lower)
        except OSError as err:
            self.emit(prefix + "Error: " + str(err))
            return

        for index, entry in enumerate(entries):
            path = os.path.join(root, entry)
            is_last = index == len(entries) - 1
            connector = "`-- " if is_last else "|-- "
            self.emit(prefix + connector + entry)
            if os.path.isdir(path):
                child_prefix = prefix + ("    " if is_last else "|   ")
                self.print_tree(path, max_depth, child_prefix, current_depth + 1)

    def cmd_mkdir(self, args, arg_string=""):
        if not args:
            self.emit_error("Usage: MKDIR <directory> [more...]")
            return False
        succeeded = True
        for operand in args:
            dirname = os.path.expanduser(operand)
            try:
                os.makedirs(dirname, exist_ok=False)
                self.emit("Directory '%s' created." % dirname)
            except OSError as err:
                self.emit_error("Error creating directory:", err)
                succeeded = False
        return succeeded

    def cmd_del(self, args, arg_string=""):
        dry_run = False
        force = False
        operands = []
        for arg in args:
            lowered = arg.lower()
            if lowered in ("--dry-run", "/dry-run", "-n"):
                dry_run = True
            elif lowered in ("--force", "/force", "-f"):
                force = True
            else:
                operands.append(arg)

        if not operands:
            self.emit_error("Usage: DEL [--dry-run] [--force] <file> [more...]")
            return False

        if len(operands) > 1:
            joined = " ".join(operands)
            if os.path.isfile(os.path.expanduser(joined)):
                operands = [joined]

        targets = [os.path.expanduser(path) for path in self.expand_globs(operands)]

        if dry_run:
            missing = False
            for filename in targets:
                self.emit("Would delete: %s" % filename)
                if not os.path.isfile(filename):
                    missing = True
            if missing:
                self.emit_error("Some targets are not existing files.")
                return False
            return True

        if len(targets) > 1 and not force:
            self.emit("About to delete %d files:" % len(targets))
            for filename in targets:
                self.emit(" ", filename)
            if not self.confirm("Delete these %d files? [y/N] " % len(targets)):
                self.emit_error("Cancelled. Use --force to skip this prompt.")
                return False

        succeeded = True
        for filename in targets:
            try:
                os.remove(filename)
                self.emit("File '%s' deleted." % filename)
            except OSError as err:
                self.emit_error("Error deleting file:", err)
                succeeded = False
        return succeeded

    def transfer_files(self, args, verb, action):
        """Shared COPY/MOVE body: <source...> <destination>."""
        operands = [arg for arg in args if not arg.startswith("--")]
        if len(operands) < 2:
            self.emit_error("Usage: %s <source> [more...] <destination>" % verb)
            return False

        destination = os.path.expanduser(operands[-1])
        sources = [os.path.expanduser(path) for path in self.expand_globs(operands[:-1])]
        into_directory = os.path.isdir(destination)
        if len(sources) > 1 and not into_directory:
            self.emit_error("%s needs an existing directory as the destination for several files." % verb)
            return False

        succeeded = True
        for source in sources:
            target = os.path.join(destination, os.path.basename(source)) if into_directory else destination
            if os.path.abspath(source) == os.path.abspath(target):
                self.emit_error("Source and destination are the same file: %s" % source)
                succeeded = False
                continue
            try:
                action(source, target)
                self.emit("%s -> %s" % (source, target))
            except (OSError, shutil.Error) as err:
                self.emit_error("Error during %s:" % verb.lower(), err)
                succeeded = False
        return succeeded

    def cmd_copy(self, args, arg_string=""):
        return self.transfer_files(args, "COPY", shutil.copy2)

    def cmd_move(self, args, arg_string=""):
        return self.transfer_files(args, "MOVE", shutil.move)

    def cmd_rename(self, args, arg_string=""):
        if len(args) != 2:
            self.emit_error("Usage: RENAME <old> <new>")
            return False
        old, new = (os.path.expanduser(value) for value in args)
        if os.path.exists(new):
            self.emit_error("Refusing to overwrite an existing path: %s" % new)
            return False
        try:
            os.rename(old, new)
            self.emit("%s -> %s" % (old, new))
            return True
        except OSError as err:
            self.emit_error("Error renaming:", err)
            return False

    def cmd_rmdir(self, args, arg_string=""):
        recurse = False
        force = False
        operands = []
        for arg in args:
            lowered = arg.lower()
            if lowered in ("--recurse", "/s", "-r"):
                recurse = True
            elif lowered in ("--force", "/force", "-f"):
                force = True
            else:
                operands.append(arg)

        if not operands:
            self.emit_error("Usage: RMDIR [--recurse] [--force] <directory> [more...]")
            return False

        targets = [os.path.expanduser(path) for path in self.expand_globs(operands)]
        if recurse and not force:
            self.emit("About to delete these directories and everything in them:")
            for path in targets:
                self.emit(" ", path)
            if not self.confirm("Delete recursively? [y/N] "):
                self.emit_error("Cancelled. Use --force to skip this prompt.")
                return False

        succeeded = True
        for path in targets:
            try:
                if recurse:
                    shutil.rmtree(path)
                else:
                    os.rmdir(path)
                self.emit("Directory '%s' removed." % path)
            except OSError as err:
                self.emit_error("Error removing directory:", err)
                succeeded = False
        return succeeded

    def cmd_touch(self, args, arg_string=""):
        if not args:
            self.emit_error("Usage: TOUCH <file> [more...]")
            return False
        succeeded = True
        for operand in args:
            path = os.path.expanduser(operand)
            try:
                with open(path, "a", encoding="utf-8"):
                    pass
                os.utime(path, None)
            except OSError as err:
                self.emit_error("Error touching file:", err)
                succeeded = False
        return succeeded

    # ------------------------------------------------------------------
    # Commands: directory stack
    # ------------------------------------------------------------------

    def cmd_pushd(self, args, arg_string=""):
        target = self.path_operand(args) if args else None
        if args and target is None:
            self.emit_error("PUSHD accepts a single directory; quote paths containing spaces.")
            return False

        origin = os.getcwd()
        if target:
            try:
                os.chdir(os.path.expanduser(target))
            except OSError as err:
                self.emit_error("Error changing directory:", err)
                return False
        self.directory_stack.append(origin)
        self.update_prompt()
        self.emit("Current Directory:", os.getcwd())
        return True

    def cmd_popd(self, args, arg_string=""):
        if not self.directory_stack:
            self.emit_error("The directory stack is empty.")
            return False
        target = self.directory_stack.pop()
        try:
            os.chdir(target)
        except OSError as err:
            self.emit_error("Error changing directory:", err)
            return False
        self.update_prompt()
        self.emit("Current Directory:", os.getcwd())
        return True

    def cmd_dirs(self, args, arg_string=""):
        if not self.directory_stack:
            self.emit("The directory stack is empty.")
            return True
        rows = [(index, path) for index, path in enumerate(reversed(self.directory_stack), start=1)]
        self.print_table(rows, headers=("Depth", "Directory"))
        return True

    # ------------------------------------------------------------------
    # Commands: control flow
    # ------------------------------------------------------------------

    def find_keyword(self, text, keyword):
        """Index of a bare, unquoted keyword, or -1."""
        upper = text.upper()
        length = len(keyword)
        quote = None
        index = 0
        while index < len(text):
            char = text[index]
            if quote:
                if char == quote:
                    quote = None
                index += 1
                continue
            if char in ("'", '"'):
                quote = char
                index += 1
                continue
            if upper.startswith(keyword, index):
                before = text[index - 1] if index else " "
                after = text[index + length] if index + length < len(text) else " "
                if before.isspace() and after.isspace():
                    return index
            index += 1
        return -1

    def evaluate_condition(self, condition):
        """Return True/False, or None when the condition itself is malformed."""
        tokens = self.tokenise_args(condition)
        if not tokens:
            self.emit_error("IF needs a condition.")
            return None

        negate = False
        while tokens and tokens[0].upper() == "NOT":
            negate = not negate
            tokens = tokens[1:]
        if not tokens:
            self.emit_error("IF needs a condition after NOT.")
            return None

        verb = tokens[0].upper()
        rest = tokens[1:]
        result = None

        if verb in ("EXISTS", "ISFILE", "ISDIR") and len(rest) == 1:
            path = os.path.expanduser(rest[0])
            if verb == "EXISTS":
                result = os.path.exists(path)
            elif verb == "ISFILE":
                result = os.path.isfile(path)
            else:
                result = os.path.isdir(path)
        elif verb == "EMPTY":
            result = not " ".join(rest).strip()
        elif len(tokens) == 3 and tokens[1] in ("==", "!=", "<", ">"):
            left, operator, right = tokens
            if operator in ("<", ">"):
                try:
                    left_value, right_value = float(left), float(right)
                except ValueError:
                    self.emit_error("%s and %s are not both numbers." % (left, right))
                    return None
                result = left_value < right_value if operator == "<" else left_value > right_value
            else:
                result = (left == right) if operator == "==" else (left != right)
        else:
            self.emit_error("Unrecognised condition: %s" % condition.strip())
            self.emit_error("Try: EXISTS <path>, ISFILE, ISDIR, EMPTY <text>, or <a> == <b>.")
            return None

        return (not result) if negate else result

    def cmd_if(self, args, arg_string=""):
        then_at = self.find_keyword(arg_string, "THEN")
        if then_at < 0:
            self.emit_error("Usage: %s" % self.COMMAND_INFO["IF"][1])
            return False

        condition = arg_string[:then_at]
        remainder = arg_string[then_at + 4:]
        else_at = self.find_keyword(remainder, "ELSE")
        if else_at < 0:
            consequent, alternative = remainder.strip(), ""
        else:
            consequent = remainder[:else_at].strip()
            alternative = remainder[else_at + 4:].strip()

        if not consequent:
            self.emit_error("IF needs a command after THEN.")
            return False

        outcome = self.evaluate_condition(condition)
        if outcome is None:
            return False

        branch = consequent if outcome else alternative
        if not branch:
            # The condition was false and there is no ELSE: nothing to do, and
            # doing nothing successfully is the point of an IF without an ELSE.
            return True
        return self.execute_line(branch, record_history=False)

    def cmd_for(self, args, arg_string=""):
        in_at = self.find_keyword(arg_string, "IN")
        do_at = self.find_keyword(arg_string, "DO")
        if in_at < 0 or do_at < 0 or do_at < in_at:
            self.emit_error("Usage: %s" % self.COMMAND_INFO["FOR"][1])
            return False

        name = arg_string[:in_at].strip()
        items_text = arg_string[in_at + 2:do_at]
        body = arg_string[do_at + 2:].strip()

        if not re.fullmatch(r"\w+", name or ""):
            self.emit_error("FOR needs a variable name made of letters, digits or underscores.")
            return False
        if not body:
            self.emit_error("FOR needs a command after DO.")
            return False
        if self._loop_depth >= self.MAX_EXPANSION_DEPTH:
            self.emit_error("FOR stopped: loops nested too deeply.")
            return False

        items = self.expand_globs(self.tokenise_args(items_text), keep_unmatched=False)
        if not items:
            self.emit_error("FOR: nothing to iterate over.")
            return True

        had_value = name in self.variables
        previous = self.variables.get(name)
        stop_on_error = bool(self.policy.get("stop_on_error", False))
        success = True

        self._loop_depth += 1
        try:
            for item in items:
                self.variables[name] = item
                os.environ[name] = item
                step_ok = self.execute_line(body, record_history=False)
                success = step_ok and success
                if not self.running:
                    break
                if stop_on_error and not step_ok:
                    self.emit_error("FOR stopped after a failing command.")
                    break
        finally:
            self._loop_depth -= 1
            if had_value:
                self.variables[name] = previous
                os.environ[name] = previous
            else:
                self.variables.pop(name, None)
                os.environ.pop(name, None)
        return success

    # ------------------------------------------------------------------
    # Commands: text (these read piped input as well as files)
    # ------------------------------------------------------------------

    def gather_input(self, operands, usage):
        """Text from the pipe or from named files. None means 'already reported'."""
        if self._pipe_input is not None:
            return self._pipe_input
        if not operands:
            self.emit_error("Usage: %s" % usage)
            self.emit_error("Give a filename, or pipe input in with |.")
            return None
        chunks = []
        for operand in self.expand_globs(operands):
            try:
                with open(os.path.expanduser(operand), "r", encoding="utf-8", errors="replace") as stream:
                    chunks.append(stream.read())
            except OSError as err:
                self.emit_error("Error reading file:", err)
                return None
        return "".join(chunks)

    def cmd_type(self, args, arg_string=""):
        text = self.gather_input(args, self.COMMAND_INFO["TYPE"][1])
        if text is None:
            return False
        self.emit(text, end="" if text.endswith("\n") or not text else "\n")
        return True

    def cmd_grep(self, args, arg_string=""):
        use_regex = False
        case_sensitive = False
        invert = False
        only_count = False
        numbered = False
        operands = []
        for arg in args:
            lowered = arg.lower()
            if lowered in ("--regex", "-e"):
                use_regex = True
            elif lowered in ("--case", "-s"):
                case_sensitive = True
            elif lowered in ("--invert", "-v"):
                invert = True
            elif lowered in ("--count", "-c"):
                only_count = True
            elif lowered in ("--line-numbers", "-n"):
                numbered = True
            else:
                operands.append(arg)

        if not operands:
            self.emit_error("Usage: %s" % self.COMMAND_INFO["GREP"][1])
            return False

        pattern = operands[0]
        text = self.gather_input(operands[1:], self.COMMAND_INFO["GREP"][1])
        if text is None:
            return False

        if use_regex:
            try:
                matcher = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
            except re.error as err:
                self.emit_error("Invalid pattern:", err)
                return False
            hit = lambda line: bool(matcher.search(line))
        elif case_sensitive:
            hit = lambda line: pattern in line
        else:
            needle = pattern.lower()
            hit = lambda line: needle in line.lower()

        matches = [
            (number, line)
            for number, line in enumerate(text.splitlines(), start=1)
            if hit(line) != invert
        ]
        if only_count:
            self.emit(len(matches))
            return bool(matches)
        for number, line in matches:
            self.emit(("%d: %s" % (number, line)) if numbered else line)
        # Like grep, "no matches" is a non-zero status so && and || work.
        return bool(matches)

    def cmd_sort(self, args, arg_string=""):
        reverse = False
        unique = False
        numeric = False
        operands = []
        for arg in args:
            lowered = arg.lower()
            if lowered in ("--reverse", "-r"):
                reverse = True
            elif lowered in ("--unique", "-u"):
                unique = True
            elif lowered in ("--numeric", "-n"):
                numeric = True
            else:
                operands.append(arg)

        text = self.gather_input(operands, self.COMMAND_INFO["SORT"][1])
        if text is None:
            return False

        lines = text.splitlines()
        if unique:
            seen = set()
            lines = [line for line in lines if not (line in seen or seen.add(line))]

        def numeric_key(line):
            match = re.search(r"-?\d+(?:\.\d+)?", line)
            return (0, float(match.group())) if match else (1, 0.0)

        lines.sort(key=numeric_key if numeric else str.lower, reverse=reverse)
        for line in lines:
            self.emit(line)
        return True

    def head_or_tail(self, args, name, take_last):
        count = 10
        operands = []
        index = 0
        while index < len(args):
            arg = args[index]
            if arg.lower() in ("-n", "--lines"):
                index += 1
                if index >= len(args):
                    self.emit_error("Usage: %s" % self.COMMAND_INFO[name][1])
                    return False
                try:
                    count = int(args[index])
                except ValueError:
                    self.emit_error("%s needs a whole number of lines." % name)
                    return False
            else:
                operands.append(arg)
            index += 1

        if count < 1:
            self.emit_error("%s needs a count of 1 or more." % name)
            return False

        text = self.gather_input(operands, self.COMMAND_INFO[name][1])
        if text is None:
            return False
        lines = text.splitlines()
        for line in (lines[-count:] if take_last else lines[:count]):
            self.emit(line)
        return True

    def cmd_head(self, args, arg_string=""):
        return self.head_or_tail(args, "HEAD", take_last=False)

    def cmd_tail(self, args, arg_string=""):
        return self.head_or_tail(args, "TAIL", take_last=True)

    def cmd_count(self, args, arg_string=""):
        wanted = None
        operands = []
        for arg in args:
            lowered = arg.lower()
            if lowered in ("--lines", "-l"):
                wanted = "lines"
            elif lowered in ("--words", "-w"):
                wanted = "words"
            elif lowered in ("--chars", "--characters", "-c"):
                wanted = "chars"
            else:
                operands.append(arg)

        text = self.gather_input(operands, self.COMMAND_INFO["COUNT"][1])
        if text is None:
            return False

        totals = {"lines": len(text.splitlines()), "words": len(text.split()), "chars": len(text)}
        if wanted:
            # A bare number so COUNT composes: SET N=$(... | COUNT --lines)
            self.emit(totals[wanted])
        else:
            self.print_table(
                [(totals["lines"], totals["words"], totals["chars"])],
                headers=("Lines", "Words", "Characters"),
            )
        return True

    def cmd_search(self, args, arg_string=""):
        root = os.getcwd()
        containing = None
        limit = 200
        patterns = []

        index = 0
        while index < len(args):
            token = args[index].lower()
            if token in ("--in", "--root"):
                index += 1
                if index >= len(args):
                    self.emit_error("Usage: %s" % self.COMMAND_INFO["SEARCH"][1])
                    return False
                root = os.path.expanduser(args[index])
            elif token in ("--containing", "-c"):
                index += 1
                if index >= len(args):
                    self.emit_error("Usage: %s" % self.COMMAND_INFO["SEARCH"][1])
                    return False
                containing = args[index].lower()
            elif token == "--limit":
                index += 1
                try:
                    limit = int(args[index])
                except (IndexError, ValueError):
                    self.emit_error("SEARCH --limit needs a whole number.")
                    return False
            else:
                patterns.append(args[index])
            index += 1

        if not os.path.isdir(root):
            self.emit_error("SEARCH root is not a directory: %s" % root)
            return False
        pattern = patterns[0] if patterns else "*"

        found = 0
        truncated = False
        for directory, subdirectories, names in os.walk(root):
            subdirectories[:] = [name for name in subdirectories if name not in (".git", "__pycache__")]
            for name in sorted(names, key=str.lower):
                if not fnmatch.fnmatch(name, pattern):
                    continue
                path = os.path.join(directory, name)
                if containing is not None:
                    try:
                        with open(path, "r", encoding="utf-8", errors="replace") as stream:
                            if containing not in stream.read().lower():
                                continue
                    except OSError:
                        continue
                self.emit(path)
                found += 1
                if found >= limit:
                    truncated = True
                    break
            if truncated:
                break

        if truncated:
            self.emit_error("Stopped at %d results; raise it with --limit." % limit)
        elif not found:
            # A diagnostic, not data: on stdout it would be counted as a result
            # by anything downstream in a pipe or a $(...) substitution.
            self.emit_error("No files match: %s" % pattern)
        # No matches is a non-zero status, so SEARCH composes with || .
        return bool(found)

    def cmd_diff(self, args, arg_string=""):
        if len(args) != 2:
            self.emit_error("Usage: DIFF <left> <right>")
            return False
        sides = []
        for operand in args:
            path = os.path.expanduser(operand)
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as stream:
                    sides.append(stream.read().splitlines(keepends=True))
            except OSError as err:
                self.emit_error("Error reading file:", err)
                return False

        lines = list(
            difflib.unified_diff(sides[0], sides[1], fromfile=args[0], tofile=args[1], lineterm="")
        )
        if not lines:
            self.emit("Files are identical.")
            return True
        for line in lines:
            self.emit(line.rstrip("\n"))
        # Differences found is a non-zero status, matching diff(1).
        return False

    def cmd_replace(self, args, arg_string=""):
        use_regex = False
        case_sensitive = False
        in_place = False
        operands = []
        for arg in args:
            lowered = arg.lower()
            if lowered in ("--regex", "-e"):
                use_regex = True
            elif lowered in ("--case", "-s"):
                case_sensitive = True
            elif lowered in ("--in-place", "-i"):
                in_place = True
            else:
                operands.append(arg)

        if len(operands) < 2:
            self.emit_error("Usage: %s" % self.COMMAND_INFO["REPLACE"][1])
            return False

        search, replacement = operands[0], operands[1]
        files = operands[2:]
        if in_place and not files:
            self.emit_error("REPLACE --in-place needs at least one file.")
            return False

        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = search if use_regex else re.escape(search)
        try:
            matcher = re.compile(pattern, flags)
        except re.error as err:
            self.emit_error("Invalid pattern:", err)
            return False

        if not in_place:
            text = self.gather_input(files, self.COMMAND_INFO["REPLACE"][1])
            if text is None:
                return False
            self.emit(matcher.sub(replacement, text), end="")
            return True

        succeeded = True
        for operand in self.expand_globs(files):
            path = os.path.expanduser(operand)
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as stream:
                    original = stream.read()
                updated, count = matcher.subn(replacement, original)
                if count:
                    with open(path, "w", encoding="utf-8") as stream:
                        stream.write(updated)
                self.emit("%s: %d replacement(s)" % (path, count))
            except OSError as err:
                self.emit_error("Error rewriting file:", err)
                succeeded = False
        return succeeded

    # ------------------------------------------------------------------
    # Commands: environment
    # ------------------------------------------------------------------

    def cmd_set(self, args, arg_string=""):
        if not args:
            if not self.variables:
                self.emit("No session variables set. Use SET name=value.")
                return True
            self.print_table(sorted(self.variables.items()), headers=("Name", "Value"))
            return True

        assignment = arg_string.strip()
        if "=" in assignment:
            name, value = assignment.split("=", 1)
        elif len(args) >= 2:
            name, value = args[0], arg_string.split(None, 1)[1]
        else:
            self.emit_error("Usage: SET name=value")
            return False

        name = name.strip()
        value = self.strip_wrapping_quotes(value.strip())
        if not name or not re.fullmatch(r"\w+", name):
            self.emit_error("Variable names may contain only letters, digits and underscores.")
            return False

        self.variables[name] = value
        # Write through to the real environment so every child process — argv
        # programs, RUN, LEGACY — inherits it without any special plumbing.
        os.environ[name] = value
        self.emit("%s=%s" % (name, value))
        return True

    def cmd_unset(self, args, arg_string=""):
        if len(args) != 1:
            self.emit_error("Usage: UNSET <name>")
            return False
        name = args[0]
        if name not in self.variables:
            self.emit_error("No such session variable: %s" % name)
            return False
        del self.variables[name]
        os.environ.pop(name, None)
        self.emit("Variable '%s' removed." % name)
        return True

    def cmd_env(self, args, arg_string=""):
        needle = args[0].lower() if args else ""
        rows = []
        for name, value in sorted(os.environ.items()):
            if needle and needle not in name.lower():
                continue
            rows.append((name, value, "session" if name in self.variables else ""))
        if not rows:
            self.emit("No environment variables match: %s" % (args[0] if args else ""))
            return True
        self.print_table(rows, headers=("Name", "Value", "Source"))
        return True

    # ------------------------------------------------------------------
    # Commands: basics
    # ------------------------------------------------------------------

    def console_only(self, name):
        """Refuse a console-side-effect command when output is diverted.

        CLS and COLOR act on the real console handle, which no amount of stream
        swapping touches. Running `CLS > log.txt` would wipe the user's screen
        and leave an empty file, so decline instead.
        """
        if self.redirected or self._capture_depth:
            self.emit_error("%s affects the console only; it does nothing when output is redirected." % name)
            return True
        return False

    def cmd_cls(self, args, arg_string=""):
        if self.console_only("CLS"):
            return False
        command = "cls" if platform.system() == "Windows" else "clear"
        return subprocess.call(command, shell=True) == 0

    def cmd_color(self, args, arg_string=""):
        if not args:
            self.emit_error("Usage: COLOR <code>")
            return False
        if self.console_only("COLOR"):
            return False
        if platform.system() != "Windows":
            self.emit_error("COLOR is only supported by Windows console hosts.")
            return False
        code = args[0]
        if not re.fullmatch(r"[0-9A-Fa-f]{1,2}", code):
            self.emit_error("COLOR expects one or two hexadecimal digits, for example 0A.")
            return False
        try:
            if subprocess.call("color " + code, shell=True) != 0:
                self.emit_error("The console rejected color code:", code)
                return False
            self.emit("Color changed to:", code)
            return True
        except OSError as err:
            self.emit_error("Error changing color:", err)
            return False

    def cmd_echo(self, args, arg_string=""):
        # Quoting is the escape hatch for operator characters, so a wholly
        # quoted argument must print without its quotes: ECHO "a|b" -> a|b.
        text = arg_string.strip()
        if len(args) == 1 and len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
            self.emit(text[1:-1])
        else:
            self.emit(arg_string)
        return True

    def cmd_time(self, args, arg_string=""):
        self.emit("Current Time:", time.strftime("%H:%M:%S"))
        return True

    def cmd_date(self, args, arg_string=""):
        self.emit("Current Date:", time.strftime("%Y-%m-%d"))
        return True

    # ------------------------------------------------------------------
    # Commands: execution
    # ------------------------------------------------------------------

    def cmd_run(self, args, arg_string=""):
        if not arg_string.strip():
            self.emit_error("Usage: RUN [--safe] <command>")
            return False

        if args and args[0].lower() in ("--safe", "/safe"):
            safe_args = args[1:]
            if not safe_args:
                self.emit_error("Usage: RUN --safe <command>")
                return False
            try:
                status = self.run_external(" ".join(safe_args), argv=safe_args)
            except OSError as err:
                self.emit_error("Error running safe command:", err)
                return False
            self.last_status = status
            return status == 0

        if not self.authorise_shell(arg_string, "run"):
            self.emit_error("RUN's shell mode is disabled by policy; use RUN --safe <program> [args].")
            return False
        try:
            status = self.run_external(arg_string)
        except OSError as err:
            self.emit_error("Error running command:", err)
            return False
        self.last_status = status
        return status == 0

    def cmd_legacy(self, args, arg_string=""):
        legacy_cmd = arg_string.strip()
        if not legacy_cmd:
            self.emit_error("Usage: LEGACY <command>")
            return False
        if not self.authorise_shell(legacy_cmd, "legacy"):
            self.emit_error("LEGACY is disabled by policy.")
            return False
        try:
            status = self.run_external(legacy_cmd)
        except OSError as err:
            self.emit_error("Error executing legacy command:", err)
            return False
        self.last_status = status
        return status == 0

    def cmd_shell(self, args, arg_string=""):
        if not self.authorise_shell("SHELL", "legacy"):
            self.emit_error("SHELL is disabled by policy.")
            return False
        self.emit("Launching external shell...")
        try:
            if platform.system() == "Windows":
                subprocess.Popen("start cmd", shell=True)
            else:
                shell = shutil.which("x-terminal-emulator") or shutil.which("xterm")
                if not shell:
                    self.emit_error("No terminal emulator found.")
                    return False
                subprocess.Popen(shell, shell=True)
            return True
        except OSError as err:
            self.emit_error("Error launching shell:", err)
            return False

    def cmd_which(self, args, arg_string=""):
        if len(args) != 1:
            self.emit_error("Usage: WHICH <program>")
            return False
        found = shutil.which(args[0])
        if found:
            self.emit(found)
            return True
        self.emit_error("Program not found on PATH: %s" % args[0])
        return False

    # ------------------------------------------------------------------
    # Commands: help and discovery
    # ------------------------------------------------------------------

    def cmd_help(self, args, arg_string=""):
        if args:
            command = args[0].upper()
            info = self.COMMAND_INFO.get(command)
            if not info:
                self.emit_error("No help topic for: %s" % args[0])
                self.print_suggestions(args[0], to_error=True)
                return False
            category, usage, description = info
            self.emit("%s (%s)" % (command, category))
            self.emit("Usage:", usage)
            self.emit(description)
            return True

        self.emit("")
        self.emit("Advanced CMD Emulator Help:")
        self.emit("")
        self.emit("Type COMMANDS to list available commands.")
        self.emit("Type HELP <command> for command-specific help.")
        self.emit("Type SUGGEST <text> to discover similar commands and aliases.")
        self.emit("Type EXPLAIN <line> to see exactly how PyCMD will interpret it.")
        self.emit("")
        self.emit("Common commands:")
        rows = []
        for key in self.FEATURED:
            info = self.COMMAND_INFO.get(key)
            if info:
                rows.append((info[1], info[2]))
        # Never truncate help: losing part of a usage string is worse than wrapping.
        self.print_table(rows, truncate=False)
        self.emit("")
        self.emit("Notes:")
        for note in (
            "Commands are case-insensitive, and so are alias, macro and bookmark names.",
            "Chain commands with && (on success), || (on failure) and ; (always).",
            "Redirect builtin output with >, >> and 2>, and read a file with <.",
            "Pipe builtins into programs: DIR --details | findstr .py",
            "A single & is literal, so filenames such as A&B.txt keep working.",
            "A word found on PATH runs directly, with no shell in between.",
            "A word that is neither a builtin nor on PATH is a typo, and is refused.",
            "Macros can use {1}, {2}, and {*} placeholders for RUNMACRO arguments.",
        ):
            self.emit(" -", note)
        self.emit("")
        return True

    def cmd_commands(self, args, arg_string=""):
        grouped = {}
        for command, (category, usage, description) in self.COMMAND_INFO.items():
            grouped.setdefault(category, []).append((command, usage, description))

        wanted = args[0].lower() if args else None
        if wanted:
            matches = [category for category in grouped if category.lower() == wanted]
            if not matches:
                self.emit_error("No such category: %s" % args[0])
                self.emit_error("Categories:", ", ".join(sorted(grouped)))
                return False
            categories = matches
        else:
            categories = sorted(grouped)

        for category in categories:
            self.emit("")
            self.emit("%s:" % category)
            rows = sorted(grouped[category], key=lambda item: item[0])
            self.print_table(rows, headers=("Command", "Usage", "Description"), truncate=False)
        return True

    def cmd_config(self, args, arg_string=""):
        self.emit("PyCMD configuration:")
        self.emit("  Version:", __version__)
        self.emit("  User:", getpass.getuser())
        self.emit("  Python:", sys.version.split()[0])
        self.emit("  Platform:", platform.platform())
        self.emit("  Interactive:", "yes" if self.interactive else "no")
        self.emit("  Config file:", self.config_file or "disabled")
        self.emit("  Config loaded:", "yes" if self.config_loaded else "no (using defaults)")
        self.emit("  History file:", self.history_file or "disabled")
        self.emit("  History records:", self.record_file or "disabled")
        if self.record_file:
            self.emit("  Record size:", "%.1f KiB" % (self.record_file_size() / 1024.0))
        self.emit("  Readline:", self.readline_backend or "unavailable")
        self.emit("  Aliases/macros/bookmarks: %d/%d/%d" % (len(self.aliases), len(self.macros), len(self.bookmarks)))
        self.emit("  Last status:", self.last_status)
        return True

    def cmd_suggest(self, args, arg_string=""):
        text = arg_string or (args[0] if args else "")
        if not text:
            self.emit_error("Usage: SUGGEST <text>")
            return False
        self.print_suggestions(text)
        return True

    def print_suggestions(self, text, to_error=False):
        write = self.emit_error if to_error else self.emit
        suggestions = self.get_suggestions(text)
        if suggestions:
            write("Did you mean: " + ", ".join(suggestions))
        else:
            write("No close PyCMD command or alias found.")

    def cmd_explain(self, args, arg_string=""):
        if not arg_string.strip():
            self.emit_error("Usage: EXPLAIN <command line>")
            return False

        line = arg_string.strip()
        rows = []
        reaches_shell = False

        if self.policy.get("operators", True) and not self.is_raw_tail(line):
            try:
                segments = self.split_operators(line)
            except ValueError as err:
                self.emit_error("Input parse error:", err)
                return False
        else:
            segments = [(None, line)]

        for operator, text in segments:
            stage = text.strip()
            if not stage:
                rows.append((operator or "run", "syntax error", "empty command segment"))
                continue
            label = {None: "run", "&&": "on success", "||": "on failure", ";": "then", "|": "pipe into"}.get(
                operator, operator or "run"
            )
            redirections = []
            if not self.is_raw_tail(stage):
                try:
                    stage, redirections = self.parse_redirections(stage)
                except ValueError as err:
                    rows.append((label, "syntax error", str(err)))
                    continue
            for descriptor, mode, target in redirections:
                verb = {"r": "reads from", "w": "writes to", "a": "appends to"}[mode]
                stream = {0: "stdin", 1: "stdout", 2: "stderr"}.get(descriptor, "fd%d" % descriptor)
                rows.append((label, "%s %s" % (stream, verb), target))
            shell_step = self.explain_chain(stage, rows, label)
            reaches_shell = reaches_shell or shell_step

        self.print_table(rows, headers=("When", "Resolves as", "Detail"))
        if reaches_shell:
            mode = self.policy.get("shell_fallback", "confirm")
            self.emit("")
            self.emit_error(
                "Warning: this line contains a command PyCMD does not know."
                " With shell_fallback=%s it would %s."
                % (mode, {"off": "be refused", "confirm": "ask first", "always": "run in the OS shell"}[mode])
            )
        return True

    def explain_chain(self, stage, rows, label, depth=0):
        command, arg_string = self.split_input(stage)
        kind, name, payload = self.classify_command(command)
        indent = "  " * depth

        if kind == "alias":
            rows.append((label if not depth else "", indent + "alias " + name, payload))
            if depth >= self.MAX_EXPANSION_DEPTH:
                rows.append(("", indent + "  stopped", "possible alias loop"))
                return False
            expanded = payload + (" " + arg_string if arg_string else "")
            return self.explain_chain(expanded, rows, label, depth + 1)

        if kind == "macro":
            rows.append((label if not depth else "", indent + "macro " + name, payload))
            if depth >= self.MAX_EXPANSION_DEPTH:
                rows.append(("", indent + "  stopped", "possible macro loop"))
                return False
            reaches_shell = False
            for step in self.split_macro_commands(payload):
                reaches_shell = self.explain_chain(step, rows, "", depth + 1) or reaches_shell
            return reaches_shell

        if kind == "builtin":
            category, usage, _ = self.COMMAND_INFO.get(name, ("", name, ""))
            rows.append((label if not depth else "", indent + "builtin " + name, usage))
            return False

        program = self.resolve_program(command)
        if program:
            rows.append((label if not depth else "", indent + "program " + command, program))
            return False

        rows.append((label if not depth else "", indent + "UNKNOWN " + command, "not a builtin and not on PATH"))
        return True

    def cmd_policy(self, args, arg_string=""):
        if not args:
            rows = [(key, str(self.policy.get(key, default))) for key, default in sorted(DEFAULT_POLICY.items())]
            self.print_table(rows, headers=("Setting", "Value"))
            self.emit("")
            self.emit("shell_fallback: off | confirm | always — what happens to an unknown command.")
            self.emit("Change with: POLICY <setting> <value>")
            return True

        if len(args) != 2:
            self.emit_error("Usage: POLICY [key value]")
            return False

        key, value = args[0].lower(), args[1]
        if key not in DEFAULT_POLICY:
            self.emit_error("No such policy setting: %s" % args[0])
            self.emit_error("Known settings:", ", ".join(sorted(DEFAULT_POLICY)))
            return False

        default = DEFAULT_POLICY[key]
        if isinstance(default, bool):
            lowered = value.strip().lower()
            if lowered not in TRUE_WORDS + FALSE_WORDS:
                self.emit_error("Expected on/off for %s." % key)
                return False
            self.policy[key] = lowered in TRUE_WORDS
        else:
            choices = POLICY_CHOICES.get(key, ())
            if value.strip().lower() not in choices:
                self.emit_error("Expected one of %s for %s." % (", ".join(choices), key))
                return False
            self.policy[key] = value.strip().lower()

        # An explicit POLICY command is a deliberate choice, so it is stored.
        self.stored_policy[key] = self.policy[key]
        return self.persist(
            "Policy updated: %s -> %s" % (key, self.policy[key]),
            "(not persisted)",
        )

    def cmd_record(self, args, arg_string=""):
        if not args:
            state = "on" if self.policy.get("record", True) else "off"
            self.emit("Command recording:", state)
            self.emit("  File:", self.record_file or "disabled")
            self.emit("  Size: %.1f KiB" % (self.record_file_size() / 1024.0))
            self.emit("  Note: every command line you type is stored here.")
            return True

        value = args[0].strip().lower()
        if value not in TRUE_WORDS + FALSE_WORDS:
            self.emit_error("Usage: RECORD [on|off]")
            return False
        self.policy["record"] = value in TRUE_WORDS
        self.stored_policy["record"] = self.policy["record"]
        return self.persist(
            "Command recording %s." % ("enabled" if self.policy["record"] else "disabled"),
            "(not persisted)",
        )

    # ------------------------------------------------------------------
    # Commands: history and stats
    # ------------------------------------------------------------------

    def cmd_history(self, args, arg_string=""):
        if args and args[0].lower() in ("--clear", "/clear"):
            self.history.clear()
            if self.record_file and os.path.exists(self.record_file):
                self.emit(
                    "Session history cleared (on-disk records kept at %s; use HISTORY --purge to delete them)."
                    % self.record_file
                )
            else:
                self.emit("Session history cleared.")
            return True

        if args and args[0].lower() in ("--purge", "/purge"):
            return self.purge_history_records()

        if args and args[0].lower() in ("search", "find"):
            query = " ".join(args[1:]).strip()
            if not query:
                self.emit_error("Usage: HISTORY search <text>")
                return False
            return self.search_history(query)

        if args and args[0].lower() == "last":
            limit = 10
            if len(args) > 1:
                try:
                    limit = int(args[1])
                except ValueError:
                    self.emit_error("Usage: HISTORY last [limit]")
                    return False
            if limit < 1:
                self.emit_error("HISTORY last needs a limit of 1 or more.")
                return False
            return self.print_history_entries(self.history[-limit:], len(self.history) - min(limit, len(self.history)) + 1)

        limit = None
        if args:
            try:
                limit = int(args[0])
            except ValueError:
                self.emit_error("Usage: HISTORY [limit|last n|search text|--clear|--purge]")
                return False
            if limit < 1:
                self.emit_error("HISTORY needs a limit of 1 or more.")
                return False

        entries = self.history if limit is None else self.history[-limit:]
        return self.print_history_entries(entries, len(self.history) - len(entries) + 1)

    def print_history_entries(self, entries, start=1):
        if entries:
            self.emit("Command History:")
            for index, command in enumerate(entries, start=start):
                self.emit("%d: %s" % (index, command))
        else:
            self.emit("No commands in history.")
        return True

    def search_history(self, query):
        query_lower = query.lower()
        session = self.history
        if session and self._executing_line and session[-1] == self._executing_line:
            session = session[:-1]

        session_matches = [
            {"source": "session", "time": "", "cwd": "", "command": command}
            for command in session
            if query_lower in command.lower()
        ]
        record_matches = [
            dict(record, source="record")
            for record in self.iter_history_records()
            if query_lower in str(record.get("command", "")).lower()
        ]
        matches = session_matches[-10:] + record_matches[-10:]
        if not matches:
            self.emit("No history matches for: %s" % query)
            return True

        rows = [
            (
                match.get("source", ""),
                match.get("time", ""),
                match.get("cwd", ""),
                match.get("command", ""),
            )
            for match in matches
        ]
        self.print_table(rows, headers=("Source", "Time", "Cwd", "Command"))
        return True

    def purge_history_records(self):
        # The rotated generation holds just as many command lines as the live
        # file, so "records deleted" has to mean both or it is a false promise.
        targets = [path for path in self.record_files() if os.path.exists(path)]
        if not targets:
            self.emit("No on-disk history records to purge.")
            return True

        total = sum(os.path.getsize(path) for path in targets)
        for path in targets:
            self.emit("Records file: %s (%.1f KiB)" % (path, os.path.getsize(path) / 1024.0))
        if not self.confirm("Delete %d file(s), %.1f KiB of command records? [y/N] " % (len(targets), total / 1024.0)):
            self.emit_error("Cancelled; records kept.")
            return False

        succeeded = True
        for path in targets:
            try:
                os.remove(path)
            except OSError as err:
                self.emit_error("Could not delete records:", err)
                succeeded = False
        if succeeded:
            self.emit("On-disk command records deleted.")
        return succeeded

    def record_files(self):
        if not self.record_file:
            return []
        return [self.record_file, self.record_file + ".1"]

    def cmd_stats(self, args, arg_string=""):
        if not self.command_stats:
            self.emit("No commands have been executed yet.")
            return True

        stats = list(self.command_stats)
        total = len(stats)
        failures = sum(1 for item in stats if not item["success"])
        average = sum(item["duration"] for item in stats) / total
        self.emit("Session stats:")
        self.emit("  Commands:", total)
        self.emit("  Failures:", failures)
        self.emit("  Average duration:", "%.3fs" % average)

        slowest = sorted(stats, key=lambda item: item["duration"], reverse=True)[:5]
        self.emit("")
        self.emit("Slowest commands:")
        rows = [
            (
                item["time"],
                "%.3fs" % item["duration"],
                "ok" if item["success"] else "failed",
                item["command"],
            )
            for item in slowest
        ]
        self.print_table(rows, headers=("Time", "Duration", "Result", "Command"))
        return True

    # ------------------------------------------------------------------
    # Commands: aliases, macros, bookmarks
    # ------------------------------------------------------------------

    def cmd_alias(self, args, arg_string=""):
        name, command = self.split_first_token(arg_string)
        if not name or not command:
            self.emit_error("Usage: ALIAS <name> <command>")
            return False
        ok, reason = self.validate_name(name, "alias")
        if not ok:
            self.emit_error("Cannot create alias '%s': %s" % (name, reason))
            return False
        self.aliases[name] = command
        self.rebuild_indexes()
        return self.persist("Alias created: %s -> %s" % (name, command), "(not persisted)")

    def cmd_unalias(self, args, arg_string=""):
        if len(args) != 1:
            self.emit_error("Usage: UNALIAS <name>")
            return False
        key = self.normalise_command(args[0])
        name = self.alias_index.get(key)
        if name is None:
            self.emit_error("No such alias: %s" % args[0])
            return False
        del self.aliases[name]
        self.rebuild_indexes()
        return self.persist("Alias '%s' removed." % name, "(not persisted)")

    def cmd_listaliases(self, args, arg_string=""):
        if self.aliases:
            rows = sorted((name, command) for name, command in self.aliases.items())
            self.print_table(rows, headers=("Alias", "Command"))
        else:
            self.emit("No aliases defined.")
        return True

    def cmd_macro(self, args, arg_string=""):
        name, macro_text = self.split_first_token(arg_string)
        if not name or not macro_text:
            self.emit_error("Usage: MACRO <name> <command>; <command>")
            return False
        ok, reason = self.validate_name(name, "macro")
        if not ok:
            self.emit_error("Cannot create macro '%s': %s" % (name, reason))
            return False
        commands = self.split_macro_commands(macro_text)
        if not commands:
            self.emit_error("Usage: MACRO <name> <command>; <command>")
            return False
        self.macros[name] = macro_text
        self.rebuild_indexes()
        return self.persist("Macro saved: %s (%d command(s))" % (name, len(commands)), "(not persisted)")

    def cmd_runmacro(self, args, arg_string=""):
        dry_run = False
        stop_on_error = None
        remainder = arg_string
        while True:
            token, rest = self.split_first_token(remainder)
            lowered = token.lower()
            if lowered in ("--dry-run", "/dry-run", "-n"):
                dry_run = True
                remainder = rest
                continue
            if lowered in ("--stop", "/stop"):
                stop_on_error = True
                remainder = rest
                continue
            break

        name, extra_string = self.split_first_token(remainder)
        if not name:
            self.emit_error("Usage: RUNMACRO [--dry-run] [--stop] <name> [args]")
            return False
        extra_args = self.tokenise_args(extra_string)
        return self.run_macro(name, extra_args, extra_string, dry_run=dry_run, stop_on_error=stop_on_error)

    def cmd_unmacro(self, args, arg_string=""):
        if len(args) != 1:
            self.emit_error("Usage: UNMACRO <name>")
            return False
        key = self.normalise_command(args[0])
        name = self.macro_index.get(key)
        if name is None:
            self.emit_error("No such macro: %s" % args[0])
            return False
        del self.macros[name]
        self.rebuild_indexes()
        return self.persist("Macro '%s' removed." % name, "(not persisted)")

    def cmd_listmacros(self, args, arg_string=""):
        if self.macros:
            rows = sorted((name, command) for name, command in self.macros.items())
            self.print_table(rows, headers=("Macro", "Commands"))
        else:
            self.emit("No macros defined.")
        return True

    @staticmethod
    def protect_substitution(value):
        """Stop a macro argument being re-read as shell syntax.

        The expansion is fed back through the parser, so an argument such as
        '; DEL important.txt' would otherwise become a second command that the
        macro's author never wrote. Values that contain no operator characters
        are passed through untouched, so ordinary arguments look unchanged.
        """
        if not value or not any(char in value for char in ";|&<>"):
            return value
        return '"' + value.replace('"', "'") + '"'

    def expand_macro_command(self, command, args, arg_string):
        """Substitute {1}, {2} and {*} in a single pass, never rescanning."""

        def replace(match):
            token = match.group(1)
            if token == "*":
                return self.protect_substitution(arg_string)
            index = int(token)
            if 1 <= index <= len(args):
                return self.protect_substitution(args[index - 1])
            return match.group(0)

        return re.sub(r"\{(\*|\d+)\}", replace, command)

    def run_macro(self, name, args=None, arg_string="", macro_depth=0, alias_depth=0, dry_run=False, stop_on_error=None):
        args = args or []
        if max(macro_depth, self._macro_depth) >= self.MAX_EXPANSION_DEPTH:
            self.emit_error("Macro expansion stopped: possible macro loop.")
            return False

        key = self.normalise_command(name)
        resolved = self.macro_index.get(key)
        macro_text = self.macros.get(resolved) if resolved else None
        if not macro_text:
            self.emit_error("No such macro: %s" % name)
            self.print_suggestions(name, to_error=True)
            return False

        if stop_on_error is None:
            stop_on_error = bool(self.policy.get("stop_on_error", False))

        success = True
        self._macro_depth += 1
        try:
            for command in self.split_macro_commands(macro_text):
                expanded = self.expand_macro_command(command, args, arg_string)
                self.emit(">>", expanded)
                if dry_run:
                    continue
                step_ok = self.execute_line(
                    expanded,
                    record_history=False,
                    alias_depth=alias_depth,
                    macro_depth=self._macro_depth,
                )
                success = step_ok and success
                if not self.running:
                    break
                if stop_on_error and not step_ok:
                    self.emit_error("Macro stopped after a failing command.")
                    break
        finally:
            self._macro_depth -= 1
        return success

    def cmd_bookmark(self, args, arg_string=""):
        name, rest = self.split_first_token(arg_string)
        if not name:
            self.emit_error("Usage: BOOKMARK <name> [path]")
            return False
        ok, reason = self.validate_name(name, "bookmark")
        if not ok:
            self.emit_error("Cannot create bookmark '%s': %s" % (name, reason))
            return False
        path = os.path.expanduser(self.strip_wrapping_quotes(rest)) if rest else os.getcwd()
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            self.emit_error("Bookmark path is not a directory: %s" % path)
            return False
        self.bookmarks[name] = path
        self.rebuild_indexes()
        return self.persist("Bookmark saved: %s -> %s" % (name, path), "(not persisted)")

    def cmd_jump(self, args, arg_string=""):
        if len(args) != 1:
            self.emit_error("Usage: JUMP <name>")
            return False
        key = self.normalise_command(args[0])
        name = self.bookmark_index.get(key)
        path = self.bookmarks.get(name) if name else None
        if not path:
            self.emit_error("No such bookmark: %s" % args[0])
            self.print_suggestions(args[0], to_error=True)
            return False
        try:
            os.chdir(path)
            self.update_prompt()
            self.emit("Current Directory:", os.getcwd())
            return True
        except OSError as err:
            self.emit_error("Error changing directory:", err)
            return False

    def cmd_unbookmark(self, args, arg_string=""):
        if len(args) != 1:
            self.emit_error("Usage: UNBOOKMARK <name>")
            return False
        key = self.normalise_command(args[0])
        name = self.bookmark_index.get(key)
        if name is None:
            self.emit_error("No such bookmark: %s" % args[0])
            return False
        del self.bookmarks[name]
        self.rebuild_indexes()
        return self.persist("Bookmark '%s' removed." % name, "(not persisted)")

    def cmd_listbookmarks(self, args, arg_string=""):
        if self.bookmarks:
            rows = sorted((name, path) for name, path in self.bookmarks.items())
            self.print_table(rows, headers=("Bookmark", "Path"))
        else:
            self.emit("No bookmarks defined.")
        return True

    # ------------------------------------------------------------------
    # Commands: session
    # ------------------------------------------------------------------

    def cmd_restart(self, args, arg_string=""):
        self.emit("Restarting CMD Emulator...")
        try:
            self.out.flush()
        except (AttributeError, ValueError, OSError):
            pass
        self.save_readline_history()
        self.save_config()
        try:
            os.execl(sys.executable, sys.executable, SCRIPT_PATH, *LAUNCH_ARGV)
        except OSError as err:
            self.emit_error("Restart failed:", err)
            return False

    def cmd_exit(self, args, arg_string=""):
        self.emit("Exiting CMD Emulator.")
        self.running = False
        return True

    # ------------------------------------------------------------------
    # Session drivers
    # ------------------------------------------------------------------

    def run_script(self, path):
        try:
            with open(path, "r", encoding="utf-8-sig") as script:
                lines = script.readlines()
        except OSError as err:
            self.emit_error("Could not read script:", err)
            return 1

        status = 0
        for number, raw in enumerate(lines, start=1):
            line = raw.strip()
            first = line.split(None, 1)[0].upper() if line.split() else ""
            if not line or line.startswith("#") or first == "REM":
                continue
            if not self.execute_line(line, record_history=False):
                self.emit_error("Script %s failed at line %d: %s" % (path, number, line))
                if self.policy.get("stop_on_error", False):
                    return self.last_status or 1
            status = self.last_status
            if not self.running:
                break
        return status

    def run(self):
        if self.show_banner:
            self.emit("Welcome to the Advanced CMD Emulator")
            self.emit("PyCMD %s - type HELP, COMMANDS, or EXPLAIN <line>" % __version__)
            self.emit("By Jared (C)03/2019 - Enhanced 2026")
            if readline is None:
                self.emit_error(
                    "Note: readline is unavailable, so TAB completion and line editing are off."
                    " On Windows, 'pip install pyreadline3' enables them."
                )
        self.update_prompt()

        consecutive_errors = 0
        while self.running:
            try:
                user_input = input(self.prompt)
            except EOFError:
                self.emit("")
                self.running = False
                break
            except KeyboardInterrupt:
                self.emit("")
                self.emit_error("KeyboardInterrupt detected. Type EXIT to quit.")
                continue

            try:
                self.process_input(user_input)
                consecutive_errors = 0
            except KeyboardInterrupt:
                self.emit_error("Interrupted.")
            except Exception as err:
                self.emit_error("An error occurred:", err)
                consecutive_errors += 1
                if consecutive_errors >= 10:
                    self.emit_error("Too many consecutive errors; exiting.")
                    self.running = False
            self.update_prompt()
        return self.last_status


def build_parser():
    parser = argparse.ArgumentParser(
        prog="pycmd",
        description="PyCMD %s - a small, predictable CMD-style shell in Python." % __version__,
    )
    parser.add_argument("script", nargs="?", help="run a file of PyCMD commands, then exit")
    parser.add_argument("-c", "--command", action="append", metavar="LINE", help="run a command line, then exit (repeatable)")
    parser.add_argument("--safe-mode", action="store_true", help="disable every route to the OS shell")
    parser.add_argument("--config", metavar="PATH", help="use an alternative config file")
    parser.add_argument("--no-config", action="store_true", help="do not read or write any config file")
    parser.add_argument("--no-record", action="store_true", help="do not write on-disk command records")
    parser.add_argument("--no-banner", action="store_true", help="skip the startup banner")
    parser.add_argument("--version", action="version", version="PyCMD " + __version__)
    return parser


def main(argv=None):
    options = build_parser().parse_args(sys.argv[1:] if argv is None else argv)

    one_shot = bool(options.command) or bool(options.script)
    config_file = None if options.no_config else (options.config or CONFIG_FILE)

    emulator = CMDEmulator(
        config_file=config_file,
        record_file=None if options.no_record else RECORD_FILE,
        history_file=None if one_shot else HISTORY_FILE,
        auto_persist_history=not one_shot,
        interactive=False if one_shot else None,
        show_banner=not (options.no_banner or one_shot),
    )

    # These override the session only. stored_policy is left alone, so a single
    # --safe-mode run cannot silently lock down every future session.
    if options.safe_mode:
        emulator.policy.update(
            {
                "shell_fallback": "off",
                "path_programs": False,
                "legacy": False,
                "run_shell": False,
            }
        )
    elif one_shot:
        # A typo in a script must never become a shell command with nobody watching.
        emulator.policy["shell_fallback"] = "off"

    status = 0
    if options.command:
        for line in options.command:
            emulator.execute_line(line, record_history=False)
            status = emulator.last_status
            if not emulator.running:
                break
    if options.script and emulator.running:
        status = emulator.run_script(options.script) or status
    if not one_shot:
        status = emulator.run()

    return status


if __name__ == "__main__":
    sys.exit(main() or 0)
