Getting started
===============

Install
-------

TIpy-asm needs Python 3.10 or newer. From a checkout of the repository, run:

.. code-block:: console

   python -m pip install .

This installs the ``tipy-asm`` command and a shorter alias, ``ti84py``.

CE builds need nothing else and work offline, because the package includes
fasmg for Windows and Linux (x64 and x86) along with its CE includes. On other
systems, such as macOS, put fasmg on your ``PATH``.

Two targets and one converter need extra tools:

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - To use
     - You need
   * - The classic target
     - `SPASM-ng <https://github.com/alberthdev/spasm-ng>`_ on your ``PATH``
   * - Flash Apps
     - `CEdev <https://github.com/CE-Programming/toolchain>`_; the installer is built for you
   * - Image assets
     - Pillow: ``python -m pip install "tipy-asm[images]"``

Run ``tipy-asm doctor`` at any time to see what is installed.

Create a project
----------------

.. code-block:: console

   tipy-asm new mygame
   cd mygame
   tipy-asm build

This writes ``bin/MYGAME.8xp``. Send that file to your calculator, or load it in
the `CEmu <https://ce-programming.github.io/CEmu/>`_ emulator. The program draws a
square that you move with the arrow keys. Press :kbd:`Clear` to quit.

To run it on a TI-84 Plus CE, choose it from the :kbd:`prgm` menu. Depending on
your OS version, you may need a shell such as Cesium, or the arTIfiCE jailbreak,
to run assembly programs.

Edit ``src/main.py`` and build again. While you work, this rebuilds whenever you
save a file:

.. code-block:: console

   tipy-asm build --watch

Check your code
---------------

``tipy-asm check`` compiles for each target without writing any files. Errors
point at your own file and line, and suggest a fix where they can:

.. code-block:: text

   src/main.py:12: error: graphics has no method pixl(); did you mean graphics.pixel()? run 'tipy-asm api graphics' to list them
       graphics.pixl(x, y)

Examples
--------

Each folder in ``examples/`` in the repository is a project. Build one with:

.. code-block:: console

   tipy-asm build examples/catch --target ce

.. list-table::
   :header-rows: 1
   :widths: 15 20 65

   * - Example
     - Targets
     - Shows
   * - ``catch``
     - CE, classic
     - A small game: functions, several source files, arrays, random numbers, held
       keys, and a high score saved with :doc:`storage <libraries/storage>`.
   * - ``star``
     - CE, classic
     - A spinning star: :doc:`math <libraries/math>` ``sin`` and ``cos``, lines and
       circles, a color from :doc:`color <libraries/color>`, and held keys.
   * - ``dice``
     - CE, classic
     - Dice rolls: :doc:`random <libraries/random>`, ``keyboard.read()``, and 16-bit
       counters kept between runs with :doc:`file <libraries/file>`.
   * - ``walk``
     - CE
     - A sprite you move with the arrow keys: a PNG built into an AppVar by
       ``[[tool.tipy.assets]]``, drawn with :doc:`sprite <libraries/sprite>`. Needs
       Pillow to build.
   * - ``coins``
     - CE
     - A coin hunt that stores PNG sprites all three ways: in its own AppVar, in a
       shared pack, and built into the program. See :doc:`projects`.
   * - ``bounce``
     - CE, classic
     - A bouncing ball from a PNG built into the program, so it needs no AppVar.
   * - ``asm_demo``
     - CE, classic
     - Routines written in :doc:`assembly files <assembly>`.
   * - ``flash_app``
     - Flash App
     - Hello world as a :doc:`Flash App <flash-apps>`, with its installer.

Next, read about :doc:`the language <language>`, or browse
:doc:`the library methods <libraries/index>`.
