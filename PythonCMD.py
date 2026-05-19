#!/usr/bin/env python3
"""
Advanced CMD Emulator for Windows [Version 3.0 - Enhanced 2026]
By Jared (C)03/2019 - Enhanced 2026

PyCMD keeps the original simple command surface and adds practical shell
quality-of-life features: better command discovery, optional persistent
aliases, directory bookmarks, command suggestions, and lightweight stats.

For best functionality run this on the Python command line.
Visit my GitHub: http://www.github.com/Jared-dareJ/
"""

import atexit
import difflib
import getpass
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import time

try:
    import readline
except ImportError:  # pragma: no cover - depends on the host Python build
    readline = None


HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".cmd_emulator_history")
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".pycmd_config.json")
RECORD_FILE = os.path.join(os.path.expanduser("~"), ".pycmd_history.jsonl")


class CMDEmulator:
    COMMAND_INFO = {
        "CWD": ("Navigation", "CWD <directory>", "Change working directory."),
        "CD": ("Navigation", "CD <directory>", "Alias for CWD."),
        "PWD": ("Navigation", "PWD", "Display the current working directory."),
        "DIR": ("Files", "DIR [path] [--details]", "List directory contents."),
        "MKDIR": ("Files", "MKDIR <directory>", "Create a new directory."),
        "DEL": ("Files", "DEL [--dry-run] <filename>", "Delete a file."),
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
        "RUNMACRO": ("Productivity", "RUNMACRO <name> [args]", "Run a saved macro."),
        "UNMACRO": ("Productivity", "UNMACRO <name>", "Remove a saved macro."),
        "LISTMACROS": ("Productivity", "LISTMACROS", "List all saved macros."),
        "BOOKMARK": ("Productivity", "BOOKMARK <name> [path]", "Save a directory bookmark."),
        "JUMP": ("Productivity", "JUMP <name>", "Change to a saved bookmark."),
        "UNBOOKMARK": ("Productivity", "UNBOOKMARK <name>", "Remove a directory bookmark."),
        "LISTBOOKMARKS": ("Productivity", "LISTBOOKMARKS", "List directory bookmarks."),
        "HISTORY": ("Insight", "HISTORY [limit|last n|search text|--clear]", "Show, search, or clear session history."),
        "STATS": ("Insight", "STATS", "Show command counts, failures, and slow commands."),
        "SUGGEST": ("Insight", "SUGGEST <text>", "Show command and alias suggestions."),
        "COMMANDS": ("Help", "COMMANDS", "List commands grouped by category."),
        "HELP": ("Help", "HELP [command]", "Show general or command-specific help."),
        "_HELP": ("Help", "_HELP [command]", "Alias for HELP."),
        "?": ("Help", "? [command]", "Shortcut for HELP."),
        "??": ("Help", "??", "Shortcut for COMMANDS."),
        "CONFIG": ("Help", "CONFIG", "Show PyCMD config and history locations."),
        "TREE": ("Files", "TREE [path] [depth]", "Show a compact directory tree."),
        "RESTART": ("Session", "RESTART", "Restart the CMD Emulator session."),
        "EXIT": ("Session", "EXIT", "Exit the emulator."),
    }

    def __init__(
        self,
        history_file=HISTORY_FILE,
        config_file=CONFIG_FILE,
        record_file=RECORD_FILE,
        auto_persist_history=True,
    ):
        self.prompt = ""
        self.history = []
        self.aliases = {}
        self.macros = {}
        self.bookmarks = {}
        self.command_stats = []
        self.history_file = history_file
        self.config_file = config_file
        self.record_file = record_file
        self.record_write_failed = False
        self.running = True

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
            "PWD": self.cmd_pwd,
            "ECHO": self.cmd_echo,
            "RUN": self.cmd_run,
            "TIME": self.cmd_time,
            "DATE": self.cmd_date,
            "HISTORY": self.cmd_history,
            "STATS": self.cmd_stats,
            "SUGGEST": self.cmd_suggest,
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

        self.load_config()
        self.configure_readline(auto_persist_history)
        self.update_prompt()

    def update_prompt(self):
        self.prompt = os.getcwd() + "> "

    def configure_readline(self, auto_persist_history):
        if readline is None:
            return

        if self.history_file:
            try:
                readline.read_history_file(self.history_file)
            except FileNotFoundError:
                pass
            except OSError as err:
                print("Warning: could not read history file:", err)

        try:
            readline.set_completer(self.complete)
            readline.parse_and_bind("tab: complete")
        except Exception as err:
            print("Warning: command completion is unavailable:", err)

        if auto_persist_history and self.history_file:
            atexit.register(self.save_readline_history)

    def save_readline_history(self):
        if readline is None or not self.history_file:
            return
        try:
            readline.write_history_file(self.history_file)
        except OSError as err:
            print("Warning: could not save history file:", err)

    def load_config(self):
        if not self.config_file:
            return
        try:
            with open(self.config_file, "r", encoding="utf-8") as config_stream:
                config = json.load(config_stream)
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError) as err:
            print("Warning: could not load config:", err)
            return

        aliases = config.get("aliases", {})
        macros = config.get("macros", {})
        bookmarks = config.get("bookmarks", {})
        if isinstance(aliases, dict):
            self.aliases = {str(name): str(command) for name, command in aliases.items()}
        if isinstance(macros, dict):
            self.macros = {str(name): str(command) for name, command in macros.items()}
        if isinstance(bookmarks, dict):
            self.bookmarks = {str(name): str(path) for name, path in bookmarks.items()}

    def save_config(self):
        if not self.config_file:
            return False
        config = {
            "version": 1,
            "aliases": self.aliases,
            "macros": self.macros,
            "bookmarks": self.bookmarks,
        }
        try:
            with open(self.config_file, "w", encoding="utf-8") as config_stream:
                json.dump(config, config_stream, indent=2, sort_keys=True)
                config_stream.write("\n")
            return True
        except OSError as err:
            print("Warning: could not save config:", err)
            return False

    def complete(self, text, state):
        options = self.get_suggestions(text)
        if state < len(options):
            return options[state]
        return None

    def get_suggestions(self, text, limit=6):
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

    def get_path_suggestions(self, text, limit=6):
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
            display_value = os.path.join(display_directory, name) if display_directory else name
            candidate_path = os.path.join(directory, name)
            if os.path.isdir(candidate_path):
                display_value += os.sep
            suggestions.append(display_value)
            if len(suggestions) >= limit:
                break
        return suggestions

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
            print("Input parse error:", err)
            return arg_string.split()

    @staticmethod
    def strip_wrapping_quotes(value):
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            return value[1:-1]
        return value

    def print_table(self, rows, headers=None):
        rows = list(rows)
        if headers:
            rows = [headers] + rows
        if not rows:
            return
        widths = [max(len(str(row[index])) for row in rows) for index in range(len(rows[0]))]
        for row_index, row in enumerate(rows):
            print("  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))
            if headers and row_index == 0:
                print("  ".join("-" * width for width in widths))

    def record_stat(self, command_line, success, duration):
        record = {
            "command": command_line,
            "success": success,
            "duration": duration,
            "time": time.strftime("%H:%M:%S"),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "cwd": os.getcwd(),
        }
        self.command_stats.append(record)
        if len(self.command_stats) > 200:
            self.command_stats = self.command_stats[-200:]
        self.append_history_record(record)

    def append_history_record(self, record):
        if not self.record_file or self.record_write_failed:
            return
        try:
            with open(self.record_file, "a", encoding="utf-8") as record_stream:
                json.dump(record, record_stream, sort_keys=True)
                record_stream.write("\n")
        except OSError as err:
            self.record_write_failed = True
            print("Warning: could not save history record:", err)

    def load_history_records(self):
        if not self.record_file or not os.path.exists(self.record_file):
            return []
        records = []
        try:
            with open(self.record_file, "r", encoding="utf-8") as record_stream:
                for line in record_stream:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError as err:
            print("Warning: could not read history records:", err)
        return records

    def cmd_cwd(self, args, arg_string=""):
        if args:
            dir_path = " ".join(args)
        else:
            dir_path = input("Enter directory path: ").strip()
        try:
            os.chdir(os.path.expanduser(dir_path))
            self.update_prompt()
            return True
        except Exception as err:
            print("Error changing directory:", err)
            return False

    def cmd_cls(self, args, arg_string=""):
        command = "cls" if platform.system() == "Windows" else "clear"
        subprocess.call(command, shell=True)
        return True

    def cmd_color(self, args, arg_string=""):
        if not args:
            print("Usage: COLOR <code>")
            return False
        if platform.system() != "Windows":
            print("COLOR is only supported by Windows console hosts.")
            return False
        code = args[0]
        try:
            subprocess.call("color " + code, shell=True)
            print("Color changed to:", code)
            return True
        except Exception as err:
            print("Error changing color:", err)
            return False

    def cmd_help(self, args, arg_string=""):
        if args:
            command = args[0].upper()
            info = self.COMMAND_INFO.get(command)
            if not info:
                print(f"No help topic for: {args[0]}")
                self.print_suggestions(args[0])
                return False
            category, usage, description = info
            print(f"{command} ({category})")
            print("Usage:", usage)
            print(description)
            return True

        print(
            """
Advanced CMD Emulator Help:

Type COMMANDS to list available commands.
Type HELP <command> for command-specific help.
Type SUGGEST <text> to discover similar commands and aliases.

Common commands:
  CWD <directory>       Change working directory.
  DIR [path]            List directory contents.
  TREE [path] [depth]   Show a compact directory tree.
  RUN <command>         Execute an external command/program.
  RUN --safe <command>  Execute without shell metacharacter expansion.
  !<command>            Execute through the OS shell.
  ALIAS <name> <cmd>    Create a persistent command shortcut.
  MACRO <name> a; b     Save multiple commands as one workflow.
  BOOKMARK <name>       Save the current directory for quick jumps.
  HISTORY search <text> Search command history records.
  STATS                 Show lightweight session statistics.
  EXIT                  Exit the emulator.

Notes:
- Commands are case-insensitive.
- Type ? RUN for quick command help or ?? for the command list.
- Alias names keep the spelling you choose.
- Macros can use {1}, {2}, and {*} placeholders for RUNMACRO arguments.
- Unknown commands show suggestions before PyCMD tries legacy execution.
"""
        )
        return True

    def cmd_commands(self, args, arg_string=""):
        grouped = {}
        for command, (category, usage, description) in self.COMMAND_INFO.items():
            grouped.setdefault(category, []).append((command, usage, description))

        for category in sorted(grouped):
            print(f"\n{category}:")
            rows = [(command, usage, description) for command, usage, description in grouped[category]]
            self.print_table(rows, headers=("Command", "Usage", "Description"))
        return True

    def cmd_config(self, args, arg_string=""):
        print("PyCMD configuration:")
        print("  User:", getpass.getuser())
        print("  Python:", sys.version.split()[0])
        print("  Platform:", platform.platform())
        print("  Config file:", self.config_file or "disabled")
        print("  History file:", self.history_file or "disabled")
        print("  History records:", self.record_file or "disabled")
        print("  Readline:", "available" if readline is not None else "unavailable")
        return True

    def cmd_legacy(self, args, arg_string=""):
        legacy_cmd = arg_string or input("Legacy CMD> ")
        if not legacy_cmd.strip():
            print("Usage: LEGACY <command>")
            return False
        try:
            exit_code = os.system(legacy_cmd)
            return exit_code == 0
        except Exception as err:
            print("Error executing legacy command:", err)
            return False

    def cmd_dir(self, args, arg_string=""):
        target = os.getcwd()
        details = False
        for arg in args:
            if arg.lower() in ("--details", "/details"):
                details = True
            else:
                target = arg

        try:
            target = os.path.expanduser(target)
            items = sorted(os.listdir(target), key=str.lower)
            if not details:
                for item in items:
                    print(item)
                return True

            rows = []
            for item in items:
                item_path = os.path.join(target, item)
                stat = os.stat(item_path)
                item_type = "<DIR>" if os.path.isdir(item_path) else "file"
                size = "" if os.path.isdir(item_path) else str(stat.st_size)
                modified = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
                rows.append((item_type, size, modified, item))
            self.print_table(rows, headers=("Type", "Size", "Modified", "Name"))
            return True
        except Exception as err:
            print("Error listing directory:", err)
            return False

    def cmd_tree(self, args, arg_string=""):
        target = os.path.expanduser(args[0]) if args else os.getcwd()
        try:
            depth = int(args[1]) if len(args) > 1 else 2
        except ValueError:
            print("Usage: TREE [path] [depth]")
            return False

        if depth < 0:
            print("Depth must be 0 or greater.")
            return False
        if not os.path.isdir(target):
            print("Tree path is not a directory:", target)
            return False

        target = os.path.abspath(target)
        print(target)
        self.print_tree(target, depth)
        return True

    def print_tree(self, root, max_depth, prefix="", current_depth=0):
        if current_depth >= max_depth:
            return
        try:
            entries = sorted(os.listdir(root), key=str.lower)
        except OSError as err:
            print(prefix + "Error:", err)
            return

        for index, entry in enumerate(entries):
            path = os.path.join(root, entry)
            is_last = index == len(entries) - 1
            connector = "`-- " if is_last else "|-- "
            print(prefix + connector + entry)
            if os.path.isdir(path):
                child_prefix = prefix + ("    " if is_last else "|   ")
                self.print_tree(path, max_depth, child_prefix, current_depth + 1)

    def cmd_mkdir(self, args, arg_string=""):
        if not args:
            print("Usage: MKDIR <directory_name>")
            return False
        dirname = os.path.expanduser(" ".join(args))
        try:
            os.makedirs(dirname, exist_ok=False)
            print(f"Directory '{dirname}' created.")
            return True
        except Exception as err:
            print("Error creating directory:", err)
            return False

    def cmd_del(self, args, arg_string=""):
        if not args:
            print("Usage: DEL [--dry-run] <filename>")
            return False

        dry_run = False
        file_parts = []
        for arg in args:
            if arg.lower() in ("--dry-run", "/dry-run", "-n"):
                dry_run = True
            else:
                file_parts.append(arg)

        if not file_parts:
            print("Usage: DEL [--dry-run] <filename>")
            return False

        filename = os.path.expanduser(" ".join(file_parts))
        if dry_run:
            print(f"Would delete: {filename}")
            return os.path.isfile(filename)

        try:
            os.remove(filename)
            print(f"File '{filename}' deleted.")
            return True
        except Exception as err:
            print("Error deleting file:", err)
            return False

    def cmd_pwd(self, args, arg_string=""):
        print("Current Directory:", os.getcwd())
        return True

    def cmd_echo(self, args, arg_string=""):
        print(arg_string)
        return True

    def cmd_run(self, args, arg_string=""):
        if not arg_string.strip():
            print("Usage: RUN [--safe] <command>")
            return False
        if args and args[0].lower() in ("--safe", "/safe"):
            safe_args = args[1:]
            if not safe_args:
                print("Usage: RUN --safe <command>")
                return False
            try:
                completed = subprocess.run(safe_args, shell=False)
                return completed.returncode == 0
            except Exception as err:
                print("Error running safe command:", err)
                return False

        try:
            completed = subprocess.run(arg_string, shell=True)
            return completed.returncode == 0
        except Exception as err:
            print("Error running command:", err)
            return False

    def cmd_time(self, args, arg_string=""):
        print("Current Time:", time.strftime("%H:%M:%S"))
        return True

    def cmd_date(self, args, arg_string=""):
        print("Current Date:", time.strftime("%Y-%m-%d"))
        return True

    def cmd_history(self, args, arg_string=""):
        if args and args[0].lower() in ("--clear", "/clear"):
            self.history.clear()
            print("Session history cleared.")
            return True

        if args and args[0].lower() in ("search", "find"):
            query = " ".join(args[1:]).strip()
            if not query:
                print("Usage: HISTORY search <text>")
                return False
            return self.search_history(query)

        if args and args[0].lower() == "last":
            if len(args) == 1:
                limit = 10
            else:
                try:
                    limit = int(args[1])
                except ValueError:
                    print("Usage: HISTORY last [limit]")
                    return False
            return self.print_history_entries(self.history[-limit:])

        limit = None
        if args:
            try:
                limit = int(args[0])
            except ValueError:
                print("Usage: HISTORY [limit|last n|search text|--clear]")
                return False

        entries = self.history[-limit:] if limit else self.history
        return self.print_history_entries(entries)

    def print_history_entries(self, entries):
        if entries:
            print("Command History:")
            start = len(self.history) - len(entries) + 1
            for index, command in enumerate(entries, start=start):
                print(f"{index}: {command}")
        else:
            print("No commands in history.")
        return True

    def search_history(self, query):
        query_lower = query.lower()
        session_matches = [
            {"source": "session", "time": "", "cwd": "", "command": command}
            for command in self.history
            if query_lower in command.lower()
        ]
        record_matches = [
            {"source": "record", **record}
            for record in self.load_history_records()
            if query_lower in str(record.get("command", "")).lower()
        ]
        matches = (session_matches + record_matches)[-20:]
        if not matches:
            print(f"No history matches for: {query}")
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

    def cmd_stats(self, args, arg_string=""):
        if not self.command_stats:
            print("No commands have been executed yet.")
            return True

        total = len(self.command_stats)
        failures = sum(1 for item in self.command_stats if not item["success"])
        average = sum(item["duration"] for item in self.command_stats) / total
        print("Session stats:")
        print("  Commands:", total)
        print("  Failures:", failures)
        print("  Average duration:", f"{average:.3f}s")

        slowest = sorted(self.command_stats, key=lambda item: item["duration"], reverse=True)[:5]
        print("\nSlowest commands:")
        rows = [
            (item["time"], f"{item['duration']:.3f}s", "ok" if item["success"] else "failed", item["command"])
            for item in slowest
        ]
        self.print_table(rows, headers=("Time", "Duration", "Result", "Command"))
        return True

    def cmd_suggest(self, args, arg_string=""):
        text = arg_string or (args[0] if args else "")
        if not text:
            print("Usage: SUGGEST <text>")
            return False
        self.print_suggestions(text)
        return True

    def print_suggestions(self, text):
        suggestions = self.get_suggestions(text)
        if suggestions:
            print("Did you mean:", ", ".join(suggestions))
        else:
            print("No close PyCMD command or alias found.")

    def cmd_alias(self, args, arg_string=""):
        if len(args) < 2:
            print("Usage: ALIAS <name> <command>")
            return False
        name = args[0]
        command_start = arg_string.find(name) + len(name)
        command = arg_string[command_start:].strip()
        if not command:
            print("Usage: ALIAS <name> <command>")
            return False
        self.aliases[name] = command
        self.save_config()
        print(f"Alias created: {name} -> {command}")
        return True

    def cmd_unalias(self, args, arg_string=""):
        if len(args) != 1:
            print("Usage: UNALIAS <name>")
            return False
        name = args[0]
        if name in self.aliases:
            del self.aliases[name]
            self.save_config()
            print(f"Alias '{name}' removed.")
            return True
        print(f"No such alias: {name}")
        return False

    def cmd_listaliases(self, args, arg_string=""):
        if self.aliases:
            rows = sorted((name, command) for name, command in self.aliases.items())
            self.print_table(rows, headers=("Alias", "Command"))
        else:
            print("No aliases defined.")
        return True

    def cmd_macro(self, args, arg_string=""):
        if len(args) < 2:
            print("Usage: MACRO <name> <command>; <command>")
            return False

        name = args[0]
        macro_start = arg_string.find(name) + len(name)
        macro_text = arg_string[macro_start:].strip()
        commands = self.split_macro_commands(macro_text)
        if not commands:
            print("Usage: MACRO <name> <command>; <command>")
            return False

        self.macros[name] = macro_text
        self.save_config()
        print(f"Macro saved: {name} ({len(commands)} command(s))")
        return True

    def cmd_runmacro(self, args, arg_string=""):
        if not args:
            print("Usage: RUNMACRO <name> [args]")
            return False

        name = args[0]
        extra_start = arg_string.find(name) + len(name)
        extra_string = arg_string[extra_start:].strip()
        return self.run_macro(name, args[1:], extra_string)

    def cmd_unmacro(self, args, arg_string=""):
        if len(args) != 1:
            print("Usage: UNMACRO <name>")
            return False
        name = args[0]
        if name in self.macros:
            del self.macros[name]
            self.save_config()
            print(f"Macro '{name}' removed.")
            return True
        print(f"No such macro: {name}")
        return False

    def cmd_listmacros(self, args, arg_string=""):
        if self.macros:
            rows = sorted((name, command) for name, command in self.macros.items())
            self.print_table(rows, headers=("Macro", "Commands"))
        else:
            print("No macros defined.")
        return True

    def split_macro_commands(self, macro_text):
        commands = []
        current = []
        quote = None

        for char in macro_text:
            if char in ("'", '"'):
                quote = None if quote == char else char if quote is None else quote
                current.append(char)
                continue
            if char == ";" and quote is None:
                command = "".join(current).strip()
                if command:
                    commands.append(command)
                current = []
                continue
            current.append(char)

        command = "".join(current).strip()
        if command:
            commands.append(command)
        return commands

    def expand_macro_command(self, command, args, arg_string):
        expanded = command.replace("{*}", arg_string)
        for index, value in enumerate(args, start=1):
            expanded = expanded.replace("{" + str(index) + "}", value)
        return expanded

    def run_macro(self, name, args=None, arg_string="", macro_depth=0):
        args = args or []
        if macro_depth >= 10:
            print("Macro expansion stopped: possible macro loop.")
            return False

        macro_text = self.macros.get(name)
        if not macro_text:
            print(f"No such macro: {name}")
            self.print_suggestions(name)
            return False

        success = True
        for command in self.split_macro_commands(macro_text):
            expanded = self.expand_macro_command(command, args, arg_string)
            print(">>", expanded)
            success = self.execute_line(
                expanded,
                record_history=False,
                macro_depth=macro_depth + 1,
            ) and success
        return success

    def cmd_bookmark(self, args, arg_string=""):
        if not args:
            print("Usage: BOOKMARK <name> [path]")
            return False
        name = args[0]
        path = os.path.expanduser(" ".join(args[1:])) if len(args) > 1 else os.getcwd()
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            print("Bookmark path is not a directory:", path)
            return False
        self.bookmarks[name] = path
        self.save_config()
        print(f"Bookmark saved: {name} -> {path}")
        return True

    def cmd_jump(self, args, arg_string=""):
        if len(args) != 1:
            print("Usage: JUMP <name>")
            return False
        name = args[0]
        path = self.bookmarks.get(name)
        if not path:
            print(f"No such bookmark: {name}")
            self.print_suggestions(name)
            return False
        try:
            os.chdir(path)
            self.update_prompt()
            print("Current Directory:", os.getcwd())
            return True
        except Exception as err:
            print("Error changing directory:", err)
            return False

    def cmd_unbookmark(self, args, arg_string=""):
        if len(args) != 1:
            print("Usage: UNBOOKMARK <name>")
            return False
        name = args[0]
        if name in self.bookmarks:
            del self.bookmarks[name]
            self.save_config()
            print(f"Bookmark '{name}' removed.")
            return True
        print(f"No such bookmark: {name}")
        return False

    def cmd_listbookmarks(self, args, arg_string=""):
        if self.bookmarks:
            rows = sorted((name, path) for name, path in self.bookmarks.items())
            self.print_table(rows, headers=("Bookmark", "Path"))
        else:
            print("No bookmarks defined.")
        return True

    def cmd_shell(self, args, arg_string=""):
        print("Launching external shell...")
        try:
            if platform.system() == "Windows":
                subprocess.Popen("start cmd", shell=True)
            else:
                shell = shutil.which("x-terminal-emulator") or shutil.which("xterm")
                if not shell:
                    print("No terminal emulator found.")
                    return False
                subprocess.Popen(shell, shell=True)
            return True
        except Exception as err:
            print("Error launching shell:", err)
            return False

    def cmd_which(self, args, arg_string=""):
        if len(args) != 1:
            print("Usage: WHICH <program>")
            return False
        found = shutil.which(args[0])
        if found:
            print(found)
            return True
        print(f"Program not found on PATH: {args[0]}")
        return False

    def cmd_restart(self, args, arg_string=""):
        print("Restarting CMD Emulator...")
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def cmd_exit(self, args, arg_string=""):
        print("Exiting CMD Emulator.")
        self.running = False
        return True

    def process_input(self, user_input):
        self.execute_line(user_input, record_history=True)

    def execute_line(self, user_input, record_history=True, alias_depth=0, macro_depth=0):
        command_line = user_input.strip()
        if not command_line:
            return True

        if record_history:
            self.history.append(command_line)
            if readline is not None:
                readline.add_history(command_line)

        command, arg_string = self.split_input(command_line)
        args = self.tokenise_args(arg_string)

        if command in self.aliases:
            if alias_depth >= 10:
                print("Alias expansion stopped: possible alias loop.")
                self.record_stat(command_line, False, 0)
                return False
            expanded = self.aliases[command]
            if arg_string:
                expanded = expanded + " " + arg_string
            return self.execute_line(
                expanded,
                record_history=False,
                alias_depth=alias_depth + 1,
                macro_depth=macro_depth,
            )

        if command in self.macros:
            return self.run_macro(command, args, arg_string, macro_depth=macro_depth)

        command_key = command.upper()
        started = time.perf_counter()
        success = False
        try:
            if command_key in self.commands:
                result = self.commands[command_key](args, arg_string)
                success = result is not False
            else:
                print("Command not recognized.")
                self.print_suggestions(command)
                print("Trying legacy mode...")
                success = os.system(command_line) == 0
        except Exception as err:
            print("Error executing command:", err)
            success = False

        duration = time.perf_counter() - started
        self.record_stat(command_line, success, duration)
        return success

    def run(self):
        print("Welcome to the Advanced CMD Emulator")
        print("For help, type HELP or _HELP")
        print("By Jared (C)03/2019 - Enhanced 2026")
        time.sleep(1)
        self.update_prompt()

        while self.running:
            try:
                user_input = input(self.prompt)
                self.process_input(user_input)
                self.update_prompt()
            except KeyboardInterrupt:
                print("\nKeyboardInterrupt detected. Type EXIT to quit.")
            except Exception as err:
                print("An error occurred:", err)


def main():
    emulator = CMDEmulator()
    emulator.run()


if __name__ == "__main__":
    main()
