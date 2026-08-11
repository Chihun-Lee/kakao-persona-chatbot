# -*- coding: utf-8 -*-
"""페르소나 응답 엔진 — 프로파일 + few-shot + 가상 메모리를 프롬프트로 조립."""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

from .memory import load_memory


class PersonaEngine:
    def __init__(self, build_dir: str | Path, provider, fewshot_k: int = 30):
        self.build_dir = Path(build_dir)
        self.provider = provider
        self.fewshot_k = fewshot_k
        self.personas: dict[str, dict] = {}
        for p in sorted((self.build_dir / "personas").glob("*.json")):
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            self.personas[data["profile"]["name"]] = data
        self.memory, self.timeline = load_memory(self.build_dir / "memory")
        # few-shot은 세션 내내 동일하게 유지 (프롬프트 캐시 친화적)
        self._fewshot_cache: dict[str, list[dict]] = {}

    # ---------- 프롬프트 조립 ----------

    def _style_summary(self, prof: dict) -> str:
        lines = [
            f"- 평균 메시지 길이 {prof['avg_msg_len']}자, 한 번에 평균 {prof['avg_msgs_per_turn']}개의 짧은 메시지를 연달아 보냄",
            f"- 'ㅋㅋ' 사용률 {prof['laugh_rate']:.0%}, 'ㅠㅠ/ㅜㅜ' {prof['cry_rate']:.0%}, '!' {prof['exclaim_rate']:.0%}, '?' {prof['question_rate']:.0%}, '~' {prof['tilde_rate']:.0%}",
        ]
        if prof.get("comma_pause_rate", 0) > 0.03:
            lines.append(f"- ',,'를 말끝 여운으로 자주 씀 ({prof['comma_pause_rate']:.0%})")
        if prof.get("vowel_echo_rate", 0) > 0.03:
            lines.append(f"- 말끝 모음을 한 번 더 치는 버릇 (예: '그런가ㅏ', '했어ㅓ') ({prof['vowel_echo_rate']:.0%})")
        endings = ", ".join(f"'{e['ending']}'" for e in prof["top_endings"][:10])
        lines.append(f"- 자주 쓰는 말끝: {endings}")
        words = ", ".join(w["word"] for w in prof["top_words"][:15])
        lines.append(f"- 자주 쓰는 단어: {words}")
        if prof.get("notes"):
            lines.append(f"- 추가 메모: {prof['notes']}")
        return "\n".join(lines)

    def _fewshot_block(self, bot: str) -> str:
        if bot not in self._fewshot_cache:
            bank = self.personas[bot]["fewshot"]
            rng = random.Random(7)
            self._fewshot_cache[bot] = rng.sample(bank, min(self.fewshot_k, len(bank)))
        blocks = []
        for ex in self._fewshot_cache[bot]:
            ctx = "\n".join(f"{c['speaker']}: {' / '.join(c['texts'])}" for c in ex["context"])
            resp = "\n".join(f"{bot}: {t}" for t in ex["response"])
            blocks.append(f"{ctx}\n{resp}")
        return "\n---\n".join(blocks)

    def _timeline_block(self, n_days: int = 10) -> str:
        recent = self.timeline[-n_days:]
        if not recent:
            return ""
        lines = [f"{d['date']}: {', '.join(d['keywords'][:5])}" for d in recent if d["keywords"]]
        return "\n".join(lines)

    def build_system(self, bot: str, other: str) -> str:
        prof = self.personas[bot]["profile"]
        span = f"{self.timeline[0]['date']} ~ {self.timeline[-1]['date']}" if self.timeline else ""
        return f"""당신은 '{bot}'이다. '{other}'와(과) 나누는 카카오톡 1:1 대화에서 {bot} 본인으로서 답장한다.
두 사람은 {span} 동안 실제로 대화를 나눈 사이이며, 아래는 그 대화에서 추출한 {bot}의 실제 문체 특징과 실제 대화 예시다.

[{bot}의 문체 프로파일]
{self._style_summary(prof)}

[실제 대화 예시 — 이 말투를 그대로 재현할 것]
{self._fewshot_block(bot)}

[최근 대화 주제 타임라인]
{self._timeline_block()}

[규칙]
1. 실제 카카오톡처럼 짧은 메시지 여러 개로 나눠서 답한다 (보통 1~3개).
2. 위 예시의 말투·어미·습관(오타 스타일 포함)을 그대로 쓴다. 표준어로 교정하지 않는다.
3. AI라는 언급, 설명조, 존댓말(원래 안 쓰면) 금지. {bot}이 아는 것만 아는 척한다.
4. [기억] 블록이 주어지면 그 내용을 실제 겪은 일처럼 자연스럽게 반영한다.
5. 출력은 반드시 JSON 배열 형식으로만: ["메시지1", "메시지2"]"""

    # ---------- 생성 ----------

    def generate(self, bot: str, other: str, history: list[dict], recall_k: int = 2):
        """history: [{"speaker": 이름, "text": 내용}, ...] (오래된 것부터)"""
        query = " ".join(h["text"] for h in history[-4:])
        recalls = self.memory.search(query, k=recall_k) if query.strip() else []
        recall_block = ""
        if recalls:
            snips = []
            for r in recalls:
                date = r["start"][:10]
                lines = r["lines"][:14]
                snips.append(f"({date})\n" + "\n".join(lines))
            recall_block = "[기억 — 과거에 실제로 나눈 대화]\n" + "\n\n".join(snips) + "\n\n"

        convo = "\n".join(f"{h['speaker']}: {h['text']}" for h in history[-40:])
        prompt = f"""{recall_block}[현재 대화]
{convo}

{bot}(으)로서 다음 답장을 JSON 배열로만 출력하라."""
        raw = self.provider.generate(self.build_system(bot, other), prompt)
        return self._parse_messages(raw), [
            {"date": r["start"][:10], "score": r["score"], "preview": r["lines"][:6]} for r in recalls
        ]

    @staticmethod
    def _parse_messages(raw: str) -> list[str]:
        text = raw.strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
        m = re.search(r"\[.*\]", text, re.S)
        if m:
            try:
                arr = json.loads(m.group(0))
                msgs = [str(x).strip() for x in arr if str(x).strip()]
                if msgs:
                    return msgs[:5]
            except (json.JSONDecodeError, TypeError):
                pass
        return [line.strip() for line in text.splitlines() if line.strip()][:5] or ["..."]
