# Setup Checklist — what YOU need to do

Follow the steps in order. Each step says what to do, exactly how, and how to know it worked.
Commands are for a terminal (Git Bash or PowerShell) opened in the repo root
(`nba_fan_yahoo/`) unless stated otherwise.

What the app needs, in one line each:

| Service | Used for | Required now? |
|---|---|---|
| Gemini API key | the AI answers + embeddings | **Yes** |
| Google Cloud project + Firestore | stores the document vectors for retrieval | **Yes** |
| Firestore (same project) | user accounts / Yahoo links | **Yes** (no extra setup) |
| Google OAuth client | "Login with Google" | **Yes** (to log in) |
| Yahoo developer app | reading your fantasy league | **Yes** (to sync a league) |
| HTTPS tunnel (ngrok/cloudflared) | Google/Yahoo redirect to `https://` | **Yes** (for local login) |
| OpenAI | — | **No longer needed** |
| Azure | optional blob storage only | No |

---

## Step 0 — Install Python packages (2 min)

```
pip install -r requirements.txt
```

**Check:** `python -m pytest -q` prints `70 passed, 9 deselected`. (No keys needed; fully offline.)

---

## Step 1 — Get a Gemini API key (3 min)

1. Open https://aistudio.google.com/apikey and sign in with your Google account.
2. Click **Create API key** → pick a project (or "Create API key in new project").
3. Copy the key. Keep it for Step 5 as `GEMINI_API_KEY`.

**Check the key works** (replace `YOUR_KEY`):
```
python -c "import litellm; print(litellm.completion(model='gemini/gemini-3.8-flash', messages=[{'role':'user','content':'say hi'}], api_key='YOUR_KEY').choices[0].message.content)"
```
It should print a greeting. (Verified on 2026-10-07 with `gemini-3.8-flash`; `gemini-2.5-flash` is no longer available to new keys.) If it says the model isn't found, use the current Flash model name from AI Studio in `LLM_MODEL` (Step 5). A 503 "high demand" is temporary; retry in a minute.

---

## Step 2 — Embedding model and vector size (nothing to do, just know it)

Firestore needs the exact vector length when you create its index and **supports at most 2048 dimensions**.
Tested with a real key: `gemini/text-embedding-004` no longer exists, and `gemini/gemini-embedding-001`
natively returns 3072 numbers (too many), but it accepts a shorter size. So the app is configured to use

```
EMBEDDING_MODEL=gemini/gemini-embedding-001
EMBEDDING_DIMENSIONS=768
```

**So `DIM` = 768** for the index in Step 4. If you ever change either value, you must recreate the index and re-run Step 10.

---

## Step 3 — Google Cloud project + Firestore (10 min)

`gcloud` is already installed and you're signed in as urilevy1999@gmail.com.

1. **Pick/create a project.** Your current default (`ir-assignment3-445213`) looks like a
   different project, so I recommend a new one:
   ```
   gcloud projects create nba-fantasy-ai-<yourname>      # name must be globally unique
   gcloud config set project nba-fantasy-ai-<yourname>
   ```
2. **Link billing** (Firestore vector search requires a billing account, even though small usage
   stays in the free tier): https://console.cloud.google.com/billing/linkedaccount → select the project → link.
3. **Enable Firestore:**
   ```
   gcloud services enable firestore.googleapis.com
   ```
4. **Create the database** (choose the region closest to you, e.g. `eur3` for Europe, `nam5` for US; this cannot be changed later):
   ```
   gcloud firestore databases create --location=eur3
   ```
5. **Log in for local development** (lets the app use your account, no key file needed):
   ```
   gcloud auth application-default login
   gcloud auth application-default set-quota-project nba-fantasy-ai-<yourname>
   ```

**Check:** `gcloud firestore databases list` shows a `(default)` database.

---

## Step 4 — Create the vector index (1 min + a few minutes to build)

Use `768` (the `DIM` from Step 2):

```
gcloud firestore indexes composite create --collection-group=chunks --query-scope=COLLECTION --field-config=field-path=embedding,vector-config='{"dimension":"768","flat":"{}"}'
```

> PowerShell: wrap the whole `--field-config=...` argument in double quotes and escape inner
> quotes, or just run this in Git Bash where the line above works as written.

