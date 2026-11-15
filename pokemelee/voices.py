"""Rebuild the accepted fighter voice banks using fixed, saved slot recipes."""
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import subprocess
import wave

import numpy as np

from .catalog import load as recipe
from .cries import Cries
from .export import fingerprint
from .workspace import output_directory, receipt, write_blob


def wav_read(source):
    with wave.open(io.BytesIO(source) if isinstance(source, bytes) else str(source)) as reader:
        samples = np.frombuffer(reader.readframes(reader.getnframes()), "<i2").astype(float) / 32768
        return reader.getframerate(), samples.reshape(-1, reader.getnchannels()).mean(axis=1)


def wav_write(path, rate, samples):
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())


def active_rms(samples):
    frames = np.array([np.sqrt((samples[i:i+256] ** 2).mean())
                       for i in range(0, max(1, len(samples) - 256), 256)])
    return float(np.sqrt((frames[frames > frames.max() * .25] ** 2).mean()))


def cut(samples, rate, head, tail):
    a, b, cross = int(head * rate), int(tail * rate), int(.02 * rate)
    ramp = np.sqrt(np.linspace(0, 1, cross))
    return np.concatenate([samples[:a-cross], samples[a-cross:a] * ramp[::-1] +
                           samples[-b:-b+cross] * ramp, samples[-b+cross:]])


def clip(cry_rate, cry, vanilla_rate, vanilla, role, semitones):
    active = np.nonzero(np.abs(cry) > .05)[0]
    if not len(active):
        raise ValueError("Cry contains no audible samples")
    cry = cry[active[0]:active[-1]+1]
    speed = 2 ** (semitones / 12)
    wanted = max(.30, len(vanilla) / vanilla_rate * speed)
    whole = role in {"taunt", "win", "star"} or wanted >= .9 * len(cry) / cry_rate
    result = (cry if whole else cut(cry, cry_rate, .58 * wanted, .42 * wanted)).copy()
    fade = int(.03 * cry_rate)
    result[-fade:] *= np.linspace(1, 0, fade)
    gain = min(active_rms(vanilla) / active_rms(result), .95 / np.abs(result).max())
    return round(cry_rate * speed), result * gain


def mex(executable, *args):
    result = subprocess.run([str(executable), *map(str, args)], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ValueError(f"MexCLI {args[0]} failed: {(result.stderr or result.stdout)[-500:]}")
    try:
        report = json.loads(result.stdout)
    except ValueError as exc:
        raise ValueError(f"MexCLI {args[0]} did not return its JSON result") from exc
    if not report.get("success"):
        raise ValueError(f"MexCLI {args[0]} failed: {result.stdout[-500:]}")
    return report


def build_announcer(melee, colosseum, output, runtime):
    spec = recipe("announcer.json")
    name = spec["bank"]
    executable = Path(runtime).resolve() / "mex/win-x64/MexCLI.exe"
    if not executable.is_file():
        raise ValueError("Fetch the pinned Windows MexCLI runtime first")
    with output_directory(output, "announcer") as root:
        cries = Cries(colosseum)
        source = root / "vanilla" / name
        target = root / "files/audio/us" / name
        write_blob(root, f"vanilla/{name}", melee.read("audio/us/" + name))
        write_blob(root, f"files/audio/us/{name}", source.read_bytes())
        clips = root / "clips"
        clips.mkdir()
        for row in spec["slots"]:
            parts = []
            for mon in row["cries"]:
                rate, samples = wav_read(cries.wav(mon["internal"], mon["dex"]))
                active = np.nonzero(np.abs(samples) > .05)[0]
                if not len(active):
                    raise ValueError("Announcer cry contains no audible samples")
                parts.append((rate, samples[active[0]:active[-1]+1]))
            rate = parts[0][0]
            if any(r != rate for r, _ in parts):
                raise ValueError("Paired announcer cries need matching sample rates")
            joined = [parts[0][1]]
            for _, samples in parts[1:]:
                joined.extend([np.zeros(int(.12 * rate)), samples])
            samples = np.concatenate(joined)
            fade = int(.03 * rate)
            samples[-fade:] *= np.linspace(1, 0, fade)
            index = row["slot"]
            vanilla = clips / f"{index}-vanilla.wav"
            mex(executable, "ssm-to-wav", source, index, vanilla)
            _, reference = wav_read(vanilla)
            gain = min(active_rms(reference) / active_rms(samples), .95 / np.abs(samples).max())
            wav = clips / f"{index}-cry.wav"
            wav_write(wav, rate, samples * gain)
            mex(executable, "ssm-replace", target, index, wav, target)
        actual = fingerprint(target)
        if actual["sha256"] != recipe("references/normal.json")["files"]["audio/us/" + name]["sha256"]:
            raise ValueError("Announcer bank differs from the accepted build")
        return receipt(root, "announcer", {"melee": melee.info(), "colosseum": colosseum.info()},
                       [{"path": "files/audio/us/" + name, "replaced_slots": len(spec["slots"]), **actual}])


def build_voices(melee, colosseum, output, runtime, selected=None):
    banks = recipe("voices.json")["banks"]
    names = sorted(banks if selected is None else set(selected))
    if not names or any(name not in banks for name in names):
        raise ValueError("Unknown or empty voice-bank selection")
    executable = Path(runtime).resolve() / "mex/win-x64/MexCLI.exe"
    if not executable.is_file():
        raise ValueError("Fetch the pinned Windows MexCLI runtime first")
    references = recipe("references/normal.json")["files"]
    with output_directory(output, "voices") as root:
        cries = Cries(colosseum)
        species = {(r["internal"], r["dex"]) for name in names for r in banks[name]}
        source_cries = {}
        for internal, dex in sorted(species):
            wav = cries.wav(internal, dex)
            write_blob(root, f"cries/{internal}.wav", wav)
            source_cries[internal] = wav_read(wav)
        for name in names:
            write_blob(root, f"vanilla/{name}", melee.read("audio/us/" + name))
        (root / "files/audio/us").mkdir(parents=True)
        (root / "clips").mkdir()
        def build(name):
            source = root / "vanilla" / name
            target = root / "files/audio/us" / name
            target.write_bytes(source.read_bytes())
            clips = root / "clips" / name
            clips.mkdir()
            for row in banks[name]:
                index = row["slot"]
                vanilla = clips / f"{index}-vanilla.wav"
                mex(executable, "ssm-to-wav", source, index, vanilla)
                vrate, samples = wav_read(vanilla)
                rate, cry = source_cries[row["internal"]]
                rate, samples = clip(rate, cry, vrate, samples, row["role"], row["semitones"])
                path = clips / f"{index}-cry.wav"
                wav_write(path, rate, samples)
                mex(executable, "ssm-replace", target, index, path, target)
            actual = fingerprint(target)
            if actual["sha256"] != references["audio/us/" + name]["sha256"]:
                raise ValueError(f"Voice bank {name} differs from the accepted build")
            return {"path": "files/audio/us/" + name, "replaced_slots": len(banks[name]), **actual}
        with ThreadPoolExecutor(max_workers=min(6, len(names))) as pool:
            outputs = list(pool.map(build, names))
        return receipt(root, "voices", {"melee": melee.info(), "colosseum": colosseum.info()}, outputs)
