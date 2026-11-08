serial
======

.. py:module:: ti84.serial

Send and receive bytes. On CE this is USB serial, through CEdev's ``srldrvce``
library:

- **Computer:** plugged into a computer, the calculator appears as a serial port.
- **Arduino or another CE:** with an OTG cable, the calculator is the host for an
  Arduino or other USB serial adapter, or for another CE.

On classic calculators, it uses the link port, with the OS's own byte routines.

.. code-block:: python

   from ti84 import keyboard, serial

   serial.begin(9600)
   while not keyboard.is_down(keyboard.CLEAR):
       if serial.connected():
           byte = serial.read_byte()
           if byte >= 0:
               serial.write_byte(byte)
   serial.end()

``examples/echo`` in the repository is this program.

CE requirements
---------------

CE programs that use serial need LibLoad and the CE C libraries (``USBDRVCE`` and
``SRLDRVCE``) on the calculator, from https://tiny.cc/clibs. The program loads them
when it starts, and shows which one is missing if it cannot.

Call :py:func:`connected` or :py:func:`read_byte` often. They handle USB events,
including opening the port when a device is plugged in. The USB driver is
stopped when the program exits, even without :py:func:`end`.

Classic link port
-----------------

:py:func:`read_byte` returns -1 at once when nothing is being sent. A byte that
cannot be sent, such as with no calculator on the other end, makes
:py:func:`write_byte` return False instead of showing ERR:LINK. The link port
cannot tell whether a cable is in, so :py:func:`connected` is always True.

Methods
-------

.. tipy-methods:: serial