**Check:** `gcloud firestore indexes composite list` shows the index with state `READY`
(wait until it's READY; it can take a few minutes). Searching before it's ready fails with a
"requires an index" error.

---

## Step 5 — Create `src/.env` (5 min)

Create the file `nba_fan_yahoo/src/.env` (it is git-ignored, never commit it):

```env
# --- AI (new) ---
LLM_MODEL=gemini/gemini-3.8-flash
EMBEDDING_MODEL=gemini/gemini-embedding-001
EMBEDDING_DIMENSIONS=768
GEMINI_API_KEY=<from Step 1>
GOOGLE_CLOUD_PROJECT=<project id from Step 3>

# --- Optional: archive copy of synced league JSON ---
# Leave all of these out and no archive is kept (the AI index in Firestore is what the chat uses).
# BLOB_STORAGE=gcs            # gcs | azure | none  (auto: gcs if GCS_BUCKET set, azure if AZURE_STORAGE_CONNECTION_STRING set)
# GCS_BUCKET=<bucket name>    # see 'Optional: Cloud Storage bucket' below
# LLM_FALLBACK_MODEL=gemini/gemini-3.7-flash

# --- App ---
FLASK_SECRET_KEY=<run: python -c "import secrets; print(secrets.token_hex(32))">

# --- Google login ---
GOOGLE_CLIENT_ID=<Step 6>
GOOGLE_CLIENT_SECRET=<Step 6>

# --- Yahoo ---
YAHOO_CLIENT_ID=<Step 7>
YAHOO_CLIENT_SECRET=<Step 7>
YAHOO_REDIRECT_URL=https://<your-tunnel-host>/auth/yahoo/callback
```

Optional: `RETRIEVAL_TOP_K=5`, `CHAT_HISTORY_TURNS=10`, `SYSTEM_PROMPT_PATH=...`, `DEBUG=true`.
You can delete `OPENAI_API_KEY`; nothing reads it any more (unless you set `LLM_MODEL=openai/...`).

---

## Step 6 — Google login credentials (10 min)

1. https://console.cloud.google.com/apis/credentials (use the same project).
2. If asked, configure the **OAuth consent screen** first (External, add yourself as a test user).
3. **Create credentials → OAuth client ID → Web application.**
4. **Authorized redirect URIs:** `https://<your-tunnel-host>/auth/google/callback`
   (the tunnel host comes from Step 8; you can come back and add it).
5. Copy the Client ID and secret into `.env`.

## Step 7 — Yahoo developer app (10 min)

1. https://developer.yahoo.com/apps/ → **Create an App**.
2. Redirect URI: `https://<your-tunnel-host>/auth/yahoo/callback` (same value as `YAHOO_REDIRECT_URL`).
3. API permissions: **Fantasy Sports → Read**.
4. Copy Client ID / Secret into `.env`.

## Step 8 — HTTPS tunnel (5 min)

The code builds the Google/Yahoo redirect URLs with `https` (`router/auth_routes.py`), and Yahoo only
accepts `https`. So locally you need a tunnel to port 8000:

```
ngrok http 8000          # or: cloudflared tunnel --url http://localhost:8000
```

Copy the `https://....` host it prints into Steps 6 and 7 (and `YAHOO_REDIRECT_URL`).
Note: a free ngrok URL changes every time you restart it; update the two consoles + `.env` when it does.

---

## Step 9 — Verify Firestore works with the real contract tests (2 min)

```
# Git Bash
FIRESTORE_TEST_PROJECT=<project id> python -m pytest -m integration -q
# PowerShell
$env:FIRESTORE_TEST_PROJECT="<project id>"; python -m pytest -m integration -q
```

**Check:** `9 passed`. If it fails with "requires an index", wait for the index to be READY (Step 4)
and make sure the dimension matches. These tests create a temporary `test_rag_*` collection and delete it.

> The tests pad their tiny vectors to `EMBEDDING_DIMENSIONS` (768 by default), so they work against the 768-dim index from Step 4.

---

## Step 10 — Load the documents into the index (5 min)

This reads the rules PDF + player stats + schedule, embeds them with Gemini and stores them in Firestore:

```
cd src
python -m appl.scripts.fantasy_rules.fantasy_rule
```

**Check:** it prints "✅ Player stats and schedule successfully updated". In the
Firestore console (https://console.firebase.google.com → your project → Firestore) you see
`rag_collections → general → chunks` with documents.
Re-running replaces the old content (no duplicates).

League data (`league_<id>`) is indexed automatically when you sync a league in the app (Step 12).

---

## Step 11 — Start the server

```
cd src
python -m appl.app
```
(Stop the old server from earlier first. It's still running the old code on port 8000.)
Start your tunnel (Step 8) in another terminal.

**Check:** `curl localhost:8000/health` returns OK, and the tunnel URL opens the landing page.

## Step 12 — Try it end to end

1. Open the tunnel URL → **Login with Google** → **Connect Yahoo** → sync your league
   (this indexes `league_<id>`).
2. Ask a question without the UI:
   ```
   curl -X POST localhost:8000/chat -H "Content-Type: application/json" -d "{\"session_id\":\"s1\",\"user_message\":\"What are the scoring categories?\"}"
   ```
   You should get an answer based on the rules PDF.
3. Ask a follow-up with the same `session_id` (e.g. "and which one matters most?") — it should remember the conversation.

## Step 13 — Prove the LLM is swappable (optional, 2 min)

In `.env` set `LLM_MODEL=openai/gpt-4o-mini` and `OPENAI_API_KEY=...`, restart, repeat the curl.
(Embeddings stay on Gemini, so no re-index is needed. Changing `EMBEDDING_MODEL` **does** require re-running Step 10 and every league sync, and a new index if the dimension differs.)

---

## Optional: Cloud Storage bucket for the league-data archive

Azure is **no longer required**: league sync works with no blob storage at all. If you want an archive copy of each synced JSON file in Google Cloud:

```
gcloud storage buckets create gs://<unique-bucket-name> --location=eur3
```
then set `GCS_BUCKET=<unique-bucket-name>` in `.env` (uses the same `gcloud auth application-default login` credentials; files are stored under `<container>/<leagueId>/…`, and unchanged files are not re-uploaded).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `DefaultCredentialsError` / "Could not automatically determine credentials" | Run `gcloud auth application-default login` (Step 3.5). |
| "The query requires a vector index" | Index not READY yet, or wrong dimension/collection-group (Step 4). |
| "Vector dimension mismatch" / invalid argument | `EMBEDDING_MODEL` dimension ≠ index dimension. Recreate the index with the right `DIM`, re-index. |
| `/chat` returns 502 "AI service is unavailable" | Bad/missing `GEMINI_API_KEY`, quota, or wrong model name. Details are in the server log. |
| `/chat` returns 400 | Body must be JSON with `session_id` and non-empty `user_message`. |
| Chat answers ignore your league | League wasn't synced after the change; sync it again (Step 12). |
| Google/Yahoo login "redirect_uri mismatch" | The tunnel URL changed or isn't registered exactly (Steps 6–8). |
| Conversation memory resets | Sessions are kept in server memory; a restart (or the dev auto-reloader) clears them. Known limitation, see AI_DESIGN.md. |
