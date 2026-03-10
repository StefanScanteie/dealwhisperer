"""Synthesizer — combine opportunity + data-source results into a battle-card brief via Claude."""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import anthropic

log = logging.getLogger(__name__)

_NA = "No Access"
_MODEL = "claude-sonnet-4-20250514"
_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt"


def _load_system_prompt() -> str:
    """Load the SE system prompt from the external file next to this module."""
    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


_SYSTEM_PROMPT = _load_system_prompt()

BRIEF_KEYS = [
    "company", "deal_stage", "deal_mood", "deal_mood_reason", "deal_snapshot",
    "roi_hook", "objections", "demo_flow", "osint_insight", "conversation_hook",
    "open_action_items", "call_objectives", "expansion_opportunity", "qbr_headline_stats",
    "competitive_angle", "industry_proof_point", "renewal_defense",
    "discovery_questions", "technical_win_map", "key_stakeholders",
    "risk_factors", "follow_up_email",
]

_STRING_FIELDS = [
    "company", "deal_stage", "deal_mood", "deal_mood_reason", "deal_snapshot",
    "roi_hook", "osint_insight", "conversation_hook", "competitive_angle",
    "industry_proof_point", "renewal_defense", "follow_up_email",
]

_CAMEL_TO_SNAKE = {
    "dealSnapshot": "deal_snapshot",
    "roiHook": "roi_hook",
    "dealMood": "deal_mood",
    "dealStage": "deal_stage",
    "openActionItems": "open_action_items",
    "demoFlow": "demo_flow",
    "osintInsight": "osint_insight",
    "conversationHook": "conversation_hook",
    "expansionOpportunity": "expansion_opportunity",
    "qbrHeadlineStats": "qbr_headline_stats",
    "competitiveAngle": "competitive_angle",
    "industryProofPoint": "industry_proof_point",
    "renewalDefense": "renewal_defense",
    "callObjectives": "call_objectives",
    "dealMoodReason": "deal_mood_reason",
    "discoveryQuestions": "discovery_questions",
    "technicalWinMap": "technical_win_map",
    "keyStakeholders": "key_stakeholders",
    "riskFactors": "risk_factors",
    "followUpEmail": "follow_up_email",
}


# ── helpers ─────────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _se_name() -> str:
    return os.getenv("SE_NAME", "Sophos SE")


def _base_brief() -> Dict[str, Any]:
    return {"generated_at": _now(), "se_name": _se_name()}


