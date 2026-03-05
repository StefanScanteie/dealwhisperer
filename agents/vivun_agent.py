"""Vivun API agent — fetch and normalise opportunity data.

When VIVUN_API_KEY is not set the agent looks for local sample data in
``data/sample_opportunities.json`` (ships with the repo for demos).
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger(__name__)

_SAMPLE_FILE = Path(__file__).resolve().parent.parent / "data" / "sample_opportunities.json"


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['VIVUN_API_KEY']}",
        "Accept": "application/json",
    }


def _normalize(raw: Dict[str, Any], notes: List[Dict[str, Any]]) -> Dict[str, Any]:
    account = raw.get("account") or {}
    return {
        "id": str(raw.get("id") or raw.get("uuid") or ""),
        "name": raw.get("name") or raw.get("opportunity_name") or "",
        "company_name": account.get("name") or raw.get("company_name") or "",
        "industry": account.get("industry") or raw.get("industry") or "",
        "stage": raw.get("stage") or raw.get("sales_stage") or "",
        "deal_value": int(raw.get("amount") or raw.get("deal_value") or 0),
        "close_date": raw.get("close_date") or raw.get("expected_close_date") or "",
        "competitor": raw.get("primary_competitor") or raw.get("competitor") or "",
        "products_scoped": raw.get("products_scoped") or raw.get("products") or ["Taegis XDR"],
        "taegis_tenant_id": raw.get("taegis_tenant_id") or raw.get("customer_tenant_id"),
        "account_executive": raw.get("account_executive") or raw.get("ae_name") or "",
        "se_notes": notes,
        "technical_win_criteria": raw.get("technical_win_criteria") or raw.get("tech_win_criteria") or "",
    }


def _load_sample(opp_name: str) -> Optional[Dict[str, Any]]:
    """Fuzzy-match a name against data/sample_opportunities.json."""
    if not _SAMPLE_FILE.is_file():
        return None
    try:
        items = json.loads(_SAMPLE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    needle = opp_name.lower()
    for item in items:
        if needle in (item.get("name") or "").lower() or needle in (item.get("company_name") or "").lower():
            log.info("Matched sample opportunity: %s", item.get("name"))
            return item
    return None


def get_opportunity(opp_name: str) -> Optional[Dict[str, Any]]:
    """
    Look up an opportunity by name.

    When VIVUN_API_KEY is set the real API is called.  Otherwise the agent
    falls back to ``data/sample_opportunities.json`` for demo purposes.
    Returns None only when nothing matches in either source.
    """
    api_key = os.getenv("VIVUN_API_KEY")
    if not api_key:
        sample = _load_sample(opp_name)
        if sample:
            log.info("Using sample data (VIVUN_API_KEY not set).")
            return sample
        log.warning("VIVUN_API_KEY not set and no sample match for '%s'.", opp_name)
        return None

    base = os.getenv("VIVUN_BASE_URL", "https://api.vivun.com/v1").rstrip("/")

    try:
        resp = requests.get(
            f"{base}/opportunities",
            headers=_headers(),
            params={"search": opp_name, "limit": 1},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("data") or resp.json().get("items") or []
        if not items:
            log.info("No opportunity found for '%s'.", opp_name)
            return None

        raw = items[0]
        opp_id = raw.get("id") or raw.get("uuid")

        notes_resp = requests.get(
            f"{base}/opportunities/{opp_id}/notes",
            headers=_headers(),
            timeout=10,
        )
        notes_resp.raise_for_status()
        raw_notes = notes_resp.json().get("data") or notes_resp.json().get("items") or []
        notes = [
            {
                "date": n.get("created_at") or n.get("date") or "",
                "author": n.get("author") or n.get("created_by") or "",
                "note": n.get("note") or n.get("body") or "",
            }
            for n in raw_notes
        ]

        return _normalize(raw, notes)
    except Exception as exc:
        log.warning("Vivun request failed: %s", exc)
        return None


def is_existing_customer(opp: Dict[str, Any]) -> bool:
    """True when the opportunity carries a Taegis tenant ID (existing customer)."""
    return bool(opp.get("taegis_tenant_id"))
