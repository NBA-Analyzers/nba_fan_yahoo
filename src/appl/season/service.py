"""
Glue between stored leagues and the season tools: the in-season ranker, and the
league files the AI chat retrieves from.

Manual leagues use the same chat as Yahoo leagues. Their chat league id is
"manual-<id>", so they get their own RAG collection, and the files carry the
same names the Yahoo sync uses (league_settings, team_rosters, standing,
free_agents), plus what only a manual league has (draft results, moves, notes).
"""

import hashlib
import json
import logging
import threading

from ..draft.player_pool import load_inseason_pool
from ..draft.ranker import DraftRanker
from ..model.vector_store import generate_league_vector_store_id
from . import snapshot as snapshots
from .analyzer import SeasonAnalyzer

logger = logging.getLogger(__name__)

MANUAL_CHAT_PREFIX = "manual-"
FREE_AGENTS_FOR_CHAT = 40
STAT_LINE = ("GP", "MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV", "FG3M", "FGM", "FGA", "FTM", "FTA")

# (pool id, categories, teams, roster size) -> DraftRanker
_rankers: dict[tuple, DraftRanker] = {}
MAX_RANKERS = 32
# RAG collection -> hash of what was last indexed into it
_indexed: dict[str, str] = {}
_index_lock = threading.Lock()


def ranker_for(snap) -> DraftRanker:
    pool = load_inseason_pool()
    key = (id(pool), tuple(snap.categories), snap.num_teams, snap.roster_size)
    if key not in _rankers:
        if len(_rankers) >= MAX_RANKERS:
            _rankers.clear()
        _rankers[key] = DraftRanker(
            pool, categories=snap.categories, num_teams=snap.num_teams, roster_size=snap.roster_size
        )
    return _rankers[key]


# --- chat ids ----------------------------------------------------------------

def manual_chat_id(league_id: str) -> str:
    return f"{MANUAL_CHAT_PREFIX}{league_id}"


def manual_id_from_chat(chat_league_id: str | None) -> str | None:
    """The manual league id inside a chat league id, or None for a Yahoo league."""
    if chat_league_id and chat_league_id.startswith(MANUAL_CHAT_PREFIX):
        return chat_league_id[len(MANUAL_CHAT_PREFIX):]
    return None


# --- the files the chat retrieves from ---------------------------------------

def stat_line(player: dict | None) -> dict:
    if not player:
        return {"stats": "no stats found"}
    line = {k: round(player[k], 1) for k in STAT_LINE if k in player}
    line["FG%"] = round(player["FGM"] / player["FGA"], 3) if player.get("FGA") else None
    line["FT%"] = round(player["FTM"] / player["FTA"], 3) if player.get("FTA") else None
    return {"team": player.get("team"), "pos": player.get("pos"), "per_game": line}


def manual_league_files(league: dict) -> dict:
    """Everything the chat should know about a manual league, as named JSON files."""
    snap = snapshots.from_manual(league)
    ranker = ranker_for(snap)
    report = SeasonAnalyzer(ranker, snap).report()
    names = snap.team_names
    mine = snap.my_team

    free_agents = ranker.rank(taken_names=snap.rostered(), my_roster_names=snap.rosters[mine],
                              limit=FREE_AGENTS_FOR_CHAT)
    return {
        "league_settings": {
            "league_name": league["name"],
            "league_type": "Manual league, entered by hand (not synced from Yahoo)",
            "scoring": "Rotisserie-style categories; the standings below are estimated from "
                       "each roster's per-game stats, not real game results",
            "categories": league["categories"],
            "num_teams": league["num_teams"],
            "roster_size": league["roster_size"],
            "roster_slots": league.get("slots"),
            "draft_type": "auction" if league["is_auction"] else "snake",
            "auction_budget": league["budget"] if league["is_auction"] else None,
            "draft_status": league["status"],
            "my_team": names[mine],
            "teams": names,
        },
        "team_rosters": [
            {
                "team": names[i],
                "is_my_team": i == mine,
                "players": [{"name": n, **stat_line(ranker.find(n))} for n in roster],
            }
            for i, roster in enumerate(snap.rosters)
        ],
        "standing": [
            {"place": t["place"], "team": t["name"], "is_my_team": t["is_mine"], "points": t["points"],
             "category_ranks": t["ranks"], "category_totals": t["values"]}
            for t in sorted(report["teams"], key=lambda t: t["place"])
        ],
        "my_team_analysis": {
            "team": names[mine],
            "place": report["my_team"]["place"],
            "categories": report["my_categories"],
            "advice": [a["text"] for a in report["advice"]],
            "trade_ideas": report["trades"],
            "pickup_ideas": report["pickups"],
            "weakest_players": report["drops"],
        },
        "free_agents": [{"name": r["name"], "value_for_my_team": r["score"], **stat_line(ranker.find(r["name"]))}
                        for r in free_agents],
        "draft_results": [
            {"pick": i + 1, "team": names[p["team"]] if p["team"] < len(names) else p["team"],
             "player": p["player_name"], "cost": p["cost"]}
            for i, p in enumerate(league["picks"])
        ],
        "transactions": [
            {"date": m["ts"], "type": m["kind"], "team": names[m["team"]],
             "partner": names[m["partner"]] if m.get("partner") is not None else None,
             "added_or_received": m["add"], "dropped_or_sent": m["drop"]}
            for m in league.get("moves", [])
            if m["team"] < len(names)
        ],
        "league_notes": [{"date": n["ts"], "phase": n["phase"], "text": n["text"]} for n in league["notes"]],
    }


def index_manual_league(indexer, league: dict) -> str:
    """Index the league's files for the chat. Skipped when nothing changed since
    the last time (embedding costs money). Returns the collection id."""
    collection = generate_league_vector_store_id(manual_chat_id(league["id"]))
    files = manual_league_files(league)
    digest = hashlib.sha1(json.dumps(files, sort_keys=True, default=str).encode()).hexdigest()
    with _index_lock:
        if _indexed.get(collection) == digest:
            return collection
    indexer.update_league_files(manual_chat_id(league["id"]), files)
    with _index_lock:
        _indexed[collection] = digest
    return collection


def index_manual_league_async(indexer, league: dict) -> threading.Thread:
    """Same as index_manual_league, in a background thread so the chat opens at once."""
    def run():
        try:
            index_manual_league(indexer, league)
            logger.info(f"Manual league {league['id']}: indexed for chat")
        except Exception as e:
            logger.error(f"Manual league {league['id']}: chat indexing failed: {e}", exc_info=True)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread
