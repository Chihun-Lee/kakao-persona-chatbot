# -*- coding: utf-8 -*-
"""LLM 프로바이더 추상화.

- anthropic  : Anthropic API (ANTHROPIC_API_KEY 또는 `ant auth login` 프로파일)
- claude-cli : Claude Code CLI 구독 인증으로 동작 (`claude -p`) — API 키 불필요
- openai-compat : Ollama / LM Studio / mlx_lm.server 등 OpenAI 호환 로컬 서버
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.request


class LLMError(RuntimeError):
    pass


class AnthropicProvider:
    def __init__(self, model: str = "claude-opus-5-5", effort: str = "low", max_tokens: int = 2048):
        import anthropic  # 선택 의존성 — 이 프로바이더를 쓸 때만 필요
        self.client = anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens

    def generate(self, system: str, prompt: str) -> str:
        kwargs: dict = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        if self.model.startswith(("claude-opus-5", "claude-fable-5")):
            # 안전 분류기 거절 시 서버측 폴백 (권장 기본값)
            resp = self.client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
        else:
            resp = self.client.messages.create(**kwargs)
        if resp.stop_reason == "refusal":
            raise LLMError("모델이 응답을 거부했습니다 (safety refusal).")
        return next((b.text for b in resp.content if b.type == "text"), "")


class ClaudeCLIProvider:
    """Claude Code CLI(구독 인증)를 백엔드로 사용. 별도 API 키가 필요 없다."""

    def __init__(self, model: str = "sonnet", timeout: int = 180):
        self.model = model
        self.timeout = timeout

    def generate(self, system: str, prompt: str) -> str:
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        try:
            # 개인 설정과 도구를 읽지 않도록 빈 폴더에서 설정 없이 실행한다
            with tempfile.TemporaryDirectory() as empty:
                proc = subprocess.run(
                    ["claude", "-p", "--model", self.model, "--system-prompt", system, "--setting-sources", "project",
                     "--strict-mcp-config", "--no-session-persistence", "--tools", ""],
                    input=prompt, capture_output=True, text=True, timeout=self.timeout, env=env, cwd=empty,
                )
        except FileNotFoundError as e:
            raise LLMError("claude CLI를 찾을 수 없습니다. https://claude.com/claude-code 설치 필요") from e
        except subprocess.TimeoutExpired as e:
            raise LLMError(f"claude CLI 응답 시간 초과({self.timeout}s)") from e
        if proc.returncode != 0:
            raise LLMError(f"claude CLI 오류: {proc.stderr.strip()[:300]}")
        return proc.stdout.strip()


class OpenAICompatProvider:
    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "qwen2.5:7b",
                 max_tokens: int = 1024, timeout: int = 180):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout

    def generate(self, system: str, prompt: str) -> str:
        body = json.dumps({
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.load(r)
        except Exception as e:  # noqa: BLE001 — 네트워크 계열 오류를 사용자 메시지로 변환
            raise LLMError(f"로컬 LLM 서버 호출 실패: {e}") from e
        return data["choices"][0]["message"]["content"]


def make_provider(config: dict):
    p = config.get("provider", "claude-cli")
    if p == "anthropic":
        return AnthropicProvider(config.get("model", "claude-opus-5-5"),
                                 config.get("effort", "low"),
                                 config.get("max_tokens", 2048))
    if p == "claude-cli":
        return ClaudeCLIProvider(config.get("model", "sonnet"))
    if p == "openai-compat":
        return OpenAICompatProvider(config.get("base_url", "http://127.0.0.1:11434"),
                                    config.get("model", "qwen2.5:7b"),
                                    config.get("max_tokens", 1024))
    raise LLMError(f"알 수 없는 provider: {p}")
