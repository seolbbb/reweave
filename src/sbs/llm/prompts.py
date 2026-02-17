"""Prompt templates for all LLM-powered pipeline stages."""

SEGMENTATION_SYSTEM = """\
You are a conversation analyst. Your task is to identify topic transitions \
in a conversation and segment it into coherent topical sections.

For each segment, provide:
- start_index: the message index where the topic begins
- end_index: the message index where the topic ends (inclusive)
- topic_label: a concise label for the topic (2-6 words)

Return segments that cover all messages without gaps or overlaps."""

SEGMENTATION_USER = """\
Analyze the following conversation and identify topic segments.

Conversation messages:
{messages}

Return the segments as structured data."""

SEGMENTATION_BATCH_SYSTEM = """\
You are a conversation analyst. For each conversation in the input, identify topic transitions \
and segment it into coherent topical sections.

For each conversation item:
- conversation_id: the exact input conversation id
- segments: list of:
  - start_index: message index where the topic begins
  - end_index: message index where the topic ends (inclusive)
  - topic_label: concise topic label (2-6 words)

Rules:
- Segment each conversation independently.
- Segment indices are local to each conversation.
- Return exactly one item per input conversation_id.
- Do not merge or split conversations across ids."""

SEGMENTATION_BATCH_USER = """\
Analyze the following conversation batch and return structured segmentation for each conversation.

Input batch:
{batch_payload}
"""

EXTRACTION_SYSTEM = """\
You are a knowledge extraction specialist. Your task is to extract structured \
knowledge from a conversation segment about "{topic_label}".

Extract:
- concepts: Key concepts discussed (name + description + importance 1-5)
- decisions: Decisions or conclusions reached (decision + rationale)
- insights: Notable insights or learnings (insight + context)
- todos: Action items mentioned (task + status)
- open_questions: Unresolved questions (question + context)
- references: External resources mentioned (title + author + year + source_type + mention_context)
- summary: A 1-2 sentence summary of the segment

Be thorough but precise. Only extract what is actually discussed."""

EXTRACTION_USER = """\
Extract structured knowledge from this conversation segment about "{topic_label}":

{messages}"""

SYNTHESIS_SYSTEM = """\
You are a Zettelkasten note writer and triage editor. Your task is to transform \
extracted knowledge into atomic notes and classify each note as either fleeting or permanent.

Rules:
1. ONE idea per note -- the note should be about exactly one concept or insight
2. Self-contained -- a reader should understand the note without other context
3. Rephrase, don't copy -- rewrite in your own words, synthesizing the knowledge
4. Use clear, concise language
5. Include relevant context from the source
6. Classify note type:
   - permanent: stable, reusable knowledge with clear claim or model
   - fleeting: rough or incomplete idea that needs refinement before permanence

For each note, provide:
- title: A declarative statement or descriptive phrase (not a question)
- body: The note content in Markdown (2-5 paragraphs)
- recommended_type: "fleeting" or "permanent"
- why_type: one sentence rationale for your type choice
- tags: 2-5 relevant tags (lowercase, hyphenated)
- link_candidates: Names of other concepts this note could link to
- expansion_prompts: 2-4 prompts that would help evolve the note (required for fleeting notes)"""

SYNTHESIS_USER = """\
Create atomic Zettelkasten notes from this extracted knowledge:

Topic: {topic_label}
Summary: {summary}

Concepts: {concepts}
Decisions: {decisions}
Insights: {insights}
References: {references}

Source conversation: {source_ref}
Conversation date: {conversation_date}"""

LINKING_CLUSTER_SYSTEM = """\
You are a knowledge organizer. Given a list of note titles and summaries, \
group them into 5-15 topical clusters. Each cluster should have a clear theme.

Return clusters with:
- cluster_label: A descriptive label for the cluster
- note_ids: List of note IDs belonging to this cluster"""

LINKING_CLUSTER_USER = """\
Group the following notes into topical clusters:

{notes_summary}"""

LINKING_DISCOVER_SYSTEM = """\
You are a knowledge connector. Given a set of notes within a topic cluster, \
find meaningful links between them.

Link types:
- supports: One note provides evidence for another
- extends: One note builds upon another
- contrasts: Notes present different perspectives
- prerequisite: One note is needed to understand another
- example-of: One note provides a concrete example of another

For each link, provide:
- source_note_id: ID of the first note
- target_note_id: ID of the second note
- relationship: The type of relationship
- description: Brief explanation of the connection"""

LINKING_DISCOVER_USER = """\
Find meaningful connections between these notes in the "{cluster_label}" cluster:

{notes_detail}"""

VALIDATION_ATOMICITY_SYSTEM = """\
You are a quality checker for Zettelkasten notes. Evaluate whether the given note \
contains exactly ONE core idea (atomic) and is self-contained.

Return:
- is_atomic: true/false
- reason: Brief explanation"""

VALIDATION_ATOMICITY_USER = """\
Evaluate this note for atomicity:

Title: {title}
Content:
{body}"""


# Runtime prompt overrides loaded from prompt bundles.
_PROMPT_OVERRIDES: dict[str, str] = {}


def set_prompt_overrides(overrides: dict[str, str] | None) -> None:
    """Set runtime prompt overrides."""
    global _PROMPT_OVERRIDES
    _PROMPT_OVERRIDES = dict(overrides or {})


def clear_prompt_overrides() -> None:
    """Clear runtime prompt overrides."""
    _PROMPT_OVERRIDES.clear()


def get_prompt(name: str, default: str) -> str:
    """Resolve a prompt template by name with fallback to default."""
    return _PROMPT_OVERRIDES.get(name, default)
