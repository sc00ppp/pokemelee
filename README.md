# PokéMelee builder

Builds PokéMelee from your own two discs:

- **Super Smash Bros. Melee**, USA, version 1.02 (`GALE01`, revision 2)
- **Pokémon Colosseum**, USA (`GC6E01`)

You get two versions, each as an ISO and as an xdelta patch against your Melee ISO:
**PokéMelee** and **PokéMelee AniMelee**.

This repository holds build code and recipes only. It contains no game files, and the ISOs and patches it makes
stay on your computer.

## Using the builder

1. Download the **PokéMelee Builder** zip and extract the whole folder somewhere you can write to (not Program Files).
2. Run `PokeMeleeBuilder.exe` and drop both ISOs on its window (or on the exe itself).
3. Press **Build**. It takes about 10 minutes and needs about 20 GB of free space while it runs.

The finished files go next to your Melee ISO by default:

```text
PokeMelee/
  PokeMelee.iso            PokeMelee.xdelta
  PokeMelee AniMelee.iso   PokeMelee AniMelee.xdelta
  PokeMelee build log.txt
```

The ISOs must be full-size images (1.36 GB). Compressed or trimmed images (`.rvz`, `.ciso`, `.gcz`, `.nkit.iso`)
don't work; convert them back to `.iso` in Dolphin first (right-click the game > Convert File).

Windows 10/11 64-bit only for now, with a graphics card that runs OpenGL (the portraits, icons and
stage-select pictures are rendered on it).

## How it works

Nothing is downloaded and no AI runs during a build. The builder reads both discs, rebuilds every part from fixed
recipes and assembles the two ISOs with MexCLI:

- **Characters:** each of the 29 accepted costumes is rebuilt from its Colosseum model, the matching Melee costume and
  a small *model patch* (`pokemelee/recipes/model-patches/*.mpatch`, 3.4 MB in total). The result is byte-for-byte
  the accepted costume, with no Blender involved.
- **Character-select icons** are cut from each costume's portrait scene, rendered by HSDRawViewer with the camera
  pulled back (`pokemelee/recipes/icons.json` holds each crop).
- **Stages, menus, voices, music, portraits and alternate colours** are rebuilt from the discs by their own recipes.

Every finished ISO is read back and checked, and each xdelta is decoded against your Melee ISO and hash-compared
before the build counts as done.

## Building from source (maintainers)

Needs Windows x64, Python 3.13 and the .NET 8 SDK (plus Visual C++ build tools for `compile-audio`).

```powershell
python -m pip install ".[stages,presentation]"
python -m pokemelee fetch-tools --platform win-x64
python -m pokemelee compile-stages
python -m pokemelee compile-audio
python -m pokemelee build --melee "melee.iso" --colosseum "colosseum.iso" --out "work/build-01"
```

Add `--github-auth` to `fetch-tools` while the HSDRaw and MexCLI forks are private. The output folder must be new;
`--profile normal|animelee` builds one version.

The model patches carry game-derived data, so they are not committed. They live in
`pokemelee/recipes/model-patches/` on the maintainer's machine and go into the builder zip.
To regenerate them, replay the original Blender recipes once and write patches from that cast:

```powershell
python -m pokemelee fetch-tools --platform win-x64 --tool maintainer
python -m pokemelee source-models --colosseum "colosseum.iso" --out work/source-models
python -m pokemelee melee-targets --melee "melee.iso" --out work/melee-targets
python -m pokemelee replay-cast --colosseum "colosseum.iso" --models work/source-models --targets work/melee-targets --out work/cast
python -m pokemelee model-patches --melee "melee.iso" --colosseum "colosseum.iso" --cast work/cast
```

Package the user folder (and zip) from an installed runtime:

```powershell
python tools/package_builder.py --runtime runtime --out "dist/PokeMelee Builder" --zip
```

Single steps (`cast`, `css-icons`, `stages`, `voices`, `music`, `menus`, …) are listed by `python -m pokemelee --help`.

Checks:

```powershell
python -m unittest discover -s tests -v
python tools/check_source.py
```

## Tools

The pinned versions and checksums are in `pokemelee/dependencies.lock.json`. No fork code is copied here.

| Tool | Source | Used for |
| --- | --- | --- |
| HSDRaw / HSDRawViewer | [ssbmNucleus-hsdlib](https://github.com/sc00ppp/ssbmNucleus-hsdlib) | DAT reading and writing, portraits, icons and stage-select pictures |
| MexCLI | [ssbmNucleus-mex](https://github.com/sc00ppp/ssbmNucleus-mex) | Assembling and exporting the ISOs |
| xdelta3 3.1.0 | [xdelta-gpl](https://github.com/jmacd/xdelta-gpl) | Making and checking the patches |
| MusyX | [musyx](https://github.com/AxioDL/musyx) | Rendering Colosseum music and sounds |
| GNU PowerPC binutils 2.42 | [gc-wii-binutils](https://github.com/encounter/gc-wii-binutils) | Assembling the small game code changes |
| Blender, rigswap, GameCube model reader | see the lockfile | Maintainer only: regenerating the model patches |

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for licences and [BUILD_PLAN.md](BUILD_PLAN.md) for the
pipeline history.
