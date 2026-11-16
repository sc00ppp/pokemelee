"""The complete fixed two-disc build, with local ISO and verified patch outputs."""
import json
import os
from pathlib import Path

from .catalog import art_indices
from .disc import Disc
from .export import export_artifacts, fingerprint
from .mex import Mex
from .parallel import Graph
from .runtime import lock
from .workspace import output_directory, receipt, write_json


def preflight(runtime):
    if os.name != 'nt':
        raise ValueError('No output written. Complete builds currently require Windows x64')
    from .stages import NATIVE_TOOLS
    runtime = Path(runtime).resolve()
    for name, tool in lock()['tools'].items():
        spec = tool['platforms'].get('win-x64')
        if not spec or tool.get('maintainer'):
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


def write_disc(assembled, melee, runtime, profile, output):
    """The version's ISO from its MEX project, checked file by file, and its xdelta against the user's Melee."""
    project = Path(assembled) / 'project/project.mexproj'
    built = Path(assembled) / 'built.iso'
    Mex(runtime, project, Path(assembled) / 'export-logs').command('export', built, timeout=1800)
    checks = verify_export(project, built, melee)
    write_json(Path(assembled) / 'export-checks.json', checks)
    return export_artifacts(melee.path, built, output,
                            xdelta=runtime / 'xdelta/win-x64' / lock()['tools']['xdelta']['platforms']['win-x64']['entrypoint'])


def build_all(melee, colosseum, output, runtime='runtime', profiles=('normal', 'animelee'), jobs=None, log=print):
    profiles = tuple(profiles)
    if not profiles or len(set(profiles)) != len(profiles) or set(profiles) - {'normal', 'animelee'}:
        raise ValueError('Expected distinct normal/animelee profiles')
    if jobs is not None and (not isinstance(jobs, int) or jobs < 1):
        raise ValueError('Character jobs must be a positive number (or left out: one per core)')
    runtime = preflight(runtime)
    from . import art, assembly, colors, costumes, icons, menu_sources, menus, model_patch
    from . import music, portraits, stage_pictures, stages, targets, voices, menu_sounds
    with output_directory(output, 'build') as root:
        work = root / 'components'
        work.mkdir()
        # every step starts once the steps it reads are built, so the shared steps, the stages and the two versions
        # run side by side (11-15)
        graph = Graph(work, log)
        step = graph.add
        donor_targets = step('melee-files', targets.melee_files, melee)
        characters = step('cast', model_patch.build_cast, melee, colosseum, runtime=runtime, jobs=jobs)
        source_art = step('stock-art', art.generate, colosseum, indices=art_indices())
        css = step('css-icons', icons.generate_icons, characters, donor_targets, runtime=runtime, profiles=profiles)
        alternates = step('colors', colors.build_colors, colosseum, characters)
        pictures = step('portraits', portraits.build_portraits, characters, donor_targets, runtime=runtime)
        alternate_pictures = step('color-portraits', portraits.build_color_portraits, colosseum, alternates,
                                  characters, donor_targets, pictures, runtime=runtime)
        menu_source = step('menu-sources', menu_sources.generate_menu_sources, colosseum, runtime=runtime)
        menu_files = step('menus', menus.build_menus, melee, menu_source, runtime=runtime)
        sound = step('voices', voices.build_voices, melee, colosseum, runtime=runtime)
        announcer = step('announcer', voices.build_announcer, melee, colosseum, runtime=runtime)
        effects = step('menu-sounds', menu_sounds.build_menu_sounds, melee, colosseum, runtime=runtime)
        songs = step('music', music.build_music, colosseum, runtime=runtime)
        discs = {}
        for profile in profiles:
            stage_files = step(profile + '-stages', stages.build_stages, melee, colosseum,
                               runtime=runtime, profile=profile)
            stage_images = step(profile + '-stage-pictures', stage_pictures.build_stage_pictures,
                                melee, [stage_files], runtime=runtime, profile=profile)
            packages = step(profile + '-costumes', costumes.package_costumes, characters, alternates,
                            pictures, alternate_pictures, source_art, donor_targets, profile=profile)
            components = {'costumes': packages, 'icons': css, 'stage-pictures': stage_images,
                          'stages': [stage_files], 'voices': sound, 'announcer': announcer,
                          'menu-sounds': effects, 'menus': menu_files, 'menu-sources': menu_source, 'music': songs}
            assembled = step(profile + '-project', assembly.build_project, melee, components,
                             runtime=runtime, profile=profile)
            discs[profile] = step(profile + '-disc', write_disc, assembled, melee, runtime, profile, output=root / profile)
        graph.run()
        outputs = [{'path': (root / profile / name).relative_to(root).as_posix(), **fingerprint(root / profile / name)}
                   for profile in profiles for name in ('pokemelee.iso', 'pokemelee.xdelta')]
        builds = {profile: disc.result for profile, disc in discs.items()}
        return receipt(root, 'build', {'melee': melee.info(True), 'colosseum': colosseum.info(True)},
                       outputs, profiles=list(profiles), builds=builds)
