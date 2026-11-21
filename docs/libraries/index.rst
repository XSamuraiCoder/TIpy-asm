Libraries
=========

Import libraries from the ``ti84`` package:

.. code-block:: python

   from ti84 import graphics, keyboard

The package includes type stubs, so VS Code and other editors can complete these
names. The stubs exist for editors only; the methods have no desktop implementation.

You can also list methods from the command line:

.. code-block:: console

   tipy-asm api graphics

Calling a method a target does not support is a compile error that says where it
is available. Nothing compiles to code that silently does nothing.

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Library
     - Provides
   * - :doc:`graphics`
     - Drawing shapes, text, and sprites
   * - :doc:`keyboard`
     - Reading keys
   * - :doc:`math`
     - Integer math
   * - :doc:`random`
     - Pseudo-random integers
   * - :doc:`storage`
     - AppVar bytes and 16-bit values; the same library as ``file``
   * - :doc:`file`
     - The same library as ``storage``
   * - :doc:`sprite`
     - Sprites stored in AppVars
   * - :doc:`color`
     - Color constants and conversions
   * - :doc:`font`
     - FontLibC fonts and font packs
   * - :doc:`graph`
     - Screen setup for Flash Apps

Method availability
-------------------

.. tipy-matrix::
