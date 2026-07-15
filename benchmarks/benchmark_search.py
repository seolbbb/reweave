"""Measure keyword and warm hybrid p95 latency on a generated local archive."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from reweave.archive import ArchiveStore  # noqa: E402
from reweave.semantic import SearchEngine, SemanticIndex  # noqa: E402

TOPICS = [
    "release canary monitoring rollback",
    "linked notes knowledge archive",
    "customer interview recent behavior",
    "database migration compatibility",
    "weekly planning focused calendar",
    "incident response visible symptoms",
    "retrieval citations source evidence",
    "privacy pseudonymous analytics",
    "strength training recovery schedule",
    "product backlog priority scoring",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--messages", type=int, default=50_000)
    parser.add_argument("--samples", type=int, default=25)
    parser.add_argument("--db", type=Path, help="Reuse an already indexed benchmark database.")
    parser.add_argument("--models-dir", type=Path, default=PROJECT_ROOT / ".benchmark-models")
    args = parser.parse_args()

    if args.db:
        store = ArchiveStore(args.db)
        engine = SearchEngine(
            store,
            SemanticIndex(store.db_path, args.models_dir),
        )
        engine.search_messages("linked notes archive", mode="auto", limit=12)
        return _report(
            messages=store.stats().total_messages,
            samples=args.samples,
            import_seconds=None,
            index_seconds=None,
            keyword_times=_measure(engine, "database migration", "keyword", args.samples),
            hybrid_times=_measure(
                engine,
                "safe production table changes",
                "auto",
                args.samples,
            ),
        )

    with TemporaryDirectory(prefix="reweave-perf-", ignore_cleanup_errors=True) as temp_dir:
        root = Path(temp_dir)
        export_path = root / "performance.json"
        export_path.write_text(
            json.dumps(
                [
                    {
                        "uuid": "performance-conversation",
                        "name": "Performance corpus",
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-01T00:00:00Z",
                        "chat_messages": [
                            {
                                "uuid": f"performance-message-{index}",
                                "sender": "assistant",
                                "text": f"{TOPICS[index % len(TOPICS)]} record {index}",
                                "created_at": "2026-01-01T00:00:00Z",
                            }
                            for index in range(args.messages)
                        ],
                    }
                ]
            ),
            encoding="utf-8",
        )
        store = ArchiveStore(root / "performance.db")
        import_started = perf_counter()
        store.import_path(export_path)
        import_seconds = perf_counter() - import_started
        semantic_index = SemanticIndex(store.db_path, args.models_dir)
        index_started = perf_counter()
        semantic_index.build()
        index_seconds = perf_counter() - index_started
        engine = SearchEngine(store, semantic_index)

        engine.search_messages("linked notes archive", mode="auto", limit=12)
        keyword_times = _measure(engine, "database migration", "keyword", args.samples)
        hybrid_times = _measure(engine, "safe production table changes", "auto", args.samples)

    return _report(
        messages=args.messages,
        samples=args.samples,
        import_seconds=import_seconds,
        index_seconds=index_seconds,
        keyword_times=keyword_times,
        hybrid_times=hybrid_times,
    )


def _report(
    *,
    messages: int,
    samples: int,
    import_seconds: float | None,
    index_seconds: float | None,
    keyword_times: list[float],
    hybrid_times: list[float],
) -> int:
    report = {
        "messages": messages,
        "samples": samples,
        "import_seconds": None if import_seconds is None else round(import_seconds, 3),
        "semantic_index_seconds": None if index_seconds is None else round(index_seconds, 3),
        "keyword_p95_ms": round(_p95(keyword_times), 3),
        "hybrid_p95_ms": round(_p95(hybrid_times), 3),
        "keyword_target_ms": 200,
        "hybrid_target_ms": 1000,
    }
    print(json.dumps(report, indent=2))
    return int(report["keyword_p95_ms"] > 200 or report["hybrid_p95_ms"] > 1000)


def _measure(engine: SearchEngine, query: str, mode: str, samples: int) -> list[float]:
    durations = []
    for _ in range(samples):
        started = perf_counter()
        engine.search_messages(query, mode=mode, limit=12)
        durations.append((perf_counter() - started) * 1000)
    return durations


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


if __name__ == "__main__":
    raise SystemExit(main())
