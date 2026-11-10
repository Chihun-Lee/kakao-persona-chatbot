# -*- coding: utf-8 -*-
"""한글을 두벌식 자판 입력 순서로 풀고 다시 조합한다.

사람의 오타는 글자가 아니라 키 입력에서 생긴다. 예를 들어 '드림'은 ㄷㅡㄹㅣㅁ 인데
ㅣ를 빠뜨리면 ㄷㅡㄹㅁ 이 되어 '듦'으로 조합된다.
"""
from __future__ import annotations

CHO = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
JUNG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")
JONG = [""] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")
V2 = {"ㅘ": "ㅗㅏ", "ㅙ": "ㅗㅐ", "ㅚ": "ㅗㅣ", "ㅝ": "ㅜㅓ", "ㅞ": "ㅜㅔ", "ㅟ": "ㅜㅣ", "ㅢ": "ㅡㅣ"}
C2 = {"ㄳ": "ㄱㅅ", "ㄵ": "ㄴㅈ", "ㄶ": "ㄴㅎ", "ㄺ": "ㄹㄱ", "ㄻ": "ㄹㅁ", "ㄼ": "ㄹㅂ", "ㄽ": "ㄹㅅ",
      "ㄾ": "ㄹㅌ", "ㄿ": "ㄹㅍ", "ㅀ": "ㄹㅎ", "ㅄ": "ㅂㅅ"}
V2R = {v: k for k, v in V2.items()}
C2R = {v: k for k, v in C2.items()}
VOWELS = set(JUNG)
CONSONANTS = set(CHO) | set(JONG[1:])
BASE = 0xAC00


def is_syllable(ch: str) -> bool:
    return BASE <= ord(ch) <= 0xD7A3


def to_keys(text: str) -> list[str]:
    """글자를 키 입력 목록으로 푼다. 한글 음절이 아니면 그대로 둔다."""
    keys: list[str] = []
    for ch in text:
        if not is_syllable(ch):
            keys.append(ch)
            continue
        code = ord(ch) - BASE
        cho, jung, jong = code // 588, (code % 588) // 28, code % 28
        keys.append(CHO[cho])
        keys.extend(V2.get(JUNG[jung], JUNG[jung]))
        if jong:
            keys.extend(C2.get(JONG[jong], JONG[jong]))
    return keys


def compose(keys: list[str]) -> str:
    """두벌식 입력기처럼 키 목록을 조합한다."""
    out: list[str] = []
    cho = jung = jong = None

    def flush():
        nonlocal cho, jung, jong
        if cho and jung:
            code = BASE + CHO.index(cho) * 588 + JUNG.index(jung) * 28 + (JONG.index(jong) if jong else 0)
            out.append(chr(code))
        else:
            out.extend(x for x in (cho, jung) if x)
        cho = jung = jong = None

    for k in keys:
        if k in VOWELS:
            if jong:
                if jong in C2:                        # 겹받침의 뒤 자음은 다음 글자로 넘어간다
                    first, second = C2[jong]
                    jong = first
                    flush()
                    cho = second
                else:
                    moved = jong
                    jong = None
                    flush()
                    cho = moved
                jung = k
            elif jung:
                if jung + k in V2R:
                    jung = V2R[jung + k]
                else:
                    flush()
                    jung = k
            else:
                jung = k
        elif k in CONSONANTS:
            if jung and not cho:                      # 자음 없이 찍힌 모음 뒤
                flush()
                cho = k
            elif not cho:
                cho = k
            elif not jung:
                flush()
                cho = k
            elif not jong:
                if k in JONG:
                    jong = k
                else:                                 # ㄸ ㅃ ㅉ 은 받침이 될 수 없다
                    flush()
                    cho = k
            elif jong + k in C2R:
                jong = C2R[jong + k]
            else:
                flush()
                cho = k
        else:
            flush()
            out.append(k)
    flush()
    return "".join(out)


