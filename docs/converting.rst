Converting and decompiling
==========================

``tipy-asm convert-project`` turns a C or ICE project into a TIpy-asm project:

.. code-block:: console

   tipy-asm convert-project path/to/project -o converted
   tipy-asm build converted

The project type is detected from its source files, and ``--type cedev`` or
``--type ice`` overrides that. The command then compiles its own output for CE and
tells you whether that worked.

What it writes
--------------

- ``src/*.py``: one module for each source file. Constants from ``foo.h`` go at the
  top of ``foo.py``, and ``#include "foo.h"`` becomes ``from foo import *``.
- ``pyproject.toml``: named from the makefile's ``NAME`` when there is one, with
  images, fonts, and ``.bin`` files declared as :doc:`assets <projects>`.
- ``assets/``: copies of those files.
- ``CONVERSION_NOTES.md``: everything that needs your attention.

What converts
-------------

Functions, globals, ``if``, ``while``, ``do``, ``for``, ``break``, ``continue``,
``return``, ternaries, casts, ``#define`` constants, and global arrays all convert.
Common ``gfx_``, ``os_``, and ``kb_`` calls map to library methods.

The current ``gfx_SetColor()`` color is kept in a variable and passed to each drawing
call.

What does not
-------------

Pointers, structs, ``switch``, ``goto``, and calls with no TIpy equivalent are not
guessed at. Each becomes a visible comment and a line in the notes, so you can search
for what is left:

.. code-block:: python

   # TODO(convert): not converted (switch): switch (mode) {
   pass

Calls with no effect here, such as ``kb_Scan()``, are removed and noted. Function-like
macros are not expanded, and are listed in the notes.

Check the results
-----------------

- **Colors:** CEdev palette indices are not RGB565 colors, so a converted
  ``gfx_SetColor(5)`` draws a different color. Named colors such as ``gfx_red`` map
  correctly.
- **Loops:** a ``for`` loop that cannot become ``range()`` becomes a ``while`` loop.
  The notes flag any such loop that contains ``continue``, which would skip its step.
- **Integers:** assembly integers are 24-bit on CE, so ``long`` values may not fit.
- **Double buffering:** assembly targets draw directly to the screen, so
  ``gfx_SwapDraw()`` is removed and a program may flicker.


Axe programs
------------

``tipy-asm convert-project`` also converts Axe Parser source, from the tokenized ``.8xp`` you edit on the calculator or from a text file
with a ``.axe`` suffix. The result is a project for the classic target.

.. code-block:: console

   tipy-asm convert-project GAME.8xp -o game

The converter keeps Axe's own rules where Python's differ:

- **Math runs left to right.** Axe has no operator precedence, so ``1+2*3`` is 9. Every
  operation is parenthesized in Axe's order, so the result is the same.
- **Variables:** ``A``-``Z`` and ``θ`` become ``a``-``z`` and ``theta``. ``r1``-``r6`` carry
  the arguments of ``sub()``.
- **Routines:** ``Lbl X`` up to its ``Return`` becomes ``lbl_x()``, and ``sub(X,1,2)`` sets
  ``r1`` and ``r2`` and calls it.
- **Numbers:** ``ᴇ1F`` is hex, ``π101`` is binary, and ``'A'`` is a character code.

``If``, ``!If``, ``Else``, ``While``, ``Repeat``, ``For(``, ``getKey``, ``getKey(n)``,
``rand``, ``Disp``, ``Text(``, ``Pause``, ``ClrDraw``, ``Pxl-On(``, ``Pxl-Off(``,
``Line(``, ``Rect(``, and ``Circle(`` convert. ``Goto``, pointers and ``{}`` memory,
sprites, and the rest of Axe's library become ``TODO(convert)`` comments and lines in
``CONVERSION_NOTES.md``.

Decompiling a program
---------------------

``tipy-asm decompile`` turns a calculator file back into source you can read:

.. code-block:: console

   tipy-asm decompile GAME.8xp

- **TI-BASIC or Axe source** comes out as text, token by token, in ``GAME.txt``.
- **An assembly program** comes out twice:

  - as a disassembly in ``GAME.asm``: Z80 for the TI-83 Plus and 84 Plus, or eZ80 in ADL
    mode for the CE, with ``L_`` labels at jump and call targets and named OS routines,
    such as ``ti.PutS`` and ``bcall(_PutS)``;
  - as Python in ``GAME.py``, which the next section describes.
- **Anything else**, such as an AppVar, comes out as a hex dump.

``-o -`` prints the result instead of writing a file. A disassembler cannot tell code
from data, so a program's tables and strings come out as instructions too; the bytes
on each line show what is really there.

Assembly as Python
~~~~~~~~~~~~~~~~~~

Machine code has no variables, types, or loops, only registers, memory, and jumps, so
the Python keeps that shape while reading as code:

- **Only code.** The lifter follows the program from its start through jumps and calls,
  so data is not mistaken for instructions. The file says how many bytes were left out.
- **Functions.** Each call target is a function. One with no jumps inside is straight
  Python; one with jumps runs through a ``goto`` dispatcher, since Python has no goto.
- **Registers and memory.** ``a``, ``bc``, ``de``, ``hl``, ``ix``, ``iy``, and ``sp`` are
  variables, and the 8-bit halves are read and written inside their pairs. Memory is
  ``mem8[...]`` and ``memw[...]``, with 16-bit words on classic calculators and 24-bit
  words on the CE.
- **Conditions.** A compare followed by a jump becomes ``if a == 5:`` or ``if hl == 0:``.
  Flags are kept in ``zf``, ``cf``, ``sf``, and ``pvf`` only when something in between would
  change what they test.
- **OS calls.** These are named: ``ti.PutS()`` on the CE and ``bcall("PutS")`` on classic
  calculators. OS RAM addresses keep their include-file names.
- **Anything else.** An instruction the lifter does not model stays as ``asm("...")``.

The file is plain Python, with small stand-ins for memory and the OS at the end. It
shows what the program does; it is not a TIpy program, because TIpy's Python has no
registers or raw memory.
