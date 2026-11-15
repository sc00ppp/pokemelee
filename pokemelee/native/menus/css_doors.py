"""Side doors on the VS character select (owner 2026-11-11: "like having the doors on the side and the chars in the
middle could go crazy" ... "i like the vertical but not the massive logo").

The four VS doors stand two a side: P1 top left, P2 top right, P3 bottom left, P4 bottom right; in VS the grid fills
the middle column, Melee-size icons five across (css_grid.vs_layout; owner: "make the icons bigger so they fill the
space"). 1P and Slippi online use their own one-door tree and keep Melee's straight rows from the file
(css_grid.straighten): every code change below checks the door count (0x804D6CF5, 1 in 1P / online, 4 in VS).

Two halves:
- the model (MnSlChr.usd, through menugraft's `moves`): each door's joints in MenuModel shifted by (dx, dy), with
  their translation keys, and its quarter of joint 85 (one joint, four door meshes on one shared buffer);
- the game code (one Gecko code, `code(icons)`), all in mncharsel (Melee 1.02), none on an m-ex or Slippi hook:
  * the "is the cursor on a door" test, which Melee does as a y band (y < 0.2 doors, 0.2..22 grid, > 22 top bar)
    at five places: in VS the doors are the two side columns, so each of those loads of 0.2 gets a threshold from
    the cursor's x instead (22 in a side column: all of it is door below the bar; -1000 in the middle: all grid);
  * the HMN/CPU and team buttons: their x per door from the door table (moved by dx), their y one range for every
    door, so the cursor y is taken into the door's own frame (y - dy) for the tests and the click's snap y gets +dy;
  * KO stars' x table (+dx), each cursor's start (on its own door), the cursor bounds widened to reach the doors;
  * the icons: every frame (cursor think) m-ex's icon table (pointer at 0x804DF9E0, Melee's 0x803F0A48 layout,
    boxes at +0xDC + 0x1C n) gets the VS boxes in VS and the file's boxes back otherwise (it lives on between
    scenes), and in VS the icon joints (root at 0x804D6F78, children in table order) get the VS place and size;
  * random: Melee's two boxes beside the bottom row, moved per mode to beside the last row.
Coordinates: the cursor's (the hand's tip is drawn at cursor + (5.1, -1)); icons are hit by the held coin, at
cursor + (2.7, -2), so icon boxes and the random boxes are in the coin's frame, which is the icons' own.

usage: from build_iso: css_doors.spec_moves() into the MnSlChr menugraft spec; after straighten,
       css_doors.install_code(proj, mexcli, icons)
       python css_doors.py code        prints the Gecko code for Melee's 25 icons in straight rows
"""

from menu_paths import SOURCE, FONTS, MENUGRAFT, DEVKIT
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

DEVKIT = DEVKIT
CODE_NAME = 'PokeMelee Side Doors (VS CSS)'

# door n: (dx, dy). Left column = Melee's door 1 moved 3 out, right column = its door 4 moved 3 out; the top doors sit
# under the top bar (bar bottom y 20.6), the bottom ones 1.5 lower than Melee's (screen bottom y -28.8).
DX = [-3.0, 33.8, -33.8, 3.0]
DY_TOP, DY_BOTTOM = 22.0, -1.5            # both exact in a float's high half (lis loads them): 0x41B00000, 0xBFC00000
DY = [DY_TOP, DY_TOP, DY_BOTTOM, DY_BOTTOM]

# MenuModel (TreeList index): each door's own joints under the shared group joints
FRAME_JOINTS = [41, 46, 51, 56]           # frame, CSP back, cover, team button; + door
SLIDERS = [61, 67, 73, 79]
KO_STARS = [87, 93, 99, 105]
NAME_PLATES = [112, 115, 116]             # + 5 * door (112: the name plate that slides up, TRAY keys)
HMN = [132, 140, 148, 156]                # the HMN/CPU/NA plate tree root of each door
TAGS = [165, 167, 169, 171]
BOTTOM_MESH = 85                          # dobj n = door n's bottom strip

