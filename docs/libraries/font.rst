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

Drawing text
------------

:py:func:`text` draws a whole string and returns the x after it, and
:py:func:`text_width` measures one. :py:func:`paragraph` word-wraps text to a width,
breaks at newlines, and returns the y below the last line. Each takes a string
literal, or the address of text, such as a pack's :py:func:`family` name. With a
``background`` color, each character's box is filled first; the default of -1
leaves what is behind.

.. code-block:: python

   from ti84 import font, graphics

   f = font.default()
   x = font.text(f, "Score: ", 4, 4, graphics.BLACK, graphics.WHITE)
   y = font.paragraph(f, "A long line wraps at the last space that fits.", 4, 20, 120)

Font packs on the calculator
----------------------------

:py:func:`find` walks the calculator's AppVars and returns the n-th font pack,
whatever its name, so a program can offer every font the user has sent:

.. code-block:: python

   from ti84 import font, graphics

   n = 0
   pack = font.find(0)
   while pack:
       name = font.family(pack)
       if name:
           font.text(font.load(pack), name, 4, 4 + n * 12, graphics.BLACK)
       n += 1
       pack = font.find(n)

:py:func:`load`, :py:func:`count`, and :py:func:`by_style` take a pack from
:py:func:`find`, or a pack's AppVar name as a string literal.

Choosing a font by style
------------------------

:py:func:`by_style` works like FontLibC's ``fontlib_GetFontByStyle``: it returns the
first font in a pack whose height, weight, and styles match, or 0.

.. code-block:: python

   from ti84 import font

   f = font.by_style("MYFONT", 6, 12, font.NORMAL, font.BOLD, 0, font.ITALIC)

Weights run from ``font.THIN`` through ``LIGHT``, ``NORMAL``, ``MEDIUM``, and ``BOLD`` to
``font.HEAVY`` (FontLibC's ``FONTLIB_BLACK``, renamed so it cannot be mistaken for
the color). Styles are ``font.SERIF``, ``ITALIC``, ``OBLIQUE``, and ``MONOSPACED``:
``styles_set`` lists styles the font must have, and ``styles_unset`` styles it must
not.

FontLibC itself draws on GraphX's 8-bit screen, while TIpy programs use the
OS's 16-bit color screen, so this library reads the font packs and draws them
itself. For text in the OS font, use :py:func:`graphics.text()
<ti84.graphics.text>` or :py:func:`graphics.char() <ti84.graphics.char>`. On
classic calculators, only the color constants are available.

Constants
---------

``font.BLACK``, ``font.WHITE``, ``font.RED``, ``font.GREEN``, ``font.BLUE``,
``font.YELLOW``, ``font.CYAN``, ``font.MAGENTA``, ``font.ORANGE``, ``font.PURPLE``,
and ``font.GRAY`` have the same values as the :doc:`color <color>` constants.

Methods
-------

.. tipy-methods:: font
