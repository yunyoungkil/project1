import yaml

from research.keyword_pool import (
    add_keyword,
    all_search_queries_for_category,
    iter_keywords,
    keywords_for_category,
    load_pool,
    problem_labels_for_category,
    resolve_legacy_problem,
)

_POOL = {
    "reading": {
        "problems": [
            {"id": "cannot_read_words", "label": "알파벳은 아는데 영어 단어를 못 읽는다", "search_queries": ["영어 단어 읽는 법"]},
            {"id": "word_stress", "label": "영어 강세 위치를 어떻게 아는가", "search_queries": ["영어 강세", "강세 규칙"]},
        ]
    },
    "listening": {
        "problems": [
            {"id": "liaison", "label": "영어 연음이 어렵다", "search_queries": ["영어 연음"]},
        ]
    },
}


def test_iter_keywords_assigns_correct_problem_per_query():
    keywords = iter_keywords(_POOL)
    by_query = {k.search_query: k for k in keywords}

    assert by_query["영어 단어 읽는 법"].problem_id == "cannot_read_words"
    assert by_query["영어 단어 읽는 법"].problem_label == "알파벳은 아는데 영어 단어를 못 읽는다"
    assert by_query["영어 강세"].problem_id == "word_stress"
    assert by_query["강세 규칙"].problem_id == "word_stress"


def test_different_queries_in_same_category_can_have_different_problems():
    keywords = keywords_for_category(_POOL, "reading")
    problem_ids = {k.problem_id for k in keywords}
    assert problem_ids == {"cannot_read_words", "word_stress"}


def test_keywords_for_category_filters_correctly():
    keywords = keywords_for_category(_POOL, "listening")
    assert len(keywords) == 1
    assert keywords[0].search_query == "영어 연음"


def test_problem_labels_for_category():
    labels = problem_labels_for_category(_POOL, "reading")
    assert labels == ["알파벳은 아는데 영어 단어를 못 읽는다", "영어 강세 위치를 어떻게 아는가"]


def test_all_search_queries_for_category_flattens_across_problems():
    queries = all_search_queries_for_category(_POOL, "reading")
    assert queries == ["영어 단어 읽는 법", "영어 강세", "강세 규칙"]


def test_missing_category_returns_empty():
    assert problem_labels_for_category(_POOL, "nonexistent") == []
    assert all_search_queries_for_category(_POOL, "nonexistent") == []
    assert keywords_for_category(_POOL, "nonexistent") == []


def _write_pool_file(tmp_path, pool):
    path = tmp_path / "keyword_pool.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(pool, f, allow_unicode=True, sort_keys=False)
    return path


def test_resolve_legacy_problem_reuses_existing_id_for_matching_label(tmp_path):
    path = _write_pool_file(tmp_path, _POOL)
    problem_id, label = resolve_legacy_problem(path, "reading", "영어 강세 위치를 어떻게 아는가")
    assert problem_id == "word_stress"
    assert label == "영어 강세 위치를 어떻게 아는가"


def test_resolve_legacy_problem_generates_deterministic_id_for_new_label(tmp_path):
    path = _write_pool_file(tmp_path, _POOL)
    id1, _ = resolve_legacy_problem(path, "reading", "완전히 새로운 고민")
    id2, _ = resolve_legacy_problem(path, "reading", "완전히 새로운 고민")
    assert id1 == id2  # same label -> same id every time
    assert id1 not in {"cannot_read_words", "word_stress"}


def test_resolve_legacy_problem_does_not_collide_with_existing_ids(tmp_path):
    path = _write_pool_file(tmp_path, _POOL)
    new_id, _ = resolve_legacy_problem(path, "reading", "또 다른 새 고민")
    existing_ids = {p["id"] for p in _POOL["reading"]["problems"]}
    assert new_id not in existing_ids


def test_legacy_add_keyword_flow_does_not_duplicate_existing_problem(tmp_path):
    """Simulates `keywords add --category reading --problem "영어 강세 위치를 어떻게 아는가"
    --query "새 검색어"` -- the legacy path should append to the existing word_stress problem,
    not create a second one with a different id."""
    path = _write_pool_file(tmp_path, _POOL)
    problem_id, problem_label = resolve_legacy_problem(path, "reading", "영어 강세 위치를 어떻게 아는가")
    add_keyword(path, "reading", problem_id, problem_label, "새 검색어")

    pool = load_pool(path)
    reading_problems = pool["reading"]["problems"]
    assert len(reading_problems) == 2  # still just cannot_read_words + word_stress
    stress_problem = next(p for p in reading_problems if p["id"] == "word_stress")
    assert "새 검색어" in stress_problem["search_queries"]


def test_legacy_add_keyword_flow_creates_new_problem_for_new_label(tmp_path):
    path = _write_pool_file(tmp_path, _POOL)
    problem_id, problem_label = resolve_legacy_problem(path, "reading", "처음 보는 고민")
    add_keyword(path, "reading", problem_id, problem_label, "처음 보는 검색어")

    pool = load_pool(path)
    reading_problems = pool["reading"]["problems"]
    assert len(reading_problems) == 3
    new_problem = next(p for p in reading_problems if p["label"] == "처음 보는 고민")
    assert new_problem["search_queries"] == ["처음 보는 검색어"]
