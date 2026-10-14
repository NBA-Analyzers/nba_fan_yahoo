"""python -m appl.ingest run <job>   (from src/; also the Cloud Run Job's command)

Jobs:
  general_index  player stats, schedule and rules -> the shared AI index (Firestore)
  player_pool    preseason + in-season draft pools -> dataset store
  all            both, in that order; exits non-zero if either fails
"""

import argparse
import json
import logging
import sys
import time

logger = logging.getLogger("appl.ingest")


def _general_index():
    from ..ai.document_indexer import DocumentIndexer
    from ..config.dependencies import build_retrieval_service
    from .jobs import general_index
    from .sinks.datasets import build_dataset_store

    return general_index.run(DocumentIndexer(build_retrieval_service()), build_dataset_store())


def _player_pool():
    from .jobs import player_pool

    return player_pool.run()


JOBS = {"general_index": _general_index, "player_pool": _player_pool}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m appl.ingest")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("job", choices=[*JOBS, "all"])
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    names = list(JOBS) if args.job == "all" else [args.job]
    failed = []
    for name in names:
        started = time.monotonic()
        try:
            result = JOBS[name]()
            logger.info("%s done in %.0fs: %s", name, time.monotonic() - started, json.dumps(result))
        except Exception:
            logger.exception("%s failed after %.0fs", name, time.monotonic() - started)
            failed.append(name)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
