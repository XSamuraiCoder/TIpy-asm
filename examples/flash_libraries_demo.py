"""Small linked-Flash-App demo of graphics, keyboard, and persistent storage."""

from ti84 import graphics, keyboard, storage

storage.create("PYDEMO", 1)
value = storage.read_byte("PYDEMO", 0)

graphics.clear()
graphics.text("TIpy Flash App libraries", 20, 30)
graphics.text("Persistent byte value:", 20, 60)
if value == 0:
    graphics.text("ZERO", 20, 80)
if value != 0:
    graphics.text("NONZERO", 20, 80)
graphics.text("Press a key to toggle, Clear to exit", 20, 120)

key = keyboard.read()
if key != keyboard.CLEAR:
    if value == 0:
        value = 1
    else:
        value = 0
    storage.write_byte("PYDEMO", 0, value)
