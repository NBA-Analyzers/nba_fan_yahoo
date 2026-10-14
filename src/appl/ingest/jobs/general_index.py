"""The shared AI index: player stats report, rest-of-season schedule and the rules PDF.
Each source lands in its own collection and is skipped when unchanged."""

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from ...ai.document_indexer import DocumentIndexer
from ..player_report import LOOKBACK_DAYS, build_player_report
from ..season import current_season, previous_season, season_end
from ..sinks.datasets import DatasetStore
from ..sources.nba import NbaSource

logger = logging.getLogger(__name__)

RULES_PDF = (Path(__file__).resolve().parents[2] / "scripts" / "fantasy_rules"
             / "Yahoo_Fantasy_Basketball_Rules_With_Comparison.pdf")


def run(indexer: DocumentIndexer, datasets: DatasetStore, nba: Optional[NbaSource] = None,
        today: Optional[date] = None, rules_pdf: Path = RULES_PDF) -> dict:
    nba = nba or NbaSource()
    today = today or date.today()
    season = current_season(today)
    result = {"season": season}

    # Stats: this season (empty before tip-off), last season, recent game logs
    current = nba.league_dash(season)
    last = nba.league_dash(previous_season(season))
    logs = nba.game_logs(season, today - timedelta(days=LOOKBACK_DAYS)) if current else []
    report = build_player_report(current, last, logs, today)
    if report:
        datasets.put(f"player_stats_{season}", report)
        result["stats"] = {"players": len(report),
                           "indexed": indexer.update_player_stats(report, season)}
    else:
        logger.warning("No player stats for %s or the season before; stats index left as is", season)
        result["stats"] = {"players": 0, "indexed": False}

    # Schedule: tomorrow to the end of the regular season
    games = nba.schedule(today + timedelta(days=1), season_end(season))
    if games:
        datasets.put(f"schedule_{season}", games)
        result["schedule"] = {"games": len(games),
                              "indexed": indexer.update_schedule(games, season)}
    else:
        logger.warning("No upcoming games found; schedule index left as is")
        result["schedule"] = {"games": 0, "indexed": False}

    result["rules"] = {"indexed": indexer.update_rules(str(rules_pdf))}
    indexer.drop_legacy_general()
    return result
