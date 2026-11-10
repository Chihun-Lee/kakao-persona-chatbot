# -*- coding: utf-8 -*-
"""원문에서 개인정보를 가린다. 페르소나 파일에는 가린 글만 들어간다."""
from __future__ import annotations

import re

_RULES = [
    (re.compile(r"\b\d{6}\s*-\s*[1-4]\d{6}\b"), "[주민번호]"),
    (re.compile(r"\b01[016789][-. ]?\d{3,4}[-. ]?\d{4}\b"), "[전화]"),
    (re.compile(r"\b0\d{1,2}[-. ]\d{3,4}[-. ]\d{4}\b"), "[전화]"),
    (re.compile(r"\b\d{3,6}-\d{2,6}-\d{2,7}\b"), "[계좌]"),
    (re.compile(r"\b(?:\d{4}[- ]){3}\d{4}\b"), "[카드]"),
    (re.compile(r"[\w.+-]+@[\w.-]+\.\w+"), "[메일]"),
    (re.compile(r"https?://\S+"), "[링크]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[키]"),
]
_TITLED = re.compile(r"[가-힣]{2,4}(?=\s?(?:박사|교수|대표|사장|회장|전무|상무|이사|부장|차장|과장|대리|주임|팀장|실장|소장|원장|본부장|선임|책임|연구원|님|씨)(?:님)?\b)")
_COMMON = {"선생", "고객", "담당", "대표", "사장", "교수", "박사", "여러분", "어머", "아버", "할머", "할아버", "형", "누"}
MARK = "OO"
_SENSITIVE = re.compile(r"비밀번호|비번|패스워드|주민|계좌|통장|연봉|월급|급여|병원|진단|수술|임신|이혼|난청|건선|파열|우울|입원|약 먹|치료|보험|대출|\[주민번호\]|\[계좌\]|\[카드\]|\[키\]|\[전화\]")


def mask(text: str, names: list[str] | None = None) -> str:
    """정해진 형식의 개인정보와, 넘겨받은 사람 이름, 호칭 앞의 이름을 가린다."""
    for pattern, repl in _RULES:
        text = pattern.sub(repl, text)
    for name in sorted(names or [], key=len, reverse=True):
        if len(name) >= 2:
            text = text.replace(name, MARK)
    return _TITLED.sub(lambda m: m.group() if m.group() in _COMMON else MARK, text)


def usable_example(text: str) -> bool:
    """페르소나 예문으로 넣어도 되는 글인지 본다. 숫자, 가린 이름, 민감어가 있으면 뺀다."""
    return not (re.search(r"\d", text) or MARK in text or "[" in text or _SENSITIVE.search(text))
