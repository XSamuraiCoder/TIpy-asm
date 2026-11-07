"""Find the assemblers' files. CE builds use the fasmg and includes inside this package.

``toolchain/bin`` holds upstream fasmg command-line binaries, and
``toolchain/include`` holds the CE includes from CE-Programming/asm-docs. fasmg's
Windows build is 32-bit, so a shared library could not load into 64-bit Python;
the compiler runs the binary instead.
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

TOOLCHAIN = Path(__file__).resolve().parent / "toolchain"
CE_INCLUDE_FILES = ("commands.alm", "ez80.alm", "ez80.inc", "ti84pceg.inc", "tiformat.inc")
CLASSIC_INCLUDE_URL = "https://raw.githubusercontent.com/alberthdev/spasm-ng/v0.5-beta.3/inc/ti83plus.inc"


def bundled_fasmg() -> Path | None:
    """Return the packaged fasmg for this computer, or None if there is no such build."""
    machine = platform.machine().lower()
    if sys.platform == "win32":
        name = "fasmg.exe"          # 32-bit, and runs on x64 and Arm Windows
    elif sys.platform.startswith("linux") and machine in ("x86_64", "amd64"):
        name = "fasmg.x64"
    elif sys.platform.startswith("linux") and machine in ("i386", "i486", "i586", "i686", "x86"):
        name = "fasmg"
    else:
        return None
    path = TOOLCHAIN / "bin" / name
    return path if path.is_file() else None


def _runnable(path: Path) -> Path:
    """Wheels built on Windows lose the executable bit, so restore it if needed."""
    if sys.platform == "win32" or os.access(path, os.X_OK):
        return path
    mode = path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    try:
        path.chmod(mode)
        return path
    except OSError:
        pass                        # a read-only install: run a private copy instead
    # Never a predictable shared path, where another user could plant a binary.
    try:
        folder = Path.home() / ".cache" / "tipy-asm"
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    except (OSError, RuntimeError):
        folder = Path(tempfile.mkdtemp(prefix="tipy-asm-"))
    copy = folder / path.name
    shutil.copyfile(path, copy)
    copy.chmod(mode)
    return copy


def ensure_fasmg() -> str:
    """Return the fasmg to run: the packaged one, otherwise one on PATH."""
    bundled = bundled_fasmg()
    if bundled is not None:
        return str(_runnable(bundled))
    existing = shutil.which("fasmg")
    if existing:
        return existing
    raise OSError(f"this package has no fasmg for {sys.platform} on {platform.machine()}; "
                  "install fasmg on PATH, or pass --ce-assembler PATH")


def ensure_ce_includes() -> Path:
    """Return the folder holding the packaged CE includes in its ``include`` subfolder."""
    missing = [name for name in CE_INCLUDE_FILES if not (TOOLCHAIN / "include" / name).is_file()]
    if missing:
        raise OSError(f"this installation is missing CE include file(s): {', '.join(missing)}; reinstall tipy-asm")
    return TOOLCHAIN


def ensure_classic_include_directory(assembler: str | None = None) -> Path:
    """Find or download SPASM-ng's TI-83 Plus system equates include."""
    candidates: list[Path] = []
    if assembler:
        assembler_path = Path(assembler)
        if assembler_path.is_file():
            binary_dir = assembler_path.resolve().parent
            candidates.extend((binary_dir, binary_dir / "inc", binary_dir / "include",
                               binary_dir.parent / "inc", binary_dir.parent / "include"))
    current_dir = Path.cwd()
    candidates.extend((current_dir, current_dir / "inc", current_dir / "include"))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "TIpy-asm" / "include")
    candidates.extend((Path.home() / ".ti84py" / "include",
                       Path(tempfile.gettempdir()) / "TIpy-asm" / "include"))

    for candidate in candidates:
        include_file = candidate / "ti83plus.inc"
        if _valid_classic_include(include_file):
            return candidate

    cache_candidates = []
    if local_app_data:
        cache_candidates.append(Path(local_app_data) / "TIpy-asm" / "include")
    cache_candidates.extend((Path.home() / ".ti84py" / "include",
                             Path(tempfile.gettempdir()) / "TIpy-asm" / "include"))
    cache_dir = None
    last_error = None
    for candidate in cache_candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            cache_dir = candidate
            break
        except OSError as exc:
            last_error = exc
    if cache_dir is None:
        raise OSError(f"cannot create a classic assembler include cache: {last_error}")

    request = urllib.request.Request(CLASSIC_INCLUDE_URL, headers={"User-Agent": "ti84py-asm"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = response.read(512 * 1024 + 1)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise OSError(f"could not download the SPASM-ng TI-83 Plus include: {exc}") from exc
    if len(data) > 512 * 1024 or b"_FillRect" not in data or b"_ClearRect" not in data:
        raise OSError("downloaded SPASM-ng TI-83 Plus include is invalid")
    destination = cache_dir / "ti83plus.inc"
    with tempfile.NamedTemporaryFile(dir=cache_dir, prefix="ti83plus-", suffix=".tmp", delete=False) as temp:
        temp.write(data)
        temp_path = Path(temp.name)
    temp_path.replace(destination)
    return cache_dir


def _valid_classic_include(path: Path) -> bool:
    try:
        data = path.read_bytes()
    except OSError:
        return False
    return len(data) <= 512 * 1024 and b"_FillRect" in data and b"_ClearRect" in data
