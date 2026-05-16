# NSMB-Code-Reference
This is a fork of https://github.com/MammaMiaTeam/NSMB-Code-Reference, with modifications and additions for importing the headers' data into Ghidra.

## Instructions
These instructions are for Windows 11, but you may be able to get it to work on another OS. These instructions assume you know how to use a terminal and git.

### Part 1: Download and install things
- NDS-ROM-Exporter: https://github.com/SuuperW/NDS-ROM-Exporter
- Ghidra: https://github.com/NationalSecurityAgency/ghidra/releases
- NSMB-Code-Reference: This repo! Clone it.
- - The original NSMB-Code-Reference repo was designed to work with Nintendo's Nitro SDK. If you have that, follow the instructions [here](https://github.com/MammaMiaTeam/NSMB-Code-Template#preparing-the-template) except put the files in `nitro_include` insead of `include`. If you do not, copy the `fake_nitro` directory and rename the copy to `nitro_include`.
- Python: Make sure Python is installed.
- LLVM for ARM: https://github.com/ARM-software/LLVM-embedded-toolchain-for-Arm/releases
- - Download version 18.1.3. Choose the download for your operating system.
- - Extract the files into a directory with a short path (some paths will be very long, so extracting into a short path is necessary to prevent Windows from failing due to paths being too long).
- - Windows will create a folder and put the compressed folder inside that folder. Move the inner folder to the root of this repo and rename the folder to `LLVM-ET-Arm`. You should have a `LLVM-ET-Arm/bin`.
- - You may proceed to step 2 while waiting for this.

### Part 2: Set up Ghidra and a Python virtual environment
- Open a terminal in the directory with Ghidra (where file `ghidraRun` is).
- Create a Python virtual environment. `python -m venv venv`
- Activate the virtional environment. `.\venv\Scripts\activate.bat`
- Install clang 18, then libclang 18. (libclang must be installed after clang is installed) `pip install clang==18.1.8` `pip install libclang==18.1.1`
- Close the terminal.
- By default, Ghidra runs without Python enabled. Copy `ghidraWithPy.bat` from `ghidra_files` in this repo into the directory with Ghidra. This file will activate the virtual environment then start Ghidra with Python enabled.
- Run `ghidraWithPy.bat`
- - The first time you run it, you will be asked if you want to install PyGhidra. Type `y` then press enter.

### Part 3: Importing data into Ghidra
- Run `.\NDS-ROM-Exprter path/to/ROM`
- - If you have the bios files, but them in the same directory as the ROM or provide paths to them with `-bios7 path` and `-bios9 path`.
- - This will create a file `ghidraData.bin` in the working directory.
- Move `ghidraData.bin` to the `ghidra_files` directory of this repo (or to one named `files`).
- Create a new project in Ghidra
- - File -> New Project -> Non-shared project -> Next
- - Choose a directory to save the Ghidra project and give the project a name, then click Finish
- Open the Code Browser tool in Ghidra (click the green dragon icon)
- Open the Script Manager (Window -> Script Manager)
- Add the PyGhidra directory from NSMB-Code-Reference
- - Click the "Manage Script Directories" icon (looks like a menu icon) in the top-right of the Script Manager window.
- - Click the green plus icon and navigate to the directory
- - Close the Bundle Manager window
- - Click the "Refresh Script List" icon in the Script Manager window
- On the left side of the Script Manager window, scroll down to NDS-SRE and select it
- If you are using `fake_nitro`, run `fake_nitro_generator.py`. Select the folder where you cloned this repo to and wait a bit for it to finish.
- Run `main_script.py`, select the folder whre you cloned this repo to and wait a while for it to finish.
- - After this script finishes, Ghidra will automatically begin to analyze the program but only from the functions the script created. You'll want to use the menu option Analysis -> Auto Analyze to have it analyze the entire thing.
- - This will take a long time and Ghidra may be unresponsive during this time. (There will be a progress bar in the bottom right, which will reset about a thousand times during this process.)
