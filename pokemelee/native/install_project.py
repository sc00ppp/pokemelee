"""Replay the final layout, music and gameplay settings on a new project."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'menus'))
from pokemelee.cast import checked_component
from pokemelee.mex import Mex
from pokemelee.native import follower_code, required_code, stock_tex
import css_grid
import css_doors
import main_colo
import sss_art
import sss_layout


def main():
    project, shots, music = map(Path, sys.argv[1:])
    mex = Mex(os.environ['POKEMELEE_RUNTIME'], project, project.parent / 'final-logs')
    icons = css_grid.straighten(mex, first='Plusle & Minun')
    sss_art.install(project.parent, shots)
    sss_layout.arrange(mex)
    mex.command('add-code', required_code.NAME, required_code.source())
    lines = follower_code.build().splitlines()
    name = lines.pop(0).removeprefix('$!')
    lines.extend(follower_code.alias_ini_lines({27: 23, 28: 23}, {28}))
    text = '\n'.join(line.split('#', 1)[0].strip() for line in lines if line.strip())
    mex.command('add-code', name, text)
    mex.command('add-code', main_colo.CODE_NAME, main_colo.code())
    css_doors.check_hooks(css_doors.gct_hooks((project.parent / 'files/codes.gct').read_bytes()), icons)
    mex.command('add-code', css_doors.CODE_NAME, css_doors.code(icons))
    mex.command('set-fighter-announcer-id', 'Plusle & Minun', 510009)
    record = json.loads((checked_component(music, 'music') / 'receipt.json').read_text())
    tracks = {Path(r['path']).stem: music / r['path'] for r in record['outputs']}
    for stage, song, title in (
        ('Agate Village', 'country_song', 'Agate Village'),
        ('Realgam Colosseum', 'tool_battle1_song', 'Colosseum Battle 1'),
        ('Phenac Stadium', 'tool_battle2_song', 'Colosseum Battle 2'),
        ('Mt. Battle Crater', 'tool_battle3_song', 'Colosseum Battle 3'),
        ('Mt. Battle Garden', 'battle8_song', 'Colosseum Battle (142)'),
        ('Phenac City', 'battle7_song', 'Colosseum Battle (146, long)'),
        (None, 'worldmap_song', 'Orre Map')):
        args = [tracks[song], title, 'stage', stage] if stage else [tracks[song], title, 'menu']
        result = mex.command('add-playlist-music', *args,
                             stdin=json.dumps([{'musicId': -1, 'chance': 100}]))
        if 'musicId' not in result:
            raise ValueError('Music did not import: ' + song)
    stock_tex.project(project.parent)
    mex.command('save')


if __name__ == '__main__':
    main()
