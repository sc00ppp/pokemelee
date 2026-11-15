"""The accepted six menu sound replacements, rendered from Colosseum's bank."""
from pathlib import Path
import subprocess

import numpy as np

from .catalog import load
from .export import fingerprint
from .fsys import entries
from .voices import mex, wav_read, wav_write
from .workspace import output_directory, receipt, write_blob

SLOTS = [(117, 859), (118, 858), (119, 857), (127, 922), (128, 923), (122, 893)]


def active_rms(samples):
    frames = np.array([np.sqrt((samples[i:i+128] ** 2).mean())
                       for i in range(0, max(1, len(samples) - 128), 128)])
    return float(np.sqrt((frames[frames > frames.max() * .25] ** 2).mean()))


def build_menu_sounds(melee, colosseum, output, runtime):
    runtime = Path(runtime).resolve()
    renderer, cli = runtime / "audio/fxrender.exe", runtime / "mex/win-x64/MexCLI.exe"
    if not renderer.is_file() or not cli.is_file():
        raise ValueError("Install MexCLI and compile the audio helpers first")
    with output_directory(output, "menu-sounds") as root:
        common = {n.split("_", 1)[1].rsplit(".", 1)[0]: b for n, b in entries(colosseum.read("common.fsys"))}
        for suffix in ("proj", "pool", "sdir"):
            write_blob(root, "bank/snd_se_" + suffix, common["snd_se_" + suffix])
        write_blob(root, "bank/snd_se.samp", colosseum.read("sound/snd_se.samp"))
        source, target = root / "vanilla/main.ssm", root / "files/audio/us/main.ssm"
        write_blob(root, "vanilla/main.ssm", melee.read("audio/us/main.ssm"))
        write_blob(root, "files/audio/us/main.ssm", source.read_bytes())
        clips = root / "clips"
        clips.mkdir()
        for index, fx in SLOTS:
            result = subprocess.run([str(renderer), str(root / "bank"), "snd_se", "6", str(clips),
                                     str(fx), str(fx), "4"], capture_output=True, text=True, timeout=120)
            (root / f"{fx}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
            if result.returncode or not (clips / f"{fx}.wav").is_file():
                raise ValueError(f"Menu effect {fx} did not render")
            vanilla = clips / f"{index}-vanilla.wav"
            mex(cli, "ssm-to-wav", source, index, vanilla)
            rate, samples = wav_read(clips / f"{fx}.wav")
            active = np.nonzero(np.abs(samples) > .004)[0]
            if not len(active):
                raise ValueError("Menu effect contains no audible samples")
            samples = samples[active[0]:active[-1]+1]
            _, reference = wav_read(vanilla)
            samples = samples * (active_rms(reference) / active_rms(samples))
            peak = np.abs(samples).max()
            if peak > .97:
                samples *= .97 / peak
            fade = int(.008 * rate)
            samples[-fade:] *= np.linspace(1, 0, fade)
            wav = clips / f"{index}-new.wav"
            wav_write(wav, rate, samples)
            mex(cli, "ssm-replace", target, index, wav, target)
        actual = fingerprint(target)
        if actual["sha256"] != load("references/normal.json")["files"]["audio/us/main.ssm"]["sha256"]:
            raise ValueError("Menu sound bank differs from the accepted build")
        return receipt(root, "menu-sounds", {"melee": melee.info(), "colosseum": colosseum.info()},
                       [{"path": "files/audio/us/main.ssm", "replaced_slots": len(SLOTS), **actual}])
