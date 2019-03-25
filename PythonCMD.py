from subprocess import call
import os
print("""
This is a CMD EMULATOR\n    For best functionality use this on the Python Command Line
To change directory you will need to type CWD, then once prompted type the directory path. Use Forward Slashes
Default drive will be the one you launch the script in.
Some commands have benn adapted for easier use, but still give the same output.
For help type _HELP
Or my GitHub http://www.github.com/Jared-dareJ/
Example\n  CWD /Users/Jared/PycharmProjects
        By Jared (C)03/2019
""")


def cls():
    call('cls', shell=True)

def colour(colour):
    call('color ' + colour, shell=True)
    print("Colour Changed To:")
    return

def acontinue():
    print("Press Enter To Continue")
    input()

print("Press Enter To Continue")
input("")

cls()
print("For Help Type _HELP")
print("For normal CMD type LEGACY, Press Enter Then Type The Command")
print("All commands displayed are case sensitive")
acontinue()

#For best emulation quality when in the command line run autoexec
os.chdir('/users')
call('cls', shell=True)
print("CMD Emulator For Windows [Version 1]")
print("    (C) Jared 2019")

def CWD():
    print("Please type the full path of the directory:")
    ChDir = input(os.getcwd() + '> cd ')
    os.chdir(ChDir)

while 1:
    runCOM = input(os.getcwd() + '> ')
    if runCOM == 'CWD':
        CWD()
