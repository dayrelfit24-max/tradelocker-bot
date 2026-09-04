"""
Popular games (2025–2026) — SEO keywords and filename detection.
Sorted by what audiences are actively searching on YouTube.
"""

from __future__ import annotations

# canonical_key -> display name in titles
GAME_DISPLAY: dict[str, str] = {
    "fortnite": "Fortnite",
    "minecraft": "Minecraft",
    "roblox": "Roblox",
    "gta": "GTA",
    "call of duty": "Call of Duty",
    "valorant": "Valorant",
    "league of legends": "League of Legends",
    "apex": "Apex Legends",
    "cs2": "CS2",
    "marvel rivals": "Marvel Rivals",
    "overwatch 2": "Overwatch 2",
    "rocket league": "Rocket League",
    "ea fc": "EA Sports FC",
    "nba 2k": "NBA 2K",
    "helldivers 2": "Helldivers 2",
    "palworld": "Palworld",
    "elden ring": "Elden Ring",
    "monster hunter wilds": "Monster Hunter Wilds",
    "battlefield": "Battlefield",
    "arc raiders": "ARC Raiders",
    "destiny 2": "Destiny 2",
    "diablo 4": "Diablo IV",
    "path of exile 2": "Path of Exile 2",
    "wow": "World of Warcraft",
    "ffxiv": "Final Fantasy XIV",
    "rust": "Rust",
    "rainbow six": "Rainbow Six Siege",
    "pubg": "PUBG",
    "dota 2": "Dota 2",
    "honkai star rail": "Honkai Star Rail",
    "genshin impact": "Genshin Impact",
    "wuthering waves": "Wuthering Waves",
    "zelda": "Zelda",
    "pokemon": "Pokémon",
    "super smash bros": "Super Smash Bros",
    "street fighter 6": "Street Fighter 6",
    "tekken 8": "Tekken 8",
    "mortal kombat": "Mortal Kombat",
    "forza": "Forza",
    "starfield": "Starfield",
    "halo": "Halo",
    "f1": "F1",
    "hogwarts legacy": "Hogwarts Legacy",
    "baldurs gate 3": "Baldur's Gate 3",
    "lies of p": "Lies of P",
    "black myth wukong": "Black Myth Wukong",
    "dead by daylight": "Dead by Daylight",
    "sea of thieves": "Sea of Thieves",
    "lethal company": "Lethal Company",
    "among us": "Among Us",
    "fall guys": "Fall Guys",
    "clash royale": "Clash Royale",
    "free fire": "Free Fire",
    "mobile legends": "Mobile Legends",
    "five nights": "Five Nights at Freddy's",
    "resident evil": "Resident Evil",
    "silent hill": "Silent Hill",
    "assassins creed": "Assassin's Creed",
    "spider-man": "Marvel's Spider-Man",
    "god of war": "God of War",
    "last of us": "The Last of Us",
    "cyberpunk": "Cyberpunk 2077",
    "star wars": "Star Wars Outlaws",
    "borderlands": "Borderlands",
    "warframe": "Warframe",
    "sims 4": "The Sims 4",
    "animal crossing": "Animal Crossing",
    "splatoon": "Splatoon",
    "mario": "Mario",
    "sonic": "Sonic",
    "gaming": "Gaming",
}

