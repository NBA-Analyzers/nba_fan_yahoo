"""One-off copy of the Supabase tables google_auth, yahoo_auth, google_fantasy and
yahoo_league into Firestore (see repository/firestore/user_data.py for the layout).

  python -m appl.scripts.migrate_supabase_to_firestore --dry-run
  python -m appl.scripts.migrate_supabase_to_firestore

Needs SUPABASE_URL and SUPABASE_KEY (read access) and Firestore credentials
(GOOGLE_CLOUD_PROJECT + application default credentials).

- Idempotent: a document that already exists is skipped, never overwritten, so a re-run
  can't replace newer tokens with old ones.
- --dry-run reads both sides and writes nothing.
- Google and Yahoo tokens are copied (so logins stay long-lived) but never printed.
- Prints counts per collection: source rows, written (or would write), already there, invalid.
"""
import argparse
import os
import sys

from ..draft.manual_league import user_hash

PAGE = 1000


def api_url(url: str) -> str:
    """The REST base URL. Accepts the dashboard URL
    (https://supabase.com/dashboard/project/<ref>) as well as https://<ref>.supabase.co."""
    marker = "/dashboard/project/"
    if marker in url:
        return f"https://{url.split(marker)[1].split('/')[0]}.supabase.co"
    return url.rstrip("/")


def fetch_table(url: str, key: str, table: str) -> list[dict]:
    """All rows of a table through Supabase's REST API (no supabase package needed)."""
    import requests

    rows, start = [], 0
    while True:
        resp = requests.get(
            f"{api_url(url)}/rest/v1/{table}?select=*",
            headers={"apikey": key, "Authorization": f"Bearer {key}",
                     "Range": f"{start}-{start + PAGE - 1}"},
            timeout=60,
        )
        resp.raise_for_status()
        page = resp.json()
        rows.extend(page)
        if len(page) < PAGE:
            return rows
        start += PAGE


def _clean(row: dict) -> dict:
    return {k: v for k, v in row.items() if v is not None}


def plan(tables: dict[str, list[dict]]):
    """Yield (collection, doc id, data, source table) for every row that can be copied.
    A row without its key fields is yielded with doc id None (counted as invalid)."""
    for row in tables.get("google_auth", []):
        sub = row.get("google_user_id")
        if not sub or "/" in sub:
            yield "users", None, row, "google_auth"
            continue
        email = (row.get("email") or "").lower()
        yield "users", user_hash(sub), _clean(
            {"user_id": sub, "full_name": row.get("full_name"), "email": email,
             "access_token": row.get("access_token"),
             "created_at": row.get("created_at"), "last_updated": row.get("last_updated")}
        ), "google_auth"
        yield "identities", user_hash(f"google.com:{sub}"), {
            "user_id": sub, "provider": "google.com", "email": email,
            "email_verified": True}, "google_auth"
    for row in tables.get("yahoo_auth", []):
        guid = row.get("yahoo_user_id")
        if not guid or "/" in guid:
            yield "yahoo_auth", None, row, "yahoo_auth"
            continue
        yield "yahoo_auth", guid, _clean(row), "yahoo_auth"
    for row in tables.get("google_fantasy", []):
        sub, fid = row.get("google_user_id"), row.get("fantasy_user_id")
        platform = (row.get("fantasy_platform") or "").lower()
        if not (sub and fid and platform) or "/" in fid:
            yield "fantasy_connections", None, row, "google_fantasy"
            continue
        yield "fantasy_connections", f"{user_hash(sub)}_{platform}_{fid}", _clean(
            {**row, "fantasy_platform": platform}), "google_fantasy"
    for row in tables.get("yahoo_league", []):
        league, guid = row.get("league_id"), row.get("yahoo_user_id")
        if not (league and guid) or "/" in str(league) or "/" in guid:
            yield "yahoo_leagues", None, row, "yahoo_league"
            continue
        yield "yahoo_leagues", f"{league}_{guid}", _clean(row), "yahoo_league"


def migrate(tables: dict[str, list[dict]], client, dry_run: bool) -> dict[str, dict]:
    from google.api_core.exceptions import AlreadyExists

    counts: dict[str, dict] = {}
    for name, rows in tables.items():
        counts[name] = {"read": len(rows)}
    for collection, doc_id, data, source in plan(tables):
        c = counts.setdefault(collection, {"read": 0})
        for k in ("written", "skipped", "invalid"):
            c.setdefault(k, 0)
        if doc_id is None:
            c["invalid"] += 1
            print(f"  invalid row in {source}: missing or bad key fields", file=sys.stderr)
            continue
        ref = client.collection(collection).document(doc_id)
        if dry_run:
            c["skipped" if ref.get().exists else "written"] += 1
            continue
        try:
            ref.create(data)
            c["written"] += 1
        except AlreadyExists:
            c["skipped"] += 1
    return counts


def print_counts(counts: dict, dry_run: bool) -> None:
    verb = "would write" if dry_run else "written"
    print(f"\nMigration {'DRY RUN' if dry_run else 'result'}")
    for name, c in counts.items():
        print(f"  {name:22} source rows={c.get('read', 0):<5} {verb}={c.get('written', 0):<5} "
              f"already there={c.get('skipped', 0):<5} invalid={c.get('invalid', 0)}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="read only, write nothing")
    args = parser.parse_args(argv)

    url = os.environ.get("SUPABASE_URL")
    # the service-role key can read rows behind row-level security; SUPABASE_KEY is the fallback
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASSE_SERVICE_ROLE_KEY")
           or os.environ.get("SUPABASE_KEY"))
    if not url or not key:
        print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set", file=sys.stderr)
        return 2
    if key.startswith("sb_publishable_") or key.startswith("eyJ") and "anon" in key[:200]:
        print("Warning: this looks like a publishable/anon key. Row-level security may hide "
              "rows, so counts can read 0. Use the service-role (secret) key.", file=sys.stderr)
    from google.cloud import firestore

    client = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    tables = {t: fetch_table(url, key, t)
              for t in ("google_auth", "yahoo_auth", "google_fantasy", "yahoo_league")}
    counts = migrate(tables, client, args.dry_run)
    print_counts(counts, args.dry_run)
    return 1 if any(c.get("invalid") for c in counts.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
