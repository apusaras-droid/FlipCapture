from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def restart_as_admin() -> bool:
    """Start another instance through the standard Windows UAC prompt."""
    ctypes.windll.shell32.ShellExecuteW.restype = ctypes.c_void_p
    executable = Path(sys.executable)
    if executable.name.lower() == "python.exe":
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.exists():
            executable = pythonw
    parameters = subprocess.list2cmdline(["-m", "flipcapture", "gui"])
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", str(executable), parameters, str(Path.cwd()), 1
    )
    return bool(result and int(result) > 32)
