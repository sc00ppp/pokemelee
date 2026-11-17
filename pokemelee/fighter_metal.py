"""A metal or cloaked fighter draws its own costume, not the donor's metal model.

Under the Metal Box or the Cloaking Device the game hides visibility set 0 and shows set 2 on the fighter file's own
metal model (ftData +0x5C, a separate mesh in Pl<code>.dat that ft_800C85B8 hangs on the skeleton) and set 3 on the
costume's DObjs (src/melee/ft/ftdrawcommon.c:236-242, ftparts.c:730-759, ftmetal.c:161-249). A replaced costume
cannot reach that model, so every metal or cloaked fighter was drawn as the vanilla one. In the fighter file, per
costume row: set 3 takes set 0's lookup, so the metal draw shows what the normal draw shows, option for option; set 2
is emptied and the metal model unhooked, so no DObjs are built for it and nothing hides or shows them. Sets 0 and 1
(the normal draw, shadows and the magnifier) are untouched, and so is every costume file. Pointer edits only: the file
loses one relocation for each pointer nulled and never grows.

AniMelee only, PlCo.dat: every metal fighter is drawn with one shared material, PlCo ftLoadCommonData[20] -> joint ->
DObj -> MObj (ftCo_800C8064, ftmaterial.c:76). It is lit, and AniMelee costumes carry no normals, so the fighter went
near-black. Their bodies carry vertex colour white and their outline hulls black, so the material is made unlit, takes
the vertex colour, and multiplies it by a flat steel grey from its TObj's own TEV block (present but switched off;
tobj.c MakeColorGenTExp): a light steel fighter that keeps its black outline. Four value edits, each old value checked
first; nothing moves or grows. The normal disc keeps the game's lit chrome; the cloak (lbRefract) never reads this.
MexCLI's export writes PlCo.dat anew, so the edit is made on the exported disc after the export, never in the project
(patch_exported_common; builder.write_disc and verify_export)."""
import hashlib
from pathlib import Path

from .dat import Dat
from .disc import Disc
from .export import fingerprint

SETS = 4
BODY, PARTS, COSTUME_METAL = 0, 2, 3
METAL_MODEL = 0x5C       # ftData field: the metal model's top joint


def metal_draws_costume(d):
    """Edit Dat ``d`` in place; the number of costume rows changed."""
    root = next((offset for name, offset in d.roots if name.startswith('ftData')), None)
    if root is None:
        raise ValueError('The fighter file has no ftData root')
    x8 = d.ptr(root + 0x08)
    table = d.ptr(x8 + 0x04) if x8 is not None else None
    if table is None:
        raise ValueError('The fighter file has no visibility tables')
    # One row of SETS lookups per costume; the table ends where the next object starts.
    end = min(v for v in [d.u32(at) for at in d.relocations] + [o for _, o in d.roots] + [len(d.data)] if v > table)
    rows = 0
    for row in range(table, end - 4 * SETS + 1, 4 * SETS):
        fields = [row + 4 * k for k in range(SETS)]
        if not any(f in d.relocations for f in fields):
            continue
        d.point(fields[COSTUME_METAL], d.ptr(fields[BODY]))
        d.point(fields[PARTS], None)
        rows += 1
    if not rows:
        raise ValueError('The fighter file has no costume rows')
    d.point(root + METAL_MODEL, None)
    return rows


def patch_fighter_files(files, names):
    """Patch each named fighter file in the project folder ``files``; their fingerprints, for the export check."""
    out = []
    for name in sorted(set(names)):
        path = Path(files) / name
        d = Dat.read(path)
        metal_draws_costume(d)
        d.save(path)
        out.append({'path': name, **fingerprint(path)})
    return out


COMMON = 'PlCo.dat'
METAL_ENTRY = 20         # ftLoadCommonData entry: the metal material's joint
STEEL = bytes.fromhex('c4ccd8')
# (where, field offset, old value, new value): MObj +0x04 rendermode DIFFUSE|SPECULAR|TEX0 -> VERTEX|TEX0 (what the
# AniMelee costumes use); TEV +0x08 colour inputs TEX0,KONST,TEXC,ZERO -> ZERO,ZERO,ZERO,KONST; +0x10 the konst colour
# (None: the steel grey); +0x1C active: the colour stage on.
STEEL_EDITS = (('mobj', 0x04, '0000001c', '00000012'), ('tev', 0x08, '8580080f', '0f0f0f80'),
               ('tev', 0x10, '00000000', None), ('tev', 0x1C, '00000000', '40000000'))


def steel_metal(d, grey=STEEL):
    """Edit PlCo Dat ``d`` in place so its metal material draws vertex colour times ``grey`` (3 bytes), unlit; the data
    offsets written. Every old value is checked before anything is written: a file that is not the expected one is
    refused untouched."""
    root = d.root('ftLoadCommonData')
    if root is None:
        raise ValueError('PlCo.dat has no ftLoadCommonData root')
    joint = d.ptr(root + 4 * METAL_ENTRY)
    dobj = d.ptr(joint + 0x10) if joint is not None else None
    mobj = d.ptr(dobj + 0x08) if dobj is not None else None
    tobj = d.ptr(mobj + 0x08) if mobj is not None else None
    tev = d.ptr(tobj + 0x58) if tobj is not None else None
    if tev is None or d.ptr(tobj + 0x04) is not None:
        raise ValueError('PlCo.dat: the metal material is not one MObj with one TObj and its TEV block')
    if len(grey) != 3:
        raise ValueError('The steel grey is three bytes, RGB')
    base, edits = {'mobj': mobj, 'tev': tev}, []
    for where, field, old, new in STEEL_EDITS:
        at, old = base[where] + field, bytes.fromhex(old)
        new = bytes.fromhex(new) if new is not None else bytes(grey) + b'\xff'
        found = bytes(d.data[at:at + 4])
        if found != old:
            raise ValueError(f'PlCo.dat {where} +{field:#x} (data {at:#x}) is {found.hex()}, expected {old.hex()}')
        edits.append((at, new))
    for at, new in edits:
        d.data[at:at + 4] = new
    return [at for at, _ in edits]


def patch_exported_common(built_iso, profile):
    """After MexCLI's export, AniMelee only: the exported disc's PlCo.dat gets the steel metal material, written in
    place (same offset, same size, only the four values). Its row for verify_export: the sha256 the disc must now hold,
    the exported file's own, and the file offsets changed. The normal profile's disc is not opened for writing."""
    if profile != 'animelee':
        return []
    entry = Disc(built_iso, 'melee').entries[COMMON]
    with open(built_iso, 'r+b') as stream:
        stream.seek(entry.offset)
        raw = stream.read(entry.size)
        if len(raw) != entry.size:
            raise ValueError('The exported disc is truncated at ' + COMMON)
        d = Dat(raw)
        fields = steel_metal(d)
        # Value edits only: the data block goes back over the exported file, and its relocation table keeps its own
        # order (PlCo's is not sorted; Dat.save would sort it).
        out = bytearray(raw)
        out[0x20:0x20 + len(d.data)] = d.data
        changed = [i for i in range(len(raw)) if raw[i] != out[i]]
        if not changed or not set(changed) <= {0x20 + at + k for at in fields for k in range(4)}:
            raise ValueError(COMMON + ': the steel edit would change more than its four values')
        stream.seek(entry.offset)
        stream.write(out)
    return [{'path': COMMON, 'bytes': len(out), 'sha256': hashlib.sha256(out).hexdigest(),
             'exported_sha256': hashlib.sha256(raw).hexdigest(), 'changed': changed}]
