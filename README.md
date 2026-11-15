# PokéMelee builder

Build PokéMelee locally from your own **Super Smash Bros. Melee USA v1.02**
(`GALE01`, revision 2) and **Pokémon Colosseum USA** (`GC6E01`, revision 0) discs.
This repository contains authored build code and recipes. It contains no game
ISOs, extracted Nintendo assets/code, edited model caches, or binary game patches.
The builder produces **both `pokemelee.iso` and `pokemelee.xdelta`**
locally. Generated game outputs are never uploaded to this repo or its releases.

**No AI runs during a build.** The program extracts the source data from the two
discs, applies fixed mappings and authored edits, and assembles the outputs.
No LLM, prompts, API keys, model downloads or newly generated rigging choices.
Once the tools are installed, the build runs offline.

**Status: both variants assemble, boot, and produce verified patches. The final
single-command cold build check is running.** The accepted Cast Test 30 and
AniMelee Test 23 are comparison references only. A normal build never reads them.

The fixed recipes regenerate all 29 characters, 102 alternate costumes, paired
portraits, character/stage menus, six stages, voices and music. The stage files,
source models, audio, menu source images and CSS icons match the accepted assets.
Twenty-seven base character exports match byte for byte. Pikachu and Scyther
retain the small documented conversion differences in `cast-finishing.json`.
The original Melee bonus movie is preserved.

## Dependencies live in their own repositories

