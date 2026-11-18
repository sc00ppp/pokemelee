"""Assemble generated components through the pinned standalone m-ex tool."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from . import fighter_metal, rest_values
from .cast import checked_component
from .catalog import PACKAGE, load
from .export import fingerprint
from .mex import Mex
from .portraits import CODES
from .workspace import output_directory, receipt, write_json

PAIR = 'Plusle & Minun'
PARTNER = 'Minun'


def team_slots(spec, colours, fighter):
    """Red/blue/green costume index of a mon: the slot its recolour recipe's teams name (by default the colour named
    after the team), else 0. Slippi's online Teams mode gives each player that index from each client's own table, so
    where recipes/rest-values.json lists vanilla's indices for the fighter, they must be the same."""
    slots = {colour: i for i, colour in enumerate(colours)}
    teams = {team: slots.get(spec.get('teams', {}).get(team, team), 0) for team in ('red', 'blue', 'green')}
    vanilla = rest_values.team_indices(fighter)
    wrong = {team: teams[team] for team, k in vanilla.items() if teams[team] != k}
    if wrong:
        raise ValueError(f'{fighter}: Teams costume indices {wrong} differ from vanilla\'s {vanilla}; Slippi\'s online '
                         'Teams mode would load another joint tree on each side (recipes/rest-values.json, teams)')
    return teams


def install_costumes(mex, package):
    """Append all rebuilt slots in one import, then remove only the original slots."""
    record = json.loads((package / 'receipt.json').read_text())
    costumes = record['costumes']
    originals = mex.fighters()
    by_code = {d['costumes'][0]['file']['fileName'][2:4]: i for i, (_, d) in enumerate(originals)
               if d.get('costumes') and d['costumes'][0]['file']['fileName'].startswith('Pl')}
    # Clone while Pichu still has the disc's own costumes; each clone owns its files.
    clones = {}
    for name in (PARTNER, PAIR):
        result = mex.command('duplicate-fighter', by_code['Pc'], '--name', name, '--json')
        if result.get('missingFiles'):
            raise ValueError(f'Incomplete donor for {name}: {result["missingFiles"]}')
        clones[name] = result['internalId']
    fs = mex.fighters()
    if clones != {PARTNER: 27, PAIR: 28}:
        raise ValueError('The pinned roster layout changed')
    assigned = {mon: (clones[PAIR] if mon == 'Plusle' else clones[PARTNER] if mon == 'Minun'
                      else by_code[CODES[rows[0]['fighter']]]) for mon, rows in costumes.items()}
    add, remove, gone = {}, {}, set()
    for mon, index in assigned.items():
        prior = fs[index][1]['costumes']
        add[str(index)] = [str(package / row['path']) for row in costumes[mon]]
        remove[str(index)] = list(range(len(prior)))
        gone.update(c['file']['fileName'] for c in prior)
    result = mex.batch('import-costumes', add)
    expected = sum(map(len, add.values()))
    if result.get('totalImported') != expected:
        raise ValueError(f'Expected {expected} imported costumes: {result}')
    mex.batch('remove-costumes', remove)
    specs = load('recolors.json')
    fs = mex.fighters()
    for mon, index in assigned.items():
        file, data = fs[index]
        rows = costumes[mon]
        if len(data['costumes']) != len(rows):
            raise ValueError(f'{mon}: incorrect installed costume count')
        teams = team_slots(specs[mon], [row['color'] for row in rows], rows[0]['fighter'])
        data.update({team + 'CostumeIndex': slot for team, slot in teams.items()})
        for costume, row in zip(data['costumes'], rows):
            costume['name'] = mon + (' (Colosseum)' if row['color'] == 'default' else ' ' + row['color'].title())
        if mon in ('Plusle', 'Minun'):
            data['subCharacter'] = clones[PARTNER] if mon == 'Plusle' else by_code['Pc']
            data['subCharacterBehavior'] = 0
        file.write_text(json.dumps(data, indent=2), encoding='utf-8')
    for a, b in (('Jynx', 'Smoochum'), ('Plusle', 'Minun'), ('Alakazam', 'Sceptile')):
        if [r['color'] for r in costumes[a]] != [r['color'] for r in costumes[b]]:
            raise ValueError(f'{a}/{b} costume slots do not align')
    mex.command('save')
    return assigned, gone


