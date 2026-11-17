# From the accepted build to a portable builder

The targets are the finished Cast Test 30 and AniMelee Test 23 desktop builds,
rebuilt from the user's two source discs. Do not change the cast, choose different stage
revisions, or reorganize Nucleus, VAMP or rigswap.

The build contract is fixed: two user-supplied source ISOs in, both existing
variants as local ISOs and verified xdeltas out. Replay the accepted result with no LLM calls, prompts, API
keys, new rigging choices or authoring sessions. After dependency setup it must
work offline. The user never has to run Rigswap or operate Blender.

Implemented build pipeline:

- A standalone Python package, with no Nucleus path injection or vault dependency.
- Disc identification and bounded filesystem/archive extraction.
- Real Colosseum stock/fallback CSS icon generation for all 29 cast members.
- Exact fork release pins and direct fetch/install with hash verification.
- A local ISO-and-xdelta exporter with base/output fingerprints and decoded
  patch verification, called automatically for each requested variant.
- All 29 source models rebuilt from Colosseum, matching the original GLBs.
- All fighter and announcer voices, six menu sounds and seven looping music
  tracks rebuilt from the discs, matching the accepted audio files.
- All 29 fixed character recipes, with their original mappings and corrections;
  25 match the accepted exports exactly, Combusken's arm roll and Machoke's crest
  color are corrected, and two retain documented small conversion differences.
- All 102 alternate costumes, 131 packages per variant, rendered character
  icons and portraits, pair composition, menu assets and stage pictures.
- A fresh m-ex project per variant, including paired fighters, team colors,
  announcer calls, menu layout, stage/music playlists and required engine code.
- A complete `build` command that creates both variants, reads their installed
  files back, preserves the original bonus movie and verifies both patches.

Validation:

- All 22 normal/AniMelee stage files match the desktop references exactly.
- All 29 source models, fighter/announcer banks, menu sound bank and seven music
  tracks match the accepted source/output fingerprints.
- Both complete integration projects exported, passed installed-file read-back
  checks, booted in Dolphin and produced decode/hash-verified patches.
- Character-select and stage-select menus were rendered and compared with both
  accepted ISOs. Pair followers, alternate colors and contact attacks were
  exercised in game. These are developer checks, not user-run harness steps.
- The source-only wheel was installed separately and generated art from the
  original disc without importing the checkout.
- Every component was regenerated in an initially empty build directory from
  the two original discs and pinned tools. The run resumed its own verified
  components after renderer startup/window-size fixes and a receipt serialization
  fix; no historical generated assets were used. Both final ISO/xdelta pairs
  have complete receipts and passed decoded-patch hash verification.
- All 27 fighter identities were loaded and exercised in Dolphin across the
  integration checks. Both final ISOs passed additional gameplay smoke tests;
  their 138 costume/code files match the tested integration ISOs exactly.
- Synthetic tests and source-only patch round trips run on Windows and Linux.
  The complete game build is Windows-only and is checked locally; game content
  is never uploaded to CI. AniMelee retains the full original bonus movie and
  exceeds standard disc size by about 12 MB, so physical-disc/hardware support
  is not claimed.

Tool setup downloads exact pinned dependencies from their own repositories.
The source setup currently compiles the small stage/menu and audio helpers with
the .NET SDK and Visual C++ build tools. An optional future installer can carry
those compiled tools. It must never include generated game content. Users do
not need Nucleus, a Rigswap project, an AI service, or historical asset caches.

The stage revisions were resolved against the accepted local outputs:

| Melee stage | Colosseum scene | Accepted recipe |
| --- | --- | --- |
| Dream Land | Agate Village | v34; house/tree lowered 2 units, Taillow set on its branch, Celebi still and half hidden behind the tree |
| Fountain of Dreams | Realgam Colosseum | v11; the crowd's flip-book plays, at a quarter of Colosseum's rate |
| Battlefield | Phenac Stadium lobby | v10 |
| Final Destination | Mt. Battle crater | v6 |
| Yoshi's Story | Mt. Battle garden | second-round v10; the Taillows fly on their flying loop |
| Pokémon Stadium | Phenac City | second-round v7; original four transformations |

The historical scripts and finished ISOs remain verification references.
Ordinary builds use only the original discs, this repository's recipes and the
installed pinned tools.
