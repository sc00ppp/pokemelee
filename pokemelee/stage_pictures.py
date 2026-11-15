"""Reproduce stage-select pictures using a pinned, isolated offline renderer."""
import io
import json
from pathlib import Path
import subprocess
import time

from PIL import Image

from .assembly import copy_outputs
from .export import fingerprint
from .mex import Mex
from .workspace import output_directory, receipt

FRAMING = {
    'battlefield': (31, (0, 35.7, 189.5), (0, 29.7, 0)),
    'finaldestination': (32, (0, 14, 237.1), (0, 8, 0)),
    'dreamland': (28, (0, 34.2, 214.1), (0, 28.2, 0)),
    'yoshisstory': (8, (0, 29.5, 201.7), (0, 23.5, 0)),
    'fountainofdreams': (2, (0, 29.9, 175.3), (0, 23.9, 0)),
    'pokemonstadium': (3, (0, 65, 310), (0, 8, 0)),
}
CLEAN_PATCHES = ((0x80030384, 0x60000000), (0x800872F8, 0x38600000),
                 (0x800304C4, 0x60000000), (0x8005A634, 0x48000094),
                 (0x802275F8, 0x480000F0), (0x80030E44, 0x4E800020))


def wait_for(predicate, seconds, message):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.08)
    raise ValueError(message)


def capture(iso, renderer, output, stage):
    from .native.capture import boot, match_setup, memory_input, nav, observe, screenshot_win
    from .native.capture.melee_mem import Dolphin
    internal, eye, interest = FRAMING[stage]
    output.mkdir(parents=True)
    user = output / 'User'
    user.mkdir()
    boot._patch_dolphin_ini(str(user), 'unused', render_size=(1280, 960))
    boot._patch_logger_ini(str(user))
    boot._patch_hotkeys(str(user))
    boot._patch_clean_osd(str(user))
    def graphics(upsert, _):
        for name, value in {'AspectRatio': 0, 'ShowFPS': 'False', 'ShowNetPlayPing': 'False',
                            'ShowNetPlayMessages': 'False', 'EFBScale': 7, 'MSAA': 8, 'SSAA': 'True'}.items():
            upsert('Settings', name, value)
        upsert('Enhancements', 'MaxAnisotropy', '4')
    boot._write_ini(str(user / 'Config/GFX.ini'), graphics)
    def config(upsert, _):
        upsert('Core', 'GFXBackend', 'D3D')
        upsert('Core', 'SlippiJukeboxEnabled', 'False')
        upsert('Core', 'EmulationSpeed', '1')
        upsert('DSP', 'Backend', 'No audio output')
        upsert('DSP', 'Volume', '0')
        upsert('Core', 'SlotA', '0')
        upsert('Core', 'SlotB', '0')
        upsert('Display', 'RenderWindowXPos', '0')
        upsert('Display', 'RenderWindowYPos', '0')
    boot._write_ini(str(user / 'Config/Dolphin.ini'), config)
    memory_input.prepare(user, iso)
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 4  # show without activating; input is process-local memory
    with (output / 'renderer.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([str(renderer), '-b', '-e', str(iso), '-u', str(user)],
                                   cwd=renderer.parent, stdout=log, stderr=subprocess.STDOUT,
                                   startupinfo=startup)
        d = pad = None
        try:
            d = Dolphin(process.pid)
            wait_for(lambda: d.locate() if process.poll() is None else False, 45, 'Renderer did not boot Melee')
            address = wait_for(lambda: memory_input.mailbox_address(d), 30, 'Renderer input did not initialize')
            pad = memory_input.MemoryInput(d, address)
            # Patch before the first match compiles these functions into JIT code.
            for at, value in CLEAN_PATCHES:
                d.write_u32(at, value)
            if not nav.nav_to_css(d, pad, timeout=60, log=lambda s: print(stage, s, flush=True)):
                raise ValueError('Renderer could not reach the offline character select')
            observe.wait_game_frames(d, 120)
            if not match_setup.patch_one_player(d):
                raise ValueError('Renderer solo-stage setup failed')
            match_setup.force_time_infinite(d)
            match_setup.write_solo_player(d, 2)
            match_setup.warp_to_stage_select(d)
            wait_for(lambda: d.u8(0x80479D30) == 2 and d.u8(0x80479D33) == 1,
                     15, 'Renderer did not reach stage select')
            match_setup.write_solo_player(d, 2)
            table = wait_for(lambda: d.u32(0x804D6C90), 10, 'Stage select table missing')
            if not 0x80000000 <= table < 0x81800000:
                raise ValueError('Invalid stage select table')
            d.write_s8(table + 3, internal)
            if not observe.wait_in_game(d, timeout=40) or not observe.wait_game_frames(d, 240):
                raise ValueError('Generated stage did not finish loading')
            # Accepted clean-shot modifications are confined to this renderer's RAM.
            for _ in range(25):
                for at, value in CLEAN_PATCHES:
                    d.write_u32(at, value)
                d.write_u8(0x804D6D58, 1)
                d.write_u32(0x80452C6C, 8)
                for at, vector in ((0x80453040, interest), (0x8045304C, eye)):
                    for axis, value in enumerate(vector):
                        d.write_f32(at + axis * 4, value)
                d.write_f32(0x80453058, 40)
                d.write_f32(0x80452C78, 16384)
                time.sleep(.02)
            picture = screenshot_win.capture_via_printwindow(process.pid, max_width=1280)
            if not picture:
                raise ValueError('Renderer returned no stage picture')
            im = Image.open(io.BytesIO(picture))
            if im.size != (1280, 960):
                raise ValueError(f'Unexpected stage render size: {im.size}')
            return picture
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=8)
            if d is not None:
                d.close()


def build_stage_pictures(melee, stages, output, runtime, profile='normal', selected=None):
    names = list(selected or FRAMING)
    if not names or len(set(names)) != len(names) or set(names) - FRAMING.keys():
        raise ValueError('Unknown or duplicate stage picture selection')
    runtime = Path(runtime).resolve()
    renderer = runtime / 'stage-renderer/win-x64/Slippi Dolphin.exe'
    if not renderer.is_file():
        raise ValueError('Install the pinned stage renderer')
    with output_directory(output, 'stage-pictures') as root:
        project = root / 'render-project/project.mexproj'
        mex = Mex(runtime, project, root / 'logs')
        mex.command('create', melee.path, project.parent, 'Pokemelee stage pictures', project=False, timeout=1800)
        for component in stages:
            copy_outputs(component, 'stages', project.parent / 'files', '.dat')
            copy_outputs(component, 'stages', project.parent / 'files', '.usd')
        iso = root / 'render.iso'
        mex.command('export', iso, timeout=1800)
        outputs = []
        for stage in names:
            picture = capture(iso, renderer, root / 'capture' / stage, stage)
            target = root / (stage + '.png')
            target.write_bytes(picture)
            outputs.append({'stage': stage, 'path': target.name, **fingerprint(target)})
        return receipt(root, 'stage-pictures', {'melee': melee.info(), 'stages': stages},
                       outputs, profile=profile)
