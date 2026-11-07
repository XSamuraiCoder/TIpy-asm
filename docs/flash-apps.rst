Flash Apps
==========

A Flash App lives in the calculator's archive and opens from the **apps** menu. TIpy-asm
builds one by translating your program to C and compiling it with
`CEdev <https://github.com/CE-Programming/toolchain>`_. Flash Apps support more of
Python than the assembly targets, including recursion and strings in variables.

The CE OS only accepts apps signed by TI, so a TIpy-asm app is delivered as AppVars
plus an installer program that copies it into flash. ``tipy-asm flash-app`` builds
both.

Build
-----

With CEdev on your ``PATH``, run this in a project folder:

.. code-block:: console

   tipy-asm flash-app

``examples/flash_app`` in the repository is a complete project to start from: it
clears the screen and says hello world in the center. The
build writes to ``python_port/bin/``:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - File
     - What it is
   * - ``HELLO.0.8xv``
     - The app, split into AppVars named ``HELLO0``, ``HELLO1``, and so on.
   * - ``INSTALL.8xp``
     - The installer program.
   * - ``HELLO.8ek``
     - The app itself, which the CE OS will not accept directly.

``python_port/`` is generated on every build, so do not edit it.

Install
-------

#. Send ``INSTALL.8xp`` and every ``HELLO.*.8xv`` file to the calculator.
#. Run ``INSTALL`` from the home screen. Depending on your OS version, you may need a
   shell such as Cesium, or the arTIfiCE jailbreak, to run it.
#. Open the app from the **apps** menu. The installer offers to delete its own files.

.. warning::

   The installer writes to the calculator's flash memory. Back up anything important,
   and do not interrupt it while it runs.

Delete an app
-------------

Run ``INSTALL`` again. When the app is already installed, the installer shows its
name and asks whether to delete it. Press :kbd:`Enter` to delete it, or :kbd:`Clear`
to keep it. The installer only needs its own program for this, not the AppVars.

A deleted app stays in flash until the OS tidies the archive, which it does when the
installer exits. The installer checks the same app list as the **apps** menu, so a
deleted app no longer counts as installed, even before the tidy-up. To install again afterwards, send
the AppVars and run ``INSTALL`` once more. You can also delete an app from the
**mem** menu as usual.

How the installer works
-----------------------

The installer is a TIpy-asm program: ``ti84asm/installer/installer.py`` holds its
logic, and ``installlib.asm`` holds the routines that unlock, erase, and write flash.
``flash-app`` compiles them with the CE target every time it builds an app, with the
app's name and AppVar prefix filled in.

- The installation logic is a line-by-line port of the installer in
  `CE-Programming/app_tools <https://github.com/CE-Programming/app_tools>`_, whose readme
  permits copying it to make a custom installer. A test runs the compiled installer
  against a Python copy of upstream's C on hundreds of random layouts, and requires
  the same flash writes and erases, in the same order.
- The flash routines are upstream's assembly, with only their entry points changed to
  take arguments in registers.
- Checking for and deleting an app follow the Cesium shell: the installer walks the
  apps with the OS's ``FindAppUp``, which skips deleted apps, compares whole names,
  and calls ``DeleteApp`` to delete one.

None of this has been run on real hardware by the test suite, which uses a simulator.
Test a new build in `CEmu <https://ce-programming.github.io/CEmu/>`_ first.

Settings
--------

``[tool.tipy.flash]`` in ``pyproject.toml`` can change the defaults. All are optional.

.. list-table::
   :header-rows: 1
   :widths: 25 25 50

   * - Key
     - Default
     - Meaning
   * - ``project_dir``
     - The project folder
     - Where ``python_port/`` is built.
   * - ``optimize``
     - ``speed``
     - ``speed`` or ``size``.
   * - ``appvar_prefix``
     - The app's name
     - AppVar names, before the number: 1-6 letters or digits.
   * - ``installer_name``
     - ``INSTALL``
     - The installer program's name.
   * - ``appvar_split_size``
     - ``65200``
     - Bytes per AppVar.

Using your own installer
------------------------

If ``project_dir`` contains ``installer/makefile``, ``flash-app`` builds that CEdev
project as the installer instead, passing ``NAME``, ``APPVAR_PREFIX``,
``APPVAR_SPLIT_SIZE``, and ``BINDIR`` on the ``make`` command line. Its makefile's
values are the defaults in that case.
