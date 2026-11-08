"""Collect coins on a grassy field. The arrow keys move; CLEAR quits.

Uses the three ways to store a PNG sprite, chosen in pyproject.toml:

- The hero is its own AppVar (storage = "appvar"): sprite.load("HERO").
- Grass and flowers share the TILES AppVar (storage = "pack"): sprite.load("TILES", GRASS).
- The coin is built into the program (storage = "program"): graphics.sprite(COIN, x, y).

Every build writes src/sprites.py with COIN, GRASS, and FLOWER from the PNGs.
Send HERO.8xv and TILES.8xv to the calculator with COINS.8xp.
"""
from ti84 import graphics, keyboard, math, random, sprite

from sprites import COIN, FLOWER, GRASS

TILE = 16
COIN_SIZE = 12
COLS = graphics.width // TILE
ROWS = graphics.height // TILE
TOP = TILE          # the score bar is the top row of tiles
STEP = 2

coin = [0, 0]       # the coin's x and y


def draw_tile(col, row, grass, flower):
    tile = flower if (col * 7 + row * 3) % 5 == 0 else grass
    sprite.draw(tile, col * TILE, row * TILE)


def redraw_tiles(x, y, size, grass, flower):
    """Redraw the tiles under a square, erasing whatever was drawn there."""
    for row in range(y // TILE, (y + size - 1) // TILE + 1):
        for col in range(x // TILE, (x + size - 1) // TILE + 1):
            draw_tile(col, row, grass, flower)


def place_coin():
    # In the middle of a random tile below the score bar.
    coin[0] = random.randrange(COLS) * TILE + 2
    coin[1] = random.randint(1, ROWS - 1) * TILE + 2
    graphics.sprite(COIN, coin[0], coin[1])


def show_score(score):
    graphics.fill_rect(0, 0, graphics.width, TOP, graphics.WHITE)
    graphics.text("Coins:", 4, 2)
    graphics.text_int(score, 60, 2)


def main():
    hero = sprite.load("HERO")
    grass = sprite.load("TILES", GRASS)
    flower = sprite.load("TILES", FLOWER)
    if hero == 0 or grass == 0 or flower == 0:
        print("Send HERO.8xv and")
        print("TILES.8xv too")
        return
    size = sprite.width(hero)
    x = (graphics.width - size) // 2
    y = (graphics.height - size) // 2
    score = 0
    graphics.begin()
    for row in range(1, ROWS):
        for col in range(COLS):
            draw_tile(col, row, grass, flower)
    show_score(score)
    place_coin()
    sprite.draw(hero, x, y)
    while not keyboard.is_down(keyboard.CLEAR):
        dx = keyboard.is_down(keyboard.RIGHT) - keyboard.is_down(keyboard.LEFT)
        dy = keyboard.is_down(keyboard.DOWN) - keyboard.is_down(keyboard.UP)
        if dx or dy:
            redraw_tiles(x, y, size, grass, flower)
            x = math.clamp(x + dx * STEP, 0, graphics.width - size)
            y = math.clamp(y + dy * STEP, TOP, graphics.height - size)
            if math.abs(x + size // 2 - coin[0] - COIN_SIZE // 2) < 12 and \
                    math.abs(y + size // 2 - coin[1] - COIN_SIZE // 2) < 12:
                redraw_tiles(coin[0], coin[1], COIN_SIZE, grass, flower)
                score += 1
                show_score(score)
                place_coin()
            else:
                graphics.sprite(COIN, coin[0], coin[1])
            sprite.draw(hero, x, y)
            graphics.delay(2000)
    graphics.end()
    print("Coins:", score)


main()
