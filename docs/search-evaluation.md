# Search Evaluation

Reweave includes two reproducible local evaluation tools:

```powershell
.venv\Scripts\python.exe benchmarks\evaluate_search.py
.venv\Scripts\python.exe benchmarks\benchmark_search.py
```

Both use the production FastEmbed model
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. The model cache
is local and ignored by Git.

## Golden-query quality

Measured on 2026-07-14 on Windows with 32 Korean and English queries from
`benchmarks/search_golden.json`:

| Metric | Keyword | Hybrid |
| --- | ---: | ---: |
| Recall@10 | 0.3438 | 0.9688 |
| Exact-query hits | 5/5 | 5/5 |

Hybrid retrieval improved Recall@10 by 181.82% relative to keyword retrieval,
while preserving every exact-query hit. The suite includes paraphrases,
cross-language concepts, exact phrases, citations, privacy, product decisions,
and operational topics.

## 50,000-message latency

Measured on 2026-07-14 on Windows with 25 warm samples after loading the model:

| Metric | Result | Target |
| --- | ---: | ---: |
| Keyword p95 | 162.068 ms | 200 ms |
| Hybrid p95 | 716.879 ms | 1,000 ms |

Generating the 50,000-message test archive took 4.439 seconds. Initial semantic
indexing took 138.891 seconds. The latency measurement excludes initial model
loading and indexing, matching normal searches after Smart search is ready.

These numbers are local reference measurements rather than guarantees across
all processors, archive contents, and storage devices. Run the scripts on the
target machine after changing ranking, chunking, embedding, or SQLite schema
logic.
