# -*- coding: utf-8 -*-
"""카카오톡 내보내기 파일 파서.

CSV(모바일 내보내기: Date,User,Message)를 기본 지원하고,
macOS/Windows txt 내보내기도 best-effort로 파싱한다.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

# 대화 내용이 아닌 시스템/미디어 메시지 — 문체 학습에서 제외
MEDIA_MESSAGES = {"사진", "이모티콘", "동영상", "음성메시지", "삭제된 메시지입니다.", "메시지가 삭제되었습니다."}
MEDIA_PREFIXES = ("사진 ", "샵검색:", "보이스톡 ", "페이스톡 ", "지도:", "파일:", "송금 ")


@dataclass
class Message:
    time: datetime
    speaker: str
    text: str

    @property
    def is_media(self) -> bool:
        t = self.text.strip()
        return t in MEDIA_MESSAGES or t.startswith(MEDIA_PREFIXES)


@dataclass
class Turn:
    """같은 화자가 연속으로 보낸 메시지 묶음."""
    speaker: str
    start: datetime
    texts: list[str] = field(default_factory=list)


@dataclass
class Episode:
    """시간 간격으로 구분한 대화 에피소드 (기본: 60분 이상 공백이면 분리)."""
    idx: int
    start: datetime
    end: datetime
    turns: list[Turn] = field(default_factory=list)


def parse_csv(path: str | Path) -> list[Message]:
    msgs: list[Message] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            user = (row.get("User") or "").strip()
            text = (row.get("Message") or "").strip()
            if not user or not text:
                continue  # 삭제된 메시지 등
            try:
                t = datetime.strptime(row["Date"].strip(), "%Y-%m-%d %H:%M:%S")
            except (ValueError, KeyError):
                continue
            msgs.append(Message(t, user, text))
    return msgs


# "2026. 5. 2. 오후 1:31, 이름 : 내용" (macOS) / "2026년 5월 2일 오후 1:31, 이름 : 내용"
_TXT_LINE = re.compile(
    r"^(\d{4})[.년]\s*(\d{1,2})[.월]\s*(\d{1,2})[.일]?\s*(오전|오후)\s*(\d{1,2}):(\d{2}),?\s*(.+?)\s?:\s(.*)$"
)


def parse_txt(path: str | Path) -> list[Message]:
    msgs: list[Message] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = _TXT_LINE.match(line.rstrip("\n"))
            if not m:
                # 직전 메시지의 연속 줄
                if msgs and line.strip():
                    msgs[-1].text += "\n" + line.strip()
                continue
            y, mo, d, ampm, hh, mm, user, text = m.groups()
            h = int(hh) % 12 + (12 if ampm == "오후" else 0)
            msgs.append(Message(datetime(int(y), int(mo), int(d), h, int(mm)), user.strip(), text.strip()))
    return msgs


def parse(path: str | Path) -> list[Message]:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return parse_csv(path)
    return parse_txt(path)


def to_turns(msgs: list[Message], merge_gap_sec: int = 300) -> list[Turn]:
    """연속 메시지를 턴으로 병합. 미디어 메시지는 건너뛴다."""
    turns: list[Turn] = []
    for m in msgs:
        if m.is_media:
            continue
        if turns and turns[-1].speaker == m.speaker and (m.time - _turn_end(turns[-1], m)) <= timedelta(seconds=merge_gap_sec):
            turns[-1].texts.append(m.text)
            turns[-1]._last = m.time  # type: ignore[attr-defined]
        else:
            t = Turn(m.speaker, m.time, [m.text])
            t._last = m.time  # type: ignore[attr-defined]
            turns.append(t)
    return turns


def _turn_end(turn: Turn, _m: Message) -> datetime:
    return getattr(turn, "_last", turn.start)


def to_episodes(turns: list[Turn], gap_min: int = 60) -> list[Episode]:
    episodes: list[Episode] = []
    for turn in turns:
        last_end = getattr(episodes[-1].turns[-1], "_last", episodes[-1].end) if episodes and episodes[-1].turns else None
        if not episodes or (turn.start - last_end) > timedelta(minutes=gap_min):
            episodes.append(Episode(len(episodes), turn.start, turn.start, []))
        ep = episodes[-1]
        ep.turns.append(turn)
        ep.end = getattr(turn, "_last", turn.start)
    return episodes
