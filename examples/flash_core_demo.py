"""AppVar files and integer core helpers for a TIpy CE Flash App."""

from ti84 import file, graphics, math, random

file.create("SAVE", 4)
if file.exists("SAVE") != 0:
    previous_score = file.read_u16("SAVE", 0)
    file.write_u16("SAVE", 0, previous_score + 1)

random.seed(file.read_byte("SAVE", 0))
roll = random.randrange(6) + 1
distance = math.abs(-12)
bounded = math.clamp(distance, 0, 10)
root = math.sqrt(81)

if roll > 0:
    print("Core libraries ready")
graphics.wait_key()

# file.delete("SAVE")  # optional: remove the save AppVar
