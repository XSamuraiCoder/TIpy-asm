Assembly files
==============

Write a routine in assembly when you need speed or direct hardware access, then call
it from Python like any other function. This works on the CE and classic targets, but
not in Flash Apps.

A first routine
---------------

Put ``fastmath.asm`` next to your Python file:

.. code-block:: text

   ; tipy: def add3(a, b, c)
   add3:
       add hl,de
       add hl,bc
       ret

Then import it:

.. code-block:: python

   from fastmath import add3

   total = add3(1, 2, 3)

The ``; tipy: def`` line declares the routine and its parameters. Only declared
routines can be imported, and each needs a label with the same name.

Calling convention
------------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - What
     - Where
   * - First argument
     - ``HL``
   * - Second argument
     - ``DE``
   * - Third argument
     - ``BC``
   * - Result
     - ``HL``. A routine with nothing to return can leave anything there.

A routine can use every other register, but it must:

- preserve ``IY``, because the OS uses it for its flags;
- return with ``ret``, leaving the stack as it found it.

Integers are 24-bit on CE and 16-bit on classic, so the arguments fill the whole
register on each target. A routine takes at most three parameters. Calls accept
keyword arguments and ``as`` aliases, and ``from fastmath import *`` imports every
declared routine.

Finding the file
----------------

For ``from fastmath import add3``, the compiler looks next to the main file for, in
order:

#. ``fastmath.ce.asm`` or ``fastmath.classic.asm``, for the target being built
#. ``fastmath.ce.s`` or ``fastmath.classic.s``
#. ``fastmath.asm``
#. ``fastmath.s``

Dotted names reach into folders, so ``from lib.fastmath import add3`` reads
``lib/fastmath.asm``.

CE files are assembled by fasmg and classic files by SPASM-ng, and their syntax differs.
When it matters, write one file for each target. Simple instructions such as
``add hl,de`` mean the same on both, so one file can serve both targets.

Rules
-----

- Do not include ``ti83plus.inc`` or the CE include files. Every program already has
  them, so ``ti.`` names work on CE and ``bcall`` works on classic.
- Labels starting with ``_`` or ``var_``, and the labels ``start`` and
  ``program_exit``, belong to TIpy-asm. Use other names.
- Each file is included once, after the program's own code, however many files import
  from it.
- A routine and a Python function cannot share a name.

Editor support
--------------

Editors do not know about assembly modules. To stop them flagging the import, add a
stub, ``fastmath.pyi``, next to the file:

.. code-block:: text

   def add3(a: int, b: int, c: int) -> int: ...

To see the code the compiler generated around your routine, build with ``--keep-asm``.

Example
-------

``examples/asm_demo`` in the repository has one file shared by both targets,
``fastbits.asm``, and a screen routine written separately for each target, in
``screen.ce.asm`` and ``screen.classic.asm``. It also includes the editor stubs.
