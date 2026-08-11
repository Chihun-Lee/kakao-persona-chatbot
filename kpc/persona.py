# -*- coding: utf-8 -*-
"""화자별 페르소나(문체 프로파일 + few-shot 예시 뱅크) 추출.

방법론: 대량 few-shot 프롬프팅 (Edward Donner의 개인 채팅 클론,
WhatsApp-Llama 등에서 검증된 접근의 프롬프트 기반 변형).
통계적 문체 프로파일 + 실제 (맥락 → 응답) 예시를 함께 저장한다.
"""
from __future__ import annotations

import json
import random
import re
from collections import Counter
from pathlib import Path

from .parser import Episode, Turn

_LAUGH = re.compile(r"ㅋ+")
_CRY = re.compile(r"[ㅠㅜ]+")
_VOWEL_ECHO = re.compile(r"[가-힣][ㅏㅑㅓㅕㅗㅛㅜㅠㅡㅣㅐㅔ]\b")  # "그런가ㅏ" 식 모음 반복


def build_profile(name: str, turns: list[Turn]) -> dict:
    msgs = [t for turn in turns if turn.speaker == name for t in turn.texts]
    own_turns = [turn for turn in turns if turn.speaker == name]
    n = max(len(msgs), 1)

    endings = Counter(m.strip()[-2:] for m in msgs if len(m.strip()) >= 2)
    words = Counter(w for m in msgs for w in re.findall(r"[가-힣a-zA-Z]{2,}", m))

    return {
        "name": name,
        "message_count": len(msgs),
        "avg_msg_len": round(sum(len(m) for m in msgs) / n, 1),
        "avg_msgs_per_turn": round(len(msgs) / max(len(own_turns), 1), 2),
        "laugh_rate": round(sum(1 for m in msgs if _LAUGH.search(m)) / n, 3),
        "cry_rate": round(sum(1 for m in msgs if _CRY.search(m)) / n, 3),
        "question_rate": round(sum(1 for m in msgs if "?" in m) / n, 3),
        "exclaim_rate": round(sum(1 for m in msgs if "!" in m) / n, 3),
        "tilde_rate": round(sum(1 for m in msgs if "~" in m) / n, 3),
        "comma_pause_rate": round(sum(1 for m in msgs if ",," in m) / n, 3),
        "vowel_echo_rate": round(sum(1 for m in msgs if _VOWEL_ECHO.search(m)) / n, 3),
        "top_endings": [{"ending": e, "count": c} for e, c in endings.most_common(15)],
        "top_words": [{"word": w, "count": c} for w, c in words.most_common(30)],
        "notes": "",  # 사용자가 직접 보강 가능한 자유 서술
    }


def extract_exchanges(episodes: list[Episode], responder: str,
                      max_context_turns: int = 3) -> list[dict]:
    """(직전 맥락 → responder의 응답 턴) 쌍을 전부 추출."""
    exchanges = []
    for ep in episodes:
        for i, turn in enumerate(ep.turns):
            if turn.speaker != responder or i == 0:
                continue
            ctx = ep.turns[max(0, i - max_context_turns):i]
            if not any(c.speaker != responder for c in ctx):
                continue
            exchanges.append({
                "time": turn.start.isoformat(),
                "context": [{"speaker": c.speaker, "texts": c.texts} for c in ctx],
                "response": turn.texts,
            })
    return exchanges


def select_fewshot(exchanges: list[dict], k: int = 150, seed: int = 42) -> list[dict]:
    """품질 필터 후 시기별로 고르게 섞은 few-shot 뱅크를 만든다."""
    def quality(ex: dict) -> bool:
        resp = " ".join(ex["response"])
        if len(resp) < 4:  # "ㅇㅇ" 단답만 있는 쌍 배제 (루프 방지)
            return False
        ctx_len = sum(len(t) for c in ex["context"] for t in c["texts"])
        return ctx_len >= 4

    good = [e for e in exchanges if quality(e)]
    rng = random.Random(seed)
    if len(good) <= k:
        return good
    # 시간순 정렬 후 균등 구간에서 하나씩 뽑아 시기 편향 방지
    good.sort(key=lambda e: e["time"])
    step = len(good) / k
    return [good[min(int(i * step + rng.random() * step), len(good) - 1)] for i in range(k)]


def save_persona(out_dir: str | Path, profile: dict, fewshot: list[dict]) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{profile['name']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"profile": profile, "fewshot": fewshot}, f, ensure_ascii=False, indent=1)
    return path
