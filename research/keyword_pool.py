"""Load/manage the viewer-problem keyword pool from YAML and sync it into the DB."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from research.db import connect


@dataclass
class Keyword:
    category: str
    search_query: str
    problem: str | None = None


def load_pool(path: Path) -> dict[str, dict]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def iter_keywords(pool: dict[str, dict]) -> list[Keyword]:
    keywords: list[Keyword] = []
    for category, body in pool.items():
        problems = body.get("problems") or []
        primary_problem = problems[0] if problems else None
        for query in body.get("search_queries") or []:
            keywords.append(Keyword(category=category, search_query=query, problem=primary_problem))
    return keywords


def keywords_for_category(pool: dict[str, dict], category: str) -> list[Keyword]:
    return [k for k in iter_keywords(pool) if k.category == category]


_PARTICLES = (
    "에서부터", "으로부터", "부터", "까지", "에서", "으로", "이나", "라도", "에게", "한테",
    "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과", "도", "만",
)


def _stem(word: str) -> str:
    """Strips a trailing Korean particle (조사) so '단어를'/'단어는'/'단어' all compare equal.
    A small fixed particle list, not a real morphological analyzer -- deliberately simple."""
    for particle in sorted(_PARTICLES, key=len, reverse=True):
        if word.endswith(particle) and len(word) - len(particle) >= 2:
            return word[: -len(particle)]
    return word


def best_matching_problem(title: str, problems: list[str]) -> str | None:
    """Picks the problem statement (from a category's full problem list) whose words overlap the
    most with the video title, instead of always using the category's first/"primary" problem.
    Falls back to problems[0] when nothing overlaps, so behavior degrades gracefully."""
    if not problems:
        return None
    title_lower = (title or "").lower()
    best = problems[0]
    best_score = -1
    for problem in problems:
        words = [_stem(w) for w in problem.lower().split() if len(w) > 1]
        score = sum(1 for w in words if w and w in title_lower)
        if score > best_score:
            best_score = score
            best = problem
    return best


def sync_to_db(db_path: Path, pool: dict[str, dict]) -> int:
    """Upserts all keywords from the YAML pool into the keywords table. Returns count inserted/updated."""
    count = 0
    with connect(db_path) as conn:
        for kw in iter_keywords(pool):
            conn.execute(
                """
                INSERT INTO keywords (category, problem, search_query)
                VALUES (?, ?, ?)
                ON CONFLICT(category, search_query) DO UPDATE SET problem = excluded.problem
                """,
                (kw.category, kw.problem, kw.search_query),
            )
            count += 1
    return count


def add_keyword(path: Path, category: str, search_query: str, problem: str | None = None) -> None:
    pool = load_pool(path)
    if category not in pool:
        pool[category] = {"problems": [], "search_queries": []}
    if problem and problem not in pool[category].setdefault("problems", []):
        pool[category]["problems"].append(problem)
    if search_query not in pool[category].setdefault("search_queries", []):
        pool[category]["search_queries"].append(search_query)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(pool, f, allow_unicode=True, sort_keys=False)
