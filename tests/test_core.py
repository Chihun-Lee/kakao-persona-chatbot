# -*- coding: utf-8 -*-
from kpc.imperfect import add_noise
from kpc.jamo import compose, key_distance_one, slips, to_keys
from kpc.mask import mask, usable_example
from kpc.rewrite import number_warnings

PERSONA = {
    "protect": ["한도윤", "한내금속"],
    "noise": {"typo_per_1000": 6.0, "space_per_1000": 6.0, "period_drop": {"mail": 0.5, "kakao_work": 0.9}},
    "typos": [{"right": "확인했습니다", "wrong": "확인햇습니다"}],
    "channels": {"mail": {"signoffs": [{"text": "한도윤 드림", "weight": 0.9}, {"text": "도윤 드림", "weight": 0.07}, {"text": "도윤듦", "weight": 0.03}]}},
}
MAIL = "안녕하십니까, 한내금속 한도윤입니다.\nJ-12 납기가 하루 늦어 11/17에 납품됩니다. 금액은 2,940만 원이고 지체상금은 294,000원입니다.\n오늘 오후 확인했습니다. 할 수 있는 조치는 먼저 하겠습니다.\n\n감사합니다. 한도윤 드림"


def test_roundtrip():
    for word in ["드림", "감사합니다", "괜찮습니다", "값어치", "뭐라고", "많이"]:
        assert compose(to_keys(word)) == word


def test_user_example_drim():
    assert "듦" in slips("드림")


def test_key_distance():
    assert key_distance_one("드림", "듦")
    assert not key_distance_one("드림", "감사")


def test_numbers_never_change():
    for seed in range(300):
        out = add_noise(MAIL, PERSONA, "mail", "high", seed).text
        for fact in ["J-12", "11/17", "2,940만", "294,000"]:
            assert fact in out, (seed, out)
        assert "한내금속" in out


def test_same_seed_same_output():
    assert add_noise(MAIL, PERSONA, "mail", "normal", 7).text == add_noise(MAIL, PERSONA, "mail", "normal", 7).text


def test_off_changes_nothing():
    assert add_noise(MAIL, PERSONA, "mail", "off", 1).text == MAIL


def test_segments_rebuild_text():
    r = add_noise(MAIL, PERSONA, "mail", "high", 3)
    assert "".join(s["t"] for s in r.segments) == r.text
    assert r.edits


def test_rare_signoff_appears_sometimes():
    outs = [add_noise(MAIL, PERSONA, "mail", "low", s).text for s in range(600)]
    assert sum("한도윤 드림" in x for x in outs) > 450
    assert any("도윤듦" in x for x in outs)


def test_mask():
    t = mask("김철수 박사님 010-1234-5678 a@b.com 입금 123-45-678901", ["홍길동"])
    assert "김철수" not in t and "010" not in t and "a@b.com" not in t and "123-45" not in t
    assert not usable_example(t)
    assert usable_example("넵 확인했습니다")


def test_number_warnings():
    assert number_warnings("11/17까지 200개", "11/17까지 200개 납품") == []
    assert number_warnings("11/17까지 200개", "다음 주까지 200개")
