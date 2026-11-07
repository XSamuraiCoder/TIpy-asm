The language
============

Source files are valid Python syntax, so editors can check and complete them.
Only part of Python is available. This page describes the CE and classic assembly
targets. The Flash App target translates to C and supports more, including
recursion, strings as values, and lists created at runtime.

Integers
--------

Every value is a signed integer: 24-bit on CE, and 16-bit on classic. Arithmetic
wraps on overflow instead of growing as it does in Python.

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Operators
     - Notes
   * - ``+ - *``
     - Wrap at the target's width.
   * - ``// %``
     - Round down, as in Python. ``x // 0`` is 0 and ``x % 0`` is ``x``, because a
       calculator program cannot raise an exception. A literal zero divisor is a
       compile error.
   * - ``& | ^ ~ << >>``
     - ``>>`` keeps the sign.
   * - ``== != < <= > >=``
     - Signed. Chains such as ``0 <= x < 10`` need plain names or constants.
   * - ``and or not``
     - Follow Python, so ``a or b`` gives ``a`` or ``b``, not ``True`` or ``False``.
   * - ``a if condition else b``
     - Evaluates only the chosen value.

``True`` and ``False`` are 1 and 0, and any nonzero value counts as true.

Literals above the signed range keep their bit pattern, which is useful for masks:
on classic, ``0xFFFF`` is the same value as ``-1``.

Control flow
------------

``if``/``elif``/``else``, ``while``, ``break``, ``continue``, and ``pass`` work as
in Python. ``exit()`` ends the program from anywhere.

``for`` loops use ``range()`` with one to three arguments. The bounds can be runtime
values and are evaluated once, before the first iteration. The step must be a
constant, so the compiler knows the loop's direction.

.. code-block:: python

   for i in range(count):
       total += i

Functions
---------

Functions support parameters, default values, keyword arguments, and return
values. A function can be called before the line that defines it. A function with
no ``return`` gives 0.

.. code-block:: python

   def add(a, b=10):
       return a + b

   total = add(1) + add(1, 2) + add(b=3, a=4)

Assigning to a name makes it local to the function, as in Python. Use ``global`` to
change a module variable:

.. code-block:: python

   score = 0

   def award(points):
       global score
       score += points

**Recursion is not supported** on assembly targets, because each function's
variables live at fixed addresses. The compiler rejects it and names the cycle.
Use a loop, or the Flash App target.

Functions must be defined at module level, and ``*args`` and ``**kwargs`` are not
available.

Arrays
------

Arrays are declared at module level and hold integer constants. A tuple is
read-only, and a list can be changed:

.. code-block:: python

   SPEEDS = (1, 2, 4, 8)
   scores = [0] * 10

   scores[0] = SPEEDS[level]
   scores[0] += 1

The size in ``[value] * size`` can be a literal, or a module-level name assigned
exactly once. Constant indexes are checked at compile time and can be negative.

.. warning::

   Runtime indexes are not checked. Reading or writing past the end of an array
   uses whatever memory is there.

Assignment
----------

Chained assignment (``a = b = 0``), unpacking (``x, y = y, x``), augmented
assignment (``x += 1``), and annotations (``x: int = 0``) all work.

Printing
--------

``print()`` writes string literals and integers to the home screen, separated by
spaces and followed by a new line:

.. code-block:: python

   print("Score:", score)

Built-in functions
------------------

``print``, ``exit``, ``range``, ``abs``, ``min``, and ``max`` need no import.
``min`` and ``max`` take two or more values.

Assembly
--------

Routines written in assembly can be imported and called like functions. See
:doc:`assembly`.

Not supported
-------------

These are compile errors on assembly targets: floats, classes, strings stored in
variables, dictionaries, sets, f-strings, comprehensions, lambda functions,
generators, ``try``, and ``with``. Strings exist only as literals passed to calls
such as ``print()`` and :py:func:`graphics.text() <ti84.graphics.text>`.
