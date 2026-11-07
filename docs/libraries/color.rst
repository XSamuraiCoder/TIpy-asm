color
=====

.. py:module:: ti84.color

Color constants and conversions for the assembly targets. This library is not
available in Flash Apps, which use the constants in
:doc:`graphics <graphics>`.

Calls with constant arguments are worked out at compile time, so they add no conversion
code to your program:

.. code-block:: python

   from ti84 import color, graphics

   TEAL = color.from_rgb(0, 128, 128)
   graphics.fill_rect(0, 0, 50, 50, TEAL)

Classic colors
--------------

The classic screen has no color, so values are 0 for white and 1 for black.
:py:func:`from_rgb` picks whichever is closer in brightness, and every constant except
``WHITE`` becomes 1.

Compile-time and runtime results
--------------------------------

:py:func:`to_grayscale` and :py:func:`to_mono` round slightly differently at compile
time and at runtime, so a color near a threshold can differ by a small amount.
:py:func:`blend` works only at compile time, and its arguments must be constants.

Methods
-------

.. tipy-methods:: color

Constants
---------

.. tipy-constants:: color
