math
====

.. py:module:: ti84.math

Integer math. There are no floats, so :py:func:`sin` and :py:func:`cos` return values
scaled by 256. Multiply first, then divide:

.. code-block:: python

   from ti84 import math

   x = center + radius * math.cos(angle) // 256
   y = center + radius * math.sin(angle) // 256

On classic, integers are 16-bit, so ``radius * math.cos(angle)`` overflows once
``radius`` passes 127.

``abs()``, ``min()``, and ``max()`` are also built in, and need no import on assembly
targets.

Methods
-------

.. tipy-methods:: math
