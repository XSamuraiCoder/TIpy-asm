serial
======

.. py:module:: ti84.serial

Send and receive bytes.

- **CE:** plugged into a computer, the calculator is a USB serial port. TIpy drives
  the USB controller itself, so a program needs nothing else on the calculator: no
  LibLoad and no CE C libraries.
- **Classic:** bytes go over the link port, to another calculator, using the OS's
  own byte routines.

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

USB serial on the CE
--------------------

The calculator presents a standard CDC-ACM serial port with the USB ID 16C0:05E1,
the same as CEdev's ``srldrvce``. Windows, Linux, macOS, and Chrome's Web Serial use
it without installing anything. The computer sets the baud rate, so
:py:func:`begin`'s argument does not matter on the CE.

- **Events:** :py:func:`connected`, :py:func:`read_byte`, and the write methods
  handle USB events, so call one of them often. :py:func:`connected` is True once
  the computer has set the port up.
- **Receiving:** bytes arrive in a 256-byte buffer. While it is full, the computer
  waits.
- **Sending:** data goes out in packets of up to 63 bytes. A write gives up if the
  computer stops reading.
- **Plugging in:** when the program starts, the calculator disconnects for a
  moment, so the computer forgets the OS's own USB device and finds the serial
  port. When the program exits, USB goes back to the OS.

The calculator cannot be the USB host yet, so it cannot talk to an Arduino or
another calculator over an OTG cable.

Classic link port
-----------------

:py:func:`read_byte` returns -1 at once when nothing is being sent. A byte that
cannot be sent, such as with no calculator on the other end, makes
:py:func:`write_byte` return False instead of showing ERR:LINK. The link port
cannot tell whether a cable is in, so :py:func:`connected` is always True.

Methods
-------

.. tipy-methods:: serial