# cursor-coordinate thresholds of the middle column, exact high-half floats. The grid's boxes are hit by the coin
# (cursor + 2.7), so the right edge is the grid's (18.8) minus 2.7, which reaches 2 units over the right doors' frame
# (their HMN plates still answer on the other 4 units); the left, the left doors' edge (-18.8 visual, cursor -24).
XL, XR = -24.0, 16.25
START = [(-34.0, 0.5), (17.5, 0.5), (-34.0, -23.0), (17.5, -23.0)]   # each port's start, over its own door
# cursor bounds (cursor coords; Melee x -35..26, y -22..25)
BOUNDS = {0x804DC498: -23.5, 0x804DC49C: 29.0, 0x804DC4A0: -38.0}

# Melee 1.02 data: per-door hit table (0x24 a door): toggle x lo/hi at +0x14/+0x18, team x lo/hi at +0x1C/+0x20
DOOR_TABLE = 0x803F0DFC
DOOR_TABLE_VANILLA = [(-35.6, -28.6, -26.8, -21.0), (-19.4, -13.4, -11.4, -6.0), (-4.2, 2.2, 3.5, 9.4),
                      (11.0, 17.0, 19.0, 24.6)]
KO_TABLE = 0x803F0F10                     # 0x20 a door, star x at +0
KO_VANILLA = [-22.5, -7.1, 8.3, 23.7]


def spec_moves():
    """menugraft `moves` for MnSlChr.usd"""
    out = []
    for n in range(4):
        joints = [j + n for j in FRAME_JOINTS] + [SLIDERS[n], KO_STARS[n]] + [j + 5 * n for j in NAME_PLATES] \
            + [HMN[n], TAGS[n]]
        out.append({'model': 'MenuModel', 'joints': joints, 'dobjs': [[BOTTOM_MESH, n]], 'dx': DX[n], 'dy': DY[n]})
    return out


def _hi(v):
    w = struct.unpack('>I', struct.pack('>f', v))[0]
    if w & 0xFFFF:
        raise ValueError(f'{v} is not exact in a float high half')
    return f'0x{w >> 16:04X}'


def _const(reg, v, tmp='r12', slot=0x18):
    w = struct.unpack('>I', struct.pack('>f', v))[0]
    load = [f'lis {tmp},0x{w >> 16:04X}'] + ([f'ori {tmp},{tmp},0x{w & 0xFFFF:04X}'] if w & 0xFFFF else [])
    return load + [f'stw {tmp},{slot:#x}(r1)', f'lfs {reg},{slot:#x}(r1)']


# The right doors' HMN/CPU plates (cursor x from 14.0, Melee's door table + dx) reach into the grid's right edge:
# there, at the plates' heights (Melee's -4.6..0.2 + dy), the door wins.
PLATE_X = 14.0
PLATE_TOP = (-4.6 + DY_TOP, 0.2 + DY_TOP)
PLATE_BOTTOM = (-4.6 + DY_BOTTOM, 0.2 + DY_BOTTOM)


VS_CHECK = ['lis r12,0x804D', 'lbz r12,0x6CF5(r12)', 'cmpwi r12,1']      # door count; 1 = 1P / Slippi online


def _band(ft):
    """threshold for 'y < it is a door' into ft (Melee: 0.2)"""
    return (['stwu r1,-0x30(r1)', 'stw r11,0x8(r1)', 'stw r12,0xc(r1)', 'stfd f13,0x10(r1)', 'mfcr r11',
             f'lfs {ft},-0x353c(r2)'] + VS_CHECK + ['beq 9f', 'lfs f13,0xc(r31)']
            + _const(ft, XL) + [f'fcmpo cr0,f13,{ft}', 'blt 8f']
            + _const(ft, XR) + [f'fcmpo cr0,f13,{ft}', 'bgt 8f']
            + _const(ft, PLATE_X) + [f'fcmpo cr0,f13,{ft}', 'blt 6f', 'lfs f13,0x10(r31)']
            + _const(ft, PLATE_TOP[0]) + [f'fcmpo cr0,f13,{ft}', 'bge 8f']
            + _const(ft, PLATE_BOTTOM[1]) + [f'fcmpo cr0,f13,{ft}', 'bgt 6f']
            + _const(ft, PLATE_BOTTOM[0]) + [f'fcmpo cr0,f13,{ft}', 'bge 8f']
            + [f'6: lis r12,{_hi(-1000.0)}', 'b 7f', f'8: lis r12,{_hi(22.0)}', f'7: stw r12,0x18(r1)', f'lfs {ft},0x18(r1)',
               '9: mtcrf 0xff,r11', 'lfd f13,0x10(r1)', 'lwz r12,0xc(r1)', 'lwz r11,0x8(r1)', 'addi r1,r1,0x30'])


