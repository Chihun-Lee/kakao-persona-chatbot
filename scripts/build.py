# -*- coding: utf-8 -*-
"""원본 카카오톡 내보내기 → 페르소나 + 메모리 빌드.

사용:  python scripts/build.py <내보내기.csv> [--speakers A B] [--out build]
결과물(build/)은 개인 데이터이므로 절대 커밋하지 않는다 (.gitignore 처리됨).
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kpc import parser as kp  # noqa: E402
from kpc import persona as kpersona  # noqa: E402
from kpc.memory import save_memory  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="카카오톡 내보내기 파일 (.csv 또는 .txt)")
    ap.add_argument("--speakers", nargs="*", help="학습할 화자 이름 (기본: 메시지 수 상위 2명)")
    ap.add_argument("--out", default="build", help="출력 디렉토리")
    ap.add_argument("--fewshot", type=int, default=150, help="화자당 few-shot 예시 수")
    args = ap.parse_args()

    msgs = kp.parse(args.input)
    if not msgs:
        sys.exit("메시지를 읽지 못했습니다. 파일 형식을 확인하세요.")

    counts = Counter(m.speaker for m in msgs)
    speakers = args.speakers or [s for s, _ in counts.most_common(2)]
    print(f"총 {len(msgs)}개 메시지 | 화자: {dict(counts)}")
    print(f"학습 대상: {speakers}")

    turns = kp.to_turns(msgs)
    episodes = kp.to_episodes(turns)
    print(f"턴 {len(turns)}개, 에피소드 {len(episodes)}개")

    out = Path(args.out)
    for name in speakers:
        profile = kpersona.build_profile(name, turns)
        exchanges = kpersona.extract_exchanges(episodes, name)
        fewshot = kpersona.select_fewshot(exchanges, k=args.fewshot)
        path = kpersona.save_persona(out / "personas", profile, fewshot)
        print(f"[{name}] 메시지 {profile['message_count']}개, 예시 {len(fewshot)}개 → {path}")

    save_memory(out / "memory", episodes)
    print(f"메모리 저장 완료 → {out}/memory/ (에피소드 {len(episodes)}개)")
    print("\n다음 단계:  python -m kpc.server  →  http://127.0.0.1:8917")


if __name__ == "__main__":
    main()
