"""Run the bilingual Recall@10 golden-query evaluation against the real local model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from reweave.archive import ArchiveStore  # noqa: E402
from reweave.semantic import SearchEngine, SemanticIndex  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=PROJECT_ROOT / ".benchmark-models",
        help="FastEmbed model cache directory.",
    )
    args = parser.parse_args()
    golden = json.loads(
        (PROJECT_ROOT / "benchmarks" / "search_golden.json").read_text(encoding="utf-8")
    )

    with TemporaryDirectory(prefix="reweave-golden-", ignore_cleanup_errors=True) as temp_dir:
        root = Path(temp_dir)
        export_path = root / "golden.json"
        export_path.write_text(
            json.dumps(
                [
                    {
                        "uuid": item["id"],
                        "name": item["id"],
                        "created_at": f"2026-01-{index + 1:02d}T00:00:00Z",
                        "updated_at": f"2026-01-{index + 1:02d}T00:00:00Z",
                        "chat_messages": [
                            {
                                "uuid": f"{item['id']}-message",
                                "sender": "assistant",
                                "text": item["document"],
                                "created_at": f"2026-01-{index + 1:02d}T00:00:00Z",
                            }
                        ],
                    }
                    for index, item in enumerate(golden)
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        store = ArchiveStore(root / "golden.db")
        store.import_path(export_path)
        semantic_index = SemanticIndex(store.db_path, args.models_dir)
        engine = SearchEngine(store, semantic_index)

        keyword_hits = _evaluate(engine, golden, mode="keyword")
        semantic_index.build()
        hybrid_hits = _evaluate(engine, golden, mode="auto")
        exact_items = [item for item in golden if item.get("exact")]
        exact_keyword_hits = _evaluate(engine, exact_items, mode="keyword")
        exact_hybrid_hits = _evaluate(engine, exact_items, mode="auto")

    count = len(golden)
    keyword_recall = keyword_hits / count
    hybrid_recall = hybrid_hits / count
    relative_improvement = (
        (hybrid_recall - keyword_recall) / keyword_recall if keyword_recall else float("inf")
    )
    report = {
        "queries": count,
        "keyword_recall_at_10": round(keyword_recall, 4),
        "hybrid_recall_at_10": round(hybrid_recall, 4),
        "relative_improvement": (
            "infinite" if relative_improvement == float("inf") else round(relative_improvement, 4)
        ),
        "exact_keyword_hits": exact_keyword_hits,
        "exact_hybrid_hits": exact_hybrid_hits,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if relative_improvement < 0.2 or exact_hybrid_hits < exact_keyword_hits:
        return 1
    return 0


def _evaluate(engine: SearchEngine, golden: list[dict[str, object]], *, mode: str) -> int:
    hits = 0
    for item in golden:
        results, _ = engine.search_conversations(str(item["query"]), mode=mode, limit=10)
        hits += int(any(result.title == item["id"] for result in results))
    return hits


if __name__ == "__main__":
    raise SystemExit(main())
