Projects
========

A project is a folder whose ``pyproject.toml`` has a ``[tool.tipy]`` table. It plays
the role of a CEdev makefile. With no source file given, commands use the project in
the current folder or the nearest parent folder that has one.

``tipy-asm new`` creates this layout:

.. code-block:: text

   mygame/
     pyproject.toml
     .gitignore
     src/
       main.py

Settings
--------

.. code-block:: toml

   [tool.tipy]
   name = "BOUNCE"
   description = "A bouncing ball"
   main = "src/main.py"
   target = "ce"
   bindir = "bin"
   keep_asm = false

.. list-table::
   :header-rows: 1
   :widths: 20 25 55

   * - Key
     - Default
     - Meaning
   * - ``name``
     - From ``[project]`` or the folder
     - Calculator program name: 1-8 letters or digits. A value you set here is used
       exactly, or rejected if invalid.
   * - ``description``
     - Empty
     - Free text.
   * - ``main``
     - ``src/main.py``
     - Entry source file.
   * - ``target``
     - ``ce``
     - ``ce``, ``classic``, or ``both``.
   * - ``bindir``
     - ``bin``
     - Output folder. ``tipy-asm clean`` deletes it.
   * - ``keep_asm``
     - ``false``
     - Also keep the generated assembly in ``bindir``.

Several source files
--------------------

Importing from a file next to the main file includes it in the program. Dotted names
reach into folders:

.. code-block:: python

   from settings import SPEED
   from game.player import move

Names you import must exist, and circular imports are reported. Plain ``import
settings`` is not supported.

Assets
------

Each ``[[tool.tipy.assets]]`` table converts one file for your program. Most become
an AppVar in ``bindir``. Every build converts the assets that are out of date, and
``--force`` converts them all.

.. code-block:: toml

   [[tool.tipy.assets]]
   source = "assets/hero.png"
   name = "HERO"

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Key
     - Meaning
   * - ``source``
     - Required. The input file.
   * - ``name``
     - AppVar name: 1-8 letters or digits, starting with a letter. The default comes
       from the file's name.
   * - ``kind``
     - ``sprite``, ``image``, ``font``, or ``binary``. The default depends on the
       file's suffix, and images default to ``sprite``.
   * - ``mode``
     - ``rgb565`` or ``palette``, for the ``image`` kind.
   * - ``storage``
     - For sprites: ``appvar`` (the default), ``program``, or ``pack``. See below.
   * - ``pack``
     - For ``storage = "pack"``: the shared AppVar's name. Setting it implies
       ``storage = "pack"``.
   * - ``module``
     - For ``program`` and ``pack``: the generated module, ``sprites`` by default.

Send each ``.8xv`` to the calculator along with the program.

Where PNG sprites go
~~~~~~~~~~~~~~~~~~~~

A sprite asset's ``storage`` chooses where its pixels end up. One project can use all
three; ``examples/coins`` in the repository does.

.. list-table::
   :header-rows: 1
   :widths: 15 15 70

   * - ``storage``
     - Targets
     - What you get
   * - ``appvar``
     - CE
     - Its own AppVar, named ``name``. Load it with
       ``sprite.load("HERO")`` and draw it with :doc:`the sprite library
       <libraries/sprite>`. Keeps the program small.
   * - ``program``
     - CE, classic
     - Built into the program as a pixel constant, drawn with
       :py:func:`graphics.sprite() <ti84.graphics.sprite>`. Nothing extra to send.
       On classic, colors become black and white.
   * - ``pack``
     - CE
     - Shares one AppVar, named ``pack``, with the other sprites of that pack, in the
       order they are listed. Load one with ``sprite.load("TILES", GRASS)``. One file
       to send for many sprites.

.. code-block:: toml

   [[tool.tipy.assets]]
   source = "assets/hero.png"
   name = "HERO"                # storage = "appvar" is the default

   [[tool.tipy.assets]]
   source = "assets/coin.png"
   name = "COIN"
   storage = "program"

   [[tool.tipy.assets]]
   source = "assets/grass.png"
   name = "GRASS"
   pack = "TILES"               # implies storage = "pack"

   [[tool.tipy.assets]]
   source = "assets/flower.png"
   name = "FLOWER"
   pack = "TILES"

For ``program`` and ``pack`` sprites, ``name`` names a constant, which can be longer
than 8 characters. ``build``, ``check``, ``compile``, and ``flash-app`` write
``sprites.py`` next to your main file before compiling. It holds each ``program``
sprite's pixels, and each ``pack`` sprite's index in its pack. Import from it:

.. code-block:: python

   from ti84 import graphics, sprite
   from sprites import COIN, FLOWER, GRASS

   hero = sprite.load("HERO")
   grass = sprite.load("TILES", GRASS)
   flower = sprite.load("TILES", FLOWER)
   sprite.draw(hero, 40, 30)
   sprite.draw(grass, 0, 16)
   graphics.sprite(COIN, 100, 50)

The generated module is rewritten whenever the images or settings change, so do not
edit it, and you can leave it out of version control. A file of that name that
tipy-asm did not write is never overwritten; the build stops with an error instead.

The other kinds are data for your program to read with
:doc:`the storage library <libraries/storage>`.

A ``font`` asset takes a ``.fnt`` or text-format ``.convfont`` file, or a list of them, and
writes a FONTPACK AppVar that :doc:`the font library <libraries/font>` draws. TTF and OTF
files need converting with a separate tool first. The pack's metadata comes from these
keys, as convfont's ``-N``, ``-A``, ``-C``, ``-D``, and ``-V`` options:

.. code-block:: toml

   [[tool.tipy.assets]]
   source = ["fonts/drsans-07-normal.convfont", "fonts/drsans-07-bold.convfont"]
   kind = "font"
   name = "SAXFONT"
   family = "DrSans"            # font.family() and font.family_codes() read this
   author = "Your name"
   version = "1.0"

``family`` defaults to the first file's name up to its size, such as ``drsans`` for
``drsans-07-normal.convfont``. ``copyright`` and ``description`` are the other keys.
Changing any of them in ``pyproject.toml`` rebuilds the pack.

Toolchain paths
---------------

Assembler paths are optional. Without them, CE builds use the bundled fasmg, and
classic builds search your ``PATH``. Relative paths start at the project folder.

.. code-block:: toml

   [tool.tipy.toolchain]
   ce_assembler = "tools/fasmg.exe"
   classic_assembler = "tools/spasm.exe"

Flash Apps
----------

``tipy-asm flash-app`` builds the app and an installer for it. Its settings live
under ``[tool.tipy.flash]``, and :doc:`flash-apps` describes each one, along with
installing and deleting apps.

.. code-block:: toml

   [tool.tipy.flash]
   optimize = "size"
