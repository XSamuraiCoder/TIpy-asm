"""Walk a sprite around the screen. The arrow keys move it; CLEAR quits.

Shows a sprite asset: [[tool.tipy.assets]] in pyproject.toml turns
assets/hero.png into the HERO AppVar, and the sprite library loads and draws it.
Send HERO.8xv to the calculator with WALK.8xp.
"""
from ti84 import graphics, keyboard, math, sprite

STEP = 2


def main():
    hero = sprite.load("HERO")
    if hero == 0:
        print("Send HERO.8xv too")
        return
    width = sprite.width(hero)
    height = sprite.height(hero)
    x = (graphics.width - width) // 2
    y = (graphics.height - height) // 2
    graphics.begin()
    graphics.fill_screen(graphics.WHITE)
    graphics.text("Arrows move, CLEAR quits", 0, 4, origin="center")
    sprite.draw(hero, x, y)
    while not keyboard.is_down(keyboard.CLEAR):
        dx = keyboard.is_down(keyboard.RIGHT) - keyboard.is_down(keyboard.LEFT)
        dy = keyboard.is_down(keyboard.DOWN) - keyboard.is_down(keyboard.UP)
        if dx or dy:
            graphics.fill_rect(x, y, width, height, graphics.WHITE)
            x = math.clamp(x + dx * STEP, 0, graphics.width - width)
            y = math.clamp(y + dy * STEP, 0, graphics.height - height)
            sprite.draw(hero, x, y)
            graphics.delay(2000)
    graphics.end()


main()