def _dy_into_f13():
    """f13 = this door's dy (door index in r19: 0, 1 top, 2, 3 bottom)"""
    return [f'lis r12,{_hi(DY_TOP)}', 'cmpwi r19,2', 'blt 1f', f'lis r12,{_hi(DY_BOTTOM)}',
            '1: stw r12,0x18(r1)', 'lfs f13,0x18(r1)']


def _door_frame(original, op):
    """the original load into f0, then f0 op= dy (fsubs: cursor y into the door's frame; fadds: a snap y out of it)"""
    return ([original, 'stwu r1,-0x30(r1)', 'stw r12,0xc(r1)', 'stfd f13,0x10(r1)'] + _dy_into_f13()
            + [f'{op} f0,f0,f13', 'lfd f13,0x10(r1)', 'lwz r12,0xc(r1)', 'addi r1,r1,0x30'])


def _team_snap():
    return (['stwu r1,-0x30(r1)', 'stw r12,0xc(r1)', 'stfd f13,0x10(r1)'] + _dy_into_f13()
            + ['fadds f13,f28,f13', 'stfs f13,0x10(r31)', 'lfd f13,0x10(r1)', 'lwz r12,0xc(r1)', 'addi r1,r1,0x30'])


def _start(cursor_reg, original, out_y_reg):
    """the original instruction, then in VS: x and y of the cursor's port's start (x stored, y into f0 or stored).
    The port is the cursor's own byte (4(cursor)): at scene load the loop's r18 is already one less by the hook."""
    body = ['stwu r1,-0x30(r1)', 'stw r10,0x14(r1)', 'stw r11,0x8(r1)', 'stw r12,0xc(r1)', 'stfd f13,0x20(r1)',
            'mfcr r11', original] + VS_CHECK + ['beq 9f', f'lbz r12,4({cursor_reg})',
            'andi. r10,r12,1', f'lis r10,{_hi(START[0][0])}', 'beq 1f', f'lis r10,{_hi(START[1][0])}',
            '1: stw r10,0x18(r1)', 'lfs f13,0x18(r1)', f'stfs f13,0xc({cursor_reg})',
            'cmpwi r12,2', f'lis r10,{_hi(START[0][1])}', 'blt 2f', f'lis r10,{_hi(START[2][1])}',
            '2: stw r10,0x18(r1)']
    body += ['lfs f0,0x18(r1)'] if out_y_reg == 'f0' else ['lfs f13,0x18(r1)', f'stfs f13,0x10({cursor_reg})']
    body += ['9: mtcrf 0xff,r11', 'lfd f13,0x20(r1)', 'lwz r12,0xc(r1)', 'lwz r11,0x8(r1)', 'lwz r10,0x14(r1)',
             'addi r1,r1,0x30']
    return body


def _bits(v):
    return struct.unpack('>I', struct.pack('>f', v))[0]


def _load(reg, v):
    w = _bits(v)
    return [f'lis {reg},0x{w >> 16:04X}'] + ([f'ori {reg},{reg},0x{w & 0xFFFF:04X}'] if w & 0xFFFF else [])


