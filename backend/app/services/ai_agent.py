"""
AI Energy Agent. The platform's ML detectors and analytics act as tools; an LLM reasons over their output.
Engine order: Gemini (free key) -> Claude -> local Ollama -> rule-based fallback.
Keys go in backend/.env:  GOOGLE_API_KEY=...   (get a free one at https://aistudio.google.com/apikey)
"""
import functools
import json
import os

import httpx

from app.config import settings

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
PREFERRED_MODELS = ['gemini-3.1-flash-lite', 'gemini-3.6-flash', 'gemini-3.5-flash']  # chosen by apply_model_pick.py
SYSTEM = (
    "You are the Energy Agent of an enterprise facility-operations platform. "
    "Answer ONLY from the JSON data provided (meters, kWh, INR cost, anomalies, recommendations). "
    "Prefer incidents (grouped events in top_incidents / incident_count) over raw reading counts. "
    "Be concise (under 130 words), use concrete numbers and INR, explain likely causes of anomalies "
    "and give 1-3 specific actions. If the data does not contain the answer, say so."
)


def build_context(summary: dict, analysis: dict, facility_name: str) -> dict:
    return {
        "facility": facility_name,
        "period": summary["period"],
        "kpis": summary["kpis"],
        "energy_by_meter": summary["meter_breakdown"],
        "anomaly_summary": analysis["anomaly_summary"],
        "top_anomalies": analysis["anomalies"][:10],
        "recommendations": analysis["recommendations"],
    }


def _prompt(question: str, context: dict) -> str:
    return f"Facility data (JSON):\n{json.dumps(context, default=str)}\n\nQuestion: {question}"


def _has(key) -> bool:
    return bool(key) and len(key) >= 20


# ---------------------------- engines: each returns (text, error) ----------------------------
@functools.lru_cache(maxsize=1)
def _gemini_candidates(key: str) -> list:
    if PREFERRED_MODELS:
        return list(PREFERRED_MODELS)
    """Stable Gemini flash models to try in order (preview/experimental models have tiny free quotas)."""
    forced = os.getenv("GEMINI_MODEL") or getattr(settings, "GEMINI_MODEL", None)
    if forced:
        return [forced]
    names = []
    try:
        r = httpx.get(f"{GEMINI_BASE}/models", headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=15)
        r.raise_for_status()
        bad = ("lite", "image", "tts", "audio", "live", "thinking", "embedding", "preview", "exp", "omni", "robotics", "computer", "vision")
        names = sorted(
            {
                m["name"].split("/")[-1]
                for m in r.json().get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
                and "flash" in m["name"] and not any(x in m["name"] for x in bad)
            },
            reverse=True,
        )
    except Exception:
        pass
    for fallback in ("gemini-2.5-flash", "gemini-2.0-flash"):
        if fallback not in names:
            names.append(fallback)
    return names[:4]


def _ask_gemini(question, context):
    key = settings.GOOGLE_API_KEY
    if not _has(key):
        return None, None
    last = None
    for model in _gemini_candidates(key):
        # First try with thinking disabled (fast); some models reject that field, so retry without it.
        for thinking in ({"thinkingBudget": 0}, None):
            cfg = {"temperature": 0.3, "maxOutputTokens": 2048}
            if thinking is not None:
                cfg["thinkingConfig"] = thinking
            try:
                r = httpx.post(
                    f"{GEMINI_BASE}/models/{model}:generateContent",
                    headers={"x-goog-api-key": key, "content-type": "application/json"},
                    json={
                        "systemInstruction": {"parts": [{"text": SYSTEM}]},
                        "contents": [{"role": "user", "parts": [{"text": _prompt(question, context)}]}],
                        "generationConfig": cfg,
                    },
                    timeout=30,
                )
                r.raise_for_status()
                parts = r.json()["candidates"][0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts).strip()
                if text:
                    return text, None
                last = f"Gemini {model}: empty answer"
                break
            except Exception as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                last = f"Gemini {model} ({type(exc).__name__}): {str(exc)[:120]}"
                if status == 400 and thinking is not None:
                    continue  # retry same model without thinkingConfig
                break
    return None, last


def _ask_claude(question, context):
    key = settings.ANTHROPIC_API_KEY
    if not _has(key):
        return None, None
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
                "max_tokens": 600, "system": SYSTEM,
                "messages": [{"role": "user", "content": _prompt(question, context)}],
            },
            timeout=40,
        )
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json().get("content", [])).strip()
        return (text or None), None
    except Exception as exc:
        return None, f"Claude ({type(exc).__name__}): {str(exc)[:160]}"


def _ask_ollama(question, context):
    try:
        r = httpx.post(
            os.getenv("OLLAMA_URL", "http://localhost:11434") + "/api/chat",
            json={
                "model": os.getenv("OLLAMA_MODEL", "llama3.2"), "stream": False,
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": _prompt(question, context)}],
            },
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["message"]["content"].strip(), None
    except Exception:
        return None, None  # Ollama is optional; stay silent if it is not running


# ---------------------------- rule-based fallback ----------------------------
def _rules(question: str, c: dict) -> str:
    q = question.lower()
    k, a = c["kpis"], c["anomaly_summary"]
    if any(w in q for w in ("anomal", "spike", "why", "unusual", "problem", "alert")):
        if not c["top_anomalies"]:
            return f"No anomalies were detected for {c['facility']} in the last 7 days."
        lines = [f"{c['facility']}: {a['total']} anomalous readings in 7 days ({a['critical']} critical, {a['high']} high)."]
        for x in c["top_anomalies"][:3]:
            lines.append(f"- {x['meter_id']} at {x['recorded_at'][:16].replace('T', ' ')}: {x['power_kw']} kW, severity {x['severity']}.")
        return "\n".join(lines)
    if any(w in q for w in ("save", "recommend", "reduce", "improve", "action")):
        return "\n".join(f"- [{r['priority']}] {r['title']}: {r['description']}" for r in c["recommendations"])
    if any(w in q for w in ("cost", "bill", "spend", "rupee", "expens")):
        return f"Over {c['period']['days']} days {c['facility']} used {k['total_energy_kwh']:,.0f} kWh, costing about Rs {k['cost_inr']:,.0f}."
    if any(w in q for w in ("carbon", "co2", "emission")):
        return f"Estimated carbon footprint: {k['carbon_tco2e']} tCO2e over {c['period']['days']} days."
    if any(w in q for w in ("peak", "demand", "power")):
        return f"Average power {k['average_power_kw']} kW, peak {k['peak_power_kw']} kW. Off-hours share of energy: {k['off_hours_share_pct']}%."
    return "Try asking: 'Why are there anomalies?', 'How can we save energy?', 'What is the cost?' or 'What is the peak demand?'"


def answer(question: str, context: dict) -> dict:
    errors = []
    for engine, fn in (("gemini", _ask_gemini), ("claude", _ask_claude), ("ollama", _ask_ollama)):
        text, err = fn(question, context)
        if text:
            return {"answer": text, "mode": engine}
        if err:
            errors.append(err)
    result = {"answer": _rules(question, context), "mode": "rules"}
    if errors:
        result["note"] = " | ".join(errors)
    return result
