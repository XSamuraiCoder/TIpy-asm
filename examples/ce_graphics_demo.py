"""GraphX-inspired drawing and offscreen-frame example for TIpy CE apps."""

from ti84 import graph, graphics

graph.begin()
graph.set_draw_buffer()
graphics.set_color(graphics.PALE_MINT)
graphics.fill_screen(graphics.PALE_MINT)

# Palette colors and shape primitives can be mixed in one frame.
graphics.set_color(graphics.PINK)
graphics.fill_rectangle(24, 30, 272, 150)
graphics.set_color(graphics.ORANGE)
graphics.horiz_line(24, 190, 272)
graphics.vert_line(160, 30, 160, graphics.WHITE)
graphics.fill_circle(160, 105, 38, graphics.BLUE)
graphics.triangle(160, 68, 145, 112, 175, 112, graphics.WHITE)
# Present the offscreen frame, then wait for a fresh key.
graph.swap_draw()
graph.set_draw_screen()
graphics.text("TIpy Graphics", 112, 205)
graph.end()
graphics.wait_key()
