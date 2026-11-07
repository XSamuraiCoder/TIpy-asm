"""Build a CE Flash App from TIpy's Python subset (language lowering lives in cgen.py).

The built-in routines are compiled into the app and call the calculator OS
directly; the generated app does not load CEdev's clibs library group.

The CE OS only accepts apps signed by TI, so the app ships as AppVars plus an
installer program. A project's own installer/makefile is used when it has one;
otherwise the installer in ti84asm/installer is compiled with the CE target.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .errors import CompileError
from .cgen import FlashAppCompiler


def _makefile_value(makefile: Path, variable: str, fallback: str) -> str:
    contents = makefile.read_text(encoding="utf-8")
    match = re.search(rf"(?m)^\s*{re.escape(variable)}\s*(?::=|\?=|=)\s*([^#\r\n]+)", contents)
    return match.group(1).strip() if match else fallback


INSTALLER_SOURCES = Path(__file__).resolve().parent / "installer"


def default_appvar_prefix(app_name: str) -> str:
    """Name the AppVars after the app, so two apps' installers cannot share them."""
    prefix = re.sub(r"[^A-Za-z0-9]", "", app_name)[:6]
    return prefix if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", prefix) else "TIPY"


def build_installer(output: Path, app_name: str, appvar_prefix: str, appvar_split_size: int,
                    installer_name: str) -> Path:
    """Compile the built-in installer with the CE target and assemble it with fasmg."""
    from .compiler import Compiler
    from .fasmg import ensure_ce_includes, ensure_fasmg

    with tempfile.TemporaryDirectory(prefix="tipy-installer-") as folder:
        work = Path(folder)
        source = write_installer_sources(work, app_name, appvar_prefix, appvar_split_size, installer_name)
        try:
            assembly = Compiler(installer_name, "ce", source_dir=work).compile(source)
        except CompileError as exc:
            raise CompileError(f"internal error compiling the built-in installer: {exc}") from exc
        assembly_path = work / "installer.asm"
        assembly_path.write_text(assembly, encoding="ascii")
        output.parent.mkdir(parents=True, exist_ok=True)
        include_root = ensure_ce_includes()
        result = subprocess.run([ensure_fasmg(), str(assembly_path), str(output.resolve())],
                                cwd=include_root, text=True, capture_output=True)
        if result.returncode or not output.is_file():
            detail = (result.stdout + result.stderr).strip()
            raise CompileError("assembling the built-in installer failed" + (f":\n{detail}" if detail else ""))
    return output


def write_installer_sources(work: Path, app_name: str, appvar_prefix: str, appvar_split_size: int,
                            installer_name: str) -> str:
    """Write the installer's sources for these settings into `work`; return the merged program."""
    from .project import load_sources

    replacements = {
        "%PREFIX%": f"'{appvar_prefix}'",
        "%PREFIX_LENGTH%": str(len(appvar_prefix)),
        "%APP_NAME%": f"'{app_name}'",
        "%PROGRAM_NAME%": f"'{installer_name}'",
    }
    library = (INSTALLER_SOURCES / "installlib.asm").read_text(encoding="utf-8")
    for marker, value in replacements.items():
        library = library.replace(marker, value)
    config = (f"PREFIX = ({', '.join(str(ord(char)) for char in appvar_prefix)},)\n"
              f"PREFIX_LENGTH = {len(appvar_prefix)}\n"
              f"SPLIT_SIZE = {appvar_split_size}\n")
    shutil.copyfile(INSTALLER_SOURCES / "installer.py", work / "installer.py")
    (work / "installlib.asm").write_text(library, encoding="utf-8")
    (work / "install_config.py").write_text(config, encoding="utf-8")
    source, _ = load_sources(work / "installer.py")
    return source


