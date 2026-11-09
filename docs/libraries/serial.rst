serial
======

.. py:module:: ti84.serial

Send and receive bytes.

- **CE:** plugged into a computer, the calculator is a USB serial port. TIpy drives
  the USB controller itself, so a program needs nothing else on the calculator: no
  LibLoad and no CE C libraries.
- **TI-84 Plus and Plus SE:** the calculator's own USB port is a USB serial port too,
  with TIpy's own driver.
- **TI-83 Plus:** it has no USB, so bytes go over the link port to another
  calculator, using the OS's own byte routines.

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

USB serial on the TI-84 Plus
----------------------------

The TI-84 Plus and Plus SE present the same serial port as the CE, with the same USB
ID, so the same computer software finds them. While the program runs, TIpy drives the
USB controller itself: :py:func:`begin` keeps the OS from answering the computer as a
TI device, and :py:func:`end`, or the program's exit, gives USB back to the OS. The
data endpoints are 0x81 (in) and 0x02 (out), the pipes the TI OS uses on this
hardware. As on the CE, call :py:func:`connected` or :py:func:`read_byte` often, and
the calculator is a device only.

The 84 Plus's USB controller is undocumented. The driver follows the community's
notes and how Brandon Wilson's Linky drives it, and has not been tested on every
hardware revision.

Link port on the TI-83 Plus
---------------------------

:py:func:`read_byte` returns -1 at once when nothing is being sent. A byte that
cannot be sent, such as with no calculator on the other end, makes
:py:func:`write_byte` return False instead of showing ERR:LINK. The link port
cannot tell whether a cable is in, so :py:func:`connected` is always True.

Methods
-------

.. tipy-methods:: serial