def copy_outputs(component, operation, files, suffix=None):
    component = checked_component(component, operation)
    record = json.loads((component / 'receipt.json').read_text())
    copied = []
    for row in record['outputs']:
        source = component / row['path']
        if suffix and source.suffix != suffix:
            continue
        relative = Path(row['path'])
        if relative.parts[0] != 'files':
            raise ValueError(f'Unexpected component file: {relative}')
        target = files.joinpath(*relative.parts[1:])
        if not target.resolve().is_relative_to(files.resolve()):
            raise ValueError('Component escaped project files')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied.append({'path': target.relative_to(files).as_posix(), **fingerprint(target)})
    return copied


def build_project(melee, components, output, runtime, profile='normal'):
    """Create an independent project. Its ISO is exported only after validation."""
    runtime = Path(runtime).resolve()
    package = checked_component(components['costumes'], 'costume-packages')
    if json.loads((package / 'receipt.json').read_text())['profile'] != profile:
        raise ValueError('Costumes have the wrong profile')
    icons = checked_component(components['icons'], 'css-icons')
    shots = checked_component(components['stage-pictures'], 'stage-pictures')
    checked_component(components['music'], 'music')
    checked_component(components['menu-sources'], 'menu-sources')
    with output_directory(output, 'assembled-project') as root:
        project = root / 'project/project.mexproj'
        mex = Mex(runtime, project, root / 'logs')
        mex.command('create', melee.path, project.parent, 'Pokemelee', project=False, timeout=1800)
        assigned, gone = install_costumes(mex, package)
        # Every icon in one MexCLI run: one workspace open and one Save, the PNGs decoded side by side. The
        # icons are set in this order, so the project is what one set-css-icon call per mon left.
        names = {'Jynx': 'jynx-smoochum', 'Plusle': 'plusle-minun'}
        mex.batch('set-css-icons', {str(index): str(icons / profile / ('css-' + names.get(mon, mon.lower()) + '.png'))
                                    for mon, index in assigned.items() if mon not in ('Smoochum', 'Minun')})
        layout = mex.get_css_layout()
        selected = [ic for ic in layout['icons'] if ic.get('fighterName') != PARTNER]
        if len(selected) != 26:
            raise ValueError(f'Expected 26 selectable fighters, found {len(selected)}')
        for icon in selected:
            if icon.get('fighterName') == PAIR:
                icon.update(x=28.25, y=2.3, z=0)
        mex.set_css_layout(json.dumps({'template': layout['template'], 'icons': selected}))
        files = project.parent / 'files'
        # Metal Box and Cloaking Device: the cast's fighter files (pair partners and clones included) draw the
        # costume, not the vanilla metal model; the export check below proves the patched files reach the disc.
        fighters = mex.fighters()
        installed = fighter_metal.patch_fighter_files(
            files, [fighters[index][1]['files']['fighterDataPath'] for index in set(assigned.values())])
        for stages in components['stages']:
            installed.extend(copy_outputs(stages, 'stages', files, '.dat'))
            installed.extend(copy_outputs(stages, 'stages', files, '.usd'))
        for key, operation in (('voices', 'voices'), ('announcer', 'announcer'), ('menu-sounds', 'menu-sounds')):
            installed.extend(copy_outputs(components[key], operation, files, '.ssm'))
        copy_outputs(components['menus'], 'menus', files)
        env = {**os.environ, 'POKEMELEE_MENU_SOURCE': str(Path(components['menu-sources']).resolve()),
               'POKEMELEE_RUNTIME': str(runtime), 'PYTHONUTF8': '1'}
        with (root / 'menus-install.log').open('w', encoding='utf-8') as log:
            subprocess.run([sys.executable, str(PACKAGE / 'native/install_project.py'),
                            str(project), str(shots), str(Path(components['music']).resolve())],
                           env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1800)
        # Remove unreferenced replaced costumes and Kirby cap variants only in
        # this newly created project. Preserve unrelated disc media.
        named = set(re.findall(r'[\w.-]+\.dat', ' '.join(p.read_text() for p, _ in mex.fighters())))
        for name in gone | {p.name for p in files.glob('PlKb??Cp*.dat')}:
            if name not in named and not name.startswith('PlPr'):
                target = (files / name).resolve()
                if not target.is_relative_to(files.resolve()):
                    raise ValueError('Costume cleanup escaped project files')
                target.unlink(missing_ok=True)
        write_json(root / 'installed-components.json', installed)
        outputs = [{'path': 'project/project.mexproj', **fingerprint(project)}]
        return receipt(root, 'assembled-project', {'melee': melee.info(), 'components': components},
                       outputs, profile=profile, project='project/project.mexproj', assigned=assigned)
