"""Avatar chat microservice — STUB.

Per the project decision ("explorer first, chat later"), this service is
scaffolded but the LLM call is not yet wired. What is real:

  - GET  /                       health
  - GET  /rulers/{id}/persona    the grounding system prompt for a ruler
                                 (the exact text the model will be given)
  - POST /chat/{id}              accepts {messages:[...]} and, once a key is
                                 configured, streams an in-character reply

Wiring the model later is intentionally a few lines (see `_answer`): drop in the
Anthropic SDK, pass `build_persona_prompt(ruler)` as the system prompt, prepend
it to the conversation, and return the completion. Until `ANTHROPIC_API_KEY` is
set the endpoint returns 503 with a clear message — it never fabricates history.

CORS is wide open, matching the other public OHM APIs. Run:
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .persona import build_persona_prompt, load_ruler

app = FastAPI(title="Rulers of the Past — Avatar Chat", version="0.1.0-stub")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL = os.environ.get("CHAT_MODEL", "claude-haiku-4-5-20251001")
API_KEY = os.environ.get("ANTHROPIC_API_KEY")


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]


@app.get("/")
def health():
    return {"ok": True, "service": "otp-chat", "model": MODEL, "llm_wired": bool(API_KEY)}


def _require(ruler_id):
    r = load_ruler(ruler_id)
    if not r:
        raise HTTPException(404, f"no ruler '{ruler_id}'")
    if not r.get("chat_ready"):
        raise HTTPException(409, f"'{r['name']}' is not documented fully enough for an avatar")
    return r


@app.get("/rulers/{ruler_id}/persona")
def persona(ruler_id: str):
    r = _require(ruler_id)
    return {"id": ruler_id, "name": r["name"], "system_prompt": build_persona_prompt(r)}


@app.post("/chat/{ruler_id}")
def chat(ruler_id: str, req: ChatRequest):
    ruler = _require(ruler_id)
    system = build_persona_prompt(ruler)
    return _answer(ruler, system, [m.dict() for m in req.messages])


def _answer(ruler, system, messages):
    """The one place to wire the model. Today: a 503 holding response.

    To connect Claude later (≈10 lines):
        import anthropic
        client = anthropic.Anthropic(api_key=API_KEY)
        resp = client.messages.create(
            model=MODEL, max_tokens=400, system=system,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
        )
        return {"reply": resp.content[0].text}
    """
    if not API_KEY:
        raise HTTPException(
            503,
            f"The avatar of {ruler['name']} is not yet awakened — set ANTHROPIC_API_KEY "
            "to connect the oracle. The grounding prompt is ready at "
            f"/rulers/{ruler['id']}/persona.",
        )
    raise HTTPException(501, "model call not implemented; see _answer() in app/main.py")
