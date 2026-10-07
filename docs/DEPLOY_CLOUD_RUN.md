# Deploying to Google Cloud Run (draft — NOT tested)

Prepared while the Google project did not exist yet, so nothing here has been run. Treat it as a starting
point; expect to fix small things on the first deploy. Do this **after** `SETUP_CHECKLIST.md` Steps 1–4 work locally.

> ⚠️ `.github/workflows/main_fantasy.yml` deploys to the existing **Azure** web app on every push to `main`.
> Merging this branch to `main` before the Azure app has the new settings (`GEMINI_API_KEY`, Firestore credentials,
> `GOOGLE_CLOUD_PROJECT`) will break the running production app. Either configure those first, or switch hosting to
> Cloud Run and disable that workflow in the same change.

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
- The first deploy prints the service URL; set `YAHOO_REDIRECT_URL` to match and redeploy.

## 4. Check
`curl https://<service-url>/health`, then the `/chat` curl from SETUP_CHECKLIST Step 12.
