# -*- coding: utf-8 -*-
"""사람이 빠르게 친 글처럼 아주 작은 흐트러짐을 넣는다.

- 숫자, 날짜, 금액, 영문, 메일 주소, 사람 이름은 절대 건드리지 않는다.
- 오타와 띄어쓰기 빈도는 페르소나 원문에서 잰 값을 기준으로 한다.
- 같은 seed면 같은 결과가 나오고, 바뀐 곳을 segments로 돌려준다.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from .jamo import slips

LEVELS = {"off": 0.0, "low": 1.0, "normal": 1.6, "high": 3.2}

PROTECT = re.compile(
    r"https?://\S+|[\w.+-]+@[\w.-]+|[A-Za-z][\w-]*"
    r"|\d[\d,./:\-~]*\s*(?:%|원|만원|억|천|개|대|명|건|장|시|분|초|일|월|년|호기|호|차|회|배|톤|kg|mm|km)?"
    r"|[가-힣]{2,4}\s?(?:박사|교수|대표|사장|회장|부사장|전무|상무|이사|부장|차장|과장|대리|주임|팀장|실장|소장|원장|본부장|공장장|선임|책임|연구원|님|씨)(?:님)?"
)
# 사람들이 실제로 자주 붙여 쓰는 자리
SPACE_SLIPS = [
    r"(?:할|될|볼|갈|줄|알|쓸|올|살|될) (?=수\b|것|때|게|거|듯)",
    r"(?:것|거) (?=같|입니|이에|이고)",
    r"(?:해|드려|보내|봐|알려|확인해|전달해) (?=주|드|보)",
    r"(?:안|못) (?=되|돼|하|합|해|갑|가)",
    r"(?:잘) (?=부탁|모르|되|받)",
    r"(?:오늘|내일|이번|다음) (?=오전|오후|주|달|중)",
]
_PERIOD = re.compile(r"(?<=[가-힣])\.(?=\s|$)")
_EOJEOL = re.compile(r"[가-힣]{2,7}")
_PREDICATE = re.compile(r"(?:습니다|니다|세요|해요|네요|어요|아요|는데|해서|하고|으면|하면|겠어요|드려요)$")
_NEVER = re.compile(r"놈|년|새끼|씨발|시발|병신|죽|똥|개같|미친|망할")


@dataclass
class Result:
    text: str
    segments: list[dict] = field(default_factory=list)
    edits: list[dict] = field(default_factory=list)


def _draw(expected: float, rng: random.Random) -> int:
    whole = int(expected)
    return whole + (1 if rng.random() < expected - whole else 0)


def _protected(text: str, terms: list[str]) -> list[bool]:
    mask = [False] * len(text)
    for m in PROTECT.finditer(text):
        for i in range(m.start(), m.end()):
            mask[i] = True
    for term in terms:
        if not term:
            continue
        for m in re.finditer(re.escape(term), text):
            for i in range(m.start(), m.end()):
                mask[i] = True
    return mask


def _pick_signoff(options: list[dict], factor: float, rng: random.Random) -> str:
    """드문 변형일수록 실수 정도에 맞춰 가중치를 키운다."""
    weights = [o["weight"] * (factor if i else 1.0) for i, o in enumerate(options)]
    return rng.choices(options, weights=weights, k=1)[0]["text"]


def add_noise(text: str, persona: dict, channel: str, level: str = "low", seed: int | None = None,
              protect_terms: list[str] | None = None) -> Result:
    factor = LEVELS.get(level, 1.0)
    if factor == 0 or not text.strip():
        return Result(text, [{"t": text}], [])
    rng = random.Random(seed)
    noise = persona.get("noise", {})
    is_mail = channel == "mail"
    terms = list(persona.get("protect", [])) + list(protect_terms or [])
    mask = _protected(text, terms)
    planned: list[tuple[int, int, str, str]] = []            # (시작, 끝, 바꿀 글, 종류)

    def free(a: int, b: int) -> bool:
        return not any(mask[i] for i in range(a, b)) and not any(a < e and s < b for s, e, _, _ in planned)

    # 1. 맺음말 변형
    tail_from = 0
    if is_mail:
        options = persona.get("channels", {}).get("mail", {}).get("signoffs", [])
        if options:
            start = max(0, len(text) - 120)
            for o in sorted(options, key=lambda x: -len(x["text"])):
                pos = text.rfind(o["text"], start)
                if pos >= 0:
                    tail_from = pos
                    chosen = _pick_signoff(options, factor, rng)
                    if chosen != o["text"]:
                        planned.append((pos, pos + len(o["text"]), chosen, "signoff"))
                    for i in range(pos, pos + len(o["text"])):
                        mask[i] = True
                    break
    # 2. 마침표를 찍었다 안 찍었다
    drop = min(0.95, noise.get("period_drop", {}).get(channel, 0.15 if is_mail else 0.6) * (factor ** 0.5))
    for m in _PERIOD.finditer(text):
        if rng.random() < drop and free(m.start(), m.end()):
            planned.append((m.start(), m.end(), "", "period"))
    # 3. 붙여 쓰기
    expected = max(noise.get("space_per_1000", 1.2) * len(text) / 1000, 0.15) * factor
    spots = [m for rule in SPACE_SLIPS for m in re.finditer(rule, text)]
    rng.shuffle(spots)
    for m in spots[:_draw(expected, rng)]:
        gap = m.end() - 1
        if free(gap, gap + 1):
            planned.append((gap, gap + 1, "", "space"))
    # 4. 오타. 먼저 그 사람이 실제로 냈던 오타, 다음으로 자판 실수
    expected = max(noise.get("typo_per_1000", 1.0) * len(text) / 1000, 0.08) * factor
    if level == "high":
        expected = max(expected, 1.0)
    cap = max(1, len(text) // (250 if is_mail else 60))
    budget = min(cap, _draw(expected, rng))
    lexicon = persona.get("typos", [])[:]
    rng.shuffle(lexicon)
    for item in lexicon:
        if budget <= 0:
            break
        pos = text.find(item["right"])
        if pos >= 0 and free(pos, pos + len(item["right"])) and not _NEVER.search(item["wrong"]):
            planned.append((pos, pos + len(item["right"]), item["wrong"], "typo"))
            budget -= 1
    if budget > 0:
        words = [m for m in _EOJEOL.finditer(text) if m.start() > 0 and (not tail_from or m.end() <= tail_from)]
        rng.shuffle(words)
        for m in words:
            if budget <= 0:
                break
            if not free(m.start(), m.end()) or not _PREDICATE.search(m.group()):
                continue
            options = [o for o in slips(m.group()) if not _NEVER.search(o)]
            if options:
                planned.append((m.start(), m.end(), rng.choice(options), "typo"))
                budget -= 1
    # 합치기
    planned.sort()
    segments: list[dict] = []
    edits: list[dict] = []
    out: list[str] = []
    cursor = 0
    for start, end, new, kind in planned:
        if start > cursor:
            segments.append({"t": text[cursor:start]})
            out.append(text[cursor:start])
        segments.append({"t": new, "from": text[start:end], "kind": kind})
        edits.append({"kind": kind, "from": text[start:end], "to": new})
        out.append(new)
        cursor = end
    if cursor < len(text):
        segments.append({"t": text[cursor:]})
        out.append(text[cursor:])
    return Result("".join(out), segments, edits)
