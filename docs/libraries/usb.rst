usb
===

.. py:module:: ti84.usb

The CE's USB port, with TIpy's own driver: no LibLoad and no CE C libraries. The
calculator is a USB device. Plugged into a computer, it is a serial port, which
:doc:`serial` reads and writes. This library reports the USB state.

.. code-block:: python

   from ti84 import usb

   usb.begin()
   while not usb.connected():
       usb.poll()
   print("Set up by the computer")
   usb.end()

- :py:func:`poll` handles USB events. Call it often, or one of the
  :doc:`serial` methods, which do the same.
- :py:func:`connected` is True once a computer has set the calculator up.
- :py:func:`role` gives ``usb.HOST`` or ``usb.DEVICE``, plus ``usb.PLUG_B`` when the
  B end of a cable is in.
- :py:func:`last_event` gives the latest event, such as ``usb.HOST_CONFIGURE``.

Host mode
---------

USB host mode is not supported yet: the calculator cannot talk to keyboards, drives,
or other devices on an OTG cable. Until it is, :py:func:`find` finds nothing, and the
device and transfer methods report failure. The 256-byte buffer
(:py:func:`buffer_get` and :py:func:`buffer_set`) is still there for programs that
plan for it.

Methods
-------

.. tipy-methods:: usb
