# PokéMelee builder

Build PokéMelee locally from your own **Super Smash Bros. Melee USA v1.02**
(`GALE01`, revision 2) and **Pokémon Colosseum USA** (`GC6E01`, revision 0) discs.
This repository contains authored build code and recipes. It contains no game
ISOs, extracted Nintendo assets/code, edited model caches, or binary game patches.
The finished builder must produce **both `pokemelee.iso` and `pokemelee.xdelta`**
locally. Generated game outputs are never uploaded to this repo or its releases.

**No AI runs during a build.** The program extracts the source data from the two
discs, applies fixed mappings and authored edits, and assembles the outputs.
No LLM, prompts, API keys, model downloads or newly generated rigging choices.
Once the tools are installed, the build must work offline.

**Status: repository preparation is underway; the complete two-ISO build is not
ready yet.** Disc extraction, stock/fallback menu-icon generation, and all six
stages in both versions work. All 22 stage files rebuilt from the original discs
match the normal Cast Test 30 and AniMelee Test 23 references byte for byte.
The accepted cast is recorded. The old Cast Test 30
assembler still depends on edited Blender files and generated DAT/PNG/audio
caches; those must become recipes before this is an end-user builder.
`build` currently fails with the remaining steps and writes no ISO.

## Dependencies live in their own repositories

| Dependency | Source of truth | Use here |
| --- | --- | --- |
| HSDRaw / HSDRawViewer | [ssbmNucleus-hsdlib](https://github.com/sc00ppp/ssbmNucleus-hsdlib) | DAT library, conversion and rendering |
| m-ex / MexCLI | [ssbmNucleus-mex](https://github.com/sc00ppp/ssbmNucleus-mex) | Project creation, imports and ISO export |
| xdelta3 | [xdelta-gpl](https://github.com/jmacd/xdelta-gpl) | Create and verify local patches |

**No fork code is copied into this repo.** `pokemelee/dependencies.lock.json`
links to exact release tags, filenames and SHA-256 checksums. Setup downloads
those releases directly from their original repositories. A fork change only
enters PokéMelee after its pin is deliberately updated and tested.

The current HSDRaw and MexCLI pins are `v2026.11.09.1`, inherited from the working
Nucleus tool manifests. MexCLI is already the console build; the MexManager GUI
is unnecessary here. Keep the current runtime intact until trimming is tested.
Stage/menu helpers can link HSDRaw.dll without carrying the viewer GUI source.

Rigswap and Blender were used to author the existing character swaps. Neither
is installed by this builder or declared a required runtime. The migration work
is to preserve the already-approved bone mappings, mesh transforms, material
settings and corrections as fixed recipes. Some old export functions use
Blender's geometry/conversion APIs; retain a bundled headless converter only if
a concrete operation needs it. Reusing deterministic helper code does not mean
running Rigswap's authoring/agent pipeline.

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

The stage generator currently runs on Windows with the .NET 8 runtime and a
.NET SDK installed. These are maintainer commands while the complete builder
is being assembled:

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
