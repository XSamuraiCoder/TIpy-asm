"""A ball bounces around the screen until you press CLEAR.

The ball is assets/ball.png, built into the program by pyproject.toml
(storage = "program"), so it needs no AppVar and works on CE and classic.
Every build writes src/sprites.py with BALL; on classic, its colors become
black and white.
"""
from ti84 import graphics, keyboard

from sprites import BALL

SIZE = 8


def main():
    x = 3
    y = 5
    dx = 1
    dy = 1
    bounces = 0
    graphics.begin()
    graphics.fill_screen(graphics.WHITE)
    while not keyboard.is_down(keyboard.CLEAR):
        graphics.sprite(BALL, x, y)
        graphics.delay(1500)
        graphics.fill_rect(x, y, SIZE, SIZE, graphics.WHITE)
        if x + dx < 0 or x + dx > graphics.width - SIZE:
            dx = -dx
            bounces += 1
        if y + dy < 0 or y + dy > graphics.height - SIZE:
            dy = -dy
            bounces += 1
        x += dx
        y += dy
    graphics.end()
    print("Bounces:", bounces)


main()
