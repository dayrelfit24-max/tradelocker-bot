"""Monetization progress and growth checklist."""

from __future__ import annotations

from youtube_auth import get_youtube_service


MONETIZATION_REQUIREMENTS = {
    "subscribers": 1000,
    "watch_hours_12mo": 4000,
    "shorts_views_90d": 10_000_000,
}


def fetch_channel_stats() -> dict:
    yt = get_youtube_service()
    ch = yt.channels().list(
        part="snippet,statistics,contentDetails",
        mine=True,
    ).execute()
    items = ch.get("items", [])
    if not items:
        return {"error": "No channel found"}
    item = items[0]
    st = item["statistics"]
    subs = int(st.get("subscriberCount", 0))
    views = int(st.get("viewCount", 0))
    videos = int(st.get("videoCount", 0))
    return {
        "title": item["snippet"]["title"],
        "subscribers": subs,
        "views": views,
        "videos": videos,
        "subs_needed": max(0, MONETIZATION_REQUIREMENTS["subscribers"] - subs),
        "subs_pct": min(100, round(100 * subs / MONETIZATION_REQUIREMENTS["subscribers"], 1)),
    }


def print_growth_report() -> None:
    try:
        stats = fetch_channel_stats()
    except Exception as e:
        print(f"Could not fetch stats (run `auth` first): {e}")
        return

    if "error" in stats:
        print(stats["error"])
        return

    print("\n📊 CHANNEL GROWTH DASHBOARD")
    print("=" * 40)
    print(f"Channel: {stats['title']}")
    print(f"Subscribers: {stats['subscribers']:,} / 1,000 ({stats['subs_pct']}%)")
    print(f"Still need: {stats['subs_needed']:,} subs for YPP")
    print(f"Total views: {stats['views']:,}")
    print(f"Videos: {stats['videos']}")
    print("\n🎯 MONETIZATION (YouTube Partner Program)")
    print("  • 1,000 subscribers")
    print("  • 4,000 watch hours (last 12 months) OR 10M Shorts views (90 days)")
    print("  Check exact hours in YouTube Studio → Analytics → Reach")
    print("\n🚀 FAST GROWTH PLAYBOOK (automate what you can)")
    print("  1. Upload 3–5 Shorts/week + 1 long video/week (this pipeline)")
    print("  2. Same game niche = algorithm learns your audience")
    print("  3. Thumbnail A/B: change thumb after 48h if CTR < 4%")
    print("  4. First 24h: reply every comment, pin best question")
    print("  5. End screens + cards to your best performing video")
    print("  6. Series playlists (Part 1, 2, 3) for session time")
    print("  7. Community tab poll 2x/week")
    print("  8. Cross-post Shorts to TikTok/Reels with link in bio")
    print()