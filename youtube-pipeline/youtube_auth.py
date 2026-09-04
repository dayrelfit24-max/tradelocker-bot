"""YouTube OAuth2 — run once to authorize uploads."""

from __future__ import annotations

import sys
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import config

OAUTH_PORTS = (8080, 8081, 8082, 8090)


def _print_setup_help() -> None:
    print(
        """
╔══════════════════════════════════════════════════════════════╗
║  YouTube OAuth — fix Chrome errors BEFORE clicking Allow     ║
╚══════════════════════════════════════════════════════════════╝

In Google Cloud Console (project: stunning-cell-498318-b3):

1. APIs & Services → Library → enable "YouTube Data API v3"

2. APIs & Services → OAuth consent screen:
   • User type: External
   • Add YOUR Gmail as a "Test user" (required while app is in Testing)
   • Scopes → Add:
     - .../auth/youtube.upload
     - .../auth/youtube
     - .../auth/youtube.force-ssl

3. APIs & Services → Credentials:
   • OAuth client must be type "Desktop app" (not Web)
   • Your JSON should say "installed" at the top ✓

4. In Chrome when you see "Google hasn't verified this app":
   • Click "Advanced" → "Go to stunning-cell... (unsafe)" — normal for personal apps

Trying localhost ports 8080, 8081, 8082, 8090 ...
"""
    )


def get_credentials() -> Credentials:
    config.TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    creds: Credentials | None = None

    if config.TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(
            str(config.TOKEN_PATH), config.SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                print("⚠️  Stored token expired/revoked — starting fresh sign-in...")
                creds = None
        if not creds or not creds.valid:
            if not config.YOUTUBE_CLIENT_SECRETS.exists():
                print(
                    f"\nMissing {config.YOUTUBE_CLIENT_SECRETS}\n"
                    "Download OAuth Desktop JSON from Google Cloud Console.\n"
                )
                sys.exit(1)
            _print_setup_help()
            flow = InstalledAppFlow.from_client_secrets_file(
                str(config.YOUTUBE_CLIENT_SECRETS), config.SCOPES
            )
            creds = None
            last_err: Exception | None = None
            for port in OAUTH_PORTS:
                try:
                    print(f"Opening browser at http://localhost:{port}/ ...")
                    creds = flow.run_local_server(
                        port=port,
                        prompt="consent",
                        access_type="offline",
                        open_browser=True,
                    )
                    break
                except Exception as e:
                    last_err = e
                    err = str(e).lower()
                    if "address already in use" in err or "errno 48" in err:
                        print(f"⚠️  Port {port} busy — trying next...")
                        continue
                    print(f"\n❌ OAuth failed: {e}\n")
                    if "redirect_uri" in err or "mismatch" in err:
                        print(
                            "FIX redirect_uri_mismatch:\n"
                            "  • Recreate credential as 'Desktop app' (not Web)\n"
                            f"  • Or add redirect URI: http://localhost:{port}/\n"
                        )
                    elif "access_denied" in err or "403" in err:
                        print(
                            "FIX access_denied:\n"
                            "  • OAuth consent screen → Test users → add your Gmail\n"
                            "  • Sign in with the SAME Gmail that owns @ProGamer-ys7hu\n"
                        )
                    elif "disabled" in err or "youtube" in err:
                        print("FIX: Enable 'YouTube Data API v3' in Google Cloud Library\n")
                    sys.exit(1)
            if not creds:
                print(f"\n❌ OAuth failed on all ports: {last_err}\n")
                sys.exit(1)
        config.TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return creds


def get_youtube_service():
    creds = get_credentials()
    return build("youtube", "v3", credentials=creds)


def run_auth_cli() -> None:
    """Force OAuth flow and print channel info."""
    yt = get_youtube_service()
    ch = yt.channels().list(part="snippet,statistics", mine=True).execute()
    items = ch.get("items", [])
    if not items:
        print("Authorized but no channel found on this Google account.")
        print("Sign in with the Google account linked to @ProGamer-ys7hu")
        return
    sn = items[0]["snippet"]
    st = items[0]["statistics"]
    print(f"✅ Connected: {sn['title']}")
    print(f"   Subscribers: {st.get('subscriberCount', '?')}")
    print(f"   Total views: {st.get('viewCount', '?')}")
    print(f"   Token saved: {config.TOKEN_PATH}")