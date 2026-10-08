# Deploying to Google Cloud Run

**Status:** deployed and verified on 2026-10-08 (project `nbafantasy-511015`, service `fantasy-ai`, region `europe-west1`,
URL `https://fantasy-ai-276008835589.europe-west1.run.app`). Verified: landing page, `/health`, anonymous `/chat` -> 401, no errors in logs,
one instance, runs as the `fantasy-app` service account. **Not yet verified:** a logged-in chat on the live site (needs the Google/Yahoo
client IDs below) and the service account actually reading Firestore (the `roles/datastore.user` grant exists).

## What was actually run
1. Enabled `run`, `cloudbuild`, `artifactregistry`, `secretmanager`, `iam` APIs.
2. Created service account `fantasy-app` + `roles/datastore.user`.
3. Secrets `gemini-api-key`, `supabase-key`, `flask-secret` (new random value for production) in Secret Manager, with `secretAccessor` for `fantasy-app`.
4. Exported a **clean copy of the committed branch** (`git archive HEAD | tar -x -C <dir>`) so uncommitted local work is never deployed, then:
   `gcloud run deploy fantasy-ai --source <dir> --region europe-west1 --service-account fantasy-app@... --allow-unauthenticated --max-instances 1 --memory 1Gi --timeout 600 --env-vars-file env.yaml --set-secrets ...`
5. To add the login credentials later: put the client IDs in the env file / `gcloud run services update fantasy-ai --update-env-vars GOOGLE_CLIENT_ID=...,YAHOO_CLIENT_ID=...`, store the two client secrets in Secret Manager and attach with `--update-secrets GOOGLE_CLIENT_SECRET=google-client-secret:latest,YAHOO_CLIENT_SECRET=yahoo-client-secret:latest`.
6. Register `https://fantasy-ai-276008835589.europe-west1.run.app/auth/google/callback` (Google) and `.../auth/yahoo/callback` (Yahoo).

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
Do the same for `SUPABASE_KEY`, `FLASK_SECRET_KEY`, `GOOGLE_CLIENT_SECRET`, `YAHOO_CLIENT_SECRET`, then grant access:
```
gcloud secrets add-iam-policy-binding gemini-api-key --member=serviceAccount:fantasy-app@<PROJECT_ID>.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor
```

## 3. Deploy (builds the Dockerfile in the repo root)
```
gcloud run deploy fantasy-ai --source . --region europe-west1 --service-account fantasy-app@<PROJECT_ID>.iam.gserviceaccount.com \
  --allow-unauthenticated --max-instances 1 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=<PROJECT_ID>,LLM_MODEL=gemini/gemini-3.8-flash,LLM_FALLBACK_MODEL=gemini/gemini-3.7-flash,EMBEDDING_MODEL=gemini/gemini-embedding-001,EMBEDDING_DIMENSIONS=768,SUPABASE_URL=<url>,GOOGLE_CLIENT_ID=<id>,YAHOO_CLIENT_ID=<id>,YAHOO_REDIRECT_URL=https://<service-url>/auth/yahoo/callback \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest,SUPABASE_KEY=supabase-key:latest,FLASK_SECRET_KEY=flask-secret:latest,GOOGLE_CLIENT_SECRET=google-client-secret:latest,YAHOO_CLIENT_SECRET=yahoo-client-secret:latest
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