def _mode_value(original, vs, solo=None):
    """the original `lfs f0,...`, then f0 = vs in VS and = solo (when given) with one door"""
    body = [original, 'stwu r1,-0x20(r1)', 'stw r12,0xc(r1)'] + VS_CHECK + ['beq 8f'] + _load('r12', vs) + ['b 7f']
    body += ['8:'] + (_load('r12', solo) if solo is not None else ['b 9f'])
    return body + ['7: stw r12,0x10(r1)', 'lfs f0,0x10(r1)', '9: lwz r12,0xc(r1)', 'addi r1,r1,0x20']


# Random: Melee picks a random fighter when a coin is dropped in the grid band inside one of two boxes beside its
# bottom row (coin y -1..6, x -30..-24.4 or 24.4..30.2; 0x80260A00..A54). Those sat beside Melee's 7-icon row; the
# rows here are wider, so the boxes move per mode to just beside the last row: in VS from the last row's top down
# (the side columns never get here, they are door), with one door Melee's y and x beyond the bottom row's ends.
def random_boxes(icons):
    """{hook address: (vs value, solo value or None)} for the six loads of the random test"""
    import css_grid
    s, vs_pos, rows = css_grid.vs_layout(len(icons))
    last = vs_pos[len(vs_pos) - rows[-1]:]
    hw, hh = css_grid.STEP_X / 2 * s, 7.2 / 2 * s
    vs_l, vs_r, vs_top = last[0][0] - hw, last[-1][0] + hw, last[0][1] + hh
    solo_rows = css_grid.rows_of(icons)
    bottom = [css_grid.box(ic) for ic in solo_rows[-1]]
    solo_l, solo_r = min(b[0] for b in bottom), max(b[1] for b in bottom)
    return {0x80260A00: (vs_top, None), 0x80260A18: (-1000.0, None), 0x80260A28: (-1000.0, -1000.0),
            0x80260A34: (vs_l, solo_l), 0x80260A40: (vs_r, solo_r), 0x80260A4C: (1000.0, 1000.0)}


RANDOM_LOADS = {0x80260A00: 'lfs f0,-0x3538(r2)', 0x80260A18: 'lfs f0,-0x3534(r2)', 0x80260A28: 'lfs f0,-0x3530(r2)',
                0x80260A34: 'lfs f0,-0x352c(r2)', 0x80260A40: 'lfs f0,-0x3528(r2)', 0x80260A4C: 'lfs f0,-0x3524(r2)'}

MEX_ICONS_PTR = 0x804DF9E0                # m-ex: its icon table (Melee's 0x803F0A48 layout) at runtime
MEX_ICON_ROOT = 0x804D6F78                # m-ex: the CSS icon model's root joint (children in table order)
LAYOUT_HOOK = 0x802602D4                  # cursor think, just after it saves r19..r31: free to use until it sets them


