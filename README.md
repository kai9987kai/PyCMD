# PyCMD

PyCMD is a small Python command shell for Windows-style workflows when you want
a simple CMD-like prompt from Python. It is a single file with no third-party
dependencies — copy `PythonCMD.py` anywhere and run it.

Version 4.0 is about making the shell **predictable**: a typo can no longer
reach the OS shell, what you type is what runs, and the whole thing can be
scripted without a human at the keyboard.

## Quick start

```powershell
python PythonCMD.py
```

```text
HELP                      general help
COMMANDS                  every command, grouped by category
? RUN                     help for one command
EXPLAIN <line>            show exactly how PyCMD will interpret a line
```

## Features

- **Files**: `DIR`, `TREE`, `MKDIR`, `RMDIR`, `DEL`, `COPY`, `MOVE`, `RENAME`,
  `TOUCH`, plus `CWD`/`CD`, `PWD`, `WHICH`. Wildcards are expanded by PyCMD
  itself, and anything destructive asks before acting on more than one file.
- **Text tools**: `TYPE`, `GREP`, `SORT`, `HEAD`, `TAIL`, `COUNT`. They read a
  file *or* piped input, so a whole pipeline can run without a single external
  program: `TYPE notes.txt | SORT --unique | GREP todo`.
- **Variables and substitution**: `SET`, `UNSET`, `ENV`, with `$NAME`,
  `${NAME}`, `$?` (the last exit status) and `$(command)` substitution.
  Variables are exported, so child processes see them.
- **Control flow**: `IF <condition> THEN <cmd> [ELSE <cmd>]` and
  `FOR <name> IN <items> DO <cmd>` — enough to write real scripts.
- **Navigation**: `PUSHD`, `POPD`, `DIRS` alongside bookmarks.
- **Searching**: `SEARCH` finds files recursively by name or content;
  `DIFF` compares two files; `REPLACE` substitutes text in a stream or in place.
- **Operators**: chain commands with `&&` (on success), `||` (on failure) and
  `;` (always). A single `&` stays literal, so `DEL A&B.txt` still works.
- **Redirection**: `>`, `>>`, `2>`, `2>&1` and `<` work on PyCMD's own commands
  as well as external programs — `DIR --details > listing.txt`.
- **Pipes**: between builtins, or into a real program —
  `DIR --details | findstr .py`.
- **Execution policy**: an unrecognised command is *not* silently handed to
  `cmd.exe` (see below).
- **Persistent aliases** (`ALIAS`, `UNALIAS`, `LISTALIASES`), **macros**
  (`MACRO`, `RUNMACRO`, `UNMACRO`, `LISTMACROS`) with `{1}`, `{2}` and `{*}`
  placeholders, and **bookmarks** (`BOOKMARK`, `JUMP`, `UNBOOKMARK`,
  `LISTBOOKMARKS`). Names are case-insensitive and cannot shadow a builtin.
- **Insight**: `HISTORY` (with search and purge), `STATS`, `SUGGEST`, and
  `EXPLAIN` for showing how a line resolves before you run it.
- **Non-interactive mode**: `-c`, script files, and real exit codes.
- Optional `readline` integration for history and context-aware tab completion.

## How a command is resolved

PyCMD tries each layer in order, and `EXPLAIN` will show you the result:

1. **alias** → expanded and re-parsed
2. **macro** → each `;`-separated step is run in turn
3. **builtin** → dispatched directly
4. **program on PATH** → run directly via `argv`, with no shell in between
5. **anything else** → treated as a typo (see the policy below)

## Execution policy — the 4.0 behaviour change

In 3.0, an unrecognised command was passed straight to `os.system`. That meant a
one-key typo could destroy a file:

```text
dur > notes.txt     # 3.0: "Command not recognized" ... then cmd.exe truncates notes.txt
```

In 4.0 a word that is neither a builtin nor a program on your PATH is treated as
a typo. Nothing is opened, nothing is truncated, and the line is refused (or
confirmed first, when you are at an interactive prompt).

Real programs are unaffected: `git status`, `python --version` and
`findstr pattern` all resolve on PATH and run directly, with no shell involved.

Inspect and change the policy with `POLICY`:

| Setting | Default | Meaning |
|---|---|---|
| `shell_fallback` | `confirm` | What happens to an unknown word: `off`, `confirm`, or `always` (the 3.0 behaviour). |
| `path_programs` | `on` | Run words that resolve on PATH directly via `argv`. |
| `expand_variables` | `on` | Expand `$NAME`, `${NAME}` and `$?`. |
| `legacy` | `on` | Allow `LEGACY` and `!`. |
| `run_shell` | `on` | Allow `RUN`'s shell mode (`RUN --safe` is unaffected). |
| `operators` | `on` | Parse `&&`, `\|\|`, `;`, `\|` and redirection. Turn off for 3.0 line handling. |
| `record` | `on` | Write the on-disk command record. |
| `stop_on_error` | `off` | Stop a macro or script at the first failing command. |

```text
POLICY                          show the current policy
POLICY shell_fallback always    restore 3.0 behaviour
```

Every documented route to the OS shell is still one keystroke away and never
prompts: `!<command>`, `LEGACY <command>`, and `RUN <command>`.

## Usage examples

