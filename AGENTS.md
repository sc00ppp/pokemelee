# PokéMelee builder

This repository owns the reproducible PokéMelee build, not Nucleus or rigswap
development. Work on this repository only unless the user expands the scope.

- The only game inputs are the user's Melee and Pokémon Colosseum ISOs.
- Commit authored source, recipes, synthetic fixtures and dependency manifests.
  Never commit game assets/code, extracted textures/models, generated pixel
  headers, compiled game modifications containing copied game data, or ISO deltas.
- A successful final build must produce both a local ISO and an xdelta against
  the user's original Melee ISO. Verify the patch by decoding and hashing it.
  Never upload generated ISOs/patches to Git, releases, or CI artifacts.
- Every finished component must rebuild from those inputs and pinned tools in
  an empty work directory. A cache or a local `.blend` is not a source recipe.
- Keep HSDLib, MexCLI and rigswap source in their own repositories. Pin the
  required versions and package runtimes for users; do not copy whole forks.
- Use explicit paths. No personal drive paths, Nucleus vault, Desktop ISOs,
  hidden AI calls or API key requirements in an ordinary build.
- Run `python -m unittest discover -s tests -v` and `python tools/check_source.py`.
- Only mark a build ready when every required recipe has a working generator
  and a cold build was checked. Never silently omit failed characters/stages.
- Do not rewrite old repositories or publish a public release as part of setup.
