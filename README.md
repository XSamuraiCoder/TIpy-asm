# TI84py

TI84py is a command-line compiler for a Python-like language targeting TI-83+
and TI-84 Plus calculators. It compiles source to Z80 assembly for classic
models and eZ80 assembly or Flash Apps for the TI-84 Plus CE. The `ti84libs`
package provides the calculator libraries available to programs compiled by
the compiler.

## Install

```powershell
python -m pip install .
```

This installs the `ti84py` command. CE assembly builds use `fasmg`; classic
assembly builds use SPASM-ng. The Flash App target uses CEdev. Pass an
assembler path with `--ce-assembler` or `--classic-assembler` when it is not on
`PATH`.

## Commands

Compile Python-like source to assembly:

```powershell
ti84py compile examples\library_test.py --target ce
```

Build a calculator program:

```powershell
ti84py build examples\library_test.py --target ce --name LIBTEST
```

Build a CE Flash App and installer using a CEdev project template:

```powershell
ti84py flash-app examples\flash_libraries_demo.py --project-dir path\to\project
```

Run `ti84py --help` or `ti84py <command> --help` for options.

## Repository layout

- `ti84asm/` contains the compiler, code generators, CLI, and build drivers.
- `ti84libs/` contains built-in calculator libraries.
- `examples/` contains Python-like programs demonstrating compiler features.
- `docs/` contains language and compiler reference material.
