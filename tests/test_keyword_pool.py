from research.keyword_pool import best_matching_problem


def test_picks_the_problem_with_most_word_overlap():
    problems = [
        "영어 왕초보 어디서부터 시작해야 하나",
        "알파벳은 아는데 영어 단어를 못 읽는다",
        "영어 강세를 틀리면 문제가 되는가",
    ]
    result = best_matching_problem("영어 단어 못 읽는 이유 총정리", problems)
    assert result == "알파벳은 아는데 영어 단어를 못 읽는다"


def test_falls_back_to_first_problem_when_no_overlap():
    problems = ["첫 번째 고민", "두 번째 고민"]
    result = best_matching_problem("전혀 관련 없는 제목입니다", problems)
    assert result == "첫 번째 고민"


def test_empty_problems_returns_none():
    assert best_matching_problem("아무 제목", []) is None


def test_empty_title_falls_back_to_first_problem():
    assert best_matching_problem("", ["고민 1", "고민 2"]) == "고민 1"
