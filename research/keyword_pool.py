"""Load/manage the viewer-problem keyword pool from YAML and sync it into the DB.

Structure: category -> problems[] -> {id, label, search_queries[]}. Every search query belongs to
exactly one problem, so matching a found video back to a viewer problem is a direct lookup, not a
guess -- see youtube_search.py, which threads problem_id/problem_label through unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from research.db import connect


@dataclass
class Keyword:
    category: str
    problem_id: str
    problem_label: str
    search_query: str


def load_pool(path: Path) -> dict[str, dict]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def problems_for_category(pool: dict[str, dict], category: str) -> list[dict]:
    return (pool.get(category) or {}).get("problems") or []


def problem_labels_for_category(pool: dict[str, dict], category: str) -> list[str]:
    return [p["label"] for p in problems_for_category(pool, category) if p.get("label")]


def all_search_queries_for_category(pool: dict[str, dict], category: str) -> list[str]:
    queries: list[str] = []
    for problem in problems_for_category(pool, category):
        queries.extend(problem.get("search_queries") or [])
    return queries


def iter_keywords(pool: dict[str, dict]) -> list[Keyword]:
    keywords: list[Keyword] = []
    for category, body in pool.items():
        for problem in body.get("problems") or []:
            problem_id = problem.get("id")
            problem_label = problem.get("label")
            for query in problem.get("search_queries") or []:
                keywords.append(
                    Keyword(category=category, problem_id=problem_id, problem_label=problem_label, search_query=query)
                )
    return keywords


def keywords_for_category(pool: dict[str, dict], category: str) -> list[Keyword]:
    return [k for k in iter_keywords(pool) if k.category == category]


def sync_to_db(db_path: Path, pool: dict[str, dict]) -> int:
    """Upserts all keywords from the YAML pool into the keywords table. Returns count inserted/updated."""
    count = 0
    with connect(db_path) as conn:
        for kw in iter_keywords(pool):
            conn.execute(
                """
                INSERT INTO keywords (category, problem, problem_id, search_query)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(category, search_query) DO UPDATE SET
                    problem = excluded.problem, problem_id = excluded.problem_id
                """,
                (kw.category, kw.problem_label, kw.problem_id, kw.search_query),
            )
            count += 1
    return count


def add_keyword(path: Path, category: str, problem_id: str, problem_label: str, search_query: str) -> None:
    pool = load_pool(path)
    body = pool.setdefault(category, {"problems": []})
    problems = body.setdefault("problems", [])
    problem = next((p for p in problems if p.get("id") == problem_id), None)
    if problem is None:
        problem = {"id": problem_id, "label": problem_label, "search_queries": []}
        problems.append(problem)
    queries = problem.setdefault("search_queries", [])
    if search_query not in queries:
        queries.append(search_query)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(pool, f, allow_unicode=True, sort_keys=False)
