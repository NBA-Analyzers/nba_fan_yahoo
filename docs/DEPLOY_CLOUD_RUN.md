# Deploying to Google Cloud Run

**Status:** deployed and verified on 2026-10-08 (project `nbafantasy-511015`, service `fantasy-ai`, region `europe-west1`,
URL `https://fantasy-ai-276008835589.europe-west1.run.app`). Verified: landing page, `/health`, anonymous `/chat` -> 401, no errors in logs,
one instance, runs as the `fantasy-app` service account. **Not yet verified:** a logged-in chat on the live site (needs the Google/Yahoo
client IDs below) and the service account actually reading Firestore (the `roles/datastore.user` grant exists).

## What was actually run
1. Enabled `run`, `cloudbuild`, `artifactregistry`, `secretmanager`, `iam` APIs.
2. Created service account `fantasy-app` + `roles/datastore.user`.
3. Secrets `gemini-api-key`, `flask-secret` (new random value for production) in Secret Manager, with `secretAccessor` for `fantasy-app`.
4. Exported a **clean copy of the committed branch** (`git archive HEAD | tar -x -C <dir>`) so uncommitted local work is never deployed, then:
   `gcloud run deploy fantasy-ai --source <dir> --region europe-west1 --service-account fantasy-app@... --allow-unauthenticated --max-instances 1 --memory 1Gi --timeout 600 --env-vars-file env.yaml --set-secrets ...`
5. To add the login credentials later: put the client IDs in the env file / `gcloud run services update fantasy-ai --update-env-vars GOOGLE_CLIENT_ID=...,YAHOO_CLIENT_ID=...`, store the two client secrets in Secret Manager and attach with `--update-secrets GOOGLE_CLIENT_SECRET=google-client-secret:latest,YAHOO_CLIENT_SECRET=yahoo-client-secret:latest`.
6. Register `https://fantasy-ai-276008835589.europe-west1.run.app/auth/google/callback` (Google) and `.../auth/yahoo/callback` (Yahoo).

## Nightly data refresh (Cloud Run Job + Cloud Scheduler) — not yet run

`python -m appl.ingest run all` refreshes the shared AI index (player stats, schedule, rules; one
Firestore collection each, skipped when unchanged) and the draft/in-season player pools (stored in
GCS under `datasets/`). It runs from the same image as the service.

1. A bucket for datasets (the archive bucket works too) and access for the service account:
   ```
   gcloud storage buckets create gs://<PROJECT_ID>-fantasy-data --location europe-west1
   gcloud storage buckets add-iam-policy-binding gs://<PROJECT_ID>-fantasy-data \
     --member=serviceAccount:fantasy-app@<PROJECT_ID>.iam.gserviceaccount.com --role=roles/storage.objectAdmin
   ```
2. Give the **service** `DATASET_BUCKET=<PROJECT_ID>-fantasy-data` too, so app instances read the pools the job wrote
   (`gcloud run services update fantasy-ai --update-env-vars DATASET_BUCKET=...`). Also turn on
   `--no-cpu-throttling`: the league sync started from the chat page runs in a background thread, which
   Cloud Run otherwise starves of CPU once the response is sent.
3. Create the job (same image the service runs; `gcloud run services describe fantasy-ai --format='value(spec.template.spec.containers[0].image)'`):
   ```
   gcloud run jobs create ingest-nightly --image <IMAGE> --region europe-west1 \
     --service-account fantasy-app@<PROJECT_ID>.iam.gserviceaccount.com \
     --command python --args=-m,appl.ingest,run,all \
     --set-env-vars PYTHONPATH=/app/src,GOOGLE_CLOUD_PROJECT=<PROJECT_ID>,DATASET_BUCKET=<PROJECT_ID>-fantasy-data,EMBEDDING_MODEL=gemini/gemini-embedding-001,EMBEDDING_DIMENSIONS=768 \
     --set-secrets GEMINI_API_KEY=gemini-api-key:latest \
     --task-timeout 3600 --max-retries 1 --memory 1Gi
   gcloud run jobs execute ingest-nightly --region europe-west1 --wait
   ```
   On redeploys, point the job at the new image: `gcloud run jobs update ingest-nightly --image <IMAGE>`.
