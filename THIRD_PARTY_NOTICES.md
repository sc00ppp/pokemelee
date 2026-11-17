# Third-party components in the PokéMelee Builder

Everything below ships in this folder unchanged from its own release. The licence texts are in `LICENSES/`, under the
file names given in brackets. No game data is included: the builder reads it from your own Melee and Colosseum discs.

## Tools the builder runs (`engine/runtime`)

**HSDRaw and HSDRawViewer** (`hsdlib/win-x64`; `HSDRaw.dll` also in `mex/win-x64` and in each `stagegraft` folder).
Built from a fork of Ploaj/HSDLib (https://github.com/Ploaj/HSDLib). MIT, Copyright (c) 2021 Ploaj
[HSDLib-MIT.txt]. HSDRawViewer brings these libraries with it:
- OpenTK 4.7.4 (Core, Compute, Graphics, Input, Mathematics, OpenAL, Windowing.*), MIT [MIT-packages.txt]
- OpenTK.WinForms (GLControl), MIT [MIT-packages.txt]
- GLFW 3.3.7 (`glfw3.dll`, from OpenTK.redist.glfw 3.3.7.27), zlib licence [GLFW-Zlib.md]
- SixLabors.ImageSharp 3.1.12, Six Labors Split License [SixLabors-Split-License.txt]
- DockPanelSuite 3.1.1 and DockPanelSuite.ThemeVS2015 3.1.1, MIT [MIT-packages.txt]
- Be.Windows.Forms.HexBox.Net8 2.1.0, MIT [MIT-packages.txt]
- YamlDotNet 12.0.0, MIT [YamlDotNet-MIT.txt]
- VGAudio 2.2.1 (Alex Barney); its package names its licence only by link:
  https://raw.githubusercontent.com/Thealexbarney/VGAudio/master/LICENSE
- CSCore 1.2.1.2 (Florian R.); its package names its licence only by link:
  https://github.com/filoe/cscore/blob/master/license.md
- IONET (Ploaj), a prebuilt library shipped with HSDLib; no licence is published for it
- `sni.dll`, System.Data.SqlClient SNI 4.4.0 (Microsoft), Microsoft .NET Library licence
  [SqlClient-SNI-dotnet_library_license.txt, SqlClient-SNI-ThirdPartyNotices.txt]
- its own self-contained .NET 8.0.33 and Windows Desktop runtime, MIT
  [dotnet-runtime-pack-LICENSE.txt, dotnet-runtime-pack-THIRD-PARTY-NOTICES.txt, dotnet-windowsdesktop-LICENSE.txt]

**MexCLI and mexLib** (`mex/win-x64`). Built from a fork of Ploaj/MexManager (https://github.com/Ploaj/MexManager),
which publishes no licence, so none can be given here; they are included by the fork's maintainer. `codes.gct` and
`seed_codes.ini` come from the same project. MexCLI brings these libraries with it:
- GCILib and MeleeMedia, prebuilt libraries from the MexManager project; no licence is published for them
- NLayer 2.0.1, MIT [MIT-packages.txt]
- NVorbis 0.10.5, MIT [NVorbis-MIT.txt]
- SharpJaad 0.1.1 and SharpJaad.AAC 0.1.1, MIT [MIT-packages.txt]
- bodong.PropertyModels 11.1.1.1 (Avalonia.PropertyGrid), MIT [MIT-packages.txt]
- SixLabors.ImageSharp 3.1.12, SixLabors.ImageSharp.Drawing 2.1.4 and SixLabors.Fonts 2.0.4, Six Labors Split License
  [SixLabors-Split-License.txt]
- CSCore 1.2.1.2, as above
- its own self-contained .NET 8.0.33 runtime, MIT [dotnet-runtime-pack-LICENSE.txt, dotnet-runtime-pack-THIRD-PARTY-NOTICES.txt]

**xdelta3 3.1.0** (`xdelta/win-x64/xdelta3-3.1.0-x86_64.exe`), Copyright (C) Joshua MacDonald. GPL-2.0-or-later
[GPL-2.0.txt]. The unmodified release binary from https://github.com/jmacd/xdelta-gpl/releases/tag/v3.1.0. Its
corresponding source is that release, tag v3.1.0 of https://github.com/jmacd/xdelta-gpl.

**GNU Binutils 2.42 for powerpc-eabi** (`powerpc-binutils/win-x64`, 16 programs: `as`, `objcopy` and the rest of the
release), Copyright (C) Free Software Foundation, Inc. GPL-3.0-or-later [GPL-3.0.txt]. The unmodified files of release
2.42-2 of https://github.com/encounter/gc-wii-binutils (`powerpc-eabi-as --version`: "GNU assembler (GNU Binutils)
2.42"). Their corresponding source is GNU Binutils 2.42 (https://ftp.gnu.org/gnu/binutils/binutils-2.42.tar.xz) with
the build scripts of https://github.com/encounter/gc-wii-binutils at tag 2.42-2.

**MusyX** (`musyx/win-x64`: the source of https://github.com/AxioDL/musyx at commit
717404d77c17a95dd101bbe737d0f9549ab600e6), CC0-1.0 [musyx-LICENSE]. `audio/render.exe` and `audio/fxrender.exe` are
compiled from it together with the builder's own `render.c` and `fxrender.c`, and render Colosseum's music and sound
effects from the instrument data on your disc.

**Slippi menu map** (`slippi-menu-map/win-x64/MnMaAll.usd.diff`): an unchanged data file from Slippi Dolphin,
https://github.com/project-slippi/dolphin at commit 0653df8194eac2392dea9fe26276b70f3c87fd89
(`Data/Sys/GameFiles/GALE01/MnMaAll.usd.diff`). Slippi Dolphin is distributed under GPL-2.0 [GPL-2.0.txt, the licence
file Slippi Dolphin ships].

## Runtimes (`engine/python`, `engine/dotnet`, the launcher)

- Python 3.13.3, embeddable distribution, PSF licence and the licences of the libraries in its Windows build
  [python-LICENSE.txt]
- NumPy 2.2.6, BSD-3-Clause, with the licences of the libraries it bundles (OpenBLAS and others) [numpy-LICENSE.txt]
- SciPy 1.16.0, BSD-3-Clause, with the licences of the libraries it bundles [scipy-LICENSE.txt]
- Pillow 11.2.1, MIT-CMU [pillow-LICENSE]
- PyYAML 6.0.3, MIT [pyyaml-LICENSE]
- .NET 8.0.34 runtime for the stage helpers (`engine/dotnet`), MIT [dotnet-LICENSE.txt, dotnet-ThirdPartyNotices.txt]
- `PokeMeleeBuilder.exe` carries its own self-contained .NET 8.0.22 and Windows Forms runtime, MIT
  [dotnet-runtime-pack-LICENSE.txt, dotnet-runtime-pack-THIRD-PARTY-NOTICES.txt, dotnet-windowsdesktop-LICENSE.txt]

## PokéMelee's own parts

The `pokemelee` package, its recipes and model patches, the stage helpers (`engine/runtime/stagegraft`), `render.c`
and `fxrender.c`, and the launcher are PokéMelee's own work. No licence has been chosen for them yet.

Disc and FSYS parsing and menu-art generation are adapted from the author's earlier Colosseum and PokéMelee tooling,
and the costume and menu helpers from the author's PokéMelee and Nucleus source. Stage specs are authored graft
recipes; numeric file indices, transformation settings and output fingerprints identify each recipe without including
the game data it refers to. The model patches hold only PokéMelee's own edits; the models themselves are read from
your discs.

The compatibility hook retains attribution to KELLZ. Its machine code is assembled on your machine, by the bundled
binutils, from the source recipe.

Blender and the maintainers' model tools are not in this folder; they are used only to make the model patches.
