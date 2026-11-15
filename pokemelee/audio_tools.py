"""Compile the authored render drivers against the pinned external MusyX source."""
import os
from pathlib import Path
import subprocess

from .catalog import PACKAGE
from .runtime import lock

SOURCES = [
    "seq.c", "synth.c", "seq_api.c", "snd_synthapi.c", "stream.c", "synthdata.c",
    "synthmacros.c", "synthvoice.c", "synth_ac.c", "synth_adsr.c", "synth_vsamples.c",
    "synth_dbtab.c", "s_data.c", "hw_dspctrl.c", "hw_volconv.c", "snd3d.c", "snd_init.c",
    "snd_math.c", "snd_midictrl.c", "snd_service.c", "hardware.c", "hw_aramdma.c",
    "hw_dolphin.c", "hw_pc_output.c", "hw_pc_rate.c", "hw_pc_vsample.c", "hw_pc_song.c",
    "hw_pc_samples.c", "hw_pc_assets.c", "hw_pc_decode.c", "hw_pc.c", "hw_memory.c",
    "hw_lib_dolphin.c", "CheapReverb/creverb_fx.c", "CheapReverb/creverb.c",
    "StdReverb/reverb_fx.c", "StdReverb/reverb.c", "Delay/delay_fx.c", "Chorus/chorus_fx.c",
    "hw_pc_null.c",
]


def compiler_environment():
    if os.name != "nt":
        raise ValueError("Audio helper compilation currently supports Windows")
    vswhere = Path(os.environ["ProgramFiles(x86)"]) / "Microsoft Visual Studio/Installer/vswhere.exe"
    result = subprocess.run([str(vswhere), "-latest", "-products", "*", "-requires",
                             "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
                            capture_output=True, text=True, check=True)
    install = result.stdout.strip()
    if not install:
        raise ValueError("Install the Visual C++ build tools to compile audio helpers")
    script = Path(install) / "VC/Auxiliary/Build/vcvars64.bat"
    if '"' in str(script) or any(c in str(script) for c in "\r\n"):
        raise ValueError("Invalid compiler environment path")
    # cmd has its own quoting rules; list2cmdline's backslash-escaped quotes
    # are for ordinary Windows executables and are not accepted by cmd.
    result = subprocess.run(f'cmd /d /s /c "call "{script}" >nul && set"',
                            capture_output=True, text=True, check=True)
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line and not line.startswith("="))


def compile_audio(runtime):
    runtime = Path(runtime).resolve()
    tag = lock()["tools"]["musyx"]["tag"]
    source = runtime / "musyx/win-x64" / ("musyx-" + tag)
    if not (source / "include/musyx/pc.h").is_file():
        raise ValueError("Fetch the pinned MusyX source dependency first")
    target = runtime / "audio"
    target.mkdir(exist_ok=True)
    env = compiler_environment()
    # Search the compiler environment explicitly; executable lookup otherwise
    # uses the calling process's PATH on Windows.
    import shutil
    compiler = shutil.which("cl.exe", path=env.get("Path", env.get("PATH", "")))
    if not compiler:
        raise ValueError("Visual C++ compiler was not found in its tool environment")
    for name in ("render", "fxrender"):
        args = [compiler, "/nologo", "/O2", "/std:c11", "/experimental:c11atomics", "/W1", "/DNDEBUG",
                "/D_USE_MATH_DEFINES", "/D_CRT_SECURE_NO_WARNINGS", "/DMUSY_TARGET=MUSY_TARGET_PC",
                "/DMUSY_VERSION_MAJOR=2", "/DMUSY_VERSION_MINOR=0", "/DMUSY_VERSION_PATCH=0",
                "/I" + str(source / "include"), "/Fe:" + str(target / (name + ".exe")),
                str(PACKAGE / "native/audio" / (name + ".c"))]
        args += [str(source / "src/musyx/runtime" / item) for item in SOURCES]
        result = subprocess.run(args, cwd=target, env=env, capture_output=True, text=True, timeout=300)
        (target / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise ValueError(f"Audio helper {name} failed to compile; see its runtime log")
