"""Generate the accepted "Any Climbers" behavior from its authored assembly.

Melee decides a fighter follows its partner by asking `fp->kind == FTKIND_NANA`.
Five sites in the DOL ask it, all compiled to the same two instructions:

    lwz   rD, 4(rSRC)     # fp->kind
    cmpwi rD, 11          # FTKIND_NANA

Each site gets a C2 injection over the `lwz` that answers 11 for *any* follower
instead.  A follower is the second entity of a paired character (`x221F & 8`,
m-ex's master/slave bit).  The only vanilla fighters that bit is set for are
Nana, Sheik and Zelda, so excluding the two transform kinds is an exact test
that needs no MxDt lookup -- and therefore survives an m-ex core update, which
a pointer into MexData's heap would not.

Uses the pinned PowerPC assembler; generated machine code stays in build output.
"""
import os
import struct
import subprocess
import tempfile
from pathlib import Path

TOOLS = Path(os.environ['POKEMELEE_RUNTIME']) / 'powerpc-binutils/win-x64'
AS = TOOLS / 'powerpc-eabi-as.exe'
OBJCOPY = TOOLS / 'powerpc-eabi-objcopy.exe'


FTKIND_NANA = 11
FTKIND_SEAK = 7
FTKIND_ZELDA = 19

# addr -> (source register holding Fighter*, decomp symbol, what it gates)
SITES = {
    0x800A1040: (3,  "ftCo_800A101C+0x24",  "CPU AI type 6 + 15.0 follow leash"),
    0x800A13B4: (29, "ftCo_800A101C+0x398", "seed the 30-frame leader input log"),
    0x800A1748: (29, "ftCo_800A101C+0x72C", "follower reach constant (x56C = 1.0)"),
    0x800AA320: (3,  "ftCo_800AA320",       "stick deflection 0x40/0x7F"),
    0x800A0958: (31, "ftCo_800A08F0+0x68",  "crouch/fastfall CPU command script"),
}

# Popo's OnLoad is the only place that sets `has_follower` (x2222 & 0x04), the
# flag ftCo_800BFD9C reads to put the partner to sleep when the leader dies.
# A generic leader never gets it, so its partner would outlive it and the stock
# count would go wrong.  This hooks the branch we just took above -- reached
# only by a real follower -- and sets the bit on its LEADER, clearing it on
# itself so exactly one of the pair ever carries it.
#
# The leader is found by comparing this fighter against entity 0 rather than
# assumed to be entity 0. That was written for the D-pad-down swap, which could
# make entity 1 the leader; with the swap gone the follower is always entity 1,
# so the comparison always picks entity 0. The words are kept as accepted.
# r29 is the Fighter* here (r3 was clobbered two instructions earlier).
FOLLOWER_ARM = 0x800A105C
FOLLOWER_ARM_ASM = """
    li      0, 6
    stwu    1, -0x20(1)
    stw     10, 0x08(1)
    stw     11, 0x0C(1)
    stw     12, 0x10(1)
    lbz     11, 0xC(29)
    mulli   11, 11, 0xE90
    lis     12, 0x8045
    ori     12, 12, 0x3080
    add     11, 11, 12
    lwz     12, 0xB0(11)
    cmpwi   12, 0
    beq     1f
    lwz     10, 0x2C(12)
    cmplw   10, 29
    bne     3f
    lwz     12, 0xB4(11)
3:
    cmpwi   12, 0
    beq     1f
    lwz     12, 0x2C(12)
    cmpwi   12, 0
    beq     1f
    lbz     10, 0x2222(12)
    ori     10, 10, 4
    stb     10, 0x2222(12)
    lbz     10, 0x2222(29)
    andi.   10, 10, 0xFB
    stb     10, 0x2222(29)
1:
    lwz     12, 0x10(1)
    lwz     11, 0x0C(1)
    lwz     10, 0x08(1)
    addi    1, 1, 0x20
"""

