"""Colosseum cry lookup and DSP ADPCM decode from the user's original disc."""
import io
import struct
import wave

from .fsys import entries


def unpack(fmt, data, offset):
    if offset < 0 or offset + struct.calcsize(fmt) > len(data):
        raise ValueError("Truncated Colosseum sound structure")
    return struct.unpack_from(fmt, data, offset)


def dsp(data, count, coefs, hist1=0, hist2=0):
    """Decode 14 samples per eight-byte GameCube DSP ADPCM frame."""
    if not 0 <= count <= 10_000_000 or len(data) < ((count + 13) // 14) * 8:
        raise ValueError("Invalid DSP sample extent")
    out = bytearray()
    produced = 0
    for i in range(0, ((count + 13) // 14) * 8, 8):
        ps = data[i]
        if ps >> 4 > 7:
            raise ValueError("Invalid DSP predictor")
        c1, c2 = coefs[ps >> 4]
        scale = 1 << (ps & 15)
        for k in range(min(14, count - produced)):
            byte = data[i + 1 + k // 2]
            nib = byte >> 4 if k % 2 == 0 else byte & 15
            if nib >= 8:
                nib -= 16
            value = (scale * nib * 2048 + 1024 + c1 * hist1 + c2 * hist2) >> 11
            value = max(-32768, min(32767, value))
            out.extend(struct.pack("<h", value))
            hist2, hist1 = hist1, value
            produced += 1
    return bytes(out)


def sound_samples(project, pool):
    """Resolve each cry effect's macro to its single StartSample command."""
    macros = {}
    at = unpack(">I", pool, 0)[0]
    while at + 8 <= len(pool):
        size, identifier, _ = unpack(">IHH", pool, at)
        if size in (0, 0xFFFFFFFF):
            break
        if size < 8 or size % 8 or at + size > len(pool):
            raise ValueError("Invalid cry macro extent")
        macros[identifier] = [int.from_bytes(pool[i:i+3], "big")
                              for i in range(at + 8, at + size, 8) if pool[i+3] == 0x10]
        at += size
    at, result = 0, {}
    while at + 40 <= len(project):
        end, _, kind, *offsets = unpack(">IHH8I", project, at)
        if kind == 1:
            page = offsets[5]
            count = unpack(">H", project, page)[0]
            for i in range(count):
                sound, macro = unpack(">HH", project, page + 4 + i * 10)
                samples = macros.get(macro, [])
                if len(samples) != 1:
                    raise ValueError("Cry macro must name exactly one sample")
                result[sound] = samples[0]
        if end in (0, 0xFFFFFFFF):
            break
        if end <= at:
            raise ValueError("Cyclic sound project")
        at = end
    return result


class Cries:
    def __init__(self, disc):
        self.disc = disc
        self.common = {name.split("_", 1)[1].rsplit(".", 1)[0]: data
                       for name, data in entries(disc.read("common.fsys"))}
        self.effects, self.samples, self.cache = {}, {}, {}
        for bank in ("snd_se_nakigoe", "snd_se_nakigoe2"):
            self.effects.update(sound_samples(self.common[bank + "_proj"], self.common[bank + "_pool"]))
            directory = self.common[bank + "_sdir"]
            source = disc.read("sound/" + bank + ".samp")
            at = 0
            while at + 32 <= len(directory):
                identifier = unpack(">H", directory, at)[0]
                if identifier == 0xFFFF:
                    break
                offset, _, _, rate, count, _, _, adpcm = unpack(">IIHHIIII", directory, at + 4)
                if count >> 24 != 0 or not rate or offset >= len(source):
                    raise ValueError("Unsupported cry sample")
                _, _, _, hist2, hist1 = unpack(">HBBhh", directory, adpcm)
                coeffs = unpack(">16h", directory, adpcm + 8)
                self.samples[identifier] = (rate, source, offset, count, list(zip(coeffs[::2], coeffs[1::2])), hist1, hist2)
                at += 32

    def wav(self, internal, dex):
        if internal not in self.cache:
            if not 1 <= internal < 412:
                raise ValueError("Invalid species index")
            rel = self.common["common_rel"]
            at = 0x123260 + internal * 0x11C
            actual = unpack(">H", rel, at)[0]
            if actual != dex:
                raise ValueError("Cry recipe disagrees with the disc species table")
            row = unpack(">H", rel, at - 2)[0]
            sound = unpack(">H", rel, 0x141654 + row * 12 + 4)[0]
            sample = self.effects[sound]
            rate, source, offset, count, coefs, h1, h2 = self.samples[sample]
            pcm = dsp(source[offset:], count, coefs, h1, h2)
            output = io.BytesIO()
            with wave.open(output, "wb") as writer:
                writer.setnchannels(1)
                writer.setsampwidth(2)
                writer.setframerate(rate)
                writer.writeframes(pcm)
            self.cache[internal] = output.getvalue()
        return self.cache[internal]
