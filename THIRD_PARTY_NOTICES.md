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

No license for the new project's authored code has been selected yet. This
private preparation repository is not an announcement of a public release.
