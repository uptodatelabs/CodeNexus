"""Shared context-capsule pipelines used by both MCP server implementations."""

import logging

from .graph import DependencyGraph

logger = logging.getLogger(__name__)

_PRESET_WIDTHS = {"explore": 15, "debug": 10, "modify": 10}

# Common filler words that match nearly every node and drown real ranking.
_STOP_WORDS = {
    "the", "a", "an", "to", "for", "of", "in", "on", "and", "or",
    "fix", "add", "make", "please", "should", "with", "that", "this",
}


def _token_estimate(text: str) -> float:
    return len(text.split()) * 1.3


def extract_keywords(task: str) -> list[str]:
    """Split a task description into search keywords."""
    words = [w for w in task.lower().split() if w not in _STOP_WORDS]
    return words or task.lower().split()


def build_task_capsule(
    graph: DependencyGraph,
    task: str,
    preset: str = "auto",
    max_tokens: int = 8000,
) -> dict:
    """Search + rank nodes for a task and pack a token-budgeted capsule.

    Returns a dict with ``task``, ``pivot_files`` (full source), ``skeletons``
    (signatures only) and ``token_estimate``.
    """
    keywords = extract_keywords(task)

    candidates: list = []
    seen_ids: set[str] = set()
    for keyword in keywords:
        for node in graph.search_nodes(keyword, limit=10):
            if node.id not in seen_ids:
                candidates.append(node)
                seen_ids.add(node.id)

    def relevance_score(node) -> int:
        text = f"{node.name} {node.content} {node.signature}".lower()
        return sum(1 for keyword in keywords if keyword in text)

    candidates.sort(key=relevance_score, reverse=True)
    if preset not in ("auto", "", None):
        if preset not in _PRESET_WIDTHS:
            logger.debug("Unknown preset %r; using default width", preset)
    limit = _PRESET_WIDTHS.get(preset or "auto", 20)
    candidates = candidates[:limit]

    result: dict = {"task": task, "pivot_files": [], "skeletons": [], "token_estimate": 0}
    tokens_used = 0.0

    for node in candidates:
        if tokens_used >= max_tokens:
            break

        skeleton = f"{node.signature}\n..."
        # Full source for the best-ranked hits while budget remains; the rest
        # degrade to skeletons.
        if tokens_used + _token_estimate(node.content) < max_tokens * 0.6:
            result["pivot_files"].append(
                {"path": node.file_path, "name": node.name, "content": node.content}
            )
            tokens_used += _token_estimate(node.content)
        else:
            result["skeletons"].append(
                {"path": node.file_path, "name": node.name, "skeleton": skeleton}
            )
            tokens_used += _token_estimate(skeleton)

    result["token_estimate"] = int(tokens_used)
    return result


def build_query_capsule(
    graph: DependencyGraph,
    query: str,
    max_tokens: int = 8000,
) -> dict:
    """Lightweight context search returning skeleton capsules for a query."""
    from .parser import create_capsule

    nodes = graph.search_nodes(query, limit=10)

    parts: list[str] = []
    tokens_used = 0.0
    for node in nodes:
        if tokens_used >= max_tokens:
            break
        skeleton = create_capsule(node.content)
        parts.append(f"=== {node.file_path}::{node.name} ===\n{skeleton}")
        tokens_used += _token_estimate(skeleton)

    return {"capsule": "\n\n".join(parts), "token_estimate": int(tokens_used)}
