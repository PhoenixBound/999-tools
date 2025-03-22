This repository contains Python scripts written by PhoenixBound to help with translating *999: Nine Hours, Nine Persons, Nine Doors* on the DS. You can run them on the command line. Below are some descriptions of them. (Sorry that they don't describe things very uniformly; the tools and descriptions were written one at a time.)

Whenever the instructions reference `py`, if you're not on Windows, replace that with the proper way to run Python for your computer (`py` or `python` on Windows, `python` or `python3` on other OSes, with all appropriate arguments passed to the Python interpreter).

The instructions are generally divided into "command-line usage instructions" and "code usage instructions." The former are for if you want to run the Python script directly in a terminal window. The latter are for if you're writing a Python program (e.g. a build system for your hack, or a GUI tool where you can click buttons to convert back and forth between the two platforms).

# bg_files.py

For editing CGs and escape room backgrounds, mainly. Maybe other images too. I don't really know, I haven't checked.

Setup instructions:

* This script uses the `pillow` library to read images. Due to the nature of Python, you may want to [create a "venv"](<https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/#create-and-use-virtual-environments>) and run all of the commands out of that: `py -m venv .venv`
* `py -m pip install --upgrade pip` to make sure pip is working and up to date
* `pip install pillow`

Command line usage instructions (after activating the venv (if any) and installing the image library):

* Get the image out of the dat: `py bg_files.py dump-img <path-to-bg.dat> <output-path.png>`
* Put the image and its palette back into the dat: `py bg_files.py insert-img <path-to-original-bg.dat> <edited.png> <output.dat> [--no-compress]`

There's no real reason to use the `--no-compress` option, as far as I know, but it's convenient to me to be able to look at the uncompressed files to see what's going on when something goes wrong. There are also `decompress` and `compress` commands that may be useful for debugging.

Code usage instructions:

* The `dump_image` function takes a `bytes` object representing a .dat file, and returns a PIL Image
* The `replace_image` function takes a `bytes` object representing a .dat file and a PIL image, and returns the data for a new .dat file that has the palette and graphics of the provided PIL image.

# camera_rooms.py

For editing the "top view"/"bird's-eye view" data in escape rooms, which includes the name of the specific room you're in. The tool converts etc/camera.dat back and forth between .dat and .json

Command line usage instructions:

* To convert to an easily translatable format: `py camera_rooms.py dump <camera-dat-path.dat> <output-path.json> [--ptbr]`
* To convert back into the game format: `py camera_rooms.py make <edited-camera.json> <output-path.dat> [--ptbr]`

`<>`s means an argument is required, `[]`s means the argument is optional.

`--ptbr` will make strings meant for display in-game use the Latin-1 encoding, instead of mskanji/codepage 932.

Code usage instructions:

* `dump` takes the bytes of the file and returns a `list` of dicts. * `make_sir0_from_obj_list` takes a list of objects and returns the bytes of the camera.dat file.

# room_data.py

For editing the options in the "Memories of the escape" menu, which lets you replay old escape rooms.

Command line usage instructions:

* Dump from game format to JSON: `py room_data.py dump <room.dat> <output.json> [--ptbr]`
* Convert back from JSON into game format: `py room_data.py make <edited.json> <output.dat> [--ptbr]`

Code usage instructions:

* `import room_data`
* `room_data.dump(room_dat, display_encoding)` -- used to turn `room_dat` (bytes-like object containing the data from room.dat) into a list of dicts. If in doubt, set `display_encoding` to `'mskanji'`.
* `room_data.make_sir0_from_obj_list(thing, display_encoding)` -- used to turn `thing`, a list of dicts, back into a bytes object representing room.dat. If in doubt, set `display_encoding` to `'mskanji'`.

Note that the English game's text includes things like `captainＳs quarters` that can't be represented purely in Latin-1. You should *probably* be able to replace the Ｓ with a normal apostrophe. It feels kinda silly that 999 uses these full-width characters everywhere for basic things like quotation marks and apostrophes...

# staff_roll.py

For editing the credits, for each of the three types of endings that have credits.

Usage instructions:

* `py staff_roll.py dump <staff.dat> <output.json> [--latin1]`
* `py staff_roll.py make <edited.json> <output.dat> [--latin1]`

Code usage instructions:

* `dump(staff_dat, display_encoding=None)` -- used to turn `staff_dat` (bytes-like object containing the data from staff.dat) into a `dict` mapping ending IDs to lists of names/commands.
* `make_sir0_from_dict(thing, display_encoding)` -- used to turn `thing` (a `dict`) into the bytes for a staff.dat file. If in doubt, set `display_encoding` to `'mskanji'`.)