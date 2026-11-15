"""The complete fixed two-disc build, with local ISO and verified patch outputs."""
import json
import os
from pathlib import Path

from .catalog import art_indices
from .disc import Disc
from .export import export_artifacts, fingerprint
from .mex import Mex
from .runtime import lock
from .workspace import output_directory, receipt, write_json


def preflight(runtime):
    if os.name != 'nt':
        raise ValueError('No output written. Complete builds currently require Windows x64')
    from .stages import NATIVE_TOOLS
    runtime = Path(runtime).resolve()
    for name, tool in lock()['tools'].items():
        spec = tool['platforms'].get('win-x64')
        if not spec:
            continue
        path = runtime / name / 'win-x64'
        try:
            installed = json.loads((path / 'receipt.json').read_text())
        except (OSError, ValueError) as exc:
            raise ValueError(f'No output written. Install the pinned tool: {name}') from exc
        if installed.get('inputs', {}).get('sha256') != spec['sha256'] or any(not (path / p).is_file() for p in spec['required']):
            raise ValueError(f'No output written. Installed tool is incomplete or outdated: {name}')
    for flavor in NATIVE_TOOLS:
        if not (runtime / 'stagegraft' / flavor / f'stagegraft-{flavor}.dll').is_file():
            raise ValueError('No output written. Run compile-stages before building')
    for name in ('render', 'fxrender'):
        if not (runtime / 'audio' / (name + '.exe')).is_file():
            raise ValueError('No output written. Run compile-audio before building')
    return runtime


def verify_export(project, built_iso, melee):
    """Check installed models/media, not just whether MexCLI exited successfully."""
    import hashlib
    disc = Disc(built_iso, 'melee')
    project = Path(project)
    root = project.parent
    expected = json.loads((root.parent / 'installed-components.json').read_text())
    checks = []
    for row in expected:
        name = row['path']
        if hashlib.sha256(disc.read(name)).hexdigest() != row['sha256']:
            raise ValueError('Export changed an installed component: ' + name)
        checks.append(name)
    assembled = json.loads((root.parent / 'receipt.json').read_text())
    music = Path(assembled['inputs']['components']['music'])
    for row in json.loads((music / 'receipt.json').read_text())['outputs']:
        name = 'audio/' + Path(row['path']).name
        if hashlib.sha256(disc.read(name)).hexdigest() != row['sha256']:
            raise ValueError('Export changed an installed music track: ' + name)
        checks.append(name)
    mex_data = json.loads(project.read_text())
    for name in mex_data['fighterSaveMap']['filePaths']:
        fighter = json.loads((root / 'data/fighters' / name).read_text())
        for costume in fighter.get('costumes', []):
            file = costume['file']['fileName']
            if file not in disc.entries:
                raise ValueError('Export omitted a costume: ' + file)
            # Jigglypuff's exporter adds the per-slot hat root; other body data
            # must survive the project -> ISO copy exactly.
            if not file.startswith('PlPr') and disc.read(file) != (root / 'files' / file).read_bytes():
                raise ValueError('Export changed a costume: ' + file)
    # Keep the original bonus movie. Older ad-hoc builds replaced it for space.
    def digest_entry(source, name):
        row = source.entries[name]
        h = hashlib.sha256()
        with source.path.open('rb') as stream:
            stream.seek(row.offset)
            left = row.size
            while left:
                chunk = stream.read(min(left, 1024 * 1024))
                if not chunk:
                    raise ValueError('Truncated disc media')
                h.update(chunk)
                left -= len(chunk)
        return h.hexdigest()
    if digest_entry(disc, 'MvOmake15.mth') != digest_entry(melee, 'MvOmake15.mth'):
        raise ValueError('Export changed unrelated bonus movie media')
    return {'installed_components': checks, 'all_costumes_present': True, 'bonus_movie_preserved': True}


