graphics
========

.. py:module:: ti84.graphics

Draw on the screen. The origin is the top-left corner: the CE screen is 320 by 240
pixels, and the classic screen is 96 by 64.

.. code-block:: python

   from ti84 import graphics

   graphics.begin()
   graphics.fill_screen(graphics.WHITE)
   graphics.fill_circle(160, 120, 30, graphics.RED)
   graphics.text("HELLO", 10, 10)
   graphics.wait_key()
   graphics.end()

Literal and runtime arguments
-----------------------------

Arguments can be variables or expressions. When every argument is a constant, the
compiler works out the drawing ahead of time. Otherwise it calls a routine at
runtime, which clips to the screen. This means off-screen values behave differently:

- With **runtime** values, whatever falls off the screen is clipped.
- With **literal** values, an off-screen pixel, line, outline, or circle is a compile
  error, because it is almost certainly a mistake.

Colors
------

On CE, colors are 16-bit RGB565 values. On classic, a color is 0 for white, and
anything else is black. The constants below work on both targets, and on classic each
becomes 0 for ``WHITE`` and 1 for anything else.

.. warning::

   The literal ``0`` is black on CE and white on classic. Use ``graphics.BLACK`` and
   ``graphics.WHITE`` in programs that build for both targets.

Without a color argument, shapes and text are black. Every shape also accepts
``color=`` as a keyword.

Text
----

:py:func:`text() <ti84.graphics.text>` takes pixel coordinates on every target,
including Flash Apps. With ``origin="center"``, the text is centered on the screen
using the font's real width and height, and ``x`` and ``y`` move it from the center:

.. code-block:: python

   from ti84 import graphics

   graphics.begin()
   graphics.clear()
   graphics.text("Hello world!", 0, 0, origin="center")
   graphics.wait_key()
   graphics.end()

On CE, :py:func:`clear() <ti84.graphics.clear>` clears the whole screen, status bar
included, and :py:func:`end() <ti84.graphics.end>` brings back the home screen and
its status bar.

Screen size
-----------

.. py:data:: width

   Screen width in pixels: 320 on CE, and 96 on classic.

.. py:data:: height

   Screen height in pixels: 240 on CE, and 64 on classic.

Methods
-------

.. tipy-methods:: graphics

Color constants
---------------

.. tipy-constants:: graphics
