"""Calls assembly routines from Python. Press any key to finish."""
from ti84 import graphics

from fastbits import popcount, sum3
from screen import screen_fill

graphics.begin()
screen_fill(graphics.BLUE)
graphics.wait_key()
graphics.end()

print("Bits in 1234:", popcount(1234))
print("1 + 2 + 3 =", sum3(1, 2, 3))