def _layout(icons):
    """each frame: the icon boxes for this mode, and in VS the icon joints' place and size"""
    import css_grid
    s, vs_pos, _rows = css_grid.vs_layout(len(icons))
    hw, hh = css_grid.STEP_X / 2 * s, 7.2 / 2 * s
    n = len(icons)
    data = [_bits(hw), _bits(hh), _bits(s), 0]
    for ic, (x, y) in zip(icons, vs_pos):
        data += [_bits(v) for v in css_grid.box(ic)] + [_bits(x), _bits(y)]
    hi, lo = (MEX_ICONS_PTR + 0x8000) >> 16, MEX_ICONS_PTR - (((MEX_ICONS_PTR + 0x8000) >> 16) << 16)
    rhi, rlo = (MEX_ICON_ROOT + 0x8000) >> 16, MEX_ICON_ROOT - (((MEX_ICON_ROOT + 0x8000) >> 16) << 16)
    return (['addi r26,r5,0xbc0',                                   # the original
             'lis r19,0x804D', 'lbz r19,0x6CF5(r19)',               # door count
             f'lis r20,0x{hi:04X}', f'lwz r20,{lo}(r20)', 'cmplwi r20,0', 'beq 9f', 'addi r20,r20,0xDC',
             'bl 1f'] + [f'.long 0x{w:08X}' for w in data] +
            ['1: mflr r21', 'lfs f2,0(r21)', 'lfs f3,4(r21)', 'lfs f4,8(r21)', 'addi r23,r21,0x10', 'mr r24,r20',
             f'li r22,{n}', 'mtctr r22', 'cmpwi r19,1', 'bne 4f',
             '3: lwz r0,0(r23)', 'stw r0,0xC(r24)', 'lwz r0,4(r23)', 'stw r0,0x10(r24)', 'lwz r0,8(r23)',
             'stw r0,0x14(r24)', 'lwz r0,0xC(r23)', 'stw r0,0x18(r24)', 'addi r23,r23,0x18', 'addi r24,r24,0x1C',
             'bdnz 3b', 'b 9f',
             '4: lfs f0,0x10(r23)', 'lfs f1,0x14(r23)', 'fsubs f5,f0,f2', 'stfs f5,0xC(r24)', 'fadds f5,f0,f2',
             'stfs f5,0x10(r24)', 'fadds f5,f1,f3', 'stfs f5,0x14(r24)', 'fsubs f5,f1,f3', 'stfs f5,0x18(r24)',
             'addi r23,r23,0x18', 'addi r24,r24,0x1C', 'bdnz 4b',
             f'lis r25,0x{rhi:04X}', f'lwz r25,{rlo}(r25)', 'cmplwi r25,0', 'beq 9f', 'lwz r25,0x10(r25)',
             'addi r23,r21,0x10', f'li r22,{n}', 'mtctr r22',
             '5: cmplwi r25,0', 'beq 9f', 'lfs f0,0x10(r23)', 'stfs f0,0x38(r25)', 'lfs f1,0x14(r23)',
             'stfs f1,0x3C(r25)', 'stfs f4,0x2C(r25)', 'stfs f4,0x30(r25)', 'lwz r0,0x14(r25)', 'ori r0,r0,0x40',
             'stw r0,0x14(r25)', 'addi r23,r23,0x18', 'lwz r25,0x8(r25)', 'bdnz 5b',
             '9:'])


def _start_reset():
    # 0x80260540: lfs f0,-21.5 (then the game's stfs f0,0x10(r31))
    return _start('r31', 'lfs f0,-0x3564(r2)', 'f0')


HOOKS = [
    (0x80260930, 'drop a coin on a door', lambda: _band('f0')),
    (0x80261F48, 'A picks a coin up', lambda: _band('f6')),
    (0x802620D8, 'B picks a coin up', lambda: _band('f0')),
    (0x80262158, 'entering the grid', lambda: _band('f0')),
    (0x802622B8, 'hand pose', lambda: _band('f0')),
    (0x80261A58, 'HMN button y test', lambda: _door_frame('lfs f0,0x10(r31)', 'fsubs')),
    (0x80261A70, 'HMN button snap y', lambda: _door_frame('lfs f0,-0x34f8(r2)', 'fadds')),
    (0x80261BA4, 'team button y test', lambda: _door_frame('lfs f0,0x10(r31)', 'fsubs')),
    (0x80261BB8, 'team button snap y', _team_snap),
    (0x80260540, 'cursor start on unplug', _start_reset),
    (0x80264D3C, 'cursor start at scene load', lambda: _start('r27', 'stfs f14,0x10(r27)', 'mem')),
]
# m-ex and Slippi patch these; nothing here may land on one (checked by check_hooks)
SLIPPI_HOOKS = {0x80260310, 0x802600A8, 0x80261E5C, 0x80262004, 0x802620AC, 0x80262478, 0x80262768, 0x80263258,
                0x80264534, 0x8026699C, 0x80266BC4}


def assemble(lines):
    with tempfile.TemporaryDirectory() as td:
        s, o, b = Path(td) / 'h.s', Path(td) / 'h.o', Path(td) / 'h.bin'
        s.write_text('.text\n' + '\n'.join(lines) + '\n', encoding='utf-8')
        r = subprocess.run([str(DEVKIT / 'powerpc-eabi-as.exe'), '-mregnames', '-mgekko', '-o', str(o), str(s)],
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stderr)
        subprocess.run([str(DEVKIT / 'powerpc-eabi-objcopy.exe'), '-O', 'binary', '-j', '.text', str(o), str(b)],
                       check=True)
        data = b.read_bytes()
    return [struct.unpack('>I', data[i:i + 4])[0] for i in range(0, len(data), 4)]