# Both halves of a pair spawn at the player's spawn point plus
# `facing * ftCommon_800804EC(fp)`, which is `fp->x40 * scale`. Only Popo's and
# Nana's OnLoad set x40 (+5 and -5, read from PlPp.dat), so a generic pair stood
# in one spot, on every spawn and on the respawn platforms. This gives a follower
# whose x40 is still zero the Ice Climbers' 10-unit gap behind its leader. It is
# worked out from the master/slave bit on every call rather than stored in x40;
# the leader keeps its spawn point because when it spawns the follower does not
# exist yet. Standing still, the follower
# then closes onto its leader's exact spot within a second, as Nana does on Popo
# (measured in vanilla: -65 and -55 at Wait, both -55 by 150 frames later).
# The kind tests are TEMPLATE's: Sheik and Zelda set the bit when they transform.
FOLLOWER_SPAWN = 0x800804EC
FOLLOWER_SPAWN_GAP = -10.0
FOLLOWER_SPAWN_ASM = """
    lfs     1, 0x40(3)
    lbz     0, 0x221F(3)
    andi.   0, 0, 8
    beq     1f
    lwz     0, 4(3)
    cmpwi   0, {seak}
    beq     1f
    cmpwi   0, {zelda}
    beq     1f
    lwz     0, 0x40(3)
    cmpwi   0, 0
    bne     1f
    stwu    1, -0x10(1)
    lis     0, {gap_hi}
    stw     0, 0x08(1)
    lfs     1, 0x08(1)
    addi    1, 1, 0x10
1:
"""

# r0 is the destination at every site, and CR0 is dead here: the instruction
# right after the hook is the original `cmpwi r0, 11`, which rewrites it.  So
# this needs no scratch register and no stack frame.
TEMPLATE = """
    lbz     0, 0x221F({src})
    andi.   0, 0, 8
    lwz     0, 4({src})
    beq     1f
    cmpwi   0, {seak}
    beq     1f
    cmpwi   0, {zelda}
    beq     1f
    li      0, {nana}
1:
"""


# --- No leader swap ----------------------------------------------------------
#
# A D-pad-down swap of leader and follower used to hook Fighter_procUpdate at
# SWAP_HOOK, and a pair kept out of it had its alias entry lock the swap's
# cooldown. The owner removed it for every pair, the Ice Climbers included
# (2026-11-17); online it also split a match against vanilla Melee, which never
# swaps. install_project reads the finished codes.gct and `check_no_swap` fails
# the build if any code still hooks that address.
SWAP_HOOK = 0x8006B848


def check_no_swap(hooks) -> None:
    """Raise if `hooks`, the addresses a codes file patches, include SWAP_HOOK."""
    if SWAP_HOOK in set(hooks):
        raise RuntimeError(f"a code hooks {SWAP_HOOK:#010x}, where the removed "
                           "D-pad-down leader swap was")


# StaticPlayer, one block per port.
PLAYER_SLOTS = 0x80453080
PLAYER_STRIDE = 0xE90
ENTITY0 = 0xB0
PLAYER_TRANSFORMED = 0x0C  # two u8 indices: logical leader/follower -> entity slot


def _f32(value: float) -> int:
    """IEEE-754 single bits, so a float constant can be built with lis/ori.

    A Gecko code has no data section to `lfs` a literal out of, so a float is
    materialised as its bit pattern in a GPR, stored to the stack and loaded
    back (FOLLOWER_SPAWN's gap).
    """
    return struct.unpack(">I", struct.pack(">f", value))[0]


# Death and respawn use Player_GetEntityAtIndex(slot, logical_index), which
# already resolves transformed[], so the native logical follower index 1 is
# correct. Do not reintroduce the old 0x800BFE30 hook that passed a physical
# entity index to this logical lookup.


