keyboard
========

.. py:module:: ti84.keyboard

Read the calculator's keys.

Choosing a method
-----------------

- :py:func:`read` waits for a key, which suits menus and prompts.
- :py:func:`get` returns at once, which suits a loop that keeps running without
  input.
- :py:func:`is_down` tests a held key, and several keys can be held together, which
  suits games.

.. code-block:: python

   from ti84 import keyboard

   while not keyboard.is_down(keyboard.CLEAR):
       x += keyboard.is_down(keyboard.RIGHT) - keyboard.is_down(keyboard.LEFT)

Methods
-------

.. tipy-methods:: keyboard

Key constants
-------------

Names also work in lower case and with a ``KEY_`` prefix, so ``keyboard.enter`` and
``keyboard.KEY_ENTER`` both mean ``keyboard.ENTER``. Digit keys need the prefix, as in
``keyboard.KEY_5``.

.. tipy-constants:: keyboard