def slips(word: str) -> list[str]:
    """한 번의 키 실수로 나올 수 있는 결과를 돌려준다. 완성된 음절로만 이뤄진 것만 남긴다."""
    keys = to_keys(word)
    found: set[str] = set()
    for i in range(1, len(keys) - 1):
        if keys[i] in VOWELS:                         # 모음 하나 빠뜨리기: 드림 -> 듦
            found.add(compose(keys[:i] + keys[i + 1:]))
        if i + 2 <= len(keys):                        # 옆 키와 순서 바뀌기
            found.add(compose(keys[:i] + [keys[i + 1], keys[i]] + keys[i + 2:]))
    good = []
    for cand in found:
        if cand == word or not cand or not all(is_syllable(c) for c in cand):
            continue
        if len(word) - 1 <= len(cand) <= len(word):
            good.append(cand)
    return sorted(good)


_ROWS = ["ㅂㅈㄷㄱㅅㅛㅕㅑㅐㅔ", "ㅁㄴㅇㄹㅎㅗㅓㅏㅣ", "ㅋㅌㅊㅍㅠㅜㅡ"]
_BASE = {"ㅃ": "ㅂ", "ㅉ": "ㅈ", "ㄸ": "ㄷ", "ㄲ": "ㄱ", "ㅆ": "ㅅ", "ㅒ": "ㅐ", "ㅖ": "ㅔ"}
_POS = {k: (r, i) for r, row in enumerate(_ROWS) for i, k in enumerate(row)}


def keys_adjacent(a: str, b: str) -> bool:
    """두벌식 자판에서 붙어 있는 키인지 본다."""
    a, b = _BASE.get(a, a), _BASE.get(b, b)
    if a not in _POS or b not in _POS or a == b:
        return False
    (r1, i1), (r2, i2) = _POS[a], _POS[b]
    if r1 == r2:
        return abs(i1 - i2) == 1
    if abs(r1 - r2) != 1:
        return False
    top, low = (i1, i2) if r1 < r2 else (i2, i1)
    return low in (top, top - 1)


def plausible_slip(right: str, wrong: str) -> bool:
    """손가락이 실제로 낼 만한 실수만 인정한다. 다른 낱말로 보이는 우연한 차이를 거른다."""
    x, y = to_keys(right), to_keys(wrong)
    if len(x) == len(y):
        diff = [i for i in range(len(x)) if x[i] != y[i]]
        if len(diff) == 1:
            return keys_adjacent(x[diff[0]], y[diff[0]])
        return len(diff) == 2 and diff[1] == diff[0] + 1 and x[diff[0]] == y[diff[1]] and x[diff[1]] == y[diff[0]]
    if len(y) == len(x) - 1:                          # 키 하나를 빠뜨림
        return key_distance_one(right, wrong)
    if len(y) == len(x) + 1 and key_distance_one(right, wrong):
        i = next((j for j in range(len(x)) if x[j] != y[j]), len(x))
        near = [y[i - 1]] if i else []
        near += [y[i + 1]] if i + 1 < len(y) else []
        return any(y[i] == n or keys_adjacent(y[i], n) for n in near)
    return False


def key_distance_one(a: str, b: str) -> bool:
    """키 입력 기준으로 삭제, 삽입, 치환, 인접 교환 한 번 차이인지 본다."""
    x, y = to_keys(a), to_keys(b)
    if abs(len(x) - len(y)) > 1 or x == y:
        return False
    if len(x) == len(y):
        diff = [i for i in range(len(x)) if x[i] != y[i]]
        if len(diff) == 1:
            return True
        return len(diff) == 2 and diff[1] == diff[0] + 1 and x[diff[0]] == y[diff[1]] and x[diff[1]] == y[diff[0]]
    if len(x) > len(y):
        x, y = y, x
    i = 0
    while i < len(x) and x[i] == y[i]:
        i += 1
    return x[i:] == y[i + 1:]