def build_all(melee, colosseum, output, runtime='runtime', profiles=('normal', 'animelee'), jobs=2, log=print):
    profiles = tuple(profiles)
    if not profiles or len(set(profiles)) != len(profiles) or set(profiles) - {'normal', 'animelee'}:
        raise ValueError('Expected distinct normal/animelee profiles')
    if not isinstance(jobs, int) or not 1 <= jobs <= 4:
        raise ValueError('Character jobs must be between 1 and 4')
    runtime = preflight(runtime)
    from . import art, assembly, cast, colors, costumes, icons, menu_sources, menus
    from . import models, music, portraits, stage_pictures, stages, targets, voices, menu_sounds
    with output_directory(output, 'build') as root:
        work = root / 'components'
        work.mkdir()
        def run(name, function, *args, **kwargs):
            log('Building ' + name, flush=True)
            out = work / name
            function(*args, output=out, **kwargs)
            return str(out)
        source_models = run('source-models', models.convert_models, colosseum, runtime=runtime)
        donor_targets = run('melee-targets', targets.prepare_targets, melee, runtime=runtime)
        characters = run('cast', cast.build_cast, colosseum, source_models, donor_targets, runtime=runtime, jobs=jobs)
        source_art = run('stock-art', art.generate, colosseum, indices=art_indices())
        css = run('css-icons', icons.generate_icons, source_models, characters, runtime=runtime, profiles=profiles)
        alternates = run('colors', colors.build_colors, colosseum, characters)
        pictures = run('portraits', portraits.build_portraits, characters, donor_targets, runtime=runtime)
        alternate_pictures = run('color-portraits', portraits.build_color_portraits, colosseum, alternates,
                                 characters, donor_targets, pictures, runtime=runtime)
        menu_source = run('menu-sources', menu_sources.generate_menu_sources, colosseum, runtime=runtime)
        menu_files = run('menus', menus.build_menus, melee, menu_source, runtime=runtime)
        sound = run('voices', voices.build_voices, melee, colosseum, runtime=runtime)
        announcer = run('announcer', voices.build_announcer, melee, colosseum, runtime=runtime)
        effects = run('menu-sounds', menu_sounds.build_menu_sounds, melee, colosseum, runtime=runtime)
        songs = run('music', music.build_music, colosseum, runtime=runtime)
        outputs, builds = [], {}
        for profile in profiles:
            stage_files = run(profile + '-stages', stages.build_stages, melee, colosseum,
                              runtime=runtime, profile=profile)
            stage_images = run(profile + '-stage-pictures', stage_pictures.build_stage_pictures,
                               melee, [stage_files], runtime=runtime, profile=profile)
            packages = run(profile + '-costumes', costumes.package_costumes, characters, alternates,
                           pictures, alternate_pictures, source_art, donor_targets, profile=profile)
            components = {'costumes': packages, 'icons': css, 'stage-pictures': stage_images,
                          'stages': [stage_files], 'voices': sound, 'announcer': announcer,
                          'menu-sounds': effects, 'menus': menu_files, 'menu-sources': menu_source, 'music': songs}
            assembled = run(profile + '-project', assembly.build_project, melee, components,
                            runtime=runtime, profile=profile)
            project = Path(assembled) / 'project/project.mexproj'
            built = Path(assembled) / 'built.iso'
            log('Exporting ' + profile + ' ISO', flush=True)
            Mex(runtime, project, Path(assembled) / 'export-logs').command('export', built, timeout=1800)
            checks = verify_export(project, built, melee)
            write_json(Path(assembled) / 'export-checks.json', checks)
            log('Creating and verifying ' + profile + ' xdelta', flush=True)
            result = export_artifacts(melee.path, built, root / profile,
                                      xdelta=runtime / 'xdelta/win-x64' / lock()['tools']['xdelta']['platforms']['win-x64']['entrypoint'])
            builds[profile] = result
            for name in ('pokemelee.iso', 'pokemelee.xdelta'):
                p = root / profile / name
                outputs.append({'path': p.relative_to(root).as_posix(), **fingerprint(p)})
        return receipt(root, 'build', {'melee': melee.info(True), 'colosseum': colosseum.info(True)},
                       outputs, profiles=list(profiles), builds=builds)
