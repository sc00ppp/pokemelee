# From the accepted build to a portable builder

The target is Cast Test 30's plain PokéMelee content, rebuilt from the user's two
discs. Repo setup does not authorize changing the cast, choosing different stage
revisions, or reorganizing Nucleus, VAMP or rigswap.

The build contract is fixed: two user-supplied ISOs in, a local ISO and verified
xdelta out. It must replay the accepted result with no LLM calls, prompts, API
keys, new rigging choices or authoring sessions. After dependency setup it must
work offline. The user never has to run Rigswap or operate Blender.

Completed preparation:

- A standalone Python package, with no Nucleus path injection or vault dependency.
- Disc identification and bounded filesystem/archive extraction.
- Real Colosseum stock/fallback CSS icon generation for all 29 cast members.
- Exact fork release pins and direct fetch/install with hash verification.
- A local ISO-and-xdelta exporter with base/output fingerprints and a decoded
  patch verification. This is ready for the final assembler to call.
- The accepted cast inventory and six authored stage graft specs, with personal
  drive paths replaced by explicit input placeholders.

Remaining conversion, in dependency order:

1. **Cast recipes.** Recover the initial source-model extraction and rig mapping
   for each accepted costume. `round_cast.sh` starts several paths from
   `build.blend1`/`edited.blend`; hand scripts apply corrections to those inputs.
   Preserve the already-approved source-to-target mappings, transforms, weighting
   rules and material settings as fixed recipes; do not ask an agent to recreate
   them. Replay those recipes against data extracted from the two discs. Reuse
   deterministic conversion functions where useful, without depending on the
   Rigswap authoring application or its project folders. Blender is not an
   assumed dependency: the old prep/export path uses its geometry and Collada
   conversion APIs, so an automatic bundled headless converter may be retained
   if a specific operation requires it. Do not replace accepted runs with a
   newer-looking filename: some approved DATs were copied over older run directories.
2. **Stage inputs and generators.** The six graft specs are in this repository.
   `${melee}` means extracted Melee files, `${colosseum}` means extracted and
   decoded Colosseum sources, `${generated}` means local generated intermediates.
   These are placeholders, not paths resolved from the developer's machine.
   Phenac requires generated mesh/material files and a sanitized Stadium base;
   Agate also uses an extracted/converted Celebi. Integrate the native stage
   helpers and verify the output against `stages.json` fingerprints.
3. **Presentation.** Migrate the actual model-rendered CSS icons, costume
   portraits, menu art, stage images, voice/music selection, recolors and pair
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
