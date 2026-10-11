import json

import requests

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiError(RuntimeError):
    pass


def generate_json(api_key: str, model: str, system: str, prompt: str, schema: dict, timeout: int = 120) -> dict:
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json", "responseSchema": schema},
    }
    try:
        resp = requests.post(
            API_URL.format(model=model),
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=body,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise GeminiError(f"network error: {exc}") from exc
    if resp.status_code == 429:
        raise GeminiError("free-tier rate limit or daily quota reached - try again later")
    if resp.status_code >= 400:
        raise GeminiError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        parts = resp.json()["candidates"][0]["content"]["parts"]
        return json.loads("".join(p.get("text", "") for p in parts))
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise GeminiError(f"unexpected model response: {resp.text[:300]}") from exc
