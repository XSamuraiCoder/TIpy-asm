storage
=======

.. py:module:: ti84.storage

Save bytes in AppVars, which stay on the calculator between runs.

.. code-block:: python

   from ti84 import storage

   storage.create("SCORES", 1)
   best = storage.read_byte("SCORES", 0)
   if score > best:
       storage.write_byte("SCORES", 0, min(score, 255))

AppVar names must be string literals: 1-8 letters or digits, starting with a letter.
They are converted to upper case.

Errors
------

.. warning::

   On assembly targets, ``read_byte()`` and ``write_byte()`` **end the program** if the
   AppVar is missing or the offset is out of range. ``write_byte()`` also does so if the
   AppVar is archived. Call :py:func:`create` first.

Archived AppVars can be read on CE, but not on classic. They cannot be written on
either target.

Methods
-------

.. tipy-methods:: storage
