# TIpy-asm

TIpy-asm is a Python-based fork of [Voblit/py2ez80](https://github.com/Voblit/py2ez80),
a compiler for writing TI calculator programs in a restricted, Python-like
language. It compiles source on a computer; Python itself does not run on the
calculator.

## Quick start

Requires Python 3.10 or newer:

```powershell
python -m pip install .
tipy-asm new mygame
cd mygame
tipy-asm build
```

That creates a program you can move around with the arrow keys, and writes
`bin\MYGAME.8xp`. CE builds need nothing else and work offline: the package
includes fasmg for Windows and Linux (x64 and x86), plus its CE includes. On other
systems, put fasmg on PATH. Run `tipy-asm doctor` to see what is installed.

`examples\catch` is a complete small game. The package also installs the shorter
command alias `ti84py`.

## Targets

- **TI-84 Plus CE assembly:** eZ80 assembly, or a `.8xp` program built with the
  bundled fasmg.
- **Classic TI-83+/TI-84 Plus:** Z80 assembly, or a `.8xp` program built with
  SPASM-ng, which you install yourself.
- **TI-84 Plus CE Flash App:** translated to C, then built and packaged with
  CEdev and an installer project that you provide.

## Commands

| Command | What it does |
|---|---|
| `tipy-asm new FOLDER` | Create a project that builds straight away |
| `tipy-asm build [SOURCE]` | Build `.8xp` programs and assets. Add `--watch` to rebuild on save, or `--keep-asm` to keep the assembly |
| `tipy-asm check [SOURCE]` | Report errors on each target without writing files. `--target flash` checks the Flash App backend |
| `tipy-asm compile [SOURCE]` | Write assembly without assembling it |
| `tipy-asm flash-app [SOURCE]` | Build a CE Flash App and its installer |
| `tipy-asm api [LIBRARY]` | List library methods and the targets that support them |
| `tipy-asm doctor` | Show installed tools and the project's setup |
| `tipy-asm clean` | Delete the project's build folder |
| `tipy-asm convert-project PATH` | Convert a CEdev or ICE project into a TIpy-asm project |
| `tipy-asm convbin`, `convimg`, `convert-image` | Convert data and images by hand |
| `tipy-asm convfont` | Convert `.fnt` and text-format fonts, matching CEdev's `convfont` byte for byte |

With no source, commands use the project in the current folder or the nearest
parent folder. Errors are printed as `FILE:LINE: error: MESSAGE` with the source
line, in the original file, so editors can link to them.

## Projects

A project is configured under `[tool.tipy]` in its `pyproject.toml`:

```toml
[tool.tipy]
name = "BOUNCE"          # calculator program name, 1-8 letters or digits
main = "src/main.py"     # default
target = "ce"            # classic, ce, or both; default ce
bindir = "bin"           # default
keep_asm = false

[tool.tipy.toolchain]    # optional; the default is to search PATH
ce_assembler = "tools/fasmg.exe"
classic_assembler = "tools/spasm.exe"

[tool.tipy.flash]        # used by `tipy-asm flash-app`
project_dir = "flash"    # folder containing installer/makefile
optimize = "speed"       # or size

[[tool.tipy.assets]]     # converted into bindir by each build, when out of date
source = "assets/hero.png"
name = "HERO"            # AppVar name; the default comes from the file name
kind = "sprite"          # sprite, image, font, or binary; guessed from the suffix
```

`from settings import SPEED` includes `settings.py` from the main file's folder,
and `from game.player import move` includes `game/player.py`.

Image assets need Pillow: `python -m pip install "tipy-asm[images]"`. Send the
asset's `.8xv` to the calculator along with the program:

```python
from ti84 import sprite
hero = sprite.load("HERO")     # 0 if the AppVar is missing
sprite.draw(hero, x, y)
```

## Language on the assembly targets

The Flash App backend supports more of Python. The assembly targets support:

- Functions with parameters, defaults, keyword arguments, return values, and
  `global`. Recursion is rejected, because function variables are static.
- `if`/`elif`/`else`, `while`, `for ... in range()` with runtime bounds, `break`,
  `continue`, and `exit()`.
- `+ - * // % << >> & | ^ ~`, comparisons, `and`, `or`, `not`, and `a if c else b`.
  Integers are signed, 24-bit on CE and 16-bit on classic, and wrap on overflow.
  `x // 0` is 0 and `x % 0` is `x`, because a calculator program cannot raise.
- Module-level arrays: `TABLE = (1, 2, 3)` is read-only, and `scores = [0] * 10`
  is writable. Runtime indexes are not bounds-checked.
- `print()` of string literals and integers, and `abs`, `min`, and `max`.

Strings exist only as literals, and there are no floats, classes, or lists of
lists.

## Libraries

Import them with `from ti84 import graphics, keyboard`. Run `tipy-asm api NAME`
for each method's signature and targets. The `ti84` package also has stubs, so
VS Code/Pylance can complete these names.

| Library | Provides |
|---|---|
| `graphics` | Pixels, lines, rectangles, circles, triangles, text, and sprites. Coordinates and colors can be runtime values, and are clipped to the screen |
| `keyboard` | `read()` waits for a key, `get()` returns at once, `is_down(key)` tests a held key |
| `math` | `abs min max clamp sign sqrt pow sin cos`, all integer; `sin` and `cos` take degrees and scale by 256 |
| `random` | `seed randrange randint` |
| `storage`, `file` | AppVar bytes that persist between runs |
| `sprite` | AppVar sprites from project assets (CE only) |
| `color` | Color constants and conversions. On classic, colors are 0 (white) or 1 (black) |
| `graph` | The Flash App's graph screen (Flash App only) |

Not implemented: FontLibC fonts (`ti84.font` has only color constants, so use
`graphics.text()`), and scaled or rotated sprites. Calling these gives an error
rather than doing nothing. Text with runtime coordinates and `text_int()` need
the CE target. A failed `storage` read or write, such as a missing AppVar or a
bad offset, ends the program.

## Converting CEdev and ICE projects

```powershell
tipy-asm convert-project path\to\project -o converted
```

This writes a normal project, then compiles it and tells you whether it worked.
Code with no TIpy equivalent, such as pointers, structs, and `switch`, becomes a
`# TODO(convert)` comment and is listed in `CONVERSION_NOTES.md`. CEdev palette
indices are not RGB565 colors, so check the colors of a converted program.

## Tests

```powershell
python -m unittest discover -s tests
```

`tests/asm_sim.py` runs generated assembly on a model of both CPUs, with the OS
stubbed, and compares results with CPython. It is not an emulator, so test on
CEmu or a calculator as well.

## Documentation

The full guide and method reference live in `docs/`. To build them:

```powershell
python -m pip install -r docs/requirements.txt
python -m sphinx -W -b html docs docs/_build/html
```

Then open `docs/_build/html/index.html`. The method pages are generated from
`ti84libs/api.py`. `.github/workflows/docs.yml` checks the build on every push and
pull request, and publishes the site to GitHub Pages from `main`.
`.readthedocs.yaml` configures Read the Docs.

## Repository layout

- `ti84asm/` contains the compiler, runtime helpers, CLI, and build drivers.
- `ti84asm/toolchain/` contains the bundled [fasmg](https://flatassembler.net/) (see
  `fasmg-license.txt`) and CE includes from
  [CE-Programming/asm-docs](https://github.com/CE-Programming/asm-docs).
- `ti84libs/` contains the built-in libraries; `ti84libs/api.py` is the table of
  public methods.
- `ti84/` contains the editor stubs.
- `examples/` contains example projects.
- `docs/` contains design reference material.

This fork retains the upstream [MIT license](LICENSE).
