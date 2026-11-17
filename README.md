# PokéMelee

Super Smash Bros. Melee with every fighter replaced by a Pokémon and the six tournament stages rebuilt from
Pokémon Colosseum. It comes in two looks: **PokéMelee** and **PokéMelee AniMelee** (cel-shaded).

There are no game files in this repository. The builder makes the mod on your own computer from your own two discs.

## What you need

- **Super Smash Bros. Melee**, USA, version 1.02, as a full-size `.iso`
- **Pokémon Colosseum**, USA, as a full-size `.iso`
- Windows 10 or 11 (64-bit) with a graphics card that runs OpenGL
- About 20 GB of free space while it builds

Compressed or trimmed images (`.rvz`, `.ciso`, `.gcz`, `.nkit.iso`) don't work. Convert them back to `.iso` in
Dolphin first: right-click the game, then Convert File.

## Building it

1. Download the **PokéMelee Builder** zip from [Releases](../../releases/latest) and extract the whole folder
   somewhere you can write to (not Program Files).
2. Run `PokeMeleeBuilder.exe` and drop both ISOs on its window.
3. Press **Build**. It takes about 10 minutes.

Everything the builder needs is in that folder, and nothing is downloaded during a build. Windows may warn that the
exe comes from an unknown publisher; choose **More info**, then **Run anyway**.

The finished files go next to your Melee ISO:

```text
PokeMelee/
  PokeMelee.iso            PokeMelee.xdelta
  PokeMelee AniMelee.iso   PokeMelee AniMelee.xdelta
  PokeMelee build log.txt
```

Open either ISO in Dolphin or Slippi like any other Melee ISO.

## Playing online

PokéMelee stays in sync on Slippi against someone playing regular Melee, on all six stages.

**Plusle & Minun** are an extra fighter that regular Melee doesn't have. Only pick them against someone who is also
running PokéMelee: against regular Melee their game crashes. Slippi already refuses the pair in Ranked and Unranked.

## Who is who

| Melee | PokéMelee | Melee | PokéMelee |
| --- | --- | --- | --- |
| Mario | Magmar | Marth | Scizor |
| Luigi | Breloom | Roy | Charmeleon |
| Dr. Mario | Miltank | Link | Scyther |
| Peach | Gardevoir | Young Link | Farfetch'd |
| Bowser | Blastoise | Zelda | Alakazam |
| Yoshi | Kecleon | Sheik | Sceptile |
| Donkey Kong | Swampert | Ganondorf | Machoke |
| Fox | Quilava | Samus | Deoxys |
| Falco | Combusken | Ness | Ralts |
| Captain Falcon | Blaziken | Kirby | Wigglytuff |
| Ice Climbers | Jynx & Smoochum | Mr. Game & Watch | Unown |

Pikachu, Pichu, Jigglypuff and Mewtwo stay themselves. Every fighter has a shiny and team colours.

| Melee stage | PokéMelee stage |
| --- | --- |
| Battlefield | Phenac Stadium lobby |
| Final Destination | Mt. Battle crater |
| Dream Land | Agate Village |
| Fountain of Dreams | Realgam Colosseum |
| Yoshi's Story | Mt. Battle garden |
| Pokémon Stadium | Phenac City |

Licences of the bundled tools are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

PokéMelee is a fan project. It is not affiliated with or endorsed by Nintendo, HAL Laboratory, Game Freak, Genius
Sonority or The Pokémon Company.