# --- Kind alias: let a pair's clone leader answer "which character am I?" ---
#
# A pair's leader is a DUPLICATE of its donor with a new internal kind, and
# Melee's character code asks `fp->kind == FTKIND_X` in ~130 places: Link's
# zair (`ftCo_AirCatch` refuses anyone but Link/Y.Link/Samus), Kirby's copy
# ability, Falcon/Ganon's flame (`ftLib_GetKind` switch), Fox/Falco, Marth/Roy,
# Pikachu/Pichu ... Patching every site is not tractable; rewriting the kind
# once, after the fighter is built, is. `fp->ft_data = gFtDataList[fp->kind]`
# runs at spawn (ft/fighter.c:729) and the costume/effects/sounds are already
# resolved by then, so from the first frame on the clone can carry its donor's
# kind and every vanilla check passes. The clone shares its data files with the
# donor by design (see pairs.build_pair_zip / MexFighter.Duplicate).
#
# Hooked at Fighter_procUpdate+4 (0x8006B84C, `lbz r0,0x221F(r3)`): r3 is the
# Fighter*, r0 is the instruction's own destination and CR0 is rewritten by
# the `rlwinm.` two instructions later, so no register needs saving.
#
# The original kind is stashed in ft_var51 (0x22F4) for anything that still
# needs the clone's real id: `player_kind_words` below, and the netplay probes,
# which read it to tell the two apart.
#
# Kirby copying a pair leader goes through the alias as well. A Kirby copy is
# keyed by the victim's `fp->kind` (`ftCo_800BD9E0`), which reads the aliased
# donor kind, so the copy runs the donor's vanilla path -- but only if the
# donor's cap is resident. Melee loads caps at match start for every present
# fighter and its sub-fighter by kind: `ftKb_SpecialN_800EEC34` queues the
# cap file (+ Kirby effect bank) from the DVD and `ftKb_SpecialN_800EED50`
# parses it into the hat table. Both are called with the CLONE's kind, which
# has no vanilla-table entry, so nothing was loaded and the copy hung the game
# the frame the swallow applied (measured 2026-09-15; copying the clone's
# real kind hung the same way). Aliasing the kind argument at the entry of
# those two functions loads the donor's cap instead, exactly as if the donor
# were in the match. m-ex leaves both entries unpatched (checked against the
# vanilla DOL), and the replaced instruction is the `mflr r0` prologue, so
# CR0/r0 are free.
#
# The HUD and the results screen must NOT get the alias. m-ex's gm_80168B34 hook
# picks a stock icon as `reserved + kind + stride * costume`, with `kind` from
# `Player_80036394(slot)`, which reads `fp->kind`: so every clone leader showed
# its DONOR'S stock, slot for slot (Plusle & Minun's first stock was yellow
# Pichu), and the same read fills the match-end standings the results screen
# draws from. Those two are the only callers that care: the other two only ask
# "is this Sheik?". So the fix is the function's own return, hooked at its exit
# (0x80036414, where the entity and no-entity paths meet; r31 is the slot and
# r3-r12 are dead) rather than at each caller. It answers with the stashed kind
# only when kind and stash are a pair from the alias table, because other code
# uses ft_var51 too (Echo's Tier-2 VAR_B) and a free slot reads 0.
#
# The (clone -> donor) table is per project, so these blocks are emitted by
# `engine_code.ensure_code` at export time with the words encoded here in
# Python -- no assembler in the shipped app.
ALIAS_HOOK = 0x8006B84C
ALIAS_HOOK_ORIG = 0x8803221F      # lbz r0,0x221F(r3)
FT_ORIG_KIND = 0x22F4             # ft_var51
KIRBY_CAP_PRELOAD_HOOK = 0x800EEC34   # ftKb_SpecialN_800EEC34(kind, costume, n): DVD preload
KIRBY_CAP_LOAD_HOOK = 0x800EED50      # ftKb_SpecialN_800EED50(kind, costume): parse into hats[]
KIRBY_CAP_HOOK_ORIG = 0x7C0802A6      # mflr r0 -- the prologue both functions start with
PLAYER_KIND_HOOK = 0x80036414         # Player_80036394's exit
PLAYER_KIND_HOOK_ORIG = 0x8001001C    # lwz r0,0x1C(r1)


def alias_words(aliases: dict[int, int]) -> list[int]:
    """Instruction words for the Fighter_procUpdate alias block."""
    words = [0x80030004]                         # lwz r0,4(r3)        fp->kind
    for clone, donor in sorted(aliases.items()):
        words += [0x2C000000 | (clone & 0xFFFF),  # cmpwi r0,clone
                  0x40820010,                     # bne past this entry
                  0x90030000 | FT_ORIG_KIND,      # stw r0,ft_var51(r3)  stash the clone kind
                  0x38000000 | (donor & 0xFFFF),  # li r0,donor
                  0x90030004]                     # stw r0,4(r3)         fp->kind = donor
    words.append(ALIAS_HOOK_ORIG)                # the replaced lbz
    return words


def kirby_cap_words(aliases: dict[int, int]) -> list[int]:
    """Instruction words for a cap-loader entry hook: r3 (the kind) becomes
    the donor for every clone, then the replaced `mflr r0` runs."""
    words = []
    for clone, donor in sorted(aliases.items()):
        words += [0x2C030000 | (clone & 0xFFFF),  # cmpwi r3,clone
                  0x40820008,                     # bne +8
                  0x38600000 | (donor & 0xFFFF)]  # li r3,donor
    words.append(KIRBY_CAP_HOOK_ORIG)
    return words


