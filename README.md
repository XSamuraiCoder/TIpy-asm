# TIpy-asm

TIpy-asm is a Python-based fork of [Voblit/py2ez80](https://github.com/Voblit/py2ez80),
a compiler for writing TI calculator programs in a restricted, Python-like
language. It compiles source on a computer; Python itself does not run on the
calculator.

## Targets

- **Classic TI-83+/TI-84 Plus:** compile the supported Python subset to Z80
  assembly or build a `.8xp` program with SPASM-ng.
- **TI-84 Plus CE assembly:** compile to eZ80 assembly or build a `.8xp` program
  with fasmg.
- **TI-84 Plus CE Flash App:** translate the supported subset to C, then build
  and package it with CEdev and an installer project.

The language is not full CPython. Supported syntax and built-in libraries vary
by target: the assembly compiler supports a smaller subset than the Flash App
backend. Calculator APIs such as graphics, keyboard input, math, and persistent
storage are provided by `ti84libs` where implemented for that target.
The `ti84` package includes editor-only type stubs, so VS Code/Pylance can
complete imports such as `from ti84 import graphics, keyboard, math, storage,
file, random, graph`. The stubs describe calculator APIs; they do not provide
desktop Python runtime implementations. Library availability varies by target.
The standalone `compile` and `build` assembly backends currently provide
`graphics`, `keyboard`, `math`, and `storage`; `file`, `random`, and `graph`
are Flash App APIs. Using one of those Flash App APIs for assembly output gives
an error that points to the `flash-app` command.

## Install

Requires Python 3.10 or newer:

```powershell
python -m pip install .
```

The package installs the `tipy-asm` command and the shorter alias `ti84py`.
CE assembly builds use fasmg; the CLI can download fasmg and required include
files when they are unavailable locally. Classic builds require SPASM-ng; the
CLI can fetch its TI-83 Plus system include when it is missing. Explicit
`--name` values must be 1-8 ASCII letters or digits; source filenames are
normalized to a valid calculator program name automatically.
Flash App builds require CEdev and a project directory containing an installer
makefile.

## Usage

Compile to assembly without assembling:

```powershell
tipy-asm compile examples\library_test.py --target ce
```

Build a calculator program (`--target classic`, `ce`, or `both`):

```powershell
tipy-asm build examples\library_test.py --target ce --name LIBTEST
```

Convert a PNG or another Pillow-supported image into TIpy sprite source (install
the optional Pillow dependency with `python -m pip install 'tipy-asm[images]'`):

```powershell
tipy-asm convert-image assets\logo.png --fit ce --x 40 --y 30 -o logo_sprite.py
tipy-asm build logo_sprite.py --target ce --name LOGO
```

`graphics.sprite(pixel_rows, x, y)` draws an RGB565 sprite. Use `None` for
transparent pixels; `convert-image` preserves transparency and converts the
opaque pixels to RGB565. Sprite positions can be integer expressions or
variables, so a program can move the same sprite between frames. CE sprites
are stored as compact pixel data and drawn by a generated runtime loop. Both
assembly targets clip partially off-screen sprites; runtime-positioned sprites
must not exceed the target screen dimensions.

Build a CE Flash App and installer:

```powershell
tipy-asm flash-app examples\flash_libraries_demo.py --project-dir path\to\installer-project
```

Run `tipy-asm --help` or `tipy-asm <command> --help` to see all options.

Run the compiler regression suite from a source checkout:

```powershell
python -m unittest discover -s tests -v
```

## Repository layout

- `ti84asm/` contains the parser, code generators, command-line interface, and
  build drivers.
- `ti84libs/` contains calculator-specific built-in libraries.
- `examples/` contains source programs demonstrating the supported targets.
- `docs/` contains language and design reference material.

This fork retains the upstream [MIT license](LICENSE).