```text
HELP DIR
DIR --details
TREE . 2
ECHO built > log.txt && ECHO done
DIR --details | findstr .py
ALIAS ll DIR --details
MACRO quick ECHO hello {1}; TIME
RUNMACRO --dry-run quick kai
BOOKMARK project C:\Users\kai99\Downloads\PyCMD
JUMP project
HISTORY search python
DEL --dry-run *.tmp
COPY *.py backup
RMDIR --recurse build
TYPE notes.txt | GREP --invert done | SORT > todo.txt
DIR | COUNT
SET EDITOR=code
ECHO using $EDITOR
GREP -n TODO *.py || ECHO nothing left to do
SET N=$(TYPE notes.txt | GREP --count TODO)
IF $N > 0 THEN ECHO $N todos left ELSE ECHO all clear
FOR f IN src/*.py DO IF ISFILE $f THEN ECHO checking $f
SEARCH *.py --containing "import os"
REPLACE --in-place oldname newname src/*.py
PUSHD build && DIR && POPD
RUN --safe python --version
!echo shell shortcut
EXPLAIN ll | findstr py
```

### Conditions for `IF`

`EXISTS <path>`, `ISFILE <path>`, `ISDIR <path>`, `EMPTY <text>`, `<a> == <b>`,
`<a> != <b>`, and numeric `<a> < <b>` / `<a> > <b>` — any of them may be
preceded by `NOT`.

A script can now do real work:

```text
REM tidy up, then report what is left
FOR f IN *.tmp DO DEL --force $f
SET LEFT=$(SEARCH *.tmp | COUNT --lines)
IF $LEFT == 0 THEN ECHO clean ELSE ECHO $LEFT left over
```

## Command line

```powershell
python PythonCMD.py                      # interactive
python PythonCMD.py -c "ECHO hi"         # one-shot, then exit
python PythonCMD.py script.pycmd         # run a file of PyCMD commands
python PythonCMD.py --safe-mode          # no route to the OS shell at all
python PythonCMD.py --version
```

The process exit code is the status of the last command, so PyCMD can be used
inside a batch file or a CI step. In one-shot and script mode the shell fallback
is forced to `off`, because a typo in a script must never become a shell command
with nobody watching. Blank lines and lines starting with `#` or `REM` are
skipped in scripts.

## Files PyCMD writes

| File | Contents |
|---|---|
| `~/.pycmd_config.json` | Aliases, macros, bookmarks and policy. Written atomically. |
| `~/.pycmd_history.jsonl` | **Every command line you type**, with its working directory. Rotates at 2 MiB. |
| `~/.cmd_emulator_history` | The `readline` line-editing history. |

Because the record file captures everything you type, treat it as sensitive.
Turn it off with `RECORD off`, and delete it with `HISTORY --purge`.
`HISTORY --clear` only clears the in-memory session list and says so.

## Behaviour changes from 3.0

Besides the execution policy above:

- `MKDIR a b` creates **two** directories, and `DEL a b` deletes two, matching
  `cmd.exe`. Quote a name that contains spaces: `MKDIR "my folder"`.
- `DEL` expands wildcards itself and asks before removing more than one file.
  Use `--force` to skip the prompt and `--dry-run` to see the list first.
- Alias, macro and bookmark names cannot contain whitespace, quotes or operator
  characters, and cannot shadow a builtin. Existing entries that break these
  rules are ignored with a warning but are **kept** in the config file.
- `HISTORY 0` and other useless limits are rejected instead of printing
  everything.
- A macro argument containing `;`, `|`, `&`, `<` or `>` is quoted when it is
  substituted, so it can no longer inject a second command into the macro.

## Notes and limitations

- Redirected output is written as UTF-8, not the console code page.
- Only the text tools (`TYPE`, `GREP`, `SORT`, `HEAD`, `TAIL`, `COUNT`) read
  piped input. Piping into any other builtin discards it.
- `SORT`, `TYPE`, `COPY`, `MOVE` and friends are PyCMD builtins, so they take
  precedence over the Windows programs of the same name. Use `!sort` or
  `RUN sort` when you specifically want the system one.
- Variables expand as `$NAME`, not `%NAME%`. Expansion and `$(...)` both happen
  *after* the line is parsed, so a variable or a command's output holding
  `; DEL x` is text, never a command. An unknown name is left as typed rather
  than blanked, and an unbalanced `$(` is left literal.
- `$(...)` collapses newlines to spaces. Use `COUNT --lines` and friends when
  you want a single value to store in a variable.
- `IF` and `FOR` take the rest of the line as their body, so `&&`, `|` and `>`
  inside them belong to the branch or loop body, not to the `IF`/`FOR` itself.
- `FOR` skips wildcards that match nothing, rather than looping once over the
  literal pattern.
- `!`, `LEGACY` and `RUN` pass their tail to the OS shell verbatim, so
  operators and redirection in those lines are the shell's to interpret, not
  PyCMD's. `ALIAS`, `MACRO` and `EXPLAIN` likewise keep their tail intact.
- A line containing an unpaired quote (`ECHO don't stop`) is treated literally
  rather than refused, so operators and redirection are not detected in it.
- Two PyCMD sessions writing config at the same time still last-writer-wins;
  there is no file locking.
- `CLS` and `COLOR` act on the console only, so they decline to run when output
  is redirected or piped.
- On Windows, stock CPython has no `readline`, so tab completion and line
  editing are unavailable until you `pip install pyreadline3`. PyCMD itself
  needs nothing installed; it reports the backend in `CONFIG`.

## Development

Run tests with:

```powershell
python -m unittest discover -s tests -v
```

`tests/test_pythoncmd.py` is the 3.0 regression contract and is deliberately
left unchanged; `tests/test_pycmd4.py` covers the 4.0 behaviour.

Project style: prefer British spelling in new function names and documentation
where it reads naturally.