# canonical_key -> full title for Steam / YouTube gameplay search (not short SEO names)
FOOTAGE_SEARCH_NAMES: dict[str, str] = {
    "cs2": "Counter-Strike 2",
    "gta": "Grand Theft Auto V",
    "fortnite": "Fortnite",
    "call of duty": "Call of Duty",
    "valorant": "Valorant",
    "apex": "Apex Legends",
    "minecraft": "Minecraft",
    "roblox": "Roblox",
    "elden ring": "Elden Ring",
    "helldivers 2": "Helldivers 2",
    "marvel rivals": "Marvel Rivals",
    "halo": "Halo Infinite",
    "forza": "Forza Horizon 5",
    "starfield": "Starfield",
    "baldurs gate 3": "Baldur's Gate 3",
    "path of exile 2": "Path of Exile 2",
    "diablo 4": "Diablo IV",
    "zelda": "The Legend of Zelda",
    "pokemon": "Pokémon",
    "mario": "Super Mario",
    "animal crossing": "Animal Crossing",
    "cyberpunk": "Cyberpunk 2077",
    "black myth wukong": "Black Myth: Wukong",
    "lies of p": "Lies of P",
    "dead by daylight": "Dead by Daylight",
    "dota 2": "Dota 2",
    "overwatch 2": "Overwatch 2",
    "rocket league": "Rocket League",
    "ea fc": "EA Sports FC",
    "rainbow six": "Rainbow Six Siege",
    "pubg": "PUBG",
    "genshin impact": "Genshin Impact",
    "tekken 8": "Tekken 8",
    "street fighter 6": "Street Fighter 6",
    "super smash bros": "Super Smash Bros Ultimate",
    "spider-man": "Marvel's Spider-Man 2",
    "god of war": "God of War Ragnarök",
    "last of us": "The Last of Us",
    "star wars": "Star Wars Outlaws",
    "arc raiders": "ARC Raiders",
    "monster hunter wilds": "Monster Hunter Wilds",
    "battlefield": "Battlefield",
    "destiny 2": "Destiny 2",
    "wow": "World of Warcraft",
    "ffxiv": "Final Fantasy XIV",
    "rust": "Rust",
    "hogwarts legacy": "Hogwarts Legacy",
    "resident evil": "Resident Evil",
    "silent hill": "Silent Hill",
    "assassins creed": "Assassin's Creed",
    "borderlands": "Borderlands",
    "warframe": "Warframe",
    "sims 4": "The Sims 4",
    "splatoon": "Splatoon 3",
    "sonic": "Sonic Frontiers",
    "lethal company": "Lethal Company",
    "sea of thieves": "Sea of Thieves",
    "among us": "Among Us",
    "fall guys": "Fall Guys",
    "clash royale": "Clash Royale",
    "five nights": "Five Nights at Freddy's",
    "f1": "F1 25",
    "nba 2k": "NBA 2K25",
    "palworld": "Palworld",
    "honkai star rail": "Honkai Star Rail",
    "wuthering waves": "Wuthering Waves",
    "mortal kombat": "Mortal Kombat 1",
    "free fire": "Free Fire",
    "mobile legends": "Mobile Legends",
    "gaming": "gaming",
}

