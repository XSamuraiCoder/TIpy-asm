file
====

.. py:module:: ti84.file

AppVar access with extra helpers. This library has the same behavior and
:doc:`error handling <storage>` as ``storage`` on assembly targets, and adds
:py:func:`clear` and 16-bit values.

Unlike ``storage``, all of its methods also exist on the Flash App target, so use it
for code shared with a Flash App.

.. code-block:: python

   from ti84 import file

   file.create("SAVE", 4)
   file.write_u16("SAVE", 0, 1000)
   total = file.read_u16("SAVE", 0)

Values are stored low byte first. On classic, a value of 32768 or more reads back as a
negative number, because integers are signed 16-bit.

Methods
-------

.. tipy-methods:: file
