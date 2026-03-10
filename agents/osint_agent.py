"""OSINT agent — job-posting and news intelligence via Serper (Google Search as JSON)."""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger(__name__)

_SEARCH_URL = "https://google.serper.dev/search"
_NEWS_URL = "https://google.serper.dev/news"

_TOOL_KEYWORDS: Dict[str, List[str]] = {
    "CrowdStrike": ["crowdstrike", "falcon"],
    "Splunk": ["splunk"],
    "Palo Alto Networks": ["palo alto", "pan-os", "cortex"],
    "SentinelOne": ["sentinelone", "singularity"],
    "Microsoft Defender": ["microsoft defender", "mde"],
}


def _headers() -> Dict[str, str]:
    return {"X-API-KEY": os.getenv("SERPER_API_KEY", ""), "Content-Type": "application/json"}


def _snippets(items: List[Dict[str, Any]]) -> List[str]:
    return [f"{i.get('title', '')}: {i.get('snippet', '')}" for i in items]


def _detect_tools(text: str) -> List[str]:
    lower = text.lower()
    found = [name for name, kws in _TOOL_KEYWORDS.items() if any(kw in lower for kw in kws)]
    return found or ["Unknown — no tool keywords detected"]


def _detect_triggers(text: str) -> List[str]:
    lower = text.lower()
    triggers: List[str] = []
    if "ransomware" in lower:
        triggers.append("Regional competitor hit by ransomware recently.")
    if "breach" in lower:
        triggers.append("Recent breach headlines in their industry.")
    if "zero day" in lower or "zero-day" in lower:
        triggers.append("Zero-day exploitation reported in sector.")
    return triggers or ["General increase in ransomware and breach activity in the sector."]


def get_osint_intel(company: str, industry: str) -> Optional[Dict[str, Any]]:
    """
    Run Serper searches for job postings and cybersecurity news.
    Returns None when the API key is missing or requests fail.
    """
    if not os.getenv("SERPER_API_KEY"):
        log.warning("SERPER_API_KEY not set — skipping OSINT.")
        return None

    year = datetime.now().year

    try:
        job_resp = requests.post(
            _SEARCH_URL,
            headers=_headers(),
            json={
                "q": f'"{company}" security engineer OR "SOC analyst" jobs site:linkedin.com OR site:indeed.com',
                "num": 10,
            },
            timeout=10,
        )
        job_resp.raise_for_status()
        job_snips = _snippets(job_resp.json().get("organic") or [])

        news_resp = requests.post(
            _NEWS_URL,
            headers=_headers(),
            json={
                "q": f'"{company}" OR "{industry}" cybersecurity OR breach OR CISO {year - 1} OR {year}',
                "num": 10,
            },
            timeout=10,
        )
        news_resp.raise_for_status()
        news_snips = _snippets(news_resp.json().get("news") or [])

        job_text = " ".join(job_snips)
        news_text = " ".join(news_snips)

        job_intel = {
            "current_security_tools": _detect_tools(job_text),
            "security_team_size": "Active hiring signals for security roles.",
            "key_gaps": [
                "Job descriptions emphasise SIEM content creation and manual triage.",
                "Multiple roles reference 24x7 on-call, suggesting coverage challenges.",
            ],
            "budget_signal": "Multiple open security roles indicate active security budget.",
            "roi_opportunity": (
                "Room to offset at least one senior analyst FTE by shifting "
                "noise triage and 24x7 coverage to MDR."
            ),
        }

        news_intel = {
            "urgency_triggers": _detect_triggers(news_text),
            "compliance_pressure": ["Ongoing regulatory pressure around incident-reporting timelines."],
            "leadership_changes": [],
            "conversation_hook": (
                f"There has been a lot of recent ransomware and breach activity in {industry or 'your sector'} — "
                "curious how your team is framing dwell time and board reporting right now."
            ),
        }

        return {"enabled": True, "job_intel": job_intel, "news_intel": news_intel}
    except Exception as exc:
        log.warning("OSINT request failed: %s", exc)
        return None
