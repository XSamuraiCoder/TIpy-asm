Converting CEdev and ICE projects
=================================

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
