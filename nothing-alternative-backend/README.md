# Nothing Alternative — Backend API

FastAPI + PostgreSQL backend for cross-device session sync.

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/google` | — | Exchange Google ID token → JWT |
| POST | `/auth/apple` | — | Exchange Apple ID token → JWT |
| GET | `/auth/me` | ✓ | Verify token, get user info |
| GET | `/profiles/` | ✓ | Get all focus profiles |
| PUT | `/profiles/` | ✓ | Full profile sync from device |
| GET | `/sessions/status` | ✓ | Live session state (poll every 2s) |
| POST | `/sessions/start` | ✓ | Start a session (broadcasts to all devices) |
| POST | `/sessions/stop` | ✓ | Stop session, save to history |
| GET | `/sessions/history` | ✓ | Full session history |
| GET | `/health` | — | Health check |

Interactive docs available at `/docs` once deployed.

---

## Deploy to Railway (5 minutes)

### 1. Create the project

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Create project
railway init          # choose "Empty project"
railway add           # choose "Database → PostgreSQL"
```

### 2. Set environment variables

In the Railway dashboard → your service → Variables, add:

```
JWT_SECRET         = <run: python -c "import secrets; print(secrets.token_hex(64))">
GOOGLE_CLIENT_ID   = <from Google Cloud Console>
APPLE_CLIENT_ID    = <from Apple Developer — skip until iOS>
```

`DATABASE_URL` is injected automatically by Railway's Postgres plugin.

### 3. Deploy

```bash
railway up
```

That's it. Railway builds from `railway.toml`, installs requirements, and starts uvicorn.
Your API will be live at `https://<your-project>.up.railway.app`.

---

## Connect the Windows app

Replace the local status server URL in `nothing_alternative.py`:

```python
# Old
STATUS_PORT = 59284
# ... HTTPServer on localhost

# New — add near the top of the file
API_BASE = "https://<your-project>.up.railway.app"
API_TOKEN = "<user's JWT, stored after sign-in>"

# Replace the status poll in enforce_gatekeeper:
import requests
def get_session_status():
    r = requests.get(f"{API_BASE}/sessions/status",
                     headers={"Authorization": f"Bearer {API_TOKEN}"},
                     timeout=3)
    return r.json()   # {"active": bool, "blocked": [...], "allowed_apps": [...]}
```

The browser extension's `background.js` changes identically — swap the URL from
`http://localhost:59284/status` to `https://<your-project>.up.railway.app/sessions/status`
and add the `Authorization: Bearer <token>` header.

---

## Google Cloud setup (10 minutes)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Enable the **Google Identity** API
4. Create credentials → **OAuth 2.0 Client ID**
   - Application type: **Web application**
   - Authorised JavaScript origins: your Railway domain + `http://localhost` (for dev)
5. Copy the **Client ID** (ends in `.apps.googleusercontent.com`) → `GOOGLE_CLIENT_ID`

The client apps (Windows, Mac, mobile) each use the platform-specific Google Sign-In SDK
to get an `id_token`, then POST it to `/auth/google`. No secret needed on the client.

---

## Data model

```
users
  id, email, google_id, apple_id, display_name, created_at, last_seen_at

profiles
  id, user_id, name, allowed_apps[], banned_keywords[], is_active, updated_at

sessions                        ← completed session history
  id, user_id, goal, profile_name, started_at, ended_at,
  duration_s, blocked_count, block_log[], device_id

active_sessions                 ← live state, one row per active user
  user_id (PK), session_id, goal, blocked_sites[], allowed_apps[],
  started_at, started_by
```

`active_sessions` is the sync mechanism — when any device calls `/sessions/start`
a row is written; all other devices polling `/sessions/status` see it within 2 seconds.
When the session stops the row is deleted and all devices see `active: false`.