def player_kind_words(aliases: dict[int, int]) -> list[int]:
    """Instruction words for the Player_80036394 exit hook: an aliased fighter
    answers with the clone kind it stashed, then the replaced `lwz` runs."""
    table = []
    for clone, donor in sorted(aliases.items()):
        table += [0x2C040000 | (clone & 0xFFFF),   # cmpwi r4,clone
                  0x40820010,                      # bne +16
                  0x2C030000 | (donor & 0xFFFF),   # cmpwi r3,donor
                  0x40820008,                      # bne +8
                  0x7C832378]                      # mr r3,r4
    entity = [0x1C9F0000 | PLAYER_STRIDE,          # mulli r4,r31,stride
              0x3CA00000 | (PLAYER_SLOTS >> 16),   # lis r5,player_slots@h
              0x60A50000 | (PLAYER_SLOTS & 0xFFFF),  # ori r5,r5,player_slots@l
              0x7C842A14,                          # add r4,r4,r5
              0x88A40000 | PLAYER_TRANSFORMED,     # lbz r5,transformed[0](r4)
              0x54A5103A,                          # slwi r5,r5,2
              0x7C842A14,                          # add r4,r4,r5
              0x80840000 | ENTITY0,                # lwz r4,player_entity(r4)
              0x8084002C,                          # lwz r4,0x2C(r4)      gobj -> Fighter*
              0x80840000 | FT_ORIG_KIND]           # lwz r4,ft_var51(r4)
    skip = (len(entity) + len(table) + 1) * 4
    return ([0x2C030000,                           # cmpwi r3,0
             0x41800000 | skip]                    # blt past the table   -1: no entity
            + entity + table + [PLAYER_KIND_HOOK_ORIG])


def alias_ini_lines(aliases: dict[int, int]) -> list[str]:
    """Gecko C2 lines for a project's clone->donor table (all four hooks)."""
    if not aliases:
        return []
    out = []
    block = c2_block(ALIAS_HOOK, alias_words(aliases))
    out.append(f"{block[0]} #Fighter_procUpdate+4 -- clone leaders answer as their donor kind")
    out.extend(block[1:])
    block = c2_block(KIRBY_CAP_PRELOAD_HOOK, kirby_cap_words(aliases))
    out.append(f"{block[0]} #ftKb_SpecialN_800EEC34 -- preload the donor's Kirby cap for a clone")
    out.extend(block[1:])
    block = c2_block(KIRBY_CAP_LOAD_HOOK, kirby_cap_words(aliases))
    out.append(f"{block[0]} #ftKb_SpecialN_800EED50 -- load the donor's Kirby cap for a clone")
    out.extend(block[1:])
    block = c2_block(PLAYER_KIND_HOOK, player_kind_words(aliases))
    out.append(f"{block[0]} #Player_80036394 -- the HUD and results name the clone, not its donor")
    out.extend(block[1:])
    return out


def assemble(asm: str) -> list[int]:
    with tempfile.TemporaryDirectory() as td:
        src, obj, binf = Path(td) / "a.s", Path(td) / "a.o", Path(td) / "a.bin"
        src.write_text(asm)
        subprocess.run([str(AS), "-mregnames", "-mbig", "-mgekko",
                        "-o", str(obj), str(src)], check=True, capture_output=True)
        subprocess.run([str(OBJCOPY), "-O", "binary", str(obj), str(binf)],
                       check=True, capture_output=True)
        data = binf.read_bytes()
    return [int.from_bytes(data[i:i + 4], "big") for i in range(0, len(data), 4)]


def c2_block(addr: int, words: list[int]) -> list[str]:
    # Gecko C2: body is measured in 8-byte lines, so an odd instruction count
    # is padded with a 00000000 terminator (see the bundled m-ex codes).
    body = list(words)
    if len(body) % 2:
        body.append(0x00000000)
    else:
        body += [0x60000000, 0x00000000]
    lines = [f"C2{addr & 0x01FFFFFF:06X} {len(body) // 2:08X}"]
    for i in range(0, len(body), 2):
        lines.append(f"{body[i]:08X} {body[i + 1]:08X}")
    return lines


def build() -> str:
    out = ["$!GAMEPLAY | Any Climbers - Generic Follower AI [SSBM Nucleus]"]
    for addr, (src, sym, what) in SITES.items():
        asm = TEMPLATE.format(src=src, seak=FTKIND_SEAK,
                              zelda=FTKIND_ZELDA, nana=FTKIND_NANA)
        words = assemble(asm)
        block = c2_block(addr, words)
        out.append(f"{block[0]} #{sym} -- {what}")
        out.extend(block[1:])

    block = c2_block(FOLLOWER_ARM, assemble(FOLLOWER_ARM_ASM))
    out.append(f"{block[0]} #ftCo_800A101C+0x40 -- set has_follower on the leader")
    out.extend(block[1:])

    block = c2_block(FOLLOWER_SPAWN, assemble(FOLLOWER_SPAWN_ASM.format(
        seak=FTKIND_SEAK, zelda=FTKIND_ZELDA,
        gap_hi=hex(_f32(FOLLOWER_SPAWN_GAP) >> 16))))
    out.append(f"{block[0]} #ftCommon_800804EC -- a follower spawns behind its leader")
    out.extend(block[1:])

    return "\n".join(out) + "\n"
