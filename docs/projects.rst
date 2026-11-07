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

Each ``[[tool.tipy.assets]]`` table converts one file into an AppVar in ``bindir``.
Every build converts the assets that are out of date, and ``--force`` converts them
all.

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

Send each ``.8xv`` to the calculator along with the program. A ``sprite`` asset is
drawn with :doc:`the sprite library <libraries/sprite>`:

.. code-block:: python

   from ti84 import sprite

   hero = sprite.load("HERO")
   sprite.draw(hero, 40, 30)

The other kinds are data for your program to read with
:doc:`the storage library <libraries/storage>`.

A ``font`` asset takes a ``.fnt`` or text-format ``.convfont`` file and writes a one-font
FONTPACK AppVar. TTF and OTF files need converting with a separate tool first. The
assembly targets cannot draw FontLibC fonts yet, so these AppVars are for other programs.

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

``tipy-asm flash-app`` reads these settings. ``project_dir`` must contain
``installer/makefile``. The other settings override the installer's own values.

.. code-block:: toml

   [tool.tipy.flash]
   project_dir = "flash"
   optimize = "speed"
   appvar_prefix = "PY"
   installer_name = "INSTALL"
   appvar_split_size = 65200

``optimize`` is ``speed`` or ``size``.
