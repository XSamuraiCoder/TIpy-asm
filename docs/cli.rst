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

.. _converting-fonts:

Converting fonts
----------------

``tipy-asm convfont`` matches CEdev's ``convfont`` v1.2: the same options, exit codes,
and output bytes. It reads ``.fnt`` files with ``-f`` and text-format fonts with ``-t``.
Options such as ``-a`` and ``-w`` apply to the font named before them.

There are two small differences. ``-z`` works as CEdev's help describes, while its
binary rejects it. A failed run also never leaves an empty output file behind.

TTF and OTF files are not read. Convert them with a separate tool first. To make an
AppVar by hand, build a font pack and pass it to ``convbin``:

.. code-block:: console

   tipy-asm convfont -o fontpack -f myfont.fnt -N "My Font" myfont.bin
   tipy-asm convbin -j bin -i myfont.bin -k 8xv -n MYFONT -o MYFONT.8xv

.. tipy-commands::
