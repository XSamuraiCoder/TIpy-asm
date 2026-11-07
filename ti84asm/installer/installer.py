"""TIpy-asm Flash App installer, compiled with the TIpy-asm CE target.

tipy-asm flash-app builds this, with install_config.py generated beside it. The logic
follows install() and check_variable_overlaps() in CE-Programming/app_tools'
installer (main.c), line for line; installlib.asm holds the flash routines.

Addresses are 24-bit integers. Flash addresses are below 0x400000, so they are
positive, and RAM addresses start at 0xD00000, so they read as negative.
"""
from ti84 import keyboard

from install_config import PREFIX, PREFIX_LENGTH, SPLIT_SIZE
from installlib import (app_installed, app_name, appvar_data, clear_home, copy_app_name, delete_app,
                        delete_appvar, delete_installer, find_last_app, fix_relocations, flash_erase,
                        flash_write, flash_write_size, installer_begin, installer_end, peek16, port_setup,
                        put_str, vat_data, vat_name_char, vat_name_length, vat_next, vat_start)

MAX_APPVARS = 99
SIZE_BYTES = 3
HEADER_NAME = 256 + 3

SUCCESS = 0
ALREADY_INSTALLED = 1
MISSING_VAR = 2
PORT_SETUP_FAILED = 3
NO_SPACE = 4

sizes = [0] * MAX_APPVARS
datas = [0] * MAX_APPVARS
offsets = [0] * MAX_APPVARS
found_name = 0


def appvar_name_char(index, position):
    """Character `position` of the AppVar name PREFIX followed by `index`, or 0 past its end."""
    if position < PREFIX_LENGTH:
        return PREFIX[position]
    position -= PREFIX_LENGTH
    if index >= 10:
        if position == 0:
            return 48 + index // 10
        position -= 1
    if position == 0:
        return 48 + index % 10
    return 0


def is_installer_appvar(index):
    """strncmp(vat_name, PREFIX + index, vat_name_length) == 0, as main.c compares them."""
    for position in range(vat_name_length()):
        mine = appvar_name_char(index, position)
        if vat_name_char(position) != mine:
            return 0
        if mine == 0:
            return 1
    return 1


def check_variable_overlaps(app_start):
    first_erased_page = (app_start >> 16) - 1
    entry = vat_start()
    while True:
        entry = vat_next(entry)
        if entry == 0:
            return 1
        data = vat_data()
        if data < 0:
            continue                    # in RAM
        page = data >> 16
        if page < first_erased_page:
            continue
        ours = 0
        for index in range(MAX_APPVARS):
            if is_installer_appvar(index):
                address = app_start + SPLIT_SIZE * index
                if page >= address >> 16:
                    return 0            # it would be erased before being copied
                ours = 1
                break
        if not ours:
            return 0                    # another variable is in the way


def install():
    global found_name
    if port_setup():
        return PORT_SETUP_FAILED
    app_size = 0
    last = 0
    while True:
        if last >= MAX_APPVARS:
            return MISSING_VAR
        data = appvar_data(last)
        if data == 0:
            return MISSING_VAR
        size = peek16(data)
        datas[last] = data + 2
        sizes[last] = size
        offsets[last] = app_size
        if last == 0:
            found_name = copy_app_name(datas[0] + HEADER_NAME)
            if app_installed(found_name):
                return ALREADY_INSTALLED
        app_size += size
        if size != SPLIT_SIZE:
            break
        last += 1

    # The app's size is stored at the end of the app in flash.
    sizes[last] += SIZE_BYTES
    app_end = find_last_app()
    app_start = app_end - app_size - SIZE_BYTES
    if not check_variable_overlaps(app_start):
        return NO_SPACE

    print("Installing:")
    put_str(found_name)
    print()
    print("Please wait...")
    print()
    print("This may take a while.")
    print("Do not reset!")

    written = app_end
    wrote_size = 0
    current = last
    page = app_end >> 16
    while page >= app_start >> 16 and current >= 0:
        page_start = page << 16
        while written > page_start and current >= 0:
            segment_start = app_start + offsets[current]
            destination_end = min(segment_start + sizes[current], (page + 1) << 16)
            destination_start = max(segment_start, page_start)
            source_start = datas[current] + (destination_start - segment_start)
            if not wrote_size:
                flash_write(source_start, destination_start, destination_end - destination_start - SIZE_BYTES)
                flash_write_size(destination_end - SIZE_BYTES, app_size)
                wrote_size = 1
            else:
                flash_write(source_start, destination_start, destination_end - destination_start)
            written = destination_start
            if destination_start == segment_start:
                current -= 1
        flash_erase(page - 1)
        page -= 1

    fix_relocations(app_start)
    return SUCCESS


def confirm():
    """ENTER means yes, CLEAR means no."""
    print("ENTER: Yes   CLEAR: No")
    while True:
        key = keyboard.read()
        if key == keyboard.ENTER:
            return 1
        if key == keyboard.CLEAR:
            return 0


def delete_installer_files():
    delete_installer()
    for index in range(MAX_APPVARS):
        if appvar_data(index) == 0:
            break
        delete_appvar(index)


def uninstall():
    """Offered when the app is already installed, so one program installs and removes it."""
    print("TIpy-asm installer")
    print()
    put_str(app_name())
    print(" is installed.")
    print("Delete it?")
    if not confirm():
        return
    clear_home()
    if delete_app(app_name()):
        put_str(app_name())
        print(" deleted.")
        print("Run again to reinstall.")
    else:
        print("Could not find the app.")
        print("Delete it from the")
        print("mem menu instead.")
    keyboard.read()


def main():
    clear_home()
    if app_installed(app_name()):
        uninstall()
        return
    print("TIpy-asm installer")
    print()
    error = install()
    clear_home()
    if error == SUCCESS:
        print("Successfully installed.")
        put_str(found_name)
        print()
        print()
        print("Delete installer files?")
        if confirm():
            delete_installer_files()
        return
    if error == ALREADY_INSTALLED:
        print("Already installed.")
        print("Run again to delete it.")
    elif error == MISSING_VAR:
        print("Install failed.")
        print("Missing an AppVar.")
    elif error == PORT_SETUP_FAILED:
        print("Install failed.")
        print("Unsupported OS version.")
    else:
        print("Install failed.")
        print("Out of archive space.")
        print("Try running the")
        print("GarbageCollect command.")
    keyboard.read()


# As CEdev's crt0 does around a C program's main(); see installer_begin.
installer_begin()
main()
installer_end()
