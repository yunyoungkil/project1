from research.content_pattern_analyzer import analyze_title_rules, analyze_video


def test_is_question_detected():
    flags = analyze_title_rules("왜 아는 단어인데 안 들릴까?")
    assert flags.is_question is True


def test_is_negative_detected():
    flags = analyze_title_rules("영어 단어를 못 읽는 이유")
    assert flags.is_negative is True


def test_is_reason_detected():
    flags = analyze_title_rules("영어 발음이 이상한 이유")
    assert flags.is_reason is True


def test_is_result_detected():
    flags = analyze_title_rules("영어 단어 읽는 법 총정리")
    assert flags.is_result is True


def test_is_number_detected():
    flags = analyze_title_rules("영어 공부법 5가지")
    assert flags.is_number is True


def test_is_fear_avoidance_detected():
    flags = analyze_title_rules("이 실수 하나로 영어 망합니다")
    assert flags.is_fear_avoidance is True


def test_neutral_title_has_no_flags():
    flags = analyze_title_rules("영어 단어 목록")
    assert flags.is_question is False
    assert flags.is_fear_avoidance is False


def test_empty_title_does_not_crash():
    flags = analyze_title_rules("")
    assert flags.is_question is False
    flags_none = analyze_title_rules(None)
    assert flags_none.is_question is False


def test_analyze_video_without_gemini_uses_rule_source():
    pattern = analyze_video("v1", "왜 영어 단어가 안 읽힐까?", gemini=None)
    assert pattern.source == "rule"
    assert pattern.viewer_problem is None
    assert pattern.flags.is_question is True


class _UnavailableGemini:
    available = False


def test_analyze_video_with_unavailable_gemini_uses_rule_source():
    pattern = analyze_video("v1", "영어 단어 읽는 법", gemini=_UnavailableGemini())
    assert pattern.source == "rule"


class _FakeGemini:
    available = True

    def __init__(self, response):
        self._response = response

    def generate_json(self, prompt, max_output_tokens=1024):
        return self._response


def test_analyze_video_with_working_gemini_uses_gemini_source():
    response = {
        "viewer_problem": "아는 단어인데 안 들림",
        "title_pattern": "문제 + 이유",
        "hook": "궁금증",
        "promise": "이해시켜줌",
    }
    pattern = analyze_video("v1", "왜 안 들릴까?", gemini=_FakeGemini(response))
    assert pattern.source == "gemini"
    assert pattern.viewer_problem == "아는 단어인데 안 들림"
    assert pattern.title_pattern == "문제 + 이유"
    assert pattern.flags.is_question is True  # rule flags still computed alongside gemini


def test_analyze_video_falls_back_when_gemini_returns_none():
    pattern = analyze_video("v1", "영어 단어 읽는 법", gemini=_FakeGemini(None))
    assert pattern.source == "rule"
    assert pattern.viewer_problem is None
