# PokéMelee builder

Build PokéMelee locally from your own **Super Smash Bros. Melee USA v1.02**
(`GALE01`, revision 2) and **Pokémon Colosseum USA** (`GC6E01`, revision 0) discs.
This repository contains authored build code and recipes. It contains no game
ISOs, extracted Nintendo assets/code, edited model caches, or binary game patches.
The finished builder must produce **both `pokemelee.iso` and `pokemelee.xdelta`**
locally. Generated game outputs are never uploaded to this repo or its releases.

**Status: repository preparation is underway; the complete two-ISO build is not
ready yet.** Disc extraction and stock/fallback menu-icon generation work. The
accepted cast and all six stage graft specs are recorded. The old Cast Test 30
assembler still depends on edited Blender files and generated DAT/PNG/audio
caches; those must become recipes before this is an end-user builder.
`build` currently fails with the remaining steps and writes no ISO.

## Dependencies live in their own repositories

| Dependency | Source of truth | Use here |
| --- | --- | --- |
| HSDRaw / HSDRawViewer | [ssbmNucleus-hsdlib](https://github.com/sc00ppp/ssbmNucleus-hsdlib) | DAT library, conversion and rendering |
| m-ex / MexCLI | [ssbmNucleus-mex](https://github.com/sc00ppp/ssbmNucleus-mex) | Project creation, imports and ISO export |
| xdelta3 | [xdelta-gpl](https://github.com/jmacd/xdelta-gpl) | Create and verify local patches |
| rigswap + Blender | Shared rigswap engine; exact compatible pin still being resolved | Deterministic costume generation |

**No fork code is copied into this repo.** `pokemelee/dependencies.lock.json`
links to exact release tags, filenames and SHA-256 checksums. Setup downloads
those releases directly from their original repositories. A fork change only
enters PokéMelee after its pin is deliberately updated and tested.

The current HSDRaw and MexCLI pins are `v2026.11.09.1`, inherited from the working
Nucleus tool manifests. MexCLI is already the console build; the MexManager GUI
is unnecessary here. Keep the current runtime intact until trimming is tested.
Stage/menu helpers can link HSDRaw.dll without carrying the viewer GUI source.

Once the forks are public, setup needs no GitHub login. Until then, maintainers
can use `--github-auth` with an authenticated GitHub CLI. We do not change the
forks' visibility from this project. A later end-user package can include these
runtimes for convenience, without duplicating their source repositories.

## Working commands

Python 3.11 or newer. For menu art, install the optional dependencies:

```powershell
python -m pip install ".[art]"
python -m pokemelee check --melee "path/to/melee.iso" --colosseum "path/to/colosseum.iso"
python -m pokemelee fetch-tools --platform win-x64
```

For the current private forks:

```powershell
python -m pokemelee fetch-tools --platform win-x64 --github-auth
```

Downloads go to ignored `runtime/<tool>/<platform>/`. They are verified before
unpacking; there is no fallback to a moving `latest` version. A supplied ZIP
can also be checked with `runtime-install NAME ARCHIVE --platform win-x64 --out DIR`.

```powershell
python -m pokemelee list --game colosseum --iso "path/to/colosseum.iso"
python -m pokemelee extract --game colosseum --iso "path/to/colosseum.iso" --file M1_out.fsys --unpack-fsys --out work/phenac-inputs
python -m pokemelee menu-art --colosseum "path/to/colosseum.iso" --out work/menu-art
python -m pokemelee plan
```

## ISO and xdelta output

The local export step already works independently of the unfinished assembler.
It can package an existing local PokéMelee build:

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

The final two-disc `build` must call this exporter automatically; it is still
blocked on the character/stage/assembly work listed by `plan`.

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

The initial profile is ordinary PokéMelee. AniMelee's lined variants are separate
recipes; replacing their custom outline treatment with a generic filter would
change the approved look.

## Development checks

```powershell
python -m unittest discover -s tests -v
python tools/check_source.py
```

Set `POKEMELEE_TEST_XDELTA=1` to include a real patch round trip using synthetic
disc fixtures. CI runs it on Windows and Linux; no game data is needed.

See [BUILD_PLAN.md](BUILD_PLAN.md) for the remaining conversion work and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for dependency provenance.
