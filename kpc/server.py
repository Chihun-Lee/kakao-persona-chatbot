# -*- coding: utf-8 -*-
"""FastAPI 웹 챗봇 서버.

실행:  python -m kpc.server  (또는 uvicorn kpc.server:app)
config.json 에서 프로바이더/모델을 읽는다 (없으면 claude-cli 기본값).
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .engine import PersonaEngine
from .llm import LLMError, make_provider

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"provider": "claude-cli", "model": "sonnet", "build_dir": "build"}


config = load_config()
engine: PersonaEngine | None = None

app = FastAPI(title="kakao-persona-chatbot")


@app.on_event("startup")
def _startup():
    global engine
    engine = PersonaEngine(ROOT / config.get("build_dir", "build"), make_provider(config),
                           fewshot_k=config.get("fewshot_k", 30))


class ChatRequest(BaseModel):
    bot: str                      # 봇이 연기할 화자
    history: list[dict]           # [{"speaker": 이름, "text": 내용}]


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/info")
def info():
    return {
        "personas": list(engine.personas.keys()),
        "provider": config.get("provider"),
        "model": config.get("model"),
        "period": [engine.timeline[0]["date"], engine.timeline[-1]["date"]] if engine.timeline else None,
        "episodes": engine.memory.n,
    }


@app.post("/api/chat")
def chat(req: ChatRequest):
    others = [p for p in engine.personas if p != req.bot]
    other = others[0] if others else "상대"
    try:
        messages, recall = engine.generate(req.bot, other, req.history)
    except LLMError as e:
        return JSONResponse({"error": str(e)}, status_code=502)
    return {"messages": messages, "recall": recall}


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=config.get("port", 8917))


if __name__ == "__main__":
    main()
