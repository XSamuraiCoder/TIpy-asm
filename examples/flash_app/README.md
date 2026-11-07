# Flash App example

A TIpy-asm program built as a TI-84 Plus CE Flash App, with its installer.

## Build

This needs [CEdev](https://github.com/CE-Programming/toolchain) on your `PATH`.

```bash
tipy-asm flash-app
```

That writes three files to `python_port/bin/`:

| File | What it is |
|---|---|
| `HELLO.0.8xv` | The app, split into AppVars named `HELLO0`, `HELLO1`, ... |
| `INSTALL.8xp` | The installer, written in TIpy-asm's Python and built for you |
| `HELLO.8ek` | The app itself, which the CE OS will not accept directly |

## Install on the calculator

1. Send `INSTALL.8xp` and every `HELLO.*.8xv` file.
2. Run `INSTALL` from the home screen. Depending on your OS version, you may need a
   shell such as Cesium, or the arTIfiCE jailbreak, to run it.
3. Open the app from the **apps** menu.

## Remove it

Run `INSTALL` again. When the app is already installed, it offers to delete it.
You can also delete the app from the **mem** menu.

The installer writes to the calculator's flash memory. Back up anything important
first, and do not interrupt it while it runs.
