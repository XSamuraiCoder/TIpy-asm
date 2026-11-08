"""Roll two dice. ENTER rolls, DEL clears the stats, CLEAR quits and shows them.

Shows random numbers, waiting for a key, and the file library: an AppVar of
16-bit counters that keeps how often each total came up, between runs.
"""
from ti84 import file, keyboard, random

# Word 0 counts every roll; words 2 to 12 count each total.
WORDS = 13


def roll():
    first = random.randint(1, 6)
    second = random.randint(1, 6)
    total = first + second
    print("Rolled", first, "+", second, "=", total)
    file.write_u16("DICESTAT", total * 2, file.read_u16("DICESTAT", total * 2) + 1)
    file.write_u16("DICESTAT", 0, file.read_u16("DICESTAT", 0) + 1)


def show_stats():
    print("Rolls:", file.read_u16("DICESTAT", 0))
    for total in range(2, WORDS):
        count = file.read_u16("DICESTAT", total * 2)
        if count:
            print(total, "came up", count)


def main():
    file.create("DICESTAT", WORDS * 2)
    # Seed with the number of rolls so far, so each run rolls differently.
    random.seed(file.read_u16("DICESTAT", 0))
    print("ENTER roll, DEL reset")
    while True:
        key = keyboard.read()
        if key == keyboard.CLEAR:
            break
        if key == keyboard.ENTER:
            roll()
        if key == keyboard.DEL:
            file.clear("DICESTAT")
            print("Stats cleared")
    show_stats()


main()
