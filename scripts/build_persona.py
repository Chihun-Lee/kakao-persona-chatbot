#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""카카오톡 내보내기와 보낸 메일에서 페르소나 파일을 만든다.

예:
  python scripts/build_persona.py --id me --name 홍길동 --me 길동 --me 홍길동 \
      --kakao-work "data/work/*.csv" --kakao-friend "data/friend/*.csv" \
      --mail-jsonl data/sent.jsonl --mail-field text --out personas/private/me.json

원본 글은 복사하지 않는다. 개인정보를 가린 짧은 예문과 통계만 저장한다.
"""
from __future__ import annotations

import argparse
import glob
import json
import mailbox
import sys
from email.policy import default as email_default
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kpc.parser import parse                       # noqa: E402
from kpc import persona as P                       # noqa: E402


def read_chat(pattern: str, me: set[str]) -> tuple[list[str], set[str]]:
    own: list[str] = []
    others: set[str] = set()
    for f in sorted(glob.glob(pattern)):
        for m in parse(f):
            if m.is_media:
                continue
            if m.speaker in me:
                own.append(m.text)
            else:
                others.add(m.speaker)
    return own, others


def read_mail(args) -> list[str]:
    mails: list[str] = []
    if args.mail_jsonl:
        for line in open(args.mail_jsonl, encoding="utf-8"):
            mails.append(json.loads(line)[args.mail_field])
    if args.mbox:
        for msg in mailbox.mbox(args.mbox, factory=lambda f: __import__("email").message_from_binary_file(f, policy=email_default)):
            if not any(addr in (msg.get("From") or "") for addr in args.my_address):
                continue
            body = msg.get_body(preferencelist=("plain",))
            if body:
                mails.append(body.get_content())
    for f in sorted(glob.glob(args.mail_txt or "")):
        mails.append(Path(f).read_text(encoding="utf-8"))
    return [P.clean_mail(m) for m in mails if m and m.strip()]


def channel_rules(path: str | None) -> str:
    """말투 지침 파일을 읽는다. SKILL.md면 머리말(YAML)을 뺀다."""
    if not path:
        return ""
    text = Path(path).read_text(encoding="utf-8")
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    return text.strip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", required=True)
    ap.add_argument("--name", required=True, help="표시 이름이자 메일 서명의 전체 이름")
    ap.add_argument("--me", action="append", required=True, help="카카오톡에서 본인으로 표시되는 이름. 여러 번 지정 가능")
    ap.add_argument("--kakao-work")
    ap.add_argument("--kakao-friend")
    ap.add_argument("--mail-jsonl")
    ap.add_argument("--mail-field", default="text")
    ap.add_argument("--mbox")
    ap.add_argument("--my-address", action="append", default=[])
    ap.add_argument("--mail-txt")
    ap.add_argument("--given", help="이름만. 없으면 전체 이름의 뒤 두 글자")
    ap.add_argument("--consent", default="self", choices=["self", "fictional", "written-consent"])
    ap.add_argument("--public", action="store_true", help="웹 공개 모드에 노출. 본인이 결정할 때만")
    ap.add_argument("--rare-signoff", action="append", default=[], help="아주 가끔 쓸 맺음말 변형")
    ap.add_argument("--style-work"), ap.add_argument("--style-friend"), ap.add_argument("--style-mail")
    ap.add_argument("--typo-floor", type=float, default=2.0, help="천 글자당 오타 기본값의 하한")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    me = set(a.me)
    given = a.given or a.name[-2:]
    protect = sorted(me | {a.name, given})
    channels: dict[str, dict] = {}
    everything: list[str] = []
    names: set[str] = set()
    sources = [("kakao_work", a.kakao_work, a.style_work), ("kakao_friend", a.kakao_friend, a.style_friend)]
    loaded = []
    for cid, pattern, style in sources:
        if pattern:
            own, others = read_chat(pattern, me)
            names |= others
            loaded.append((cid, own, style))
            everything += own
    noise_period: dict[str, float] = {}
    for cid, own, style in loaded:
        stats = P.chat_stats(own)
        channels[cid] = {"stats": stats, "rules": [], "style_guide": channel_rules(style),
                         "examples": P.pick_examples(own, 40, 6, 90, sorted(names))}
        noise_period[cid] = P.period_drop(stats["ends_with_period"])
    mails = read_mail(a)
    if mails:
        everything += mails
        stats = P.mail_stats(mails, a.name, given)
        signoffs = [{"text": s["text"], "weight": s["weight"]} for s in stats["signoffs"]] or [{"text": f"{a.name} 드림", "weight": 1.0}]
        signoffs += [{"text": t, "weight": 0.02} for t in a.rare_signoff if t not in {s["text"] for s in signoffs}]
        channels["mail"] = {"stats": stats, "rules": [], "style_guide": channel_rules(a.style_mail), "signoffs": signoffs,
                            "examples": P.pick_examples(mails, 12, 40, 420, sorted(names))}
        noise_period["mail"] = P.period_drop(stats["line_ends_with_period"])
    if not channels:
        ap.error("카카오톡 또는 메일 자료를 하나 이상 지정하세요.")
    typos, typo_rate = P.mine_typos(everything)
    result = {
        "id": a.id, "display_name": a.name, "description": f"{a.name} 본인 글에서 만든 페르소나" if a.consent == "self" else "",
        "consent": a.consent, "public": a.public, "protect": protect, "channels": channels, "typos": typos,
        "noise": {"typo_per_1000": max(typo_rate, a.typo_floor), "measured_typo_per_1000": typo_rate, "space_per_1000": max(P.spacing_rate(everything), 0.6), "period_drop": noise_period},
        "source_counts": {cid: c["stats"].get("messages", c["stats"].get("mails")) for cid, c in channels.items()},
    }
    path = P.save(result, a.out)
    print(json.dumps({"out": str(path), "source_counts": result["source_counts"], "noise": result["noise"], "typos_found": len(typos)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
