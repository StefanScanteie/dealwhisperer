"""
Taegis Deal Whisperer — main Flask application.

Pipeline: Vivun → Taegis → (OSINT if prospect) → Claude → browser.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, render_template, request

from agents.vivun_agent import get_opportunity, is_existing_customer
from agents.taegis_agent import get_industry_intel, get_customer_telemetry
from agents.osint_agent import get_osint_intel
from agents.synthesizer import generate_brief

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("deal_whisperer")

app = Flask(__name__)
PORT = int(os.getenv("PORT", "5001"))


# ── helpers ─────────────────────────────────────────────────────────────────

def _api_status() -> dict:
    return {
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "vivun": bool(os.getenv("VIVUN_API_KEY")),
        "taegis": bool(os.getenv("TAEGIS_CLIENT_ID") and os.getenv("TAEGIS_CLIENT_SECRET")),
        "serper": bool(os.getenv("SERPER_API_KEY")),
    }


_SUPPORTED_LANGS = ("en", "ja", "zh", "th", "vi")


def _parse_language(body: dict) -> str:
    lang = (body.get("language") or "en").strip().lower()
    return lang if lang in _SUPPORTED_LANGS else "en"


def _fetch_taegis(opp: dict, is_customer: bool):
    """Fetch Taegis data — customer telemetry (with industry fallback) or industry intel."""
    region = opp.get("taegis_region")
    industry = opp.get("industry") or "General"
    if is_customer:
        tenant_id = opp.get("taegis_tenant_id") or "unknown"
        data = get_customer_telemetry(tenant_id, region=region)
        if data is None:
            log.info("Customer telemetry unavailable — falling back to industry intel.")
            data = get_industry_intel(industry, region=region)
        return data
    return get_industry_intel(industry, region=region)


def _no_access_list(
    taegis_data, osint_data, brief: dict, *, is_customer: bool,
) -> list[str]:
    na: list[str] = []
    if taegis_data is None:
        na.append("Taegis")
    if not is_customer and osint_data is None:
        na.append("OSINT")
    if brief.get("claude_no_access") or brief.get("error"):
        na.append("Claude")
    return na


# ── routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify(status="ok", apis=_api_status())


@app.route("/generate", methods=["POST"])
def generate():
    """Full pipeline: Vivun → Taegis → (OSINT if prospect) → synthesise."""
    body = request.get_json(silent=True) or {}
    opp_name = (body.get("opp_name") or "").strip()
    if not opp_name:
        return jsonify(error="opp_name is required"), 400

    log.info("Generating brief for: %s", opp_name)

    # 1 — Vivun
    opp = get_opportunity(opp_name)
    if opp is None:
        return jsonify(error="Opportunity not found (No Access: Vivun)"), 404

    # SE overrides from the UI (take precedence over Vivun data)
    override_tenant = (body.get("taegis_tenant_id") or "").strip()
    override_region = (body.get("taegis_region") or "").strip()
    if override_tenant:
        opp["taegis_tenant_id"] = override_tenant
        log.info("SE override: taegis_tenant_id = %s", override_tenant)
    if override_region:
        opp["taegis_region"] = override_region
        log.info("SE override: taegis_region = %s", override_region)

    is_customer = is_existing_customer(opp)
    log.info("Mode: %s | Stage: %s | Competitor: %s",
             "CUSTOMER" if is_customer else "PROSPECT",
             opp.get("stage", ""), opp.get("competitor", ""))

    # 2 — Taegis
    if is_customer and not opp.get("taegis_region"):
        log.warning("Customer tenant %s has no taegis_region — using default. "
                    "Set region in opportunity data for accuracy.", opp.get("taegis_tenant_id"))
    taegis_data = _fetch_taegis(opp, is_customer)

    # 3 — OSINT (prospect only)
    company_name = opp.get("company_name") or opp.get("name") or opp_name
    osint_data = None
    if not is_customer:
        osint_data = get_osint_intel(company_name, opp.get("industry") or "")

    # 4 — Synthesise
    language = _parse_language(body)
    brief = generate_brief(
        opp, taegis_data, osint_data,
        is_customer=is_customer,
        language=language,
    )
    brief["no_access_sources"] = _no_access_list(
        taegis_data, osint_data, brief, is_customer=is_customer,
    )

    log.info("Brief generated | Mood: %s | No-access: %s",
             brief.get("deal_mood", ""), brief["no_access_sources"] or "none")
    return jsonify(brief)


@app.route("/quick-brief", methods=["POST"])
def quick_brief():
    """Manual input — build a minimal opp, skip Taegis/OSINT, synthesise."""
    body = request.get_json(silent=True) or {}
    company = (body.get("company") or "").strip()
    if not company:
        return jsonify(error="company is required"), 400

    opp = {
        "id": "manual-001",
        "name": company,
        "company_name": company,
        "industry": (body.get("industry") or "").strip() or "General",
        "stage": (body.get("stage") or "").strip() or "Discovery",
        "deal_value": 0,
        "close_date": "",
        "competitor": (body.get("competitor") or "").strip(),
        "products_scoped": ["Taegis XDR", "Taegis MDR"],
        "taegis_tenant_id": (body.get("taegis_tenant_id") or "").strip() or None,
        "taegis_region": (body.get("taegis_region") or "").strip() or None,
        "account_executive": "",
        "se_notes": [{
            "date": "",
            "author": "SE",
            "note": f"Pain: {(body.get('pain') or '').strip()}\n{(body.get('notes') or '').strip()}",
        }],
        "technical_win_criteria": (body.get("pain") or "").strip(),
    }

    is_customer = is_existing_customer(opp)
    taegis_data = None
    if is_customer:
        log.info("Manual input with tenant %s (region %s) — fetching telemetry.",
                 opp["taegis_tenant_id"], opp.get("taegis_region") or "default")
        taegis_data = _fetch_taegis(opp, is_customer)

    language = _parse_language(body)
    brief = generate_brief(opp, taegis_data, None, is_customer=is_customer, language=language)
    brief["no_access_sources"] = _no_access_list(taegis_data, None, brief, is_customer=is_customer)
    return jsonify(brief)


# ── entry point ─────────────────────────────────────────────────────────────

def main():
    log.info("TAEGIS DEAL WHISPERER — http://localhost:%d", PORT)
    app.run(host="0.0.0.0", port=PORT, debug=False)


if __name__ == "__main__":
    main()
