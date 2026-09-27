"""One-off connectivity check for 9Router — does not print secrets."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from app.core.config import get_settings


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        env_path = Path(__file__).resolve().parents[1].parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


async def main() -> None:
    _load_dotenv()
    get_settings.cache_clear()

    import httpx

    from app.ai.llm import OpenAICompatibleLLM
    from app.core.config import get_settings as gs

    s = gs()
    print("provider=", s.llm_provider)
    print("base=", s.llm_api_base)
    print("model=", s.llm_model)
    print("key_set=", bool(s.llm_api_key))

    base = s.llm_api_base.rstrip("/")
    headers = {"Authorization": f"Bearer {s.llm_api_key}"}
    async with httpx.AsyncClient(timeout=45.0) as client:
        r = await client.get(f"{base}/models", headers=headers)
        print("models_status=", r.status_code)
        ids = [m["id"] for m in r.json().get("data", [])]
        mimo = [i for i in ids if "mimo" in i.lower() or i.startswith("oc/")]
        print("mimo_or_oc_count=", len(mimo))
        for i in mimo[:40]:
            print("model:", i)
        print("has_exact=", "oc/mimo-v2.6-flash-free" in ids)
        print("has_taha_combo=", "taha" in ids)

    llm = OpenAICompatibleLLM()
    try:
        # raw peek
        import httpx
        from app.core.config import get_settings as gs2

        s2 = gs2()
        payload = {
            "model": s2.llm_model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": 'Return {"ok": true, "ping": "pong"}'},
            ],
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{s2.llm_api_base.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {s2.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            print("raw_status=", resp.status_code)
            print("raw_body=", resp.text[:800])
        out = await llm.chat_json(
            system="Return JSON only.",
            user='Return {"ok": true, "ping": "pong"}',
        )
        print("chat_ok=", out)
    except Exception as e:  # noqa: BLE001
        print("chat_fail=", type(e).__name__, str(e)[:400])
        llm2 = OpenAICompatibleLLM(model="taha")
        try:
            out2 = await llm2.chat_json(
                system="Return JSON only.",
                user='Return {"ok": true, "ping": "pong"}',
            )
            print("taha_chat_ok=", out2)
        except Exception as e2:  # noqa: BLE001
            print("taha_chat_fail=", type(e2).__name__, str(e2)[:400])


if __name__ == "__main__":
    asyncio.run(main())