def build_flash_app(source: str, project_dir: Path, app_name: str, appvar_prefix: str | None = None,
                    installer_name: str | None = None, appvar_split_size: int | None = None,
                    optimization: str = "speed") -> list[Path]:
    """Generate C, use CEdev to link a relocatable Flash App, and build its installer."""
    optimization_flags = {"speed": "-O2", "size": "-Oz"}
    if optimization not in optimization_flags:
        raise CompileError("optimization must be 'speed' or 'size'")
    compiler = FlashAppCompiler(app_name)
    c_source = compiler.compile(source)
    project_dir = project_dir.resolve()
    installer_dir = project_dir / "installer"
    installer_makefile = installer_dir / "makefile"
    custom_installer = installer_makefile.is_file()
    # A project's own installer keeps its makefile's settings unless overridden.
    if appvar_prefix is None:
        appvar_prefix = (_makefile_value(installer_makefile, "APPVAR_PREFIX", "PY") if custom_installer
                         else default_appvar_prefix(app_name))
    if installer_name is None:
        installer_name = _makefile_value(installer_makefile, "NAME", "INSTALL") if custom_installer else "INSTALL"
    if appvar_split_size is None:
        appvar_split_size = int(_makefile_value(installer_makefile, "APPVAR_SPLIT_SIZE", "65200")
                                if custom_installer else 65200)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,5}", appvar_prefix):
        raise CompileError("Flash App AppVar prefix must be 1-6 letters/digits, starting with a letter")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,8}", installer_name):
        raise CompileError("installer name must be 1-8 ASCII letters, digits, or underscores")
    if not 1 <= appvar_split_size <= 65535:
        raise CompileError("installer AppVar split size must be between 1 and 65535 bytes")

    build_dir = project_dir / "python_port"
    source_dir = build_dir / "src"
    binary_dir = build_dir / "bin"
    source_dir.mkdir(parents=True, exist_ok=True)
    binary_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "main.c").write_text(c_source, encoding="ascii")
    makefile = f'''# Generated by TIpy-asm. The source shell and installer template are kept separately.
NAME = {app_name}
DESCRIPTION = "TIpy native-library Flash App"
APPLICATION = YES
APPLICATION_DESCRIPTION = "TIpy native-library application"
BINDIR = bin
APPVAR_PREFIX = {appvar_prefix}
APPVAR_SPLIT_SIZE = {appvar_split_size}
CFLAGS = -Wall -Wextra -Wno-unused-function -Wno-unused-variable {optimization_flags[optimization]}
CXXFLAGS = -Wall -Wextra {optimization_flags[optimization]}
# Match CEdev's default whole-program optimization while keeping TIpy's
# selected optimization level for the generated runtime and user code.
LTO = YES
HAS_PRINTF = NO
HAS_LIBC = NO
HAS_LIBCXX = NO
HAS_CUSTOM_FILE = NO

.DEFAULT_GOAL := package
.PHONY: all flash-app appvars installer package
all: package
flash-app: target
appvars: flash-app
\t$(Q)$(CONVBIN) -j 8ek -i $(call QUOTE_ARG,$(BINDIR)/$(NAME).8ek) -k 8xv-split -m $(APPVAR_SPLIT_SIZE) -o $(call QUOTE_ARG,$(BINDIR)/$(NAME).8xv) -n $(APPVAR_PREFIX)
installer: appvars
\t$(Q)$(MAKE) -B -C ../installer NAME={installer_name} APPVAR_PREFIX=$(APPVAR_PREFIX) APPVAR_SPLIT_SIZE=$(APPVAR_SPLIT_SIZE) BINDIR=../python_port/bin
package: installer

include $(shell cedev-config --makefile)
'''
    (build_dir / "Makefile").write_text(makefile, encoding="ascii")
    make = shutil.which("make")
    if not make:
        raise CompileError("CEdev make not found; install CEdev and add its bin directory to PATH")
    result = subprocess.run([make, "installer" if custom_installer else "appvars"], cwd=build_dir,
                            text=True, capture_output=True)
    if result.returncode:
        detail = (result.stdout + result.stderr).strip()
        raise CompileError(f"CE Flash App build failed (exit {result.returncode})" + (f":\n{detail}" if detail else ""))
    installer = binary_dir / f"{installer_name}.8xp"
    if not custom_installer:
        build_installer(installer, app_name, appvar_prefix, appvar_split_size, installer_name)
    # A large app is split across several AppVars: NAME.0.8xv, NAME.1.8xv, ...
    parts = sorted(binary_dir.glob(f"{app_name}.*.8xv"), key=lambda path: int(path.suffixes[0][1:]))
    outputs = [binary_dir / f"{app_name}.8ek", *(parts or [binary_dir / f"{app_name}.0.8xv"]), installer]
    missing = [str(path) for path in outputs if not path.is_file()]
    if missing:
        raise CompileError("Flash App build did not create expected output(s): " + ", ".join(missing))
    return outputs
