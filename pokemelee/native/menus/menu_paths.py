"""Explicit workspace and installed-tool paths for the saved menu recipes."""
import os
from pathlib import Path

SOURCE = Path(os.environ["POKEMELEE_MENU_SOURCE"]).resolve()
RUNTIME = Path(os.environ["POKEMELEE_RUNTIME"]).resolve()
FONTS = Path(os.environ.get("POKEMELEE_FONTS", str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts")))
MENUGRAFT = RUNTIME / "stagegraft/menugraft/stagegraft-menugraft.exe"
DEVKIT = RUNTIME / "powerpc-binutils/win-x64"
