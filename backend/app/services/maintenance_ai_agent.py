
import json

from app.services import ai_agent


SYSTEM = (
    "You are the Maintenance AI Agent of an enterprise facility-operations platform. "
    "Answer only using the supplied maintenance JSON data. "
    "Explain equipment health, risk levels, predictive alerts, telemetry freshness, "
    "maintenance schedules and work orders. "
    "Never invent sensor readings or claim a failure is certain. "
    "Give concise answers with specific asset IDs and practical actions. "
    "If the data does not contain the answer, say so."
)


def build_context(analysis: dict) -> dict:
    return {
        "facility_id": analysis.get("facility_id"),
        "total_assets": analysis.get("total_assets"),
        "analyzed_assets": analysis.get("analyzed_assets"),
        "total_alerts": analysis.get("total_alerts"),
        "assets": analysis.get("assets", []),
        "alerts": analysis.get("alerts", []),
    }


def answer(question: str, context: dict) -> dict:
    # Reuse the existing provider engines, but supply a maintenance-specific prompt.
    prompt = (
        f"Maintenance facility data (JSON):\n"
        f"{json.dumps(context, default=str)}\n\n"
        f"Question: {question}"
    )

    original_prompt = ai_agent._prompt
    original_system = ai_agent.SYSTEM

    try:
        ai_agent._prompt = lambda q, c: prompt
        ai_agent.SYSTEM = SYSTEM
        return ai_agent.answer(question, context)
    finally:
        ai_agent._prompt = original_prompt
        ai_agent.SYSTEM = original_system
