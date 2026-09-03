"""글을 써주는 AI 엔진. config/settings.yml 의 llm.provider 로 갈아끼운다.

지원: gemini (무료, 카드 불필요) / claude (유료, 품질 최상)
새 엔진을 추가하려면 _PROVIDERS 에 함수 하나만 더 넣으면 된다.
"""
from __future__ import annotations

import json
import re
import time

import requests

from common import env, log, settings

FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


# ------------------------------------------------------------------ 공통 진입점
def _cfg() -> dict:
    return settings().get("llm", {"provider": "gemini"})


def provider() -> str:
    return _cfg().get("provider", "gemini")


def key_name() -> str:
    return {"gemini": "GEMINI_API_KEY", "claude": "ANTHROPIC_API_KEY"}.get(provider(), "")


def ready() -> bool:
    return bool(env(key_name()))


def complete_json(system: str, user: str, schema: dict) -> dict | None:
    """JSON을 받아온다. 실패하면 None."""
    raw = _PROVIDERS[provider()](system, user, schema)
    if not raw:
        return None
    raw = FENCE.sub("", raw.strip()).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.error("AI 응답을 JSON으로 읽지 못했습니다: %s", raw[:200])
        return None


def complete_text(system: str, user: str) -> str | None:
    """평범한 글 한 덩어리를 받아온다."""
    raw = _PROVIDERS[provider()](system, user, None)
    return raw.strip().strip('"') if raw else None


# ------------------------------------------------------------------ Gemini (무료)
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# 구글이 모델을 없애면(404) 위에서부터 차례로 다음 것을 시도한다.
# 덕분에 몇 달 뒤 모델이 바뀌어도 시스템이 멈추지 않는다.
GEMINI_FALLBACKS = ["gemini-flash-latest", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-2.5-flash"]


def _gemini(system: str, user: str, schema: dict | None) -> str | None:
    api_key = env("GEMINI_API_KEY")
    if not api_key:
        log.error("GEMINI_API_KEY 가 없습니다. .env 또는 GitHub Secrets를 확인하세요.")
        return None

    first = _cfg().get("model", "gemini-flash-latest")
    candidates = [first] + [m for m in GEMINI_FALLBACKS if m != first]
    gen_cfg: dict = {"temperature": _cfg().get("temperature", 1.0), "maxOutputTokens": 8192}
    if schema:
        gen_cfg["responseMimeType"] = "application/json"
        system = system + "\n\n반드시 아래 JSON 형식으로만 답하세요. 설명을 덧붙이지 마세요.\n" + \
            json.dumps(_example_of(schema), ensure_ascii=False)

    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": gen_cfg,
    }
    for model in candidates:
        r = None
        for attempt in range(3):        # 과부하(503)·한도초과(429)는 잠깐 쉬었다 다시
            try:
                r = requests.post(GEMINI_URL.format(model=model),
                                  headers={"x-goog-api-key": api_key},
                                  json=body, timeout=120)
            except (requests.RequestException, ValueError) as e:
                log.warning("Gemini 통신 오류(%d회차): %s", attempt + 1, e)
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code not in (429, 503):
                break
            wait = 10 * (attempt + 1)
            log.warning("Gemini 가 바쁩니다(%s). %d초 뒤 다시 시도합니다. (%d/3)",
                        r.status_code, wait, attempt + 1)
            time.sleep(wait)

        if r is None:
            log.error("Gemini 에 연결하지 못했습니다.")
            return None
        if r.status_code == 404:
            log.warning("모델 '%s' 를 쓸 수 없습니다. 다음 모델로 시도합니다.", model)
            continue
        if r.status_code in (429, 503):
            log.warning("'%s' 가 계속 바쁩니다. 다른 모델로 시도합니다.", model)
            continue
        if r.status_code != 200:
            log.error("Gemini 오류 %s: %s", r.status_code, r.text[:300])
            return None

        if model != first:
            log.warning("'%s' 로 성공했습니다. config/settings.yml 의 llm.model 을 "
                        "'%s' 로 바꿔두면 더 빨라집니다.", model, model)
        data = r.json()
        cand = (data.get("candidates") or [{}])[0]
        if cand.get("finishReason") in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"):
            log.error("Gemini가 생성을 거부했습니다 (%s).", cand.get("finishReason"))
            return None
        parts = cand.get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts) or None

    log.error("쓸 수 있는 Gemini 모델을 찾지 못했습니다. 시도한 목록: %s", ", ".join(candidates))
    return None


def _example_of(schema: dict) -> dict:
    """JSON 스키마를 보고 '이런 모양으로 답해줘' 예시를 만든다 (Gemini용 안내)."""
    def walk(node: dict):
        t = node.get("type")
        if t == "object":
            return {k: walk(v) for k, v in node.get("properties", {}).items()}
        if t == "array":
            return [walk(node.get("items", {}))]
        if "enum" in node:
            return node["enum"][0]
        if t == "integer":          # 숫자를 문자열로 보여주면 AI가 문자열을 돌려준다
            return 0
        if t == "number":
            return 0
        if t == "boolean":
            return False
        return "..."
    return walk(schema)


# ------------------------------------------------------------------ Claude (유료)
def _claude(system: str, user: str, schema: dict | None) -> str | None:
    api_key = env("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("ANTHROPIC_API_KEY 가 없습니다. .env 또는 GitHub Secrets를 확인하세요.")
        return None
    try:
        import anthropic
    except ImportError:
        log.error("anthropic 패키지가 없습니다. pip install -r requirements.txt 를 실행하세요.")
        return None

    cfg = _cfg()
    output_config: dict = {"effort": cfg.get("effort", "low")}
    if schema:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=cfg.get("model", "claude-opus-5"),
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config=output_config,
        )
        if resp.stop_reason == "refusal":
            log.error("Claude가 생성을 거부했습니다.")
            return None
        return next((b.text for b in resp.content if b.type == "text"), None)
    except Exception as e:  # noqa: BLE001 - 봇이 죽으면 안 된다
        log.error("Claude 호출 실패: %s", e)
        return None


_PROVIDERS = {"gemini": _gemini, "claude": _claude}