def c2(addr, words):
    body = list(words)
    if len(body) % 2 == 0:
        body.append(0x60000000)
    body.append(0x00000000)
    out = [f'C2{addr & 0x01FFFFFF:06X} {len(body) // 2:08X}']
    out += [f'{body[i]:08X} {body[i + 1]:08X}' for i in range(0, len(body), 2)]
    return out


def w32(addr, value):
    w = struct.unpack('>I', struct.pack('>f', value))[0] if isinstance(value, float) else value
    return f'04{addr & 0x01FFFFFF:06X} {w:08X}'


def all_hooks(icons):
    return (HOOKS + [(LAYOUT_HOOK, 'icon layout per mode', lambda: _layout(icons))]
            + [(a, 'random box', (lambda a=a, v=v: _mode_value(RANDOM_LOADS[a], *v)))
               for a, v in random_boxes(icons).items()])


def check_hooks(existing, icons):
    """existing: addresses other codes in the project hook (C2/04). Raises if a hook here lands on one."""
    clash = sorted({a for a, _, _ in all_hooks(icons)} & (set(existing) | SLIPPI_HOOKS))
    if clash:
        raise RuntimeError('side-door hooks clash with other codes at ' + ', '.join(hex(a) for a in clash))


def code(icons):
    """icons: the css layout's icons as m-ex stores them (css_grid.straighten's return), in its table order"""
    lines = []
    for addr, _what, body in all_hooks(icons):
        lines += c2(addr, assemble(body()))
    for n in range(4):
        base = DOOR_TABLE + 0x24 * n
        for k, v in enumerate(DOOR_TABLE_VANILLA[n]):
            lines.append(w32(base + 0x14 + 4 * k, round(v + DX[n], 4)))
        lines.append(w32(KO_TABLE + 0x20 * n, round(KO_VANILLA[n] + DX[n], 4)))
    for addr, v in BOUNDS.items():
        lines.append(w32(addr, v))
    return '\n'.join(lines)


def gct_hooks(gct):
    """addresses a codes.gct patches with C2 / 04 / 06 lines"""
    out, i = set(), 8
    while i + 8 <= len(gct):
        a, b = struct.unpack('>II', gct[i:i + 8])
        if a == 0xF0000000:
            break
        t = a >> 24
        addr = 0x80000000 | (a & 0x01FFFFFF)
        if t in (0xC2, 0xC3):
            out.add(addr)
            i += 8 + b * 8
            continue
        if t in (0x04, 0x05):
            out.add(addr)
        if t in (0x06, 0x07):
            out.add(addr)
            i += 8 + ((b + 7) // 8) * 8
            continue
        i += 8
    return out


def install_code(proj, mexcli, icons, log=print):
    gct = Path(proj).parent / 'files' / 'codes.gct'
    if gct.is_file():
        check_hooks(gct_hooks(gct.read_bytes()), icons)
    text = code(icons)
    r = subprocess.run([str(mexcli), 'add-code', str(proj), CODE_NAME, text], capture_output=True, text=True,
                       timeout=120)
    log(f'side doors code ({len(icons)} icons, {text.count(chr(10)) + 1} lines): {r.returncode} '
        f'{(r.stdout or r.stderr).strip()[-200:]}')
    if r.returncode:
        raise SystemExit('side doors code not added')


def melee_icons():
    """Melee's 25 icons in straight rows (9 / 9 / 7), for printing the code without a project"""
    import css_grid
    rows = [9, 9, 7]
    out = []
    for r, (m, y) in enumerate(zip(rows, css_grid.ROWS_Y)):
        for i in range(m):
            out.append({'x': css_grid.CENTRE_X + (i - (m - 1) / 2) * css_grid.STEP_X, 'y': y})
    return out


if __name__ == '__main__':
    if sys.argv[1:] == ['code']:
        print(code(melee_icons()))
