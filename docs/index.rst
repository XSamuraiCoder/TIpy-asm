TIpy-asm
========

TIpy-asm compiles a restricted, Python-like language into programs for TI
graphing calculators. It runs on your computer, and the calculator runs native
machine code. Python itself does not run on the calculator.

.. code-block:: python

   from ti84 import graphics, keyboard

   x = 0
   graphics.begin()
   while not keyboard.is_down(keyboard.CLEAR):
       graphics.fill_rect(x, 100, 10, 10, graphics.BLUE)
       x = (x + 1) % graphics.width
   graphics.end()

Targets
-------

.. list-table::
   :header-rows: 1
   :widths: 25 35 40

   * - Target
     - Calculators
     - Built with
   * - CE
     - TI-84 Plus CE
     - fasmg, included in the package
   * - Classic
     - TI-83 Plus and TI-84 Plus
     - SPASM-ng, which you install
   * - Flash App
     - TI-84 Plus CE
     - CEdev and an installer project, which you provide

.. toctree::
   :maxdepth: 2
   :caption: Guide

   getting-started
   language
   projects
   assembly
   flash-apps
   converting

.. toctree::
   :maxdepth: 2
   :caption: Library reference

   libraries/index
   libraries/graphics
   libraries/keyboard
   libraries/math
   libraries/random
   libraries/storage
   libraries/file
   libraries/sprite
   libraries/serial
   libraries/usb
   libraries/color
   libraries/font
   libraries/graph

.. toctree::
   :maxdepth: 1
   :caption: Reference

   cli
   compiler-reference
