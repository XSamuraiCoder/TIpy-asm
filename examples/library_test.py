from ti84 import graphics, keyboard, math, storage

# Persistent AppVar operations: create once, read the existing value, and
# toggle it so repeated launches exercise both the read and write paths.
storage.create("TPYTEST", 1)
launches = storage.read_byte("TPYTEST", 0)
if launches == 0:
    storage.write_byte("TPYTEST", 0, 1)
else:
    storage.write_byte("TPYTEST", 0, 0)

# Integer math feeds a normal Python conditional.
magnitude = math.abs(-24)

# CE graphics library calls use literal coordinates and RGB565 colors.
graphics.clear()
graphics.fill_rect(0, 0, 320, 24, graphics.BLUE)
graphics.rect(20, 36, 48, 28, graphics.BLACK)
graphics.line(80, 48, 112, 64, graphics.BLACK)
graphics.circle(160, 64, 12, graphics.RED)
graphics.triangle(224, 36, 208, 64, 240, 64, graphics.GREEN)
graphics.pixel(160, 128, graphics.WHITE)

if magnitude == 24:
    graphics.fill_rect(24, 190, 12, 12, graphics.ORANGE)
if launches == 0:
    graphics.fill_rect(48, 190, 12, 12, graphics.GREEN)
else:
    graphics.fill_rect(48, 190, 12, 12, graphics.RED)

# Exercise GetCSC input and key constants. Enter changes the center marker.
# Other keys, including Clear, leave the drawing intact.
key = keyboard.read()
if key == keyboard.ENTER:
    graphics.circle(160, 128, 6, graphics.YELLOW)

graphics.wait_key()
