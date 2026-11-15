# PokéMelee builder

This repository owns the reproducible PokéMelee build, not Nucleus or rigswap
development. Work on this repository only unless the user expands the scope.

- The only game inputs are the user's Melee and Pokémon Colosseum ISOs.
- Reproduce BOTH finished reference builds: normal Cast Test 30 and AniMelee
  Test 23. The desktop ISOs are verification references, never user build inputs.
  Preserve their existing cast, rigging, stages and presentation.
- The build replays fixed, reviewed recipes. No LLM inference (local or remote),
  prompts, agent runs, API keys, model downloads, or new rigging decisions.
  After tool setup, it must run offline with the two ISOs and bundled recipes.
- Commit authored source, recipes, synthetic fixtures and dependency manifests.
  Never commit game assets/code, extracted textures/models, generated pixel
  headers, compiled game modifications containing copied game data, or ISO deltas.
- A successful final build must produce both a local ISO and an xdelta against
  the user's original Melee ISO. Verify the patch by decoding and hashing it.
  Never upload generated ISOs/patches to Git, releases, or CI artifacts.
- Every finished component must rebuild from those inputs and pinned tools in
  an empty work directory. A cache or a local `.blend` is not a source recipe.
- Keep HSDLib and MexCLI source in their own repositories. Pin the required
  versions and package runtimes for users; do not copy whole forks.
- Rigswap and Blender are historical authoring tools, not assumed runtime
  dependencies. Reuse only deterministic conversion functions if needed.
  A headless Blender converter is acceptable only for a concrete required
  operation; it must be pinned, automatic, offline and bundled for the user.
  Never rerun Rigswap's agent pipeline or require its project/cache folders.
- Use explicit paths. No personal drive paths, Nucleus vault, Desktop ISOs,
  AI calls or API key requirements in an ordinary build.
- Run `python -m unittest discover -s tests -v` and `python tools/check_source.py`.
- Only mark a build ready when every required recipe has a working generator
  and a cold build was checked. Never silently omit failed characters/stages.
- Do not rewrite old repositories or publish a public release as part of setup.