# canonical_key -> YouTube search tags
GAME_KEYWORDS: dict[str, list[str]] = {
    "fortnite": [
        "fortnite", "fortnite battle royale", "fortnite gameplay", "fortnite wins",
        "fortnite highlights", "fortnite ranked", "fortnite clutch", "fortnite tips",
        "fortnite chapter", "fortnite zero build", "fortnite update",
    ],
    "minecraft": [
        "minecraft", "minecraft survival", "minecraft hardcore", "minecraft gameplay",
        "minecraft lets play", "minecraft build", "minecraft speedrun", "minecraft mod",
        "minecraft 1.21", "minecraft tips",
    ],
    "roblox": [
        "roblox", "roblox gameplay", "roblox funny", "roblox obby", "roblox roleplay",
        "roblox brookhaven", "roblox doors", "roblox highlights",
    ],
    "gta": [
        "gta 5", "gta online", "gta rp", "gta gameplay", "gta funny moments",
        "gta heist", "gta mods", "gta 6",
    ],
    "call of duty": [
        "call of duty", "cod", "warzone", "black ops 6", "cod gameplay",
        "warzone wins", "cod ranked", "cod zombies", "warzone highlights",
    ],
    "valorant": [
        "valorant", "valorant gameplay", "valorant ranked", "valorant ace",
        "valorant clutch", "valorant tips", "valorant highlights", "valorant immortal",
    ],
    "league of legends": [
        "league of legends", "lol", "lol gameplay", "lol ranked", "lol highlights",
        "lol tips", "lol esports", "lol clutch",
    ],
    "apex": [
        "apex legends", "apex gameplay", "apex ranked", "apex highlights",
        "apex clutch", "apex tips", "apex season",
    ],
    "cs2": [
        "cs2", "counter strike 2", "cs2 gameplay", "cs2 highlights", "cs2 ranked",
        "cs2 clutch", "cs2 tips", "counter strike",
    ],
    "marvel rivals": [
        "marvel rivals", "marvel rivals gameplay", "marvel rivals ranked",
        "marvel rivals highlights", "marvel rivals tips",
    ],
    "overwatch 2": [
        "overwatch 2", "ow2", "overwatch gameplay", "overwatch ranked",
        "overwatch highlights", "overwatch tips",
    ],
    "rocket league": [
        "rocket league", "rocket league gameplay", "rocket league goals",
        "rocket league ranked", "rocket league highlights",
    ],
    "ea fc": [
        "ea sports fc", "ea fc", "fifa", "ea fc gameplay", "ea fc ultimate team",
        "ea fc career mode", "ea fc tips",
    ],
    "nba 2k": [
        "nba 2k", "nba 2k25", "nba 2k gameplay", "nba 2k mycareer",
        "nba 2k park", "nba 2k highlights",
    ],
    "helldivers 2": [
        "helldivers 2", "helldivers gameplay", "helldivers funny",
        "helldivers tips", "helldivers highlights",
    ],
    "palworld": [
        "palworld", "palworld gameplay", "palworld tips", "palworld funny",
        "palworld multiplayer",
    ],
    "elden ring": [
        "elden ring", "elden ring dlc", "elden ring boss", "elden ring gameplay",
        "elden ring tips", "soulslike",
    ],
    "monster hunter wilds": [
        "monster hunter wilds", "mhw", "monster hunter gameplay",
        "monster hunter boss", "monster hunter tips",
    ],
    "battlefield": [
        "battlefield", "battlefield 6", "battlefield gameplay", "battlefield multiplayer",
        "battlefield highlights",
    ],
    "arc raiders": [
        "arc raiders", "arc raiders gameplay", "arc raiders extraction",
        "arc raiders tips", "arc raiders highlights",
    ],
    "destiny 2": [
        "destiny 2", "destiny gameplay", "destiny raid", "destiny pvp",
        "destiny tips", "destiny highlights",
    ],
    "diablo 4": [
        "diablo 4", "diablo iv", "diablo gameplay", "diablo build", "diablo season",
    ],
    "path of exile 2": [
        "path of exile 2", "poe2", "poe2 gameplay", "poe2 build", "poe2 tips",
    ],
    "wow": [
        "world of warcraft", "wow", "wow gameplay", "wow raid", "wow mythic plus",
    ],
    "ffxiv": [
        "final fantasy xiv", "ffxiv", "ff14", "ffxiv gameplay", "ffxiv raid",
    ],
    "rust": [
        "rust", "rust gameplay", "rust pvp", "rust base", "rust wipe", "rust funny",
    ],
    "rainbow six": [
        "rainbow six siege", "r6", "r6 gameplay", "r6 ranked", "r6 clutch", "r6 tips",
    ],
    "pubg": [
        "pubg", "pubg battlegrounds", "pubg gameplay", "pubg wins", "pubg highlights",
    ],
    "dota 2": [
        "dota 2", "dota gameplay", "dota ranked", "dota highlights", "dota tips",
    ],
    "honkai star rail": [
        "honkai star rail", "hsr", "honkai gameplay", "honkai guide", "honkai gacha",
    ],
    "genshin impact": [
        "genshin impact", "genshin", "genshin gameplay", "genshin guide", "genshin boss",
    ],
    "wuthering waves": [
        "wuthering waves", "wuwa", "wuthering waves gameplay", "wuthering waves guide",
    ],
    "zelda": [
        "zelda", "tears of the kingdom", "breath of the wild", "zelda gameplay",
        "zelda tips", "nintendo switch",
    ],
    "pokemon": [
        "pokemon", "pokemon gameplay", "pokemon scarlet violet", "pokemon nuzlocke",
        "pokemon tips",
    ],
    "super smash bros": [
        "super smash bros", "smash ultimate", "smash gameplay", "smash competitive",
    ],
    "street fighter 6": [
        "street fighter 6", "sf6", "street fighter gameplay", "sf6 ranked",
    ],
    "tekken 8": [
        "tekken 8", "tekken gameplay", "tekken ranked", "tekken combo",
    ],
    "mortal kombat": [
        "mortal kombat 1", "mk1", "mortal kombat gameplay", "mk1 combo",
    ],
    "forza": [
        "forza horizon", "forza motorsport", "forza gameplay", "racing game",
    ],
    "f1": [
        "f1 24", "f1 25", "f1 game", "f1 gameplay", "formula 1 game",
    ],
    "hogwarts legacy": [
        "hogwarts legacy", "hogwarts gameplay", "harry potter game",
    ],
    "baldurs gate 3": [
        "baldurs gate 3", "bg3", "baldurs gate gameplay", "bg3 build",
    ],
    "lies of p": [
        "lies of p", "lies of p gameplay", "lies of p boss", "soulslike",
    ],
    "black myth wukong": [
        "black myth wukong", "wukong", "black myth gameplay", "black myth boss",
    ],
    "dead by daylight": [
        "dead by daylight", "dbd", "dbd gameplay", "dbd funny", "dbd killer",
    ],
    "sea of thieves": [
        "sea of thieves", "sot", "sea of thieves gameplay", "sea of thieves pvp",
    ],
    "lethal company": [
        "lethal company", "lethal company funny", "lethal company gameplay",
    ],
    "among us": [
        "among us", "among us funny", "among us gameplay",
    ],
    "fall guys": [
        "fall guys", "fall guys gameplay", "fall guys wins", "fall guys funny",
    ],
    "clash royale": [
        "clash royale", "clash royale gameplay", "clash royale deck", "clash royale tips",
    ],
    "free fire": [
        "free fire", "free fire gameplay", "free fire highlights", "garena free fire",
    ],
    "mobile legends": [
        "mobile legends", "mlbb", "mobile legends gameplay", "mobile legends ranked",
    ],
    "five nights": [
        "five nights at freddys", "fnaf", "fnaf gameplay", "fnaf horror",
    ],
    "resident evil": [
        "resident evil", "re4", "resident evil gameplay", "survival horror",
    ],
    "silent hill": [
        "silent hill", "silent hill 2", "silent hill gameplay", "horror game",
    ],
    "assassins creed": [
        "assassins creed", "ac shadows", "assassins creed gameplay",
    ],
    "spider-man": [
        "spider man 2", "spiderman ps5", "spider man gameplay", "marvel game",
    ],
    "god of war": [
        "god of war", "god of war ragnarok", "god of war gameplay",
    ],
    "last of us": [
        "the last of us", "tlou", "last of us gameplay", "last of us 2",
    ],
    "cyberpunk": [
        "cyberpunk 2077", "cyberpunk", "cyberpunk gameplay", "cyberpunk phantom liberty",
    ],
    "star wars": [
        "star wars outlaws", "star wars game", "star wars gameplay",
    ],
    "borderlands": [
        "borderlands 4", "borderlands", "borderlands gameplay", "looter shooter",
    ],
    "warframe": [
        "warframe", "warframe gameplay", "warframe build", "warframe update",
    ],
    "sims 4": [
        "the sims 4", "sims 4", "sims gameplay", "sims build",
    ],
    "animal crossing": [
        "animal crossing", "acnh", "animal crossing gameplay", "animal crossing tips",
    ],
    "splatoon": [
        "splatoon 3", "splatoon", "splatoon gameplay", "splatoon ranked",
    ],
    "mario": [
        "mario", "super mario", "mario kart", "mario gameplay", "nintendo",
    ],
    "sonic": [
        "sonic", "sonic frontiers", "sonic gameplay",
    ],
    "gaming": [
        "gaming", "gameplay", "gaming highlights", "best gaming moments",
        "funny gaming", "pro gameplay", "gaming tips", "progamer",
    ],
}

