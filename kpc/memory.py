# -*- coding: utf-8 -*-
"""가상 메모리 시스템.

- 에피소드 메모리: 과거 대화를 에피소드 단위로 저장하고 BM25로 검색 (RAG)
- 타임라인 다이제스트: 일자별 키워드 요약으로 관계의 흐름을 파악
한국어 특성상 토큰은 (공백 단위 어절 + 문자 바이그램) 혼합으로 만든다.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from .parser import Episode

_WORD = re.compile(r"[가-힣a-zA-Z0-9]+")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for w in _WORD.findall(text.lower()):
        tokens.append(w)
        if re.search(r"[가-힣]", w) and len(w) >= 3:
            tokens.extend(w[i:i + 2] for i in range(len(w) - 1))
    return tokens


def episodes_to_docs(episodes: list[Episode]) -> list[dict]:
    docs = []
    for ep in episodes:
        lines = [f"{t.speaker}: {'  '.join(t.texts)}" for t in ep.turns]
        docs.append({
            "id": ep.idx,
            "start": ep.start.isoformat(),
            "end": ep.end.isoformat(),
            "lines": lines,
        })
    return docs


def build_timeline(episodes: list[Episode]) -> list[dict]:
    """일자별 다이제스트 — 메시지 수와 그날의 특징 키워드."""
    global_df: Counter = Counter()
    by_day: dict[str, Counter] = defaultdict(Counter)
    count_by_day: Counter = Counter()
    for ep in episodes:
        for t in ep.turns:
            day = t.start.strftime("%Y-%m-%d")
            words = {w for text in t.texts for w in _WORD.findall(text) if len(w) >= 2}
            for w in words:
                by_day[day][w] += 1
            global_df.update(words)
            count_by_day[day] += len(t.texts)

    n_days = max(len(by_day), 1)
    timeline = []
    for day in sorted(by_day):
        scored = {w: c * math.log(n_days / (1 + sum(1 for d in by_day.values() if w in d)))
                  for w, c in by_day[day].items() if c >= 2}
        top = sorted(scored, key=scored.get, reverse=True)[:8]
        timeline.append({"date": day, "messages": count_by_day[day], "keywords": top})
    return timeline


class BM25Memory:
    """순수 파이썬 BM25 검색 인덱스 (외부 의존성 없음)."""

    def __init__(self, docs: list[dict], k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.doc_tfs = [Counter(tokenize("\n".join(d["lines"]))) for d in docs]
        self.doc_lens = [sum(tf.values()) for tf in self.doc_tfs]
        self.avg_len = sum(self.doc_lens) / max(len(docs), 1)
        self.df: Counter = Counter()
        for tf in self.doc_tfs:
            self.df.update(tf.keys())
        self.n = len(docs)

    def search(self, query: str, k: int = 3) -> list[dict]:
        q_tokens = tokenize(query)
        scores = [0.0] * self.n
        for tok in q_tokens:
            df = self.df.get(tok)
            if not df:
                continue
            idf = math.log(1 + (self.n - df + 0.5) / (df + 0.5))
            for i, tf in enumerate(self.doc_tfs):
                f = tf.get(tok, 0)
                if f:
                    denom = f + self.k1 * (1 - self.b + self.b * self.doc_lens[i] / self.avg_len)
                    scores[i] += idf * f * (self.k1 + 1) / denom
        ranked = sorted(range(self.n), key=lambda i: scores[i], reverse=True)
        return [dict(self.docs[i], score=round(scores[i], 2)) for i in ranked[:k] if scores[i] > 0]


def save_memory(out_dir: str | Path, episodes: list[Episode]) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = episodes_to_docs(episodes)
    with open(out_dir / "episodes.json", "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False)
    with open(out_dir / "timeline.json", "w", encoding="utf-8") as f:
        json.dump(build_timeline(episodes), f, ensure_ascii=False, indent=1)


def load_memory(build_dir: str | Path) -> tuple[BM25Memory, list[dict]]:
    build_dir = Path(build_dir)
    with open(build_dir / "episodes.json", encoding="utf-8") as f:
        docs = json.load(f)
    with open(build_dir / "timeline.json", encoding="utf-8") as f:
        timeline = json.load(f)
    return BM25Memory(docs), timeline
