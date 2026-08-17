from research.keyword_pool import (
    all_search_queries_for_category,
    iter_keywords,
    keywords_for_category,
    problem_labels_for_category,
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
