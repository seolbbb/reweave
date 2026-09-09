"""Shared local source predicates applied before keyword or semantic ranking."""


def add_context_source_filter(clauses, params, *, space_id=None, item_type=None):
    if not space_id and not item_type:
        return
    conditions = ["ce.source_conversation_id = c.id", "ci.status <> 'archived'"]
    if item_type:
        conditions.append("ci.item_type = ?")
        params.append(item_type)
    if space_id:
        conditions.append(
            "EXISTS (SELECT 1 FROM context_item_scopes cs "
            "WHERE cs.item_id = ci.id AND cs.space_id = ?)"
        )
        params.append(space_id)
    clauses.append(
        "EXISTS (SELECT 1 FROM context_evidence ce "
        "JOIN context_items ci ON ci.id = ce.item_id WHERE " + " AND ".join(conditions) + ")"
    )
