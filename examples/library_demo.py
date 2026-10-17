from ti84 import graphics, math, storage

storage.create("SAVE", 4)
storage.write_byte("SAVE", 0, 42)
saved = storage.read_byte("SAVE", 0)
distance = math.abs(-42)

count = 0
while count < 3:
    count += 1

print("LIBRARY DEMO")

# Draw a frame and cross using coordinates that fit both calculator screens.
graphics.clear()
graphics.line(10, 5, 85, 5)
graphics.line(85, 5, 85, 58)
graphics.line(85, 58, 10, 58)
graphics.line(10, 58, 10, 5)
graphics.line(10, 31, 85, 31)
graphics.line(48, 5, 48, 58)
graphics.wait_key()
