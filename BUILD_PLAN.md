# From the accepted build to a portable builder

The targets are the finished Cast Test 30 and AniMelee Test 23 desktop builds,
rebuilt from the user's two source discs. Do not change the cast, choose different stage
revisions, or reorganize Nucleus, VAMP or rigswap.

The build contract is fixed: two user-supplied source ISOs in, both existing
variants as local ISOs and verified xdeltas out. Replay the accepted result with no LLM calls, prompts, API
keys, new rigging choices or authoring sessions. After dependency setup it must
work offline. The user never has to run Rigswap or operate Blender.

Completed preparation:

- A standalone Python package, with no Nucleus path injection or vault dependency.
- Disc identification and bounded filesystem/archive extraction.
- Real Colosseum stock/fallback CSS icon generation for all 29 cast members.
- Exact fork release pins and direct fetch/install with hash verification.
- A local ISO-and-xdelta exporter with base/output fingerprints and a decoded
  patch verification. This is ready for the final assembler to call.
- All 29 source models rebuilt from Colosseum, matching the original GLBs.
- All fighter and announcer voices, six menu sounds and seven looping music
  tracks rebuilt from the discs, matching the accepted audio files.
- The accepted cast inventory and six authored stage graft specs, with personal
  drive paths replaced by explicit input placeholders.

Remaining conversion, in dependency order:

1. **Cast recipes.** Replay the saved rig mapping and edits for each accepted
   costume. Initial source-model extraction is verified for all 29 models. `round_cast.sh` starts several paths from
   `build.blend1`/`edited.blend`; hand scripts apply corrections to those inputs.
   Preserve the already-approved source-to-target mappings, transforms, weighting
   rules and material settings as fixed recipes; do not ask an agent to recreate
   them. Replay those recipes against data extracted from the two discs. Reuse
   deterministic conversion functions where useful, without depending on the
   Rigswap authoring application or its project folders. The original Colosseum reader requires the pinned headless Blender 4.5.7
   converter. The old prep/export path also uses geometry and Collada APIs;
   keep any required converter automatic, offline and pinned. Do not replace accepted runs with a
   newer-looking filename: some approved DATs were copied over older run directories.
2. **Stages complete.** All six stages, both Stadium language files and its four
   transformations rebuild from the two original discs. All 22 normal/AniMelee
   outputs match the accepted desktop builds exactly. The build resolves its
   own source archives, extracts Celebi, sanitizes Stadium, generates Phenac
   geometry/materials and applies the accepted AniMelee exceptions.
3. **Presentation.** Migrate the actual model-rendered CSS icons, costume
   portraits, menu art, stage images, recolors and pair
   composition. The working party-face icon generator is the old fallback;
   it does not replace the final portrait style.
4. **Assembly.** Extract the needed standalone interface to MexCLI from the old
   assembler. Preserve pair behavior, colors, menu layout and required engine
   changes. Stop if any component fails. Do not copy the old movie-replacement
   shortcut or silently continue with missing costumes.
5. **Cold build and release.** Run from an empty directory with only the discs
   and pinned tools. Read back installed files and exercise the game. Then
   call the exporter to produce both the ISO and xdelta locally. The end-user
   download contains the builder/tools, never a generated ISO or patch. Users
   should not install Nucleus, configure an AI service, or locate historical caches.

The stage revisions were resolved against the accepted local outputs:

| Melee stage | Colosseum scene | Accepted recipe |
| --- | --- | --- |
| Dream Land | Agate Village | v32; house/tree and perched Taillow lowered 2 units |
| Fountain of Dreams | Realgam Colosseum | v10 |
| Battlefield | Phenac Stadium lobby | v10 |
| Final Destination | Mt. Battle crater | v6 |
| Yoshi's Story | Mt. Battle garden | second-round v9 |
| Pokémon Stadium | Phenac City | second-round v7; original four transformations |

The old source scripts remain untouched in their existing local locations and
previous source backups. This repo brings in the actual portable pieces and
authored specs as they are converted, rather than importing every historical
test script and presenting it as a working build.
