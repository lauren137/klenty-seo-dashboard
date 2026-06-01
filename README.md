# Klenty SEO Live Tracking Dashboard

Live dashboard pulling GSC + GA4 metrics for tracked Klenty URLs. Built with Streamlit.

## Run locally

```bash
./run.sh
# Opens at http://localhost:8501
```

The first run creates a venv and installs deps. Subsequent runs are instant.

## Deploy to Streamlit Community Cloud (free, always-on)

### 1. Push this folder to a new GitHub repo

```bash
cd /Users/lauren/Desktop/klenty-seo-dashboard
git init
git add .
git commit -m "Initial commit: Klenty SEO Dashboard"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/klenty-seo-dashboard.git
git push -u origin main
```

**Important:** `.gitignore` already excludes `token.json`, `credentials.json`, `secrets.toml`, and `dashboard.db`. Verify with `git status` before pushing.

### 2. Connect to Streamlit Cloud

1. Go to https://share.streamlit.io
2. Sign in with the GitHub account
3. Click **New app** → pick your repo → branch `main` → main file `app.py`
4. Click **Advanced settings** → **Secrets** → paste this (fill in the actual values):

```toml
# Password to access the dashboard — share this with people you trust.
app_password = "pick-something-strong"

[google_oauth]
client_id = "277662933468-vhol93edt9jjm47mlk6fc5v2pdm68rtj.apps.googleusercontent.com"
client_secret = "YOUR_CLIENT_SECRET_HERE"
refresh_token = "YOUR_REFRESH_TOKEN_HERE"
token_uri = "https://oauth2.googleapis.com/token"

[google_targets]
ga4_property_id = "264568011"
gsc_site_url = "sc-domain:klenty.com"
site_domain = "https://www.klenty.com"
```

The exact values come from `/Users/lauren/Desktop/ga4-gsc-mcp-server/token.json` (refresh_token, client_id, client_secret).

5. Click **Deploy**. ~2 min later you'll have a URL like `https://klenty-seo.streamlit.app`.

## What's in here

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit UI — summary cards, table, trend explorer, Add URL modal |
| `google_clients.py` | GSC + GA4 API clients (auto-loads creds from Streamlit secrets or local files) |
| `data_store.py` | SQLite for tracked URL list + response cache |
| `styles.py` | Asana-inspired CSS injection |
| `seed_urls.json` | 29 URLs pre-loaded on first start |
| `.streamlit/config.toml` | Forces light theme |
| `requirements.txt` | Python deps |
| `run.sh` | One-command local launcher |

## Notes

- **24h GSC data is unreliable** — Google's API has a ~2-day lag. GA4 is fresher.
- **Cache TTL is 15 min** — click ⟳ Refresh to force-fetch.
- **Added URLs are ephemeral on Streamlit Cloud** — the SQLite DB resets on each restart. Edit `seed_urls.json` and re-push to permanently add URLs.
- **OAuth refresh tokens don't expire** unless explicitly revoked.
