"""Catch falling blocks with the paddle. LEFT and RIGHT move; CLEAR quits.

Shows functions, multi-file projects, non-blocking keys, runtime drawing,
arrays, random numbers, and a high score saved in an AppVar.
"""
from ti84 import graphics, keyboard, random, storage

from settings import BLOCK, BLOCKS, FALL_SPEED, PADDLE_HEIGHT, PADDLE_SPEED, PADDLE_WIDTH

block_x = [0] * BLOCKS
block_y = [0] * BLOCKS


def reset_block(index):
    block_x[index] = random.randrange(graphics.width - BLOCK)
    block_y[index] = -random.randrange(graphics.height)


def move_paddle(x):
    moved = x + PADDLE_SPEED * (keyboard.is_down(keyboard.RIGHT) - keyboard.is_down(keyboard.LEFT))
    return max(0, min(moved, graphics.width - PADDLE_WIDTH))


def update_block(index, paddle_x, paddle_y):
    """Move one block; return 1 if it was caught."""
    graphics.fill_rect(block_x[index], block_y[index], BLOCK, BLOCK, graphics.WHITE)
    block_y[index] += FALL_SPEED
    x, y = block_x[index], block_y[index]
    caught = 0
    if y + BLOCK >= paddle_y and x + BLOCK > paddle_x and x < paddle_x + PADDLE_WIDTH:
        caught = 1
    if caught or y >= graphics.height:
        reset_block(index)
    else:
        graphics.fill_rect(x, y, BLOCK, BLOCK, graphics.RED)
    return caught


def main():
    storage.create("CATCHSAV", 1)
    best = storage.read_byte("CATCHSAV", 0)
    score = 0
    paddle_x = (graphics.width - PADDLE_WIDTH) // 2
    paddle_y = graphics.height - PADDLE_HEIGHT - 1
    graphics.begin()
    graphics.fill_screen(graphics.WHITE)
    for index in range(BLOCKS):
        reset_block(index)
    while not keyboard.is_down(keyboard.CLEAR):
        moved = move_paddle(paddle_x)
        if moved != paddle_x:
            graphics.fill_rect(paddle_x, paddle_y, PADDLE_WIDTH, PADDLE_HEIGHT, graphics.WHITE)
            paddle_x = moved
        graphics.fill_rect(paddle_x, paddle_y, PADDLE_WIDTH, PADDLE_HEIGHT, graphics.BLUE)
        for index in range(BLOCKS):
            score += update_block(index, paddle_x, paddle_y)
    if score > best:
        storage.write_byte("CATCHSAV", 0, min(score, 255))
    graphics.end()
    print("Score:", score)
    print("Best:", max(score, best))


main()
