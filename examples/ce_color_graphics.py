"""Color and filled-shape library demo for the TI-84 Plus CE."""

from ti84 import graphics, keyboard

graphics.clear()

# Pastel wallpaper bands similar to the atmOS desktop.
graphics.fill_rect(0, 0, 320, 15, graphics.PALE_YELLOW)
graphics.fill_rect(0, 15, 320, 15, graphics.PEACH)
graphics.fill_rect(0, 30, 320, 15, graphics.ORANGE)
graphics.fill_rect(0, 45, 320, 15, graphics.PEACH)
graphics.fill_rect(0, 60, 320, 15, graphics.PINK)
graphics.fill_rect(0, 75, 320, 15, graphics.PALE_PINK)
graphics.fill_rect(0, 90, 320, 15, graphics.PINK)
graphics.fill_rect(0, 105, 320, 15, graphics.PALE_PINK)
graphics.fill_rect(0, 120, 320, 15, graphics.PINK)
graphics.fill_rect(0, 135, 320, 15, graphics.PALE_PINK)
graphics.fill_rect(0, 150, 320, 15, graphics.PINK)
graphics.fill_rect(0, 165, 320, 15, graphics.PALE_PINK)
graphics.fill_rect(0, 180, 320, 15, graphics.PINK)
graphics.fill_rect(0, 195, 320, 15, graphics.PALE_MINT)

# Status strip and three simple colored dock icons.
graphics.fill_rect(0, 0, 320, 15, graphics.PALE_YELLOW)
graphics.fill_rect(0, 208, 320, 32, graphics.PALE_MINT)
graphics.fill_rect(130, 220, 16, 16, graphics.BLUE)
graphics.fill_rect(152, 220, 16, 16, graphics.ORANGE)
graphics.fill_rect(174, 220, 16, 16, graphics.GRAY)

# Filled pointer with a dark outline.
graphics.triangle(160, 120, 160, 137, 172, 132, graphics.BLACK)
graphics.triangle(162, 124, 162, 134, 169, 131, graphics.WHITE)

graphics.wait_key()
