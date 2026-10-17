# TIpy-asm: Flash App backend upgrade

## What changed
* `ti84asm/cgen.py`: Python-subset -> C compiler used by `flash-app`. `flashapp.py` drives the CEdev build.
* `ti84asm/flash_ce.py`: Flash App library call table and native runtime. Runtime gained lists, strings, floor-div/mod, shifts, pow, print, sin/cos, get_pixel, and non-blocking keys.
* `ti84libs/keyboard.py`: full GetCSC key table (49 keys, `KEY_*` or bare names).
* `ti84libs/flash_ce.py`: compatibility exports for older imports; it shares the runtime in `ti84asm/flash_ce.py`.

## Language (Flash App target)
int / bool / str / list-of-int; `def` (annotations optional, recursion, defaults, kwargs, `global`);
`if/elif/else`, `while`, `for` over `range()`/list/str, `break`/`continue`, `a if c else b`;
`+ - * // % ** << >> & | ^ ~ and or not`, chained compares, `in`/`not in`; tuple assign/swap;
`[1,2,3]`, `[0]*n` (n constant), indexing/negative indexes, `len sum min max abs int bool ord`;
`print(..., sep=, end=)` (drawn on screen; waits for a key at exit).

Limits: 32-bit ints (wrap), no floats, no classes/lambdas/comprehensions/try/with, no string concatenation,
lists are fixed-size and hold ints. Each list literal is one static buffer (re-running it reuses the buffer).

See [compiler reference notes](docs/compiler-reference.md) for design comparisons
with CEdev, ICE, and Axe Parser.

For CE Flash Apps, `ti84py flash-app source.py --project-dir PROJECT` builds an
installer package. Add `--optimize speed` (default) or `--optimize size` to
choose the CE compiler optimization level.

For a regular CE assembly program (`.8xp`) that exercises the current
assembly-target libraries, build the demo with:

    python -m ti84asm build examples/library_test.py --target ce --name LIBTEST

It covers graphics, keyboard input, AppVar storage, and integer math. The
`file`, `random`, and `graph` APIs currently belong to the Flash App backend
and are not available to the ordinary assembly-program compiler.
