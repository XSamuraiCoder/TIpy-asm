font
====

.. py:module:: ti84.font

Draw text in FontLibC fonts on the CE. A font comes from a font pack AppVar, the
kind TIpy-asm's converter writes: a ``font`` :doc:`asset <../projects>`, or
``tipy-asm convfont`` (see :ref:`converting-fonts`).

.. code-block:: toml

   [[tool.tipy.assets]]
   source = "fonts/myfont.fnt"
   kind = "font"
   name = "MYFONT"

.. code-block:: python

   from ti84 import font, graphics

   f = font.load("MYFONT")
   if f:
       x = 10
       for code in range(65, 91):       # A to Z
           x += font.char(f, code, x, 20, graphics.BLUE)

TIpy also has a built-in 8-pixel font, the size of GraphX's default font.
:py:func:`default` returns it. It is built into the program, so it needs no AppVar:

.. code-block:: python

   from ti84 import font, graphics

   f = font.default()
   font.char(f, 65, 10, 10, graphics.BLACK)

:py:func:`load` returns a font, or 0 if the AppVar is missing or is not a font pack.
A pack can hold several fonts; ``font.load("MYFONT", 1)`` is the second, and
:py:func:`count` says how many there are.

:py:func:`char` draws a character's pixels and leaves the background, and returns
its width, so adding it up places the next character. :py:func:`height` is the
height of a line, including the font's space above and below.

FontLibC itself draws on GraphX's 8-bit screen, while TIpy programs use the
OS's 16-bit color screen, so this library reads the font packs and draws them
itself. For text in the OS font, use :py:func:`graphics.text()
<ti84.graphics.text>` or :py:func:`graphics.char() <ti84.graphics.char>`. On
classic calculators, only the color constants are available.

``examples/sax`` in the repository draws its chat in the fonts of a pack, and
switches between them.

Constants
---------

``font.BLACK``, ``font.WHITE``, ``font.RED``, ``font.GREEN``, ``font.BLUE``,
``font.YELLOW``, ``font.CYAN``, ``font.MAGENTA``, ``font.ORANGE``, ``font.PURPLE``,
and ``font.GRAY`` have the same values as the :doc:`color <color>` constants.

Methods
-------

.. tipy-methods:: font
