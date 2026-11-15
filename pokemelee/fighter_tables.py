"""Read the donor's native costume visibility tables for outline generation."""
from dataclasses import dataclass
from pathlib import Path
from .dat import Dat
SETS = 4
HIGH_DETAIL, LOW_DETAIL, OTHER_LIST, METAL = range(SETS)
JOINT_INSTANCE = 1 << 12
JOINT_NO_DOBJ = (1 << 5) | (1 << 14)

@dataclass(frozen=True)
class FighterTables:
    """What a fighter's Pl<code>.dat says about a costume's DObjs and TObjs, for one costume."""
    animated: tuple = ()        # places in the TObj list the game animates
    body: tuple | None = None   # DObj places drawn at spawn: set 0, model 0, option 0 (None: no visibility tables)
    elsewhere: frozenset = frozenset()  # DObj places another option/model of set 0 or 1, or any of set 3 names (shown or hidden
                                        # apart from the body)
    low: tuple = ()             # DObj places drawn for shadows and the magnifier: set 1, model 0, option 0, less any
                                # place another option or model of set 0 or 1 names
    reserved: frozenset = frozenset()

def fighter_tables(path, costume=0):
    """The animated TObj places and the visibility tables in a fighter's Pl<code>.dat, for ``costume`` (a costume
    with no table of its own uses costume 0's, as the game does)."""
    d = Dat.read(path)
    root = next((offset for name, offset in d.roots if name.startswith('ftData')), None)
    if root is None:
        raise ValueError(f'{Path(path).name} has no ftData root')
    x8 = d.ptr(root + 0x08)
    if x8 is None:
        return FighterTables()
    models, sets = d.u32(x8), d.ptr(x8 + 0x04)
    count, lists = d.u32(x8 + 0x08), d.ptr(x8 + 0x0C)

    def own_or_first(table, stride, k=0):
        at = d.ptr(table + costume * stride + 4 * k)
        return at if at is not None else d.ptr(table + 4 * k)

    animated = ()
    if count:
        at = own_or_first(lists, 4) if lists is not None else None
        if at is None:
            raise ValueError(f'{Path(path).name} animates {count} textures and lists none')
        animated = tuple(d.u16(at + 2 * i) for i in range(count))
    if sets is None or not models:
        return FighterTables(animated=animated)
    options = {}        # (set, model, option) -> DObj places
    for k in range(SETS):
        lookup = own_or_first(sets, 4 * SETS, k)
        for m in range(models if lookup is not None else 0):
            n, opts = d.u32(lookup + 8 * m), d.ptr(lookup + 8 * m + 4)
            for o in range(n if opts is not None else 0):
                size, places = d.u32(opts + 8 * o), d.ptr(opts + 8 * o + 4)
                options[k, m, o] = tuple(d.data[places + i] for i in range(size)) if places is not None else ()

    def named_but_by(key):
        # Set 3 addresses the costume list too (src/melee/ft/ftparts.c:741); set 2 addresses the separate metal list.
        return {p for k, places in options.items() if k != key and k[0] in (HIGH_DETAIL, LOW_DETAIL, METAL)
                for p in places}
    body = options.get((HIGH_DETAIL, 0, 0), ())
    elsewhere = frozenset(named_but_by((HIGH_DETAIL, 0, 0)))
    low = tuple(p for p in options.get((LOW_DETAIL, 0, 0), ()) if p not in named_but_by((LOW_DETAIL, 0, 0)))
    return FighterTables(animated=animated, body=body, elsewhere=elsewhere, low=low)

def joints(d, symbol):
    """The joints under root ``symbol``, as offsets, in the game's tree order."""
    root = d.root(symbol)
    if root is None:
        raise ValueError(f'the file has no root {symbol}')
    out = []

    def walk(j):
        while j is not None:
            out.append(j)
            if not d.u32(j + 4) & JOINT_INSTANCE:
                walk(d.ptr(j + 0x08))
            j = d.ptr(j + 0x0C)
    walk(root)
    return out

def joint_dobjs(d, joint):
    """The DObjs of one joint, as offsets, in chain order."""
    if d.u32(joint + 4) & JOINT_NO_DOBJ:
        return []
    return d.chain(d.ptr(joint + 0x10), 0x04)
