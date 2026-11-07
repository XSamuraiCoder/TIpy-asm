# Assembly example

Python calling routines written in assembly, on both the CE and classic targets.

| File | What it shows |
|---|---|
| `src/fastbits.asm` | Routines whose instructions work on both CPUs, so one file serves both |
| `src/screen.ce.asm` | A CE-only routine that fills video RAM |
| `src/screen.classic.asm` | The classic version of the same routine, which the classic build picks |
| `src/*.pyi` | Stubs, so editors know the routines' parameters |

Each routine is declared with a `; tipy: def name(...)` line. Arguments arrive in
`HL`, `DE`, and `BC`, the result goes back in `HL`, and a routine must preserve
`IY`.

```bash
tipy-asm build --target ce
```

The classic build needs SPASM-ng on your `PATH`. To see the generated code around
the routines, add `--keep-asm`.
