# Fix Chrome OAuth Errors (ProGamer Upload)

## Error: "Access blocked" / "has not completed Google verification"

**Fix:** On the warning page click **Advanced** → **Go to stunning-cell-498318-b3 (unsafe)**.  
This is normal for apps in Testing mode.

---

## Error: "Access denied" / "You don't have access"

**Fix:**
1. [Google Cloud Console](https://console.cloud.google.com/) → your project
2. **APIs & Services** → **OAuth consent screen**
3. Under **Test users** → **Add users** → add the Gmail you use for @ProGamer-ys7hu
4. Run auth again and sign in with that same Gmail

---

## Error: "redirect_uri_mismatch"

**Fix:**
1. **Credentials** → your OAuth client must be **Desktop app** (not Web)
2. Re-download JSON → replace `client_secrets.json`
3. Or if using Web client, add redirect URI: `http://localhost:8080/`

---

## Error: "YouTube Data API has not been used" / API disabled

**Fix:**
1. **APIs & Services** → **Library**
2. Search **YouTube Data API v3** → **Enable**

---

## Error: Missing scopes

**Fix:** OAuth consent screen → **Edit app** → **Scopes** → Add:
- `https://www.googleapis.com/auth/youtube.upload`
- `https://www.googleapis.com/auth/youtube`
- `https://www.googleapis.com/auth/youtube.force-ssl`

---

## After fix, run:

```bash
cd youtube-pipeline
source .venv/bin/activate
python pipeline.py auth
```