# External dependencies

The HSDRaw/HSDRawViewer fork is maintained at
https://github.com/sc00ppp/ssbmNucleus-hsdlib and derives from Ploaj/HSDLib.
Its upstream license is MIT. Preserve its license and notices in runtime bundles.

The m-ex/MexManager/MexCLI fork is maintained at
https://github.com/sc00ppp/ssbmNucleus-mex and derives from Ploaj/MexManager.
The current inherited dependency manifest has no SPDX license identifier.
Update this notice and the package's redistribution metadata when the fork's
public release is prepared. This repository does not relicense either fork.

The optional menu-art dependencies are Pillow and NumPy. They are installed as
external packages rather than copied here; retain their notices when bundling.

xdelta3 3.1.0 comes from https://github.com/jmacd/xdelta-gpl/releases/tag/v3.1.0.
The executable is fetched into local runtime storage, not committed. Its source
and COPYING are in that upstream release/source tree; preserve its GPL license
and provide corresponding source as required if shipping it in a runtime bundle.

Disc and FSYS parsing and menu-art generation are adapted from the owner's
existing Colosseum/PokéMelee tooling. Stage specs are the owner's authored graft
recipes. Numeric file indices, transformation settings and output fingerprints
identify recipes without including the referenced game data.

The deterministic costume and menu helpers are adapted from the owner's
existing PokéMelee and Nucleus source.

GNU PowerPC binutils 2.42-2 is fetched from
encounter/gc-wii-binutils; its upstream source and GPL notices remain external.
The compatibility hook retains attribution to KELLZ. Its machine code is
assembled locally from the source recipe.

## What the builder zip carries

`tools/package_builder.py` bundles, unchanged, with their licence files copied into `LICENSES/`:

- Python 3.13 (embeddable distribution, PSF licence) with NumPy, SciPy (BSD), Pillow (MIT-CMU) and PyYAML (MIT).
- The .NET 8 runtime (MIT) for the stage helpers, and the launcher's own self-contained .NET 8 runtime.
- The pinned user-build tools from the lockfile: HSDRawViewer/HSDRaw (MIT), MexCLI (no upstream licence, see above),
  xdelta3 (GPL-2.0+), GNU PowerPC binutils 2.42-2 (GPL-3.0+), MusyX headers (CC0)
  and the Slippi menu map. The GPL tools are unmodified upstream releases; their corresponding source is at the
  pinned tags: jmacd/xdelta-gpl v3.1.0, encounter/gc-wii-binutils 2.42-2.
- The model patches (`recipes/model-patches/*.mpatch`), which are not in Git.

Blender, rigswap and the GameCube model reader are not in the zip; only maintainers use them to regenerate the
model patches.

No license for the new project's authored code has been selected yet. This
private preparation repository is not an announcement of a public release.