# alias (lowercase) -> canonical_key — longest aliases matched first in detect_game
GAME_ALIASES: list[tuple[str, str]] = []
_raw_aliases: dict[str, list[str]] = {
    "fortnite": ["fortnite", "fnbr", "fort"],
    "minecraft": ["minecraft", "mc gameplay", "mine craft"],
    "roblox": ["roblox", "rbx"],
    "gta": ["gta6", "gta 6", "gta5", "gta 5", "gta online", "gtav", "grand theft auto"],
    "call of duty": ["warzone", "wz", "bo6", "black ops 6", "black ops", "cod", "call of duty", "modern warfare"],
    "valorant": ["valorant", "valo"],
    "league of legends": ["league of legends", "leagueoflegends", "lol gameplay", "lol ranked"],
    "apex": ["apex legends", "apexlegends", "apex"],
    "cs2": ["cs2", "counter strike 2", "counter-strike 2", "counterstrike", "csgo"],
    "marvel rivals": ["marvel rivals", "marvelrivals"],
    "overwatch 2": ["overwatch 2", "overwatch2", "ow2", "overwatch"],
    "rocket league": ["rocket league", "rocketleague", "rl gameplay"],
    "ea fc": ["ea sports fc", "ea fc", "eafifa", "fifa 25", "fifa 24", "fifa"],
    "nba 2k": ["nba 2k", "nba2k", "2k25", "2k24"],
    "helldivers 2": ["helldivers 2", "helldivers2", "helldivers"],
    "palworld": ["palworld", "pal world"],
    "elden ring": ["elden ring", "eldenring", "elden ring dlc"],
    "monster hunter wilds": ["monster hunter wilds", "monster hunter", "mhwilds", "mhw"],
    "battlefield": ["battlefield 6", "battlefield6", "battlefield 2042", "bf6", "battlefield"],
    "arc raiders": ["arc raiders", "arcraiders"],
    "destiny 2": ["destiny 2", "destiny2", "destiny"],
    "diablo 4": ["diablo 4", "diablo iv", "diablo4", "diablo"],
    "path of exile 2": ["path of exile 2", "pathofexile2", "poe2", "path of exile"],
    "wow": ["world of warcraft", "wow retail", "wow classic"],
    "ffxiv": ["final fantasy xiv", "ffxiv", "ff14", "ff xiv"],
    "rust": ["rust", "rust gameplay", "rust wipe", "rust pvp"],
    "rainbow six": ["rainbow six", "rainbow six siege", "r6 siege", "siege", "r6"],
    "pubg": ["pubg", "playerunknown", "battlegrounds"],
    "dota 2": ["dota 2", "dota2"],
    "honkai star rail": ["honkai star rail", "star rail", "hsr"],
    "genshin impact": ["genshin impact", "genshin"],
    "wuthering waves": ["wuthering waves", "wuwa"],
    "zelda": ["zelda", "tears of the kingdom", "totk", "breath of the wild", "botw"],
    "pokemon": ["pokemon", "pokémon", "scarlet violet", "pokemon sv"],
    "super smash bros": ["super smash bros", "smash ultimate", "ssbu"],
    "street fighter 6": ["street fighter 6", "street fighter", "sf6"],
    "tekken 8": ["tekken 8", "tekken8", "tekken"],
    "mortal kombat": ["mortal kombat", "mortal kombat 1", "mk1"],
    "forza": ["forza horizon", "forza motorsport", "forza", "forza horizon 5"],
    "starfield": ["starfield", "star field"],
    "halo": ["halo infinite", "halo", "master chief"],
    "f1": ["f1 25", "f1 24", "f1 game", "formula 1"],
    "hogwarts legacy": ["hogwarts legacy", "hogwarts"],
    "baldurs gate 3": ["baldurs gate 3", "baldur's gate 3", "bg3"],
    "lies of p": ["lies of p", "liesofp"],
    "black myth wukong": ["black myth wukong", "black myth", "wukong"],
    "dead by daylight": ["dead by daylight", "dbd"],
    "sea of thieves": ["sea of thieves", "seaofthieves"],
    "lethal company": ["lethal company", "lethalcompany"],
    "among us": ["among us", "amongus"],
    "fall guys": ["fall guys", "fallguys"],
    "clash royale": ["clash royale", "clashroyale"],
    "free fire": ["free fire", "freefire", "garena"],
    "mobile legends": ["mobile legends", "mlbb"],
    "five nights": ["five nights", "fnaf", "freddy"],
    "resident evil": ["resident evil", "re4 remake", "re4"],
    "silent hill": ["silent hill", "silenthill"],
    "assassins creed": ["assassins creed", "ac shadows", "assassin's creed"],
    "spider-man": ["spider man", "spiderman", "spider-man 2"],
    "god of war": ["god of war", "gow", "ragnarok"],
    "last of us": ["last of us", "tlou"],
    "cyberpunk": ["cyberpunk 2077", "cyberpunk"],
    "star wars": ["star wars outlaws", "star wars"],
    "borderlands": ["borderlands 4", "borderlands"],
    "warframe": ["warframe"],
    "sims 4": ["sims 4", "the sims"],
    "animal crossing": ["animal crossing", "acnh"],
    "splatoon": ["splatoon 3", "splatoon"],
    "mario": ["mario kart", "super mario", "mario wonder"],
    "sonic": ["sonic", "sonic frontiers"],
}