| Dependency | Source of truth | Use here |
| --- | --- | --- |
| HSDRaw / HSDRawViewer | [ssbmNucleus-hsdlib](https://github.com/sc00ppp/ssbmNucleus-hsdlib) | DAT library, conversion and rendering |
| m-ex / MexCLI | [ssbmNucleus-mex](https://github.com/sc00ppp/ssbmNucleus-mex) | Project creation, imports and ISO export |
| xdelta3 | [xdelta-gpl](https://github.com/jmacd/xdelta-gpl) | Create and verify local patches |
| Blender 4.5.7 | [Blender](https://projects.blender.org/blender/blender) | Fixed headless source-model conversion |
| Blender 4.3.2 | [Blender](https://projects.blender.org/blender/blender) | Original Melee Collada target reader |
| Offline geometry helpers | [rigswap](https://github.com/sc00ppp/rigswap) at `ade3152` | Pure conversion functions; authoring imports disabled |
| Python 3.13.3 + bpy 5.2.2 | Official Python/PyPI distributions, pinned in the lockfile | Isolated character recipe runtime |
| GameCube model reader | [Blender-Addon-Gamecube-Models](https://github.com/StarsMmd/Blender-Addon-Gamecube-Models) | Read Colosseum models with the original converter |
| MusyX | [musyx](https://github.com/AxioDL/musyx) | Render disc-supplied songs and sound effects |
| Slippi Dolphin 3.6.4 | [Ishiiruka](https://github.com/project-slippi/Ishiiruka) | Automatically render stage-select pictures in an isolated offline profile |
| GNU PowerPC binutils 2.42 | [gc-wii-binutils](https://github.com/encounter/gc-wii-binutils) | Assemble the existing pair behavior and menu compatibility code |

**No fork code is copied into this repo.** `pokemelee/dependencies.lock.json`
links to exact release tags, filenames and SHA-256 checksums. Setup downloads
those releases directly from their original repositories. A fork change only
enters PokéMelee after its pin is deliberately updated and tested.

The current HSDRaw and MexCLI pins are `v2026.11.09.1`, inherited from the working
Nucleus tool manifests. MexCLI is already the console build; the MexManager GUI
is unnecessary here. Keep the current runtime intact until trimming is tested.
Stage/menu helpers can link HSDRaw.dll without carrying the viewer GUI source.

The fixed model reader needs Blender 4.5.7's geometry and glTF conversion APIs.
That converter runs headlessly with saved options; users do not operate Blender.
The package pins the exact official runtime and reader source archive.
The character migration preserves the accepted mappings, transforms, material
settings and corrections. Rigswap's authoring/agent pipeline is not a build step.
The character interpreter has its own pinned packages. It does not use a
Rigswap installation, project folder, user Python environment, or agent cache.
Its workers reject authoring imports and network connections. The 4.3.2 target
reader is separate because Blender 4.5.7 crashes on the original Melee Collada
meshes; the accepted target files are reproduced with 4.3.2.

Once the forks are public, setup needs no GitHub login. Until then, maintainers
can use `--github-auth` with an authenticated GitHub CLI. We do not change the
forks' visibility from this project. A later end-user package can include these
runtimes for convenience, without duplicating their source repositories.

## Build both variants

The complete builder currently supports **Windows x64**. Source setup needs
Python 3.11 or newer (tested with 3.13), the .NET 8 SDK, and Visual Studio C++
build tools. The pinned viewer and exporter carry their own runtimes. Automatic
portrait/stage rendering needs a working graphics driver and Windows desktop.
No controller input or manual emulator operation is required.

Install the Python dependencies and download the pinned tools once:

```powershell
python -m pip install ".[stages,presentation]"
python -m pokemelee fetch-tools --platform win-x64
python -m pokemelee compile-stages
python -m pokemelee compile-audio
```

For the current private forks:

```powershell
python -m pokemelee fetch-tools --platform win-x64 --github-auth
```

Use `--github-auth` on the fetch command while the fork releases are private.
Downloads go to ignored `runtime/<tool>/<platform>/` and are checked against the
lockfile before unpacking. `fetch-tools` also configures the isolated geometry
interpreter. It is safe to rerun after an interrupted download: complete pinned
installations are verified and reused. Once setup finishes, building does not
access the network.

Choose a new output directory on a drive with **at least 30 GB free** for the
intermediate projects, models and output copies. Then run:

```powershell
python -m pokemelee build --melee "path/to/original-melee.iso" --colosseum "path/to/original-colosseum.iso" --out "build/pokemelee"
```

The result contains:

```text
build/pokemelee/
  normal/pokemelee.iso
  normal/pokemelee.xdelta
  normal/receipt.json
  animelee/pokemelee.iso
  animelee/pokemelee.xdelta
  animelee/receipt.json
  receipt.json
  components/
```

Both versions build by default. Use `--profile normal` or `--profile animelee`
for one version. `--runtime PATH` selects an installed tool directory and
`--jobs 2` controls concurrent character conversions. The output directory must
be new; the builder never overwrites an earlier build. A failed component stops
the build and leaves its log and `failed.json`, without a success receipt.

Every finished ISO is read back to check installed costumes, stages, audio and
the preserved bonus movie. Each xdelta is decoded against the original Melee
disc and hash-compared with its ISO before the output pair is marked complete.

## Component commands

These commands are useful for development and diagnosing a failed component;
the full `build` command runs the required steps itself. A supplied tool ZIP
can be installed with `runtime-install NAME ARCHIVE --platform win-x64 --out DIR`.

```powershell
python -m pokemelee list --game colosseum --iso "path/to/colosseum.iso"
python -m pokemelee extract --game colosseum --iso "path/to/colosseum.iso" --file M1_out.fsys --unpack-fsys --out work/phenac-inputs
python -m pokemelee menu-art --colosseum "path/to/colosseum.iso" --out work/menu-art
python -m pokemelee plan
```

The stage generator uses the authored helpers compiled during setup:

```powershell
python -m pip install ".[stages]"
python -m pokemelee compile-stages
python -m pokemelee stages --melee "path/to/melee.iso" --colosseum "path/to/colosseum.iso" --profile normal --out work/normal-stages
python -m pokemelee stages --melee "path/to/melee.iso" --colosseum "path/to/colosseum.iso" --profile animelee --out work/animelee-stages
```

Each stage build extracts its own inputs into a new directory and verifies its
outputs against the reference fingerprints. It does not read either finished
PokéMelee ISO, old stage caches, or any Nucleus installation. The AniMelee recipes
include the accepted garden silhouette treatment and Phenac crest preservation.

The original source-model conversion is also verified for all 29 cast members.
Each generated GLB matches the original authoring input byte for byte.

```powershell
python -m pokemelee source-models --colosseum "path/to/colosseum.iso" --out work/source-models
```

Fixed character replay covers the complete accepted cast. These commands create
new directories and verify component receipts and final costume hashes.
Omitting `--pokemon` builds the entire cast; a failed recipe stops the build.

```powershell
python -m pokemelee setup-geometry --github-auth
python -m pokemelee melee-targets --melee "path/to/melee.iso" --out work/melee-targets
python -m pokemelee cast --colosseum "path/to/colosseum.iso" --models work/source-models --targets work/melee-targets --pokemon Magmar --pokemon Gardevoir --out work/cast
```

Audio generation also reads the two source discs directly. The verified outputs
are 25 fighter voice banks (551 replacements), the announcer bank (29 calls),
the six menu sound replacements, and all seven looping music tracks. Every
result matches the accepted desktop build. Source cries, sound banks, instrument
samples and rendered music remain local.

```powershell
python -m pokemelee compile-audio
python -m pokemelee voices --melee "path/to/melee.iso" --colosseum "path/to/colosseum.iso" --out work/voices
python -m pokemelee voices --announcer --melee "path/to/melee.iso" --colosseum "path/to/colosseum.iso" --out work/announcer
python -m pokemelee menu-sounds --melee "path/to/melee.iso" --colosseum "path/to/colosseum.iso" --out work/menu-sounds
python -m pokemelee music --colosseum "path/to/colosseum.iso" --out work/music
```

Compiling audio helpers currently requires Visual C++ build tools. The final
end-user package will carry the compiled helpers. Keep large work/output folders
on a drive with several GB free; runtime downloads use the destination drive.

## ISO and xdelta output

The export step can also package an already assembled local PokéMelee build:

```powershell
python -m pokemelee package --melee "path/to/original-melee.iso" --built-iso "path/to/built-pokemelee.iso" --out dist/pokemelee
```

It writes `pokemelee.iso`, `pokemelee.xdelta`, and `receipt.json`. The receipt
records the exact base Melee checksum, output hashes and xdelta tool identity.
The exporter decodes the patch back against that base and checks that the result
matches the built ISO before publishing the output pair. An unchanged vanilla
ISO, mismatched round trip, failed tool or existing output directory stops it.

Only the original **Melee** disc is the patch base; Colosseum supplied the content
during the build. The generated xdelta therefore contains imported Pokémon
content and stays local, just like the generated ISO. Neither output belongs in
Git, a GitHub release or CI artifacts. Sharing local outputs is a separate user
action; the builder never uploads them.

The Windows xdelta tool is pinned to upstream 3.1.0 and is fetched with the other
tools. On Linux/macOS, supply `--xdelta PATH` or install `xdelta3` on PATH until
platform bundles are prepared. Patches use standard VCDIFF without secondary
compression or local filename headers for broad decoder compatibility. See the
[upstream command reference](https://github.com/jmacd/xdelta/blob/main/site/docs/commandline.md).

The two-disc `build` calls this exporter automatically for each requested variant.

Output directories must be new. Each successful extraction/generation records
input and output hashes in a local receipt. Failures leave a failed receipt and
never count as complete. `check` validates the header and filesystem bounds;
`--hash` adds a full-disc fingerprint, not a claim that a disc is pristine.
Uncompressed ISO/GCM inputs are supported; RVZ inputs must be converted locally.

## Repository layout

- `pokemelee/`: standalone commands, disc/FSYS readers and asset generators.
- `pokemelee/recipes/cast.json`: accepted 25-fighter cast and the two pairs.
- `pokemelee/recipes/stages/`: authored graft settings for six approved stages.
- `pokemelee/recipes/pipeline.json`: exact remaining work, consumed by `plan`.
- `pokemelee/dependencies.lock.json`: external runtime links and checksums.
- `tests/`: synthetic fixtures; no game files needed for CI.
- `work/`, `runtime/`, `dist/`: local generated data, excluded from Git.

Both finished builds are targets: **normal Cast Test 30** and **AniMelee Test 23**.
The desktop ISOs are verification references; the user still provides only the
original Melee and Colosseum discs. Both variants must produce an ISO and xdelta.
AniMelee's custom outline treatment is preserved by its existing recipes.

## Development checks

```powershell
python -m unittest discover -s tests -v
python tools/check_source.py
```

Set `POKEMELEE_TEST_XDELTA=1` to include a real patch round trip using synthetic
disc fixtures. CI runs it on Windows and Linux; no game data is needed.

See [BUILD_PLAN.md](BUILD_PLAN.md) for the remaining conversion work and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for dependency provenance.
