"""A minimal Flash App: clears the screen and says hello. Any key closes it."""
from ti84 import graphics

graphics.begin()
graphics.clear()
graphics.text("Hello world!", 0, 0, origin="center")
graphics.wait_key()
graphics.end()
