# Compiler design references

TIpy uses other calculator toolchains as references for behavior and generated
code quality. It does not copy their runtime libraries or source code.

## CEdev

CEdev is the native build toolchain for CE Flash Apps. TIpy uses its compiler,
linker, and Flash App packaging flow. Its GraphX API gives TIpy a useful target
for drawing behavior: select a draw target, render a frame, then publish it;
copy the displayed frame before a partial redraw. Its keypadc API scans once
and then lets programs inspect one or several held keys. Its fileioc API
documents AppVar handles, RAM/archive state, and persistent calculator data.
TIpy keeps its implementations embedded in each generated app, but should
match these observable conventions.

## ICE on the CE

ICE shows the value of a calculator-focused language with a quick compile path,
native assembly output, useful source diagnostics, and built-in access to CE
graphics. TIpy follows the native-code and domain-library approach, while
keeping Python syntax and the desktop CLI. ICE is archived, so it is a design
reference rather than a dependency.

## Axe Parser on the Plus

Axe demonstrates that common calculator operations should have direct, small
lowerings: drawing, input, loops, sprites, and calculator variables should not
need verbose user-side assembly. Its documentation also calls out code-size
and speed tradeoffs and fixed-width integer behavior. TIpy should preserve
clear Python semantics where possible, document architecture-specific integer
limits, and offer an explicit speed-versus-size choice rather than silently
changing source behavior.

## Changes taken from the comparison

* CE Flash App builds enable CEdev link-time optimization. TIpy defaults to
  `--optimize speed` (`-O2`) and also offers `--optimize size` (`-Oz`).
* The CE graph buffer expands its 8-bit pixels through a compile-time RGB565
  palette lookup table, avoiding per-pixel channel expansion arithmetic on
  every buffer copy.
* CE assembly `graphics.fill_rect()` emits one runtime row loop and bounded
  pixel chunks, so generated code size no longer grows with rectangle height.
* The CE runtime and call table have one implementation in
  `ti84asm/flash_ce.py`; `ti84libs/flash_ce.py` is only a compatibility shim.

TIpy's graph buffer is still a single software buffer with a 3-3-2 RGB palette.
`swap_draw()` copies it to the display; it does not provide GraphX's exact
buffer allocation, palette control, or display synchronization behavior.
Those remain compatibility and performance work, rather than claims of full
GraphX equivalence.

## References

* [CEdev toolchain](https://github.com/CE-Programming/toolchain)
* [GraphX buffer lifecycle](https://github.com/CE-Programming/toolchain/blob/master/src/graphx/graphx.h)
* [keypadc scan example](https://github.com/CE-Programming/toolchain/blob/master/examples/library_examples/keypadc/single_keys/src/main.c)
* [fileioc AppVar behavior](https://github.com/CE-Programming/toolchain/blob/master/docs/libraries/fileioc.rst)
* [ICE compiler](https://github.com/PeterTillema/ICE)
* [Axe Parser documentation](https://axe.eeems.ca/Documentation.pdf)
