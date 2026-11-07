font
====

.. py:module:: ti84.font

FontLibC fonts are **not implemented**. This library only provides color constants, on
the assembly targets, and calling anything else is a compile error. Use
:py:func:`graphics.text() <ti84.graphics.text>` to draw text.

``tipy-asm convfont`` can still convert fonts into AppVars for use by other programs.

Constants
---------

``font.BLACK``, ``font.WHITE``, ``font.RED``, ``font.GREEN``, ``font.BLUE``,
``font.YELLOW``, ``font.CYAN``, ``font.MAGENTA``, ``font.ORANGE``, ``font.PURPLE``,
and ``font.GRAY`` have the same values as the :doc:`color <color>` constants.
