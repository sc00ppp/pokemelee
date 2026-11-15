"""Approved Colosseum song rendering and loop preparation."""
import re
import struct
import subprocess
import wave
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from scipy.signal import resample
from .catalog import load
from .export import fingerprint
from .fsys import entries
from .voices import mex
from .workspace import output_directory, receipt, write_blob
GROUP = 56
SECONDS = 480
VOLUME = 112
FADE = .03

def align(m, near, ref, rate, reach=512):
    """(i, corr): the sample within `reach` of `near` from which the music best matches what follows `ref`."""
    n = rate // 2
    r = m[ref:ref + n]
    best, at = -2.0, near
    for k in range(-reach, reach + 1):
        w = m[near + k:near + k + n]
        c = float(np.dot(w, r) / (np.linalg.norm(w) * np.linalg.norm(r) + 1e-9))
        if c > best:
            best, at = c, near + k
    return at, best


def write_wav(path, rate, x):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.ascontiguousarray(np.clip(np.round(x), -32768, 32767).astype('<i2')).tobytes())


def cut_audio(rate, x, loop_at, jumps):
    loud = np.nonzero(np.abs(x).max(1) >= 8)[0]
    first = int(loud[0])
    if len(jumps) >= 2 and loop_at is not None:
        xf = x.astype(np.float64)
        m = xf.mean(1)
        a = jumps[0]                                     # the second pass starts here (the first jump back)
        # the marks are read every 32 samples, and MusyX's free-running modulation and reverb make no two passes
        # sample-identical: find where the next pass and the first pass really line up with the second
        b, cb = align(m, jumps[1], a, rate)
        p, cp = align(m, loop_at, a, rate)
        F = int(FADE * rate)
        ramp = (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, F)))[:, None]
        lead = xf[a - F:a]                               # what really plays into the loop's first sample
        body = xf[a:b].copy()
        body[-F:] = body[-F:] * (1 - ramp) + lead * ramp
        if p - first > 2 * F:
            intro = xf[first:p].copy()
            intro[-F:] = intro[-F:] * (1 - ramp) + lead * ramp
        else:                                            # the loop point is the song's start
            intro = xf[first:first]
        pad = (-len(intro)) % GROUP
        intro = np.vstack([np.zeros((pad, 2)), intro])
        n = int(round((b - a) / GROUP)) * GROUP
        body = resample(body, n, axis=0)                 # one period: band-limited, end flows into start
        out = np.vstack([intro, body])
        info = {'intro_s': round(len(intro) / rate, 3), 'loop_s': round((b - a) / rate, 3),
                'loop_resample_ppm': round((n - (b - a)) / (b - a) * 1e6, 1), 'passes_rendered': len(jumps),
                'pass_match': round(cb, 3), 'intro_match': round(cp, 3)}
    elif not jumps:                                      # plays once: all of it and a second of quiet
        end = int(loud[-1]) + rate
        end += (-(end - first)) % GROUP
        out = x[first:end].astype(np.float64)
        intro = out[:0]
        info = {'intro_s': 0.0, 'loop_s': round(len(out) / rate, 3), 'plays_once': True}
    else:
        raise ValueError(f'Only {len(jumps)} loop jump in {SECONDS} s')
    return out, len(intro), info


def build_music(colosseum, output, runtime, selected=None):
    recipes = load("music.json")["songs"]
    names = list(selected if selected is not None else [r["id"] for r in recipes])
    if not names or len(set(names)) != len(names) or set(names) - {r["id"] for r in recipes}:
        raise ValueError("Unknown or duplicate song selection")
    runtime = Path(runtime).resolve()
    renderer, cli = runtime / "audio/render.exe", runtime / "mex/win-x64/MexCLI.exe"
    if not renderer.is_file() or not cli.is_file():
        raise ValueError("Install MexCLI and compile the pinned audio helpers first")
    with output_directory(output, "music") as root:
        common = {n.split("_", 1)[1].rsplit(".", 1)[0]: b for n, b in entries(colosseum.read("common.fsys"))}
        for suffix in ("proj", "pool", "sdir"):
            data = common["snd_music_" + suffix]
            if suffix == "sdir":
                data = bytearray(data)
                for at in range(0, len(data) - 32, 32):
                    identifier = struct.unpack_from(">H", data, at)[0]
                    if identifier == 0xFFFF:
                        break
                    if identifier == 581:
                        if struct.unpack_from(">II", data, at + 20) != (0xFFFFFFFF, 1):
                            raise ValueError("Unexpected non-looping instrument marker")
                        struct.pack_into(">II", data, at + 20, 0, 0)
                        break
            write_blob(root, "bank/snd_music_" + suffix, data)
        write_blob(root, "bank/snd_music.samp", colosseum.read("sound/snd_music.samp"))
        songs = {n.split("_", 1)[1].rsplit(".", 1)[0]: b for n, b in entries(colosseum.read("bgm_archive.fsys"))}
        for name in names:
            write_blob(root, "songs/" + name + ".song", songs[name])
        (root / "wav").mkdir()
        (root / "files/audio").mkdir(parents=True)
        references = load("references/normal.json")["files"]
        def build(name):
            wav = root / "wav" / (name + ".wav")
            result = subprocess.run([str(renderer), str(root / "bank"), str(root / "songs" / (name + ".song")),
                                     "0", str(SECONDS), str(wav), str(VOLUME)],
                                    capture_output=True, text=True, timeout=600)
            (root / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
            if result.returncode:
                raise ValueError(f"Song {name} failed; see its render log")
            start = next((int(m) for m in re.findall(r"loopstart section 0 tick \d+ frame (\d+)", result.stdout)), None)
            jumps = [int(m) for m in re.findall(r"loop section 0 count \d+ frame (\d+)", result.stdout)]
            with wave.open(str(wav)) as reader:
                rate = reader.getframerate()
                samples = np.frombuffer(reader.readframes(reader.getnframes()), "<i2").reshape(-1, 2)
            audio, intro, info = cut_audio(rate, samples, start, jumps)
            cut = root / "wav" / (name + ".cut.wav")
            raw = root / "wav" / (name + ".raw.hps")
            target = root / "files/audio" / (name + ".hps")
            write_wav(cut, rate, audio)
            mex(cli, "audio-to-hps", cut, raw)
            mex(cli, "hps-set-loop", raw, target, f"{intro * 1000.0 / rate:.6f}")
            actual = fingerprint(target)
            if actual["sha256"] != references["audio/" + name + ".hps"]["sha256"]:
                raise ValueError(f"Song {name} differs from the accepted build")
            return {"path": "files/audio/" + name + ".hps", **actual, **info}
        with ThreadPoolExecutor(max_workers=min(2, len(names))) as pool:
            outputs = list(pool.map(build, names))
        return receipt(root, "music", {"colosseum": colosseum.info()}, outputs)
