"""On-demand Windows install of the upstream fasmg executable."""

from __future__ import annotations

import ctypes
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

FASMG_URL = "https://raw.githubusercontent.com/tgrysztar/fasmg/master/core/fasmg.exe"
CE_INCLUDE_BASE_URL = "https://raw.githubusercontent.com/CE-Programming/asm-docs/master/programs/include"
CE_INCLUDE_FILES = ("commands.alm", "ez80.alm", "ez80.inc", "ti84pceg.inc", "tiformat.inc")
CLASSIC_INCLUDE_URL = "https://raw.githubusercontent.com/alberthdev/spasm-ng/v0.5-beta.3/inc/ti83plus.inc"


def ensure_fasmg() -> str:
    """Find fasmg or download it to the per-user tools directory and add it to PATH."""
    existing = shutil.which("fasmg") or shutil.which("fasmg.exe")
    if existing:
        return existing
    if sys.platform != "win32":
        raise OSError("automatic fasmg installation currently supports Windows only")

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise OSError("LOCALAPPDATA is not set; install fasmg and pass --ce-assembler PATH")
    bin_dir = Path(local_app_data) / "TIpy-asm" / "bin"
    executable = bin_dir / "fasmg.exe"
    try:
        bin_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(f"cannot create the fasmg install folder {bin_dir}: {exc}") from exc

    if not executable.is_file():
        request = urllib.request.Request(FASMG_URL, headers={"User-Agent": "ti84py-asm"})
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                binary = response.read(20 * 1024 * 1024 + 1)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise OSError(f"could not download fasmg from the upstream repository: {exc}") from exc
        if len(binary) < 20_000 or len(binary) > 20 * 1024 * 1024 or binary[:2] != b"MZ":
            raise OSError("downloaded fasmg file is not a valid Windows executable")
        with tempfile.NamedTemporaryFile(dir=bin_dir, prefix="fasmg-", suffix=".tmp", delete=False) as temp:
            temp.write(binary)
            temp_path = Path(temp.name)
        temp_path.replace(executable)

    try:
        _add_user_path(bin_dir)
    except OSError as exc:
        print(f"ti84py: warning: could not add fasmg to the persistent user PATH: {exc}", file=sys.stderr)
    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
    return str(executable)


def ensure_ce_includes() -> Path:
    """Fetch TIpy-asm's managed CE fasmg includes and return their parent directory."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    candidates = []
    if local_app_data:
        candidates.append(Path(local_app_data) / "TIpy-asm")
    candidates.extend((Path.home() / ".ti84py", Path(tempfile.gettempdir()) / "TIpy-asm"))
    parent_path = None
    last_error = None
    for candidate in candidates:
        candidate_include_dir = candidate / "include"
        if all((candidate_include_dir / filename).is_file() for filename in CE_INCLUDE_FILES):
            parent_path = candidate
            break
        try:
            candidate_include_dir.mkdir(parents=True, exist_ok=True)
            parent_path = candidate
            break
        except OSError as exc:
            last_error = exc
    if parent_path is None:
        raise OSError(f"cannot create a TIpy-asm include cache: {last_error}")
    include_dir = parent_path / "include"

    for filename in CE_INCLUDE_FILES:
        destination = include_dir / filename
        if destination.is_file():
            continue
        request = urllib.request.Request(
            f"{CE_INCLUDE_BASE_URL}/{filename}", headers={"User-Agent": "ti84py-asm"}
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                data = response.read(2 * 1024 * 1024 + 1)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise OSError(f"could not download CE include {filename}: {exc}") from exc
        if len(data) > 2 * 1024 * 1024 or b"\x00" in data:
            raise OSError(f"downloaded CE include {filename} is invalid")
        with tempfile.NamedTemporaryFile(dir=include_dir, prefix=filename + "-", suffix=".tmp", delete=False) as temp:
            temp.write(data)
            temp_path = Path(temp.name)
        temp_path.replace(destination)
    return parent_path


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


def _add_user_path(bin_dir: Path) -> None:
    import winreg

    key_path = r"Environment"
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
        try:
            current, value_type = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current, value_type = "", winreg.REG_EXPAND_SZ
        paths = [part for part in current.split(os.pathsep) if part]
        normalized = {os.path.normcase(os.path.expandvars(part).rstrip("\\/")) for part in paths}
        desired = os.path.normcase(str(bin_dir).rstrip("\\/"))
        if desired not in normalized:
            updated = os.pathsep.join([*paths, str(bin_dir)])
            winreg.SetValueEx(key, "Path", 0, value_type, updated)
            try:
                ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None)
            except (AttributeError, OSError):
                pass
