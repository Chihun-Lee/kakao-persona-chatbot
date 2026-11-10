# -*- coding: utf-8 -*-
"""본인이 쓴 글에서 말투 통계, 실제 오타, 가린 예문을 뽑아 페르소나 파일을 만든다."""
from __future__ import annotations

import json
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from .imperfect import SPACE_SLIPS
from .jamo import plausible_slip, to_keys
from .mask import mask, usable_example

_END = re.compile(r"([가-힣]{1,3})[.!?~ㅋㅎㅠㅜ\s]*$")
_WORD = re.compile(r"[가-힣]{2,8}")
_QUOTE = re.compile(r"^(?:-{2,}.*(?:Original|원본|전달).*|>.*|보낸 ?사람\s*:.*|From\s*:.*|On .* wrote:.*)$", re.M)


def clean_mail(text: str) -> str:
    """답장 아래 붙은 이전 메일과 웹메일이 끼워 넣은 코드 줄을 잘라 낸다."""
    m = _QUOTE.search(text)
    body = text[:m.start()] if m else text
    return "\n".join(ln for ln in body.splitlines() if not re.match(r"\s*(?:var |function |<)", ln)).strip()


def chat_stats(messages: list[str]) -> dict:
    n = max(len(messages), 1)
    lengths = [len(m) for m in messages] or [0]
    endings = Counter(m.group(1)[-2:] for m in (_END.search(x) for x in messages) if m)
    openers = Counter(x.split()[0] for x in messages if x.split())
    rate = lambda f: round(sum(1 for x in messages if f(x)) / n, 4)
    return {
        "messages": len(messages),
        "median_chars": int(statistics.median(lengths)),
        "ends_with_period": rate(lambda x: x.rstrip().endswith(".")),
        "has_question": rate(lambda x: "?" in x),
        "has_exclaim": rate(lambda x: "!" in x),
        "has_tilde": rate(lambda x: "~" in x),
        "has_laugh": rate(lambda x: "ㅋ" in x or "ㅎㅎ" in x),
        "has_cry": rate(lambda x: "ㅠ" in x or "ㅜ" in x),
        "top_endings": [e for e, _ in endings.most_common(20)],
        "top_openers": [o for o, _ in openers.most_common(20)],
    }


def mail_stats(mails: list[str], name_full: str, name_given: str) -> dict:
    lines_all = [[ln.strip() for ln in m.splitlines() if ln.strip()] for m in mails]
    lines_all = [x for x in lines_all if x]
    n = max(len(lines_all), 1)
    ends = [m.group(1) for ms in mails for m in re.finditer(r"(?:습니다|합니다|입니다|드립니다|겠습니다)(\.?)(?=\s|$)", ms)]
    first = Counter(ls[0] for ls in lines_all if len(ls[0]) <= 40 and not ls[0].startswith(("[", "var ")))
    pattern = re.compile(rf"(?:{re.escape(name_full)}|{re.escape(name_given)})\s*(?:드림|올림|듦|드맇|배상)")
    signs = Counter()
    for m in mails:
        hits = pattern.findall(m[-160:])
        if hits:
            signs[hits[-1]] += 1
    total = max(sum(signs.values()), 1)
    return {
        "mails": len(lines_all),
        "median_chars": int(statistics.median([sum(len(x) for x in ls) for ls in lines_all])) if lines_all else 0,
        "line_ends_with_period": round(sum(1 for x in ends if x) / max(len(ends), 1), 4),
        "top_greetings": [g for g, _ in first.most_common(10)],
        "signoffs": [{"text": t, "weight": round(c / total, 4), "count": c} for t, c in signs.most_common(6)],
    }


def mine_typos(texts: list[str], min_common: int = 30, max_rare: int = 3, ratio: int = 40, top: int = 80) -> tuple[list[dict], float]:
    """드물게 나온 낱말이 흔한 낱말과 키 한 번 차이면 오타로 본다."""
    counts = Counter(w for t in texts for w in _WORD.findall(t))
    common = {w: c for w, c in counts.items() if c >= min_common}
    index: dict[str, list[str]] = defaultdict(list)

    def deletes(word: str):
        keys = to_keys(word)
        yield "".join(keys)
        for i in range(len(keys)):
            yield "".join(keys[:i] + keys[i + 1:])

    for word in common:
        for d in deletes(word):
            index[d].append(word)
    pairs = []
    typo_total = 0
    for rare, c in counts.items():
        if c > max_rare or rare in common:
            continue
        options = {w for d in deletes(rare) for w in index.get(d, [])}
        best = max((w for w in options if plausible_slip(w, rare)), key=lambda w: common[w], default=None)
        if best and common[best] >= c * ratio and len(best) >= 3:
            pairs.append({"right": best, "wrong": rare, "count": c, "right_count": common[best]})
            typo_total += c
    pairs.sort(key=lambda p: (-p["right_count"], -p["count"]))
    chars = max(sum(len(t) for t in texts), 1)
    return pairs[:top], round(typo_total / chars * 1000, 3)


def spacing_rate(texts: list[str]) -> float:
    """공백 없이 붙여 쓴 자리를 천 글자당으로 잰다."""
    chars = max(sum(len(t) for t in texts), 1)
    joined = 0
    for rule in SPACE_SLIPS:
        glued = re.compile(rule.replace(" (?=", "(?="))
        joined += sum(len(glued.findall(t)) for t in texts)
    return round(joined / chars * 1000, 3)


def pick_examples(texts: list[str], k: int, lo: int, hi: int, names: list[str], seed: int = 42) -> list[str]:
    masked = (mask(t, names) for t in texts if lo <= len(t) <= hi)
    good = sorted({t.strip() for t in masked if usable_example(t)})
    random.Random(seed).shuffle(good)
    return good[:k]


def period_drop(rate_with_period: float) -> float:
    return round(min(0.95, max(0.02, 1 - rate_with_period)), 3)


def save(persona: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(persona, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