def _strip_fences(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```", 1)[1]
        if "```" in s:
            s = s.rsplit("```", 1)[0]
        return s.strip()
    return s


def _extract_text(message: Any) -> str:
    parts = []
    for block in message.content:
        txt = (block.get("text") if isinstance(block, dict)
               else getattr(block, "text", None))
        if txt:
            parts.append(txt)
    return "".join(parts)


def _normalize_objections(raw: list) -> list[dict]:
    return [
        {
            "objection": o.get("objection") or o.get("q") or "",
            "rebuttal": o.get("rebuttal") or o.get("a") or "",
        }
        for o in raw
        if isinstance(o, dict)
    ]


def _normalize_demo_flow(raw: list) -> list[dict]:
    return [
        {
            "screen": d.get("screen") or d.get("step") or "",
            "duration_mins": int(d.get("duration_mins") or d.get("durationMins") or 0),
            "talking_point": d.get("talking_point") or d.get("talkingPoint") or "",
        }
        for d in raw
        if isinstance(d, dict)
    ]


def _normalize_expansion(raw: Any) -> dict:
    if isinstance(raw, dict):
        return {
            "surface": raw.get("surface") or "",
            "risk": raw.get("risk") or "",
            "product": raw.get("product") or "",
        }
    return {"surface": "", "risk": "", "product": ""}


def _normalize_technical_win_map(raw: list) -> list[dict]:
    return [
        {
            "criterion": t.get("criterion") or "",
            "taegis_answer": t.get("taegis_answer") or t.get("taegisAnswer") or "",
        }
        for t in raw
        if isinstance(t, dict)
    ]


def _normalize_key_stakeholders(raw: list) -> list[dict]:
    return [
        {
            "name": s.get("name") or "",
            "location": s.get("location") or "",
            "role_or_relevance": (
                s.get("role_or_relevance")
                or s.get("roleOrRelevance")
                or s.get("role") or ""
            ),
        }
        for s in raw
        if isinstance(s, dict)
    ]


def _normalize_risk_factors(raw: list) -> list[dict]:
    return [
        {
            "risk": r.get("risk") or "",
            "mitigation": r.get("mitigation") or "",
        }
        for r in raw
        if isinstance(r, dict)
    ]


def _normalize_claude_brief(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure Claude response has the exact keys and shapes the UI expects."""
    out: Dict[str, Any] = {}
    for key, val in data.items():
        snake = _CAMEL_TO_SNAKE.get(key, key) if isinstance(key, str) else key
        out[snake] = val

    out["objections"] = _normalize_objections(out.get("objections") or [])
    out["demo_flow"] = _normalize_demo_flow(out.get("demo_flow") or [])
    out["technical_win_map"] = _normalize_technical_win_map(out.get("technical_win_map") or [])
    out["key_stakeholders"] = _normalize_key_stakeholders(out.get("key_stakeholders") or [])
    out["risk_factors"] = _normalize_risk_factors(out.get("risk_factors") or [])
    out["open_action_items"] = [str(x) for x in (out.get("open_action_items") or []) if x]
    out["discovery_questions"] = [str(x) for x in (out.get("discovery_questions") or []) if x]
    out["expansion_opportunity"] = _normalize_expansion(out.get("expansion_opportunity"))
    out["qbr_headline_stats"] = [str(x) for x in (out.get("qbr_headline_stats") or []) if x]

    for key in _STRING_FIELDS:
        v = out.get(key)
        if v is None:
            out[key] = ""
        elif not isinstance(v, str):
            out[key] = str(v)

    if not isinstance(out.get("call_objectives"), list):
        out["call_objectives"] = []

    return out


# ── Claude call ─────────────────────────────────────────────────────────────


def _call_claude(payload: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=_MODEL,
        max_tokens=6144,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(payload)}],
    )
    raw = _strip_fences(_extract_text(message))
    data = json.loads(raw)
    if isinstance(data, dict):
        data.setdefault("generated_at", _now())
        data.setdefault("se_name", _se_name())
    return data


# ── empty defaults for new fields ──────────────────────────────────────────

_EMPTY_NEW_FIELDS: Dict[str, Any] = {
    "discovery_questions": [],
    "technical_win_map": [],
    "key_stakeholders": [],
    "risk_factors": [],
    "follow_up_email": "",
    "competitive_angle": "",
    "industry_proof_point": "",
}


# ── minimal (no-Claude) briefs ─────────────────────────────────────────────


def _common_fields(opp: Dict[str, Any]) -> Dict[str, str]:
    return {
        "company": opp.get("company_name") or opp.get("name") or "—",
        "stage": opp.get("stage") or "",
        "competitor": opp.get("competitor") or "",
        "industry": opp.get("industry") or "",
    }


def _customer_brief(
    opp: Dict[str, Any],
    taegis: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    f = _common_fields(opp)
    brief = _base_brief()
    brief["mode"] = "customer"
    brief["company"] = f["company"]
    brief["deal_stage"] = f["stage"] or "Renewal / Expansion"
    brief["deal_mood"] = _NA
    brief["deal_mood_reason"] = _NA

    if taegis:
        total = taegis.get("total_alerts", 0)
        high = taegis.get("high_severity_alerts", 0)
        mttr = taegis.get("avg_mttr_hours", 0)
        ind_mttr = taegis.get("industry_avg_mttr_hours", 72)
        gaps = taegis.get("coverage_gaps") or []
        gap = gaps[0] if gaps else {}

        brief["deal_snapshot"] = (
            f"In the last 90 days Taegis processed ~{total} alerts for {f['company']}, "
            f"including {high} high-severity. MTTR ~{mttr:.1f}h."
        )
        brief["roi_hook"] = f"MTTR ~{mttr:.1f}h vs industry ~{ind_mttr:.1f}h."
        brief["expansion_opportunity"] = {
            "surface": gap.get("surface") or _NA,
            "risk": gap.get("risk") or _NA,
            "product": "Taegis MDR + integrations",
        }
        brief["qbr_headline_stats"] = [
            f"{total} alerts triaged (90d).",
            f"{high} high-severity handled.",
            f"MTTR ~{mttr:.1f}h.",
        ]
    else:
        brief["deal_snapshot"] = _NA
        brief["roi_hook"] = _NA
        brief["expansion_opportunity"] = {"surface": _NA, "risk": _NA, "product": _NA}
        brief["qbr_headline_stats"] = []

    brief.update({
        "call_objectives": [],
        "objections": [],
        "open_action_items": [],
        "demo_flow": [],
        "renewal_defense": _NA,
        **_EMPTY_NEW_FIELDS,
    })
    return brief


def _prospect_brief(
    opp: Dict[str, Any],
    taegis: Optional[Dict[str, Any]],
    osint: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    f = _common_fields(opp)
    ji = (osint or {}).get("job_intel") or {}
    ni = (osint or {}).get("news_intel") or {}

    brief = _base_brief()
    brief["mode"] = "prospect"
    brief["company"] = f["company"]
    brief["deal_stage"] = f["stage"] or "Discovery"
    brief["deal_mood"] = _NA
    brief["deal_mood_reason"] = _NA

    has_context = any([f["company"], f["stage"], f["competitor"]])
    brief["deal_snapshot"] = (
        f"{f['company']} — {f['stage'] or 'Discovery'}. Competitor: {f['competitor'] or '—'}."
        if has_context else _NA
    )
    brief["roi_hook"] = ji.get("roi_opportunity") or _NA
    brief["osint_insight"] = ji.get("roi_opportunity") or _NA
    brief["conversation_hook"] = ni.get("conversation_hook") or _NA
    brief["competitive_angle"] = _NA
    brief["industry_proof_point"] = _NA if not taegis else "See Taegis benchmarks."
    brief.update({
        "call_objectives": [],
        "objections": [],
        "open_action_items": [],
        "demo_flow": [],
        **_EMPTY_NEW_FIELDS,
    })
    return brief


# ── payload construction ───────────────────────────────────────────────────


def _build_output_schema(is_customer: bool) -> Dict[str, str]:
    schema = {
        "company": "string (company name)",
        "deal_stage": "string",
        "deal_mood": "string (short, e.g. Cautiously optimistic)",
        "deal_mood_reason": "string (1 sentence explaining the mood)",
        "deal_snapshot": (
            "string (2-3 sentences on deal context, reference specific pain "
            "points from se_notes and business_challenges if available)"
        ),
        "roi_hook": "string (one compelling ROI sentence, use real numbers where available)",
        "competitive_angle": (
            "string (1-2 sentences on why we beat the incumbent, reference "
            "specific EDR tools from edr_landscape if available)"
        ),
        "industry_proof_point": "string (a relevant third-party proof point or stat for this industry)",
        "objections": (
            'array of { "objection": "...", "rebuttal": "..." } '
            "(at least 3, tailored to the specific competitor and edr_landscape)"
        ),
        "demo_flow": (
            'array of { "screen": "...", "duration_mins": number, "talking_point": "..." } '
            "(3-5 steps, relevant to the deal stage and technical_win_criteria)"
        ),
        "osint_insight": "string (one key insight from OSINT about the company or industry)",
        "conversation_hook": (
            "string (an opening question or statement that addresses the "
            "biggest pain from se_notes)"
        ),
        "open_action_items": "array of strings (concrete next steps for this specific deal)",
        "call_objectives": "array of strings (what the SE must achieve in this call)",
        "discovery_questions": (
            "array of strings (3-5 tailored questions the SE should ask on the call, "
            "based on gaps in the SE notes and deal stage)"
        ),
        "technical_win_map": (
            'array of { "criterion": "...", "taegis_answer": "..." } '
            "(map each item from technical_win_criteria to a specific Taegis capability)"
        ),
        "key_stakeholders": (
            'array of { "name": "...", "location": "...", "role_or_relevance": "..." } '
            "(extract from edr_landscape contacts; note their relevance to the deal)"
        ),
        "risk_factors": (
            'array of { "risk": "...", "mitigation": "..." } '
            "(2-4 deal risks inferred from SE notes, with suggested mitigations)"
        ),
        "follow_up_email": (
            "string (a short 3-5 sentence follow-up email draft the SE can send after the call, "
            "referencing key pain points and proposed next steps)"
        ),
    }
    if is_customer:
        schema["expansion_opportunity"] = '{ "surface": "...", "risk": "...", "product": "..." }'
        schema["qbr_headline_stats"] = "array of strings (3-5 stats)"
        schema["renewal_defense"] = "string"
    return schema


def _build_instruction(
    output_schema: Dict[str, str],
    edr_landscape: list,
    taegis_context: Dict[str, Any],
    language: str = "en",
) -> str:
    parts = [
        "Return ONLY a single JSON object. No markdown, no code fence, no explanation. "
        "Use exactly these keys (snake_case): " + ", ".join(output_schema.keys()) + ". "
        "Fill every key; use empty string or empty array if not applicable. "
        "objections: array of objects with keys objection and rebuttal. "
        "demo_flow: array of objects with keys screen, duration_mins, talking_point. "
        "technical_win_map: array of objects with keys criterion and taegis_answer. "
        "key_stakeholders: array of objects with keys name, location, role_or_relevance. "
        "risk_factors: array of objects with keys risk and mitigation. "
        "Use the se_notes, business_challenges, edr_landscape, company_profile, and "
        "technical_win_criteria fields in opp to make every section specific — avoid generic advice."
    ]
    if language == "ja":
        parts.append(
            "Write all string values in this JSON in Japanese (e.g. deal_snapshot, roi_hook, "
            "objections, demo_flow talking_points, conversation_hook, follow_up_email, etc.)."
        )
    else:
        parts.append("Write all string values in this JSON in English.")

    if edr_landscape:
        tools = ", ".join(sorted({e.get("edr", "") for e in edr_landscape if e.get("edr")}))
        contacts_count = sum(len(e.get("contacts") or []) for e in edr_landscape)
        parts.append(
            f"The customer runs {len(edr_landscape)} different endpoint security tools "
            f"across their locations ({tools}), with {contacts_count} known contacts. "
            "Use this fragmented EDR landscape as a core pain point and differentiation angle. "
            "Extract contacts into key_stakeholders with their location and inferred relevance."
        )

    ctu_pubs = taegis_context.get("ctu_publications") or []
    if ctu_pubs:
        vertical = taegis_context.get("vertical", "industry")
        parts.append(
            "The taegis_data contains real CTU (Counter Threat Unit) threat intelligence "
            f"publications from Secureworks, filtered for the {vertical} sector. "
            "Reference these publications specifically when building the industry_proof_point, "
            "conversation_hook, and objection rebuttals — use real threat actor names or threat "
            "categories from the publications to make the brief concrete and credible."
        )

    return " ".join(parts)


# ── public entry point ──────────────────────────────────────────────────────


def generate_brief(
    opp: Dict[str, Any],
    taegis_data: Optional[Dict[str, Any]],
    osint_data: Optional[Dict[str, Any]] = None,
    *,
    is_customer: bool = False,
    language: str = "en",
) -> Dict[str, Any]:
    """
    Produce a battle-card brief.  Uses Claude when ANTHROPIC_API_KEY is
    available; falls back to a deterministic minimal brief otherwise.
    language: "en" or "ja" — all narrative string fields in the brief are in that language.
    """
    if language not in ("en", "ja"):
        language = "en"

    if not os.getenv("ANTHROPIC_API_KEY"):
        brief = (
            _customer_brief(opp, taegis_data)
            if is_customer
            else _prospect_brief(opp, taegis_data, osint_data)
        )
        brief.update(error=False, claude_no_access=True)
        return brief

    output_schema = _build_output_schema(is_customer)
    taegis_context = taegis_data or {}
    edr_landscape = (opp or {}).get("edr_landscape") or []
    instruction = _build_instruction(
        output_schema, edr_landscape, taegis_context, language=language
    )

    payload = {
        "instruction": instruction,
        "output_schema": output_schema,
        "mode": "customer" if is_customer else "prospect",
        "output_language": language,
        "opp": opp,
        "taegis_data": taegis_context,
    }
    if not is_customer:
        payload["osint_data"] = osint_data or {}

    try:
        data = _call_claude(payload)
        data = _normalize_claude_brief(data)
        data.setdefault("mode", payload["mode"])
        data.setdefault("error", False)
        return data
    except Exception as exc:
        log.warning("Claude synthesis failed — falling back to minimal brief: %s", exc)
        brief = (
            _customer_brief(opp, taegis_data)
            if is_customer
            else _prospect_brief(opp, taegis_data, osint_data)
        )
        brief["error"] = True
        return brief
