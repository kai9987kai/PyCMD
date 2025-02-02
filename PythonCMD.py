#!/usr/bin/env python3
"""
Advanced CMD Emulator for Windows [Version 2.0 - Enhanced 2025]
By Jared (C)03/2019 - Enhanced 2025

Features:
  - Basic Commands: CWD, CLS, DIR, PWD, MKDIR, DEL, ECHO, RUN, TIME, DATE.
  - Legacy Mode: Execute any command via OS shell.
  - Command History: Persistent session history with auto-completion (if readline available).
  - Aliases: Create and manage command shortcuts.
  - Advanced Commands: SHELL (launch external interactive shell), RESTART (restart emulator).
  - Extended HELP with detailed command usage.
  
For best functionality run this on the Python Command Line.
Visit my GitHub: http://www.github.com/Jared-dareJ/
"""

import os
import sys
import subprocess
import time
import platform
import shutil
import getpass
import readline  # For auto-completion and persistent history (if available)
import atexit

HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".cmd_emulator_history")

# Load persistent history if available
try:
    readline.read_history_file(HISTORY_FILE)
except FileNotFoundError:
    pass
atexit.register(readline.write_history_file, HISTORY_FILE)


class CMDEmulator:
    def __init__(self):
        self.prompt = os.getcwd() + '> '
        self.history = []  # In-memory session history (for display)
        self.aliases = {}  # alias mapping: alias -> command string

        # Dispatcher: map command names to methods
        self.commands = {
            'CWD': self.cmd_cwd,
            'CLS': self.cmd_cls,
            'COLOR': self.cmd_color,
            '_HELP': self.cmd_help,
            'HELP': self.cmd_help,
            'LEGACY': self.cmd_legacy,
            'DIR': self.cmd_dir,
            'MKDIR': self.cmd_mkdir,
            'DEL': self.cmd_del,
            'PWD': self.cmd_pwd,
            'ECHO': self.cmd_echo,
            'RUN': self.cmd_run,
            'TIME': self.cmd_time,
            'DATE': self.cmd_date,
            'HISTORY': self.cmd_history,
            'ALIAS': self.cmd_alias,
            'UNALIAS': self.cmd_unalias,
            'LISTALIASES': self.cmd_listaliases,
            'SHELL': self.cmd_shell,
            'RESTART': self.cmd_restart,
            'EXIT': self.cmd_exit
        }
        self.running = True

    def update_prompt(self):
        self.prompt = os.getcwd() + '> '

    def cmd_cwd(self, args):
        """Change Working Directory. Usage: CWD <directory>"""
        if args:
            dir_path = ' '.join(args)
        else:
            dir_path = input("Enter directory path: ").strip()
        try:
            os.chdir(dir_path)
            self.update_prompt()
        except Exception as e:
            print("Error changing directory:", e)

    def cmd_cls(self, args):
        """Clear the screen."""
        if platform.system() == "Windows":
            subprocess.call('cls', shell=True)
        else:
            subprocess.call('clear', shell=True)

    def cmd_color(self, args):
        """Change console color. Usage: COLOR <code> (hex digit 0-9, A-F)"""
        if not args:
            print("Usage: COLOR <code>")
            return
        code = args[0]
        try:
            subprocess.call('color ' + code, shell=True)
            print("Color changed to:", code)
        except Exception as e:
            print("Error changing color:", e)

    def cmd_help(self, args):
        """Display help information."""
        help_text = """
Advanced CMD Emulator Help:

Basic Commands:
  CWD <directory>     : Change working directory.
  CLS                 : Clear the screen.
  DIR                 : List contents of the current directory.
  PWD                 : Display the current working directory.
  MKDIR <dirname>     : Create a new directory.
  DEL <filename>      : Delete a file.
  ECHO <text>         : Display the given text.
  RUN <command>       : Execute an external command/program.
  TIME                : Display the current system time.
  DATE                : Display the current system date.
  LEGACY              : Enter legacy mode (execute CMD commands).
  
Advanced Commands:
  HISTORY             : Show command history for this session.
  ALIAS <name> <cmd>  : Create an alias for a command.
  UNALIAS <name>      : Remove an existing alias.
  LISTALIASES         : List all command aliases.
  SHELL               : Launch an interactive system shell in a new window.
  RESTART             : Restart the CMD Emulator session.
  EXIT                : Exit the emulator.

Notes:
- Commands are case sensitive.
- When in legacy mode, simply type your CMD command.
- Aliases allow you to define shortcuts (e.g., ALIAS ls DIR).
"""
        print(help_text)

    def cmd_legacy(self, args):
        """Legacy mode: Execute a CMD command through OS shell."""
        legacy_cmd = input("Legacy CMD> ")
        try:
            os.system(legacy_cmd)
        except Exception as e:
            print("Error executing legacy command:", e)

    def cmd_dir(self, args):
        """List directory contents."""
        try:
            items = os.listdir(os.getcwd())
            for item in items:
                print(item)
        except Exception as e:
            print("Error listing directory:", e)

    def cmd_mkdir(self, args):
        """Create a new directory. Usage: MKDIR <dirname>"""
        if not args:
            print("Usage: MKDIR <directory_name>")
            return
        dirname = ' '.join(args)
        try:
            os.mkdir(dirname)
            print(f"Directory '{dirname}' created.")
        except Exception as e:
            print("Error creating directory:", e)

    def cmd_del(self, args):
        """Delete a file. Usage: DEL <filename>"""
        if not args:
            print("Usage: DEL <filename>")
            return
        filename = ' '.join(args)
        try:
            os.remove(filename)
            print(f"File '{filename}' deleted.")
        except Exception as e:
            print("Error deleting file:", e)

    def cmd_pwd(self, args):
        """Print the current working directory."""
        print("Current Directory:", os.getcwd())

    def cmd_echo(self, args):
        """Echo (print) the provided text."""
        print(' '.join(args))

    def cmd_run(self, args):
        """Execute an external command. Usage: RUN <command>"""
        if not args:
            print("Usage: RUN <command>")
            return
        try:
            subprocess.run(' '.join(args), shell=True)
        except Exception as e:
            print("Error running command:", e)

    def cmd_time(self, args):
        """Display current system time."""
        print("Current Time:", time.strftime("%H:%M:%S"))

    def cmd_date(self, args):
        """Display current system date."""
        print("Current Date:", time.strftime("%Y-%m-%d"))

    def cmd_history(self, args):
        """Show the command history of this session."""
        if self.history:
            print("Command History:")
            for idx, cmd in enumerate(self.history, start=1):
                print(f"{idx}: {cmd}")
        else:
            print("No commands in history.")

    def cmd_alias(self, args):
        """Create an alias. Usage: ALIAS <name> <command string>"""
        if len(args) < 2:
            print("Usage: ALIAS <name> <command>")
            return
        name = args[0]
        cmd = ' '.join(args[1:])
        self.aliases[name] = cmd
        print(f"Alias created: {name} -> {cmd}")

    def cmd_unalias(self, args):
        """Remove an alias. Usage: UNALIAS <name>"""
        if len(args) != 1:
            print("Usage: UNALIAS <name>")
            return
        name = args[0]
        if name in self.aliases:
            del self.aliases[name]
            print(f"Alias '{name}' removed.")
        else:
            print(f"No such alias: {name}")

    def cmd_listaliases(self, args):
        """List all defined aliases."""
        if self.aliases:
            print("Defined Aliases:")
            for name, cmd in self.aliases.items():
                print(f"{name} -> {cmd}")
        else:
            print("No aliases defined.")

    def cmd_shell(self, args):
        """Launch an interactive system shell in a new window."""
        print("Launching external shell...")
        try:
            if platform.system() == "Windows":
                subprocess.Popen("start cmd", shell=True)
            else:
                subprocess.Popen("x-terminal-emulator", shell=True)
        except Exception as e:
            print("Error launching shell:", e)

    def cmd_restart(self, args):
        """Restart the CMD Emulator session."""
        print("Restarting CMD Emulator...")
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def cmd_exit(self, args):
        """Exit the CMD Emulator."""
        print("Exiting CMD Emulator.")
        self.running = False

    def process_input(self, user_input):
        """Process user input by handling aliases and dispatching commands."""
        if not user_input.strip():
            return

        # Save to session history
        self.history.append(user_input)
        readline.add_history(user_input)

        # Tokenize input and check for aliases
        tokens = user_input.split()
        cmd = tokens[0]
        args = tokens[1:]

        # Replace alias if exists
        if cmd in self.aliases:
            alias_cmd = self.aliases[cmd]
            # Combine alias expansion with additional arguments, if any
            full_cmd = alias_cmd + ' ' + ' '.join(args)
            tokens = full_cmd.split()
            cmd = tokens[0]
            args = tokens[1:]

        # Dispatch command if exists; otherwise try to run as a legacy command.
        if cmd.upper() in self.commands:
            try:
                self.commands[cmd.upper()](args)
            except Exception as e:
                print("Error executing command:", e)
        else:
            # If not a recognized command, try legacy execution.
            print("Command not recognized. Trying legacy mode...")
            try:
                os.system(user_input)
            except Exception as e:
                print("Legacy command error:", e)

    def run(self):
        """Main loop for the CMD Emulator."""
        # Initial welcome message
        print("Welcome to the Advanced CMD Emulator")
        print("For help, type HELP or _HELP")
        print("By Jared (C)03/2019 - Enhanced 2025")
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


if __name__ == '__main__':
    main()
