"""Wrapper for CEdev's cedev-config tool.

This provides a pure-Python interface to query CEdev configuration,
falling back to calling the actual cedev-config binary when needed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .errors import CompileError


def _call_cedev_config(*args: str) -> str:
    """Call the cedev-config binary and return its stdout."""
    try:
        cedev_config = "cedev-config"
        if sys.platform == "win32":
            # Try to find it in common locations on Windows
            for path in ["C:\\CEDev\\bin\\cedev-config.exe", "C:\\CEDev\\cedev-config.exe"]:
                if Path(path).is_file():
                    cedev_config = path
                    break
        result = subprocess.run([cedev_config, *args], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise CompileError(f"cedev-config not found or failed: {exc}") from exc


def get_version() -> str:
    """Get the CE C/C++ Toolchain version."""
    return _call_cedev_config("--version")


def get_prefix() -> str:
    """Get the installation prefix."""
    return _call_cedev_config("--prefix")


def get_makefile() -> str:
    """Get the path to the core toolchain makefile."""
    return _call_cedev_config("--makefile")


def run(args: list[str]) -> str:
    """Run cedev-config with the given arguments and return stdout."""
    if not args:
        raise CompileError("cedev-config requires at least one option")
    return _call_cedev_config(*args)


def add_arguments(parser):
    """Add cedev-config command arguments."""
    parser.add_argument("option", nargs="?",
                        choices=["--version", "--prefix", "--makefile", "--help"],
                        help="configuration option to query")
