Command-line reference
======================

The commands below are also available as ``ti84py``. Each section shows the output
of that command's ``--help``.

Source arguments
----------------

``build``, ``compile``, and ``check`` accept a ``.py`` file, a project folder, or
nothing, which uses the project in or above the current folder.

Exit codes
----------

Commands exit with 0 on success and 1 on an error. ``check`` exits with 1 if any
target fails. Invalid arguments exit with 2.

Error format
------------

Compile errors use ``FILE:LINE: error: MESSAGE``, followed by the source line, so
editors can link to them.

.. tipy-commands::
