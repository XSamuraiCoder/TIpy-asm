usb
===

.. py:module:: ti84.usb

Use the CE's USB port directly, through CEdev's ``usbdrvce`` library. The
calculator is the host for keyboards, drives, or another calculator, on an OTG
cable, or a device when plugged into a computer. For serial ports, use
:doc:`serial` instead. Like serial, this library needs LibLoad and the CE C
libraries on the calculator, and the CE target.

.. code-block:: python

   from ti84 import usb

   usb.begin()
   device = 0
   while device == 0:
       usb.poll()
       device = usb.find()
   print("Vendor", usb.vendor_id(device))
   print("Product", usb.product_id(device))
   usb.end()

Devices
-------

Call :py:func:`poll` often: plugged-in devices are reset and enabled while it
runs. :py:func:`find` then walks the ready devices: ``usb.find()`` gives the first,
and ``usb.find(device)`` the next, until it returns 0. Before using a device's
endpoints, select its configuration with :py:func:`configure`.

Transfers
---------

- **Bulk and interrupt:** :py:func:`transfer` moves bytes between an endpoint and
  a RAM AppVar. Endpoint addresses 0x80 and up receive from the device; lower
  ones send to it.
- **Control:** :py:func:`control` sends a setup packet. Its data stage uses a
  256-byte buffer, read and written with :py:func:`buffer_get` and
  :py:func:`buffer_set`.

Constants
---------

``usb.HOST``, ``usb.DEVICE``, and ``usb.PLUG_B`` for :py:func:`role`;
``usb.FULL_SPEED`` and ``usb.LOW_SPEED`` for :py:func:`speed`; and the events
for :py:func:`last_event`, such as ``usb.DEVICE_CONNECTED``,
``usb.DEVICE_ENABLED``, ``usb.DEVICE_DISCONNECTED``, and ``usb.HOST_CONFIGURE``.

Methods
-------

.. tipy-methods:: usb
