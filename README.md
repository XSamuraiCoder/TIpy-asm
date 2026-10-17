# py2ez80

This is a Python-based fork of [Voblit/py2ez80](https://github.com/Voblit/py2ez80),
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

## Install

Requires Python 3.10 or newer:

```powershell
python -m pip install .
```

The package installs `py2ez80` and the compatibility command `ti84py`.
CE assembly builds use fasmg; the CLI can download fasmg and required include
files when they are unavailable locally. Classic builds require SPASM-ng.
Flash App builds require CEdev and a project directory containing an installer
makefile.

## Usage

Compile to assembly without assembling:

```powershell
py2ez80 compile examples\library_test.py --target ce
```

Build a calculator program (`--target classic`, `ce`, or `both`):

```powershell
py2ez80 build examples\library_test.py --target ce --name LIBTEST
```

Build a CE Flash App and installer:

```powershell
py2ez80 flash-app examples\flash_libraries_demo.py --project-dir path\to\installer-project
```

Run `py2ez80 --help` or `py2ez80 <command> --help` to see all options.

## Repository layout

- `ti84asm/` contains the parser, code generators, command-line interface, and
  build drivers.
- `ti84libs/` contains calculator-specific built-in libraries.
- `examples/` contains source programs demonstrating the supported targets.
- `docs/` contains language and design reference material.

This fork retains the upstream [MIT license](LICENSE).
