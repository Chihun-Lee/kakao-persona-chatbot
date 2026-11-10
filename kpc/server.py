# -*- coding: utf-8 -*-
"""페르소나 말투 변환 웹 서버.

실행:  python -m kpc.server
공개 모드(public_mode)에서는 public: true 페르소나만 보이고, 접속 수를 제한하며, 입력 글을 저장하지 않는다.
"""
from __future__ import annotations

import json
import os
import random
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .imperfect import LEVELS, add_noise
from .llm import LLMError, make_provider
from .rewrite import CHANNEL_NAMES, build_system, build_user, number_warnings

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("KPC_CONFIG", ROOT / "config.json"))


def load_config() -> dict:
    base = {"provider": "anthropic", "model": "claude-opus-5-5", "effort": "low", "max_tokens": 2048, "port": 8917,
            "public_mode": False, "rate_per_hour": 20, "daily_cap": 500, "max_chars": 1500, "access_key": ""}
    if CONFIG_PATH.exists():
        base.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    return base


config = load_config()
if config["public_mode"] and config["provider"] == "claude-cli":
    raise SystemExit("공개 모드에서는 claude-cli 프로바이더를 쓸 수 없습니다. API 키로 anthropic 프로바이더를 쓰세요.")
provider = make_provider(config)
app = FastAPI(title="persona-voice")


def load_personas() -> dict[str, dict]:
    found: dict[str, dict] = {}
    dirs = [ROOT / "personas" / "public"]
    if not config["public_mode"]:
        dirs.append(ROOT / "personas" / "private")
    for folder in dirs:
        for path in sorted(folder.glob("*.json")):
            persona = json.loads(path.read_text(encoding="utf-8"))
            if config["public_mode"] and not persona.get("public"):
                continue
            found[persona["id"]] = persona
    return found


personas = load_personas()
_hits: dict[str, deque] = defaultdict(deque)
_day = {"date": "", "count": 0}


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return request.headers.get("cf-connecting-ip") or forwarded or request.client.host


def check_limits(request: Request) -> None:
    """공개 모드에서 한 사람이 비용을 다 쓰지 못하게 막는다."""
    if not config["public_mode"]:
        return
    today = time.strftime("%Y-%m-%d")
    if _day["date"] != today:
        _day.update(date=today, count=0)
    if _day["count"] >= config["daily_cap"]:
        raise HTTPException(429, "오늘 시험 횟수가 모두 찼습니다. 내일 다시 시도해 주세요.")
    now = time.time()
    hits = _hits[client_ip(request)]
    while hits and now - hits[0] > 3600:
        hits.popleft()
    if len(hits) >= config["rate_per_hour"]:
        raise HTTPException(429, "시간당 시험 횟수를 넘었습니다. 잠시 뒤 다시 시도해 주세요.")
    hits.append(now)
    _day["count"] += 1


@app.middleware("http")
async def access_guard(request: Request, call_next):
    """access_key를 설정하면 ?key= 링크로 들어온 사람만 쓸 수 있다."""
    key = config.get("access_key")
    if not key:
        return await call_next(request)
    if request.query_params.get("key") == key:
        response = await call_next(request)
        response.set_cookie("kpc_key", key, httponly=True, max_age=7 * 86400)
        return response
    if request.cookies.get("kpc_key") == key:
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "접근 키가 필요합니다."}, status_code=401)
    return PlainTextResponse("접근 키가 필요합니다. 공유받은 링크로 접속하세요.", status_code=401)


class RewriteRequest(BaseModel):
    persona: str
    channel: str
    text: str = Field(min_length=1)
    relation: str = ""
    level: str = "low"
    protect: list[str] = []
    seed: int | None = None


class NoiseRequest(BaseModel):
    persona: str
    channel: str
    text: str = Field(min_length=1)
    level: str = "low"
    protect: list[str] = []
    seed: int | None = None


def resolve(name: str, channel: str, level: str) -> dict:
    persona = personas.get(name)
    if not persona:
        raise HTTPException(404, "없는 페르소나입니다.")
    if channel not in CHANNEL_NAMES or channel not in persona["channels"]:
        raise HTTPException(400, "이 페르소나에 없는 채널입니다.")
    if level not in LEVELS:
        raise HTTPException(400, "실수 정도는 off, low, normal, high 중 하나입니다.")
    return persona


def noise_payload(text: str, persona: dict, channel: str, level: str, seed: int | None, protect: list[str]) -> dict:
    seed = random.randrange(1_000_000) if seed is None else seed
    result = add_noise(text, persona, channel, level, seed, protect)
    return {"clean": text, "text": result.text, "segments": result.segments, "edits": result.edits, "seed": seed}


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/personas")
def list_personas():
    items = [{"id": p["id"], "name": p["display_name"], "description": p.get("description", ""), "consent": p.get("consent", ""),
              "channels": [{"id": c, "name": CHANNEL_NAMES[c]} for c in p["channels"]]} for p in personas.values()]
    return {"personas": items, "public_mode": config["public_mode"], "max_chars": config["max_chars"], "model": config.get("model", "")}


@app.post("/api/rewrite")
def rewrite(req: RewriteRequest, request: Request):
    persona = resolve(req.persona, req.channel, req.level)
    if len(req.text) > config["max_chars"]:
        raise HTTPException(413, f"{config['max_chars']}자까지 입력할 수 있습니다.")
    check_limits(request)
    try:
        clean = provider.generate(build_system(persona, req.channel), build_user(req.text, req.relation)).strip()
    except LLMError as e:
        raise HTTPException(502, str(e)) from e
    payload = noise_payload(clean, persona, req.channel, req.level, req.seed, req.protect)
    payload["warnings"] = number_warnings(req.text, clean)
    return payload


@app.post("/api/noise")
def noise(req: NoiseRequest):
    """모델을 다시 부르지 않고 실수만 새로 넣는다."""
    persona = resolve(req.persona, req.channel, req.level)
    if len(req.text) > config["max_chars"] * 3:
        raise HTTPException(413, "글이 너무 깁니다.")
    return noise_payload(req.text, persona, req.channel, req.level, req.seed, req.protect)


def main():
    import uvicorn
    uvicorn.run("kpc.server:app", host=config.get("host", "127.0.0.1"), port=config["port"])


if __name__ == "__main__":
    main()