for key, aliases in _raw_aliases.items():
    for alias in aliases:
        GAME_ALIASES.append((alias.lower(), key))

# Longest alias first so "call of duty" beats "cod" in ambiguous cases
GAME_ALIASES.sort(key=lambda x: len(x[0]), reverse=True)


def footage_search_name(name: str) -> str:
    """Full game title for trailer/gameplay search (Steam, YouTube)."""
    key = resolve_game_key(name)
    if key in FOOTAGE_SEARCH_NAMES:
        return FOOTAGE_SEARCH_NAMES[key]
    if key != "gaming":
        return GAME_DISPLAY.get(key, name.strip())
    detected = detect_game_from_text(name)
    if detected != "Gaming":
        dkey = resolve_game_key(detected)
        return FOOTAGE_SEARCH_NAMES.get(dkey, detected)
    return name.strip() or "Gaming"


def game_match_terms(name: str) -> list[str]:
    """Terms that should match a YouTube title for this game."""
    key = resolve_game_key(name)
    search = footage_search_name(name)
    terms = {search.lower(), name.lower().strip()}
    if key in GAME_DISPLAY:
        terms.add(GAME_DISPLAY[key].lower())
    if key in GAME_KEYWORDS:
        for kw in GAME_KEYWORDS[key][:6]:
            if len(kw) >= 3:
                terms.add(kw.lower())
    for alias, akey in GAME_ALIASES:
        if akey == key and len(alias) >= 3:
            terms.add(alias.lower())
    return [t for t in terms if t and t != "gaming"]


def resolve_game_key(name: str) -> str:
    """Map display name or user input to canonical keyword key."""
    lower = name.lower().strip()
    for key, display in GAME_DISPLAY.items():
        if key == lower or display.lower() == lower:
            return key
    for alias, key in GAME_ALIASES:
        if alias == lower or alias in lower:
            return key
    return "gaming"


def detect_game_from_text(text: str) -> str:
    """Return display name for best-matching popular game."""
    import re

    lower = text.lower().replace("_", " ").replace("-", " ")
    for alias, key in GAME_ALIASES:
        if len(alias) <= 4:
            if re.search(rf"\b{re.escape(alias)}\b", lower):
                return GAME_DISPLAY.get(key, key.title())
        elif alias in lower:
            return GAME_DISPLAY.get(key, key.title())
    return "Gaming"


def list_popular_games() -> list[str]:
    """All supported games for CLI listing."""
    return [GAME_DISPLAY[k] for k in GAME_DISPLAY if k != "gaming"]