random
======

.. py:module:: ti84.random

Pseudo-random integers. The sequence is the same on every run unless you seed it, so
seed from something that varies, such as how long the player waits at a title screen:

.. code-block:: python

   from ti84 import keyboard, random

   ticks = 0
   while not keyboard.get():
       ticks += 1
   random.seed(ticks)

These numbers are not suitable for anything that must be unpredictable.

Methods
-------

.. tipy-methods:: random