4. Schedule it at 09:00 UTC (after the night's NBA games):
   ```
   gcloud scheduler jobs create http ingest-nightly --location europe-west1 --schedule "0 9 * * *" --time-zone UTC \
     --uri "https://run.googleapis.com/v2/projects/<PROJECT_ID>/locations/europe-west1/jobs/ingest-nightly:run" \
     --http-method POST --oauth-service-account-email fantasy-app@<PROJECT_ID>.iam.gserviceaccount.com
   gcloud projects add-iam-policy-binding <PROJECT_ID> \
     --member=serviceAccount:fantasy-app@<PROJECT_ID>.iam.gserviceaccount.com --role=roles/run.invoker
   ```
5. Check: the job's logs end with `general_index done ...` and `player_pool done ...` (JSON counts);
   a second run the same day logs `general_stats unchanged, skipped`.

The first run also deletes the old single `rag_collections/general` collection; until it runs, the chat
has no shared stats/schedule/rules context (it searches `general_rules`, `general_stats`, `general_schedule`).

---

## Original draft notes (kept for reference)
## 1. One-time setup
```
gcloud config set project <PROJECT_ID>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
```
Create a service account for the app and let it use Firestore (and the archive bucket if you use one):
```
gcloud iam service-accounts create fantasy-app
gcloud projects add-iam-policy-binding <PROJECT_ID> --member=serviceAccount:fantasy-app@<PROJECT_ID>.iam.gserviceaccount.com --role=roles/datastore.user
# only if BLOB_STORAGE=gcs:
gcloud storage buckets add-iam-policy-binding gs://<BUCKET> --member=serviceAccount:fantasy-app@<PROJECT_ID>.iam.gserviceaccount.com --role=roles/storage.objectAdmin
```
On Cloud Run the app authenticates to Firestore/Storage as this service account — **no key file**.

## 2. Secrets (Secret Manager)
Create one secret per sensitive value (paste the value when prompted via stdin):
```
printf '%s' '<value>' | gcloud secrets create gemini-api-key --data-file=-
```
Do the same for `FLASK_SECRET_KEY`, `GOOGLE_CLIENT_SECRET`, `YAHOO_CLIENT_SECRET`, then grant access:
```
gcloud secrets add-iam-policy-binding gemini-api-key --member=serviceAccount:fantasy-app@<PROJECT_ID>.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor
```

### ESPN leagues (optional)
Private ESPN leagues are read with the user's `espn_s2` and `SWID` cookies, which open their whole ESPN account. They are stored
only Fernet-encrypted (Firestore `espn_auth`), with the key in a secret. Without `ESPN_COOKIE_KEY`, only public ESPN leagues connect.
```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" | gcloud secrets create espn-cookie-key --data-file=-
```
Grant `secretAccessor` as above and add `ESPN_COOKIE_KEY=espn-cookie-key:latest` to `--set-secrets`. Rotating the key makes users reconnect ESPN.

## 3. Deploy (builds the Dockerfile in the repo root)
```
gcloud run deploy fantasy-ai --source . --region europe-west1 --service-account fantasy-app@<PROJECT_ID>.iam.gserviceaccount.com \
  --allow-unauthenticated --max-instances 1 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=<PROJECT_ID>,LLM_MODEL=gemini/gemini-3.8-flash,LLM_FALLBACK_MODEL=gemini/gemini-3.7-flash,EMBEDDING_MODEL=gemini/gemini-embedding-001,EMBEDDING_DIMENSIONS=768,GOOGLE_CLIENT_ID=<id>,YAHOO_CLIENT_ID=<id>,YAHOO_REDIRECT_URL=https://<service-url>/auth/yahoo/callback \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest,FLASK_SECRET_KEY=flask-secret:latest,GOOGLE_CLIENT_SECRET=google-client-secret:latest,YAHOO_CLIENT_SECRET=yahoo-client-secret:latest
```
Notes:
- `--max-instances 1` and the Dockerfile's single gunicorn worker are deliberate: chat history lives in process memory
  (see AI_DESIGN.md §10.1). Move sessions to Firestore before scaling out.
- Cloud Run URLs are already HTTPS, so login redirects work without a tunnel. Register
  `https://<service-url>/auth/google/callback` and `/auth/yahoo/callback` in the Google and Yahoo consoles.
- Manual draft leagues are stored in Firestore (collection `manual_leagues`), switched on automatically when `K_SERVICE` is set. The container disk is wiped on every restart, so nothing the draft pages save may live there.
- The first deploy prints the service URL; set `YAHOO_REDIRECT_URL` to match and redeploy.

## 4. Check
`curl https://<service-url>/health`, then the `/chat` curl from SETUP_CHECKLIST Step 12.


## User data in Firestore (replaces Supabase)
Collections, all server-only (the service account reads and writes them; deploy `firestore.rules`, which denies every client):

| Collection | Document id | Holds |
|---|---|---|
| `users` | `user_hash(user_id)` | profile: `user_id`, `full_name`, `email`, `picture`, `last_updated`, Google `access_token` (**secret**) |
| `identities` | `user_hash("<provider>:<provider user id>")` | which sign-in belongs to which `user_id` (`email`, `email_verified`) |
| `yahoo_auth` | Yahoo GUID | Yahoo OAuth tokens (**secrets**: never logged, never sent to the browser) |
| `fantasy_connections` | `<user_hash>_<platform>_<fantasy user id>` | which user is linked to which Yahoo account |
| `yahoo_leagues` | `<league id>_<Yahoo GUID>` | leagues synced for a Yahoo account (the chat access check reads this) |

`user_hash` is the same helper as `manual_leagues` (`sha256(user_id)[:16]`). Writes are `set(merge=True)` on these deterministic ids,
so a double login or a Yahoo reconnect lands on the same document. A user's `user_id` is their Google `sub` for existing and new Google
users, so `manual_leagues` and `api_tokens` need no migration.

**Indexes:** none to create. Every query filters on equality of one or two fields (`google_user_id` + `fantasy_platform`,
`email` + `email_verified`), which Firestore serves from its automatic single-field indexes.

**Rules:** `gcloud firestore databases update` does not take rules; deploy with `firebase deploy --only firestore:rules`
(project = `<PROJECT_ID>`) or paste `firestore.rules` into Firebase console > Firestore > Rules.

### One-off migration from Supabase
Run **before** deploying this version, otherwise users have to reconnect Yahoo once.
```
cd src
export SUPABASE_URL=https://<project-ref>.supabase.co     # the dashboard URL also works
export SUPABASE_KEY=<service-role / secret key>           # the publishable key can't read rows behind RLS
export GOOGLE_CLOUD_PROJECT=<PROJECT_ID>
gcloud auth application-default login
python -m appl.scripts.migrate_supabase_to_firestore --dry-run   # counts only, writes nothing
python -m appl.scripts.migrate_supabase_to_firestore
```
It is safe to re-run: existing documents are skipped, never overwritten. It copies `google_auth`, `yahoo_auth`, `google_fantasy`
and `yahoo_league`. Google and Yahoo tokens are copied so logins stay long-lived. After checking the counts, the Supabase project can be
paused or deleted, and the `supabase-key` secret removed.

## Sign-in: Firebase Auth (email + Google) and server-side sessions
The home page shows the Firebase sign-in widget (email + password with a verification mail, email link, Google). The browser
signs in with the Firebase SDK; `POST /auth/session` verifies the ID token with `firebase-admin` (Application Default Credentials,
no key file) and starts our own session. Until `FIREBASE_API_KEY` and `FIREBASE_AUTH_DOMAIN` are set the page falls back to the
old "Sign in with Google" link (`/auth/google/login`), so nothing breaks before this is configured.

One-time setup (Google Cloud / Firebase console):
1. Add Firebase to the project (console.firebase.google.com > Add project > pick `<PROJECT_ID>`), or enable Identity Platform.
2. Authentication > Sign-in method: enable **Email/Password** (and "Email link (passwordless)"), and **Google**.
3. Authentication > Settings > Authorized domains: add the Cloud Run domain (`fantasy-ai-...run.app`) and your own domain.
4. Authentication > Templates: set the sender and wording of the verification and password-reset emails.
5. Project settings > Your apps > Web app: copy `apiKey` and `authDomain` (public values, not secrets).
6. Cloud Run env vars: `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN` (and `FIREBASE_PROJECT_ID` if it differs from `GOOGLE_CLOUD_PROJECT`).
   The service account needs no extra role to verify tokens.
7. Existing Google users keep their account: their `user_id` stays their Google `sub`. Run the Supabase migration first (it also
   writes the `identities` documents that let an email login with the same address join the old account).

Once Google sign-in through Firebase is verified, the old `/auth/google/*` routes and `GOOGLE_CLIENT_SECRET` can be removed.
Yahoo still connects through its own OAuth flow.

### Sessions (not the same as chat history)
Session data lives in Firestore (`web_sessions`), not in the cookie. The cookie `fbh_sid` is a random id, `HttpOnly`,
`SameSite=Lax`, `Secure` on Cloud Run (override with `SESSION_COOKIE_SECURE=1` behind an https tunnel). Sliding lifetime:
`SESSION_LIFETIME_DAYS` (default 30). `SESSION_STORE=firestore|memory` (default: Firestore when `K_SERVICE` is set).
The session id is replaced at login, and logout deletes the server-side record. Because the Yahoo refresh token is saved with
the user, a new session restores the Yahoo connection without another "Connect Yahoo".

One-time: let Firestore delete expired sessions.
```
gcloud firestore fields ttls update expires_at --collection-group=web_sessions --enable-ttl
```
The service account already has `roles/datastore.user`. Everyone is logged out once when this ships: old cookie sessions are not
migrated.
