# Insight Generation Performance

Measurements completed on June 4, 2026.

## Method

- Reproduced the existing workflow in Browser against a representative three-conversation
  selection from a local archive.
- Measured local loading, preprocessing, context packing, model-call topology, progress, and
  report rendering behavior.
- Did not send private archive content to a live provider during benchmarking.
- Used a deterministic local provider with fixed 200 ms and 800 ms response delays to compare
  serialized and parallel critical paths.

## Before

The representative selection contained 79 messages and produced four 80k-character context
groups.

| Stage | Measurement |
| --- | ---: |
| Archive loading | 14.49 ms |
| Formatting | 0.30 ms |
| Context packing | 0.22 ms |
| Context groups | 4 |
| Model calls | 5: four partial analyses plus one final merge |
| Critical-path model waits | 5, all serialized |
| Progress before completion | No meaningful staged progress |

Loading and preprocessing were not the cause of the reported approximately 70-second duration.
The dominant cost was five sequential model waits.

## After

| Stage | Measurement |
| --- | ---: |
| Archive loading | 9.40 ms |
| Language detection, compaction, formatting, and packing | 4.06 ms |
| Context groups | 3 |
| Model calls | 4: three partial analyses plus one final merge |
| Critical-path model waits | 2: parallel partial analysis plus final merge |
| Synthetic 200 ms/call run | 440 ms total versus about 1,000 ms serialized baseline |
| Browser progress visibility | 5% loading state visible within about 150 ms |
| Browser deterministic 800 ms/call run | 1.7 seconds total |

The deterministic comparison is about 56% faster. For the reported 70-second case, reducing the
critical path from five model waits to two should materially reduce elapsed time, although actual
improvement depends on provider latency, rate limits, and output speed.

## Changes

- Partial context-group analyses run concurrently with a maximum of four workers.
- Individual messages longer than 12,000 characters retain their beginning and ending while
  omitting the middle, reducing repeated or low-value context without dropping the source.
- Duplicate selected conversation IDs are removed before loading.
- The asynchronous job API records loading, preprocessing, prompt construction, model-call,
  saving, and total durations.
- The frontend enters a progress state before the job request completes and polls provider-agnostic
  progress every 500 ms.

## Streaming

The current provider abstraction exposes complete text responses, not a consistent streaming
interface across OpenAI-compatible, Anthropic, Gemini, and failover providers. This change uses
immediate staged progress for every provider. Final-answer token streaming can be added when the
provider contract supports it consistently without losing failover behavior.
