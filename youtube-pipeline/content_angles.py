"""Rotating content angles — break the same settings/mistake loop."""

from __future__ import annotations

from datetime import datetime

# Long-form angles (rotate by day) — game-specific, accurate framing
LONG_ANGLES: dict[str, list[str]] = {
    "CS2": [
        "crosshair and sensitivity mistakes losing every duel",
        "peek timing habits that get you one-tapped",
        "utility usage most players waste in Premier",
        "recoil control and spray transfer basics",
        "map positioning errors on common bombsite takes",
        "audio and info habits losing free rounds",
        "economy and force-buy decisions costing games",
    ],
    "Fortnite": [
        "edit speed settings hurting your box fights",
        "piece control habits losing mid-game fights",
        "sensitivity and aim settings for ranked",
        "rotation timing mistakes in late zones",
        "loadout choices hurting your win rate",
        "build binds and edit binds most players skip",
        "zero build vs build decision mistakes",
    ],
    "GTA": [
        "aim and sensitivity hurting Online gunfights",
        "cover and movement habits losing PvP fights",
        "auto-aim and targeting settings on PC",
        "vehicle combat mistakes in freeroam fights",
        "heist prep habits wasting your time",
        "KD-saving habits that actually work in Online",
        "controller vs keyboard mistakes on PC",
    ],
}

# Short = ONE sharp micro-topic (different from long same day)
SHORT_ANGLES: dict[str, list[str]] = {
    "CS2": [
        "fix your counter-strafe in 30 seconds",
        "stop wide-swinging this common angle",
        "one crosshair setting to copy today",
        "pre-aim this spot before every peek",
        "stop buying wrong on pistol round",
        "this smoke lineup wins free rounds",
        "lower sens might fix your flicks",
    ],
    "Fortnite": [
        "5 tips that instantly improve box fights",
        "the building trick pro players won't tell you",
        "this PC setting is killing your aim — fix it",
        "one edit bind that speeds up piece control",
        "rotate 30 seconds earlier in late zones",
        "stop taking height fights you will lose",
        "one sensitivity tweak for shotgun flicks",
        "the piece control habit ranked players use",
    ],
    "GTA": [
        "fix your aim assist on PC",
        "stop fighting in the open like this",
        "one drive-by angle that works",
        "cover swap habit that saves fights",
        "stop reloading in the wrong spot",
        "this sensitivity helps Online aim",
        "peek corners like this not that",
    ],
}


def long_topic(game: str, platform: str = "PC") -> str:
    angles = LONG_ANGLES.get(game, LONG_ANGLES["CS2"])
    angle = angles[datetime.now().day % len(angles)]
    return f"{game} on {platform}: {angle}"


def winning_short_angle(game: str, platform: str = "PC") -> str:
    """Audit-winning Short angle — numbered tips / specific mechanic."""
    angles = SHORT_ANGLES.get(game, SHORT_ANGLES.get("Fortnite", []))
    angle = angles[datetime.now().timetuple().tm_yday % len(angles)]
    return f"{game} {platform}: {angle}"


def short_topic(game: str, platform: str = "PC", long_topic_text: str = "") -> str:
    angles = SHORT_ANGLES.get(game, SHORT_ANGLES["CS2"])
    # Pick short angle offset from long so same-day pair feels different
    idx = (datetime.now().day + 3) % len(angles)
    angle = angles[idx]
    # Ensure short isn't substring of long topic
    if angle.lower() in long_topic_text.lower():
        idx = (idx + 2) % len(angles)
        angle = angles[idx]
    return f"{game} {platform}: {angle}"