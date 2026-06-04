# Search-to-Insight UX Benchmark

Research completed on June 4, 2026 using current official product documentation.

## Products Reviewed

| Product | Proven pattern | Reweave application |
| --- | --- | --- |
| [NotebookLM](https://support.google.com/notebooklm/answer/16206563?hl=en) | Keeps source selection explicit and generates reports, notes, and mind maps from the selected source set. Its [mind maps](https://support.google.com/notebooklm/answer/16212283?hl=en-GB) emphasize concepts and relationships. | Keep selected conversations visible, structure reports around concepts and connections, and preserve source navigation. |
| [Perplexity](https://docs.perplexity.ai/docs/cookbook/articles/streaming-citations/README) | Streams long-running answers and maps inline numbered citations to source results as they arrive. | Show immediate staged progress and turn source references into compact clickable citations. |
| [ChatGPT deep research](https://help.openai.com/en/articles/10500283-deep-research-faq/) | Lets users choose sources, follow live progress, and review a structured full-screen report with a source section and downloads. | Use the central workspace for a readable report, keep source cards beside it, and provide optional Markdown copy/download actions. |
| [Claude Research](https://support.anthropic.com/en/articles/11088861-using-research-on-claude-ai) | Shows research activity and returns thorough answers with easy-to-check citations. | Use plain-language progress stages and attach evidence links to findings. |
| [Readwise Reader](https://docs.readwise.io/reader/guides/ghostreader/overview) | Keeps AI assistance inside a clean reading surface. Its [prompt reference](https://docs.readwise.io/reader/guides/ghostreader/reference) recommends central sentences or paragraphs for long documents, and related highlights link back to the original source. | Render Markdown as readable content, compact unusually long messages conservatively, and open the supporting conversation from citations. |

## Shared Patterns

- Source scope remains visible before, during, and after generation.
- One primary action starts synthesis.
- Progress appears immediately and describes meaningful activity.
- Long-form output uses a document-style reading surface rather than a chat bubble or raw text panel.
- Important findings carry inline citations that open supporting material.
- Concepts, relationships, contradictions, and questions are more useful than a broad recap.
- Raw or portable formats are secondary actions, not the primary reading experience.

## Chosen Reweave Design

1. The right rail holds the selected conversation set and one **Generate insight** action.
2. Generation opens the central workspace immediately with staged progress.
3. Completed reports use a spacious document surface with localized, fixed sections.
4. Inline source references become citation buttons that open the supporting message.
5. Search excerpts and source previews render sanitized Markdown in a compact layout.
6. Copying or downloading raw Markdown remains available as an optional report action.

The design applies the benchmarked interaction patterns without adopting product branding,
visual identity, or proprietary terminology.
