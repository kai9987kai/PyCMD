# PyCMD

PyCMD is a small Python command shell for Windows-style workflows when you want
a simple CMD-like prompt from Python.

## Features

- Basic commands: `CWD`, `CD`, `CLS`, `DIR`, `PWD`, `MKDIR`, `DEL`, `ECHO`,
  `RUN`, `TIME`, and `DATE`.
- Discovery commands: `HELP <command>`, `COMMANDS`, `SUGGEST`, and typo
  suggestions for unknown commands. `? <command>` and `??` are quick help
  shortcuts.
- Persistent aliases with `ALIAS`, `UNALIAS`, and `LISTALIASES`.
- Persistent macros with `MACRO`, `RUNMACRO`, `UNMACRO`, and `LISTMACROS`.
  Macros can use `{1}`, `{2}`, and `{*}` placeholders for arguments.
- Directory bookmarks with `BOOKMARK`, `JUMP`, `UNBOOKMARK`, and
  `LISTBOOKMARKS`.
- Session history, searchable history records, and command timing stats.
- Safer execution mode with `RUN --safe <program> [args]`.
- Compact directory trees with `TREE [path] [depth]`.
- Shell shortcut execution with `!<command>`.
- Optional `readline` integration for history and tab completion when the host
  Python build supports it, including filesystem-aware suggestions.

## Usage

Run:

```powershell
python PythonCMD.py
```

Useful examples:

```text
HELP DIR
? RUN
??
COMMANDS
DIR --details
TREE . 2
ALIAS ll DIR --details
MACRO quick ECHO hello {1}; TIME
RUNMACRO quick kai
BOOKMARK project C:\Users\kai99\Desktop\PyCMD
JUMP project
HISTORY search python
DEL --dry-run example.txt
RUN --safe python --version
!echo shell shortcut
```

`RUN <command>` preserves the original shell-style behavior for compatibility.
Use `RUN --safe` when you want to execute a program without shell metacharacter
expansion.

## Development

Run tests with:

```powershell
python -m unittest discover -s tests -v
```

Project style: prefer British spelling in new function names and documentation
where it reads naturally.
