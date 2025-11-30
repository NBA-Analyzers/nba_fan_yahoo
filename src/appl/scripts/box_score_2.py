import requests
from datetime import date, timedelta

API_KEY = "e4539810-fcab-4307-b2a5-a5cf13727942"  # from balldontlie
BASE_URL = "https://api.balldontlie.io/v1/games"

def daterange(start: date, end: date):
    """Yield every date from start to end inclusive."""
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)

def fetch_games_for_date(day: date):
    """Fetch all games for a specific date (scoreboard for that day)."""
    params = {
        "dates[]": day.isoformat(),
        "per_page": 100,  # max per docs
        "page": 1,
    }
    headers = {"Authorization": API_KEY}

    all_games = []

    while True:
        resp = requests.get(BASE_URL, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        games = data.get("data", [])
        meta = data.get("meta", {})
        all_games.extend(games)

        # Pagination: if we're on the last page, break
        if meta.get("current_page") >= meta.get("total_pages", 1):
            break

        params["page"] += 1

    return all_games

def fetch_all_scoreboards_2025():
    start = date(2025, 1, 1)
    end = date(2025, 12, 31)

    all_games = []

    for day in daterange(start, end):
        games = fetch_games_for_date(day)
        if games:
            print(f"{day}: {len(games)} game(s)")
            all_games.extend(games)

    return all_games

if __name__ == "__main__":
    all_scoreboards_2025 = fetch_all_scoreboards_2025()
    print(f"Total games in 2025: {len(all_scoreboards_2025)}")
    # Example: show first game
    if all_scoreboards_2025:
        from pprint import pprint
        pprint(all_scoreboards_2025[0])