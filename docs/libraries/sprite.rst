sprite
======

.. py:module:: ti84.sprite

Draw sprites stored in AppVars, separately from your program. This keeps large images
out of the program and works on archived AppVars. This library needs the CE target and
is not available in Flash Apps.

For sprites written into your source, on either assembly target, use
:py:func:`graphics.sprite() <ti84.graphics.sprite>`.

Build a sprite
--------------

Declare the image as an :doc:`asset <../projects>`. Every build then writes
``bin/HERO.8xv``, which you send to the calculator with the program:

.. code-block:: toml

   [[tool.tipy.assets]]
   source = "assets/hero.png"
   name = "HERO"

Draw it
-------

.. code-block:: python

   from ti84 import sprite

   hero = sprite.load("HERO")
   if hero == 0:
       print("Send HERO.8xv first")
       exit()
   sprite.draw(hero, x, y)

:py:func:`load` returns the sprite's address as an integer, or 0 if the AppVar is
missing. Drawing a missing sprite does nothing.

Transparent pixels in the image stay transparent. Color 0 means transparent, so the
converter stores opaque black as the nearest visible color.

Not implemented
---------------

Scaled and rotated drawing and per-pixel access are not implemented. Calling them is a
compile error.

Methods
-------

.. tipy-methods:: sprite
