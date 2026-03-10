"""
Taegis XDR API agent — threat intel, MDR benchmarks, and tenant telemetry.

Auth and API are the same as documented for Taegis:
  - OAuth2 client credentials → /auth/api/v2/auth/token
  - GraphQL → {TAEGIS_BASE_URL}/graphql

CTPX (api.ctpx.secureworks.com = US1) supports:
  - Threat Intelligence API: threatLatestPublications, threatWatchlist, etc.
  - Alerts API: alertsServiceSearch with CQL (used for customer telemetry).
  It does NOT support the by-vertical aggregate queries (threatIntelByVertical,
  mdrBenchmarksByVertical) or tenant-level summary queries (tenantAlertSummary,
  coverageGaps, mdrActivity) — those live on standard api.taegis.secureworks.com.

Official references:
  https://docs.taegis.secureworks.com/apis/using_threat_intelligence_api/
  https://docs.taegis.secureworks.com/magic/magic_overview/
  https://github.com/secureworks/taegis-sdk-python
"""

import logging
import os
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger(__name__)

_DEFAULT_BASE = "https://api.taegis.secureworks.com"
_LOOKBACK_DAYS = 90

# Keywords used to filter CTU publications by industry
_INDUSTRY_KEYWORDS: Dict[str, List[str]] = {
    "Manufacturing": ["manufacturing", "industrial", "ics", "scada", "ot", "operational technology", "supply chain", "factory"],
    "Healthcare":    ["healthcare", "medical", "hospital", "hipaa", "pharma", "pharmaceutical", "health"],
    "Financial Services": ["financial", "banking", "fintech", "payment", "swift", "fraud"],
    "Retail":        ["retail", "ecommerce", "e-commerce", "pos", "point of sale"],
    "Government":    ["government", "federal", "public sector", "municipality", "nation-state"],
    "Technology":    ["technology", "software", "saas", "cloud", "msp", "managed service"],
    "Energy":        ["energy", "utilities", "oil", "gas", "electric", "critical infrastructure"],
}
_GENERIC_KEYWORDS = ["ransomware", "phishing", "malware", "threat actor", "apt", "vulnerability", "exploit", "initial access"]


# ── helpers ─────────────────────────────────────────────────────────────────

def _has_creds() -> bool:
    return bool(os.getenv("TAEGIS_CLIENT_ID") and os.getenv("TAEGIS_CLIENT_SECRET"))


def _get_token() -> tuple[str, str]:
    """Acquire a bearer token; returns (token, base_url)."""
    cid = os.getenv("TAEGIS_CLIENT_ID", "")
    sec = os.getenv("TAEGIS_CLIENT_SECRET", "")
    base = os.getenv("TAEGIS_BASE_URL", _DEFAULT_BASE).rstrip("/")
    if not (cid and sec):
        raise RuntimeError("Taegis credentials not configured")
    resp = requests.post(
        f"{base}/auth/api/v2/auth/token",
        json={"client_id": cid, "client_secret": sec, "grant_type": "client_credentials"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("access_token", ""), base


def _gql(query: str, variables: Dict[str, Any], token: str, base: str) -> Dict[str, Any]:
    """Execute a GraphQL query against the Taegis API."""
    resp = requests.post(
        f"{base}/graphql",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"query": query, "variables": variables},
        timeout=15,
    )
    if not resp.ok:
        try:
            body = resp.json()
            errors = body.get("errors") or body.get("error")
            log.warning("Taegis GraphQL %s: %s", resp.status_code, errors if errors is not None else body)
        except Exception:
            log.warning("Taegis GraphQL %s: %s", resp.status_code, (resp.text or "")[:500])
        resp.raise_for_status()
    return resp.json()


def _is_ctpx(base: str) -> bool:
    """CTPX (api.ctpx.secureworks.com) supports CTU TI API but not aggregate by-vertical queries."""
    return "ctpx" in base.lower()


def _industry_keywords(vertical: str) -> List[str]:
    """Return keyword list for a vertical, falling back to generic."""
    for name, kws in _INDUSTRY_KEYWORDS.items():
        if vertical.lower() in name.lower() or name.lower() in vertical.lower():
            return kws + _GENERIC_KEYWORDS
    return _GENERIC_KEYWORDS


def _score_publication(pub: Dict[str, Any], keywords: List[str]) -> int:
    """Return relevance score (higher = more relevant) for a CTU publication."""
    text = " ".join(filter(None, [
        pub.get("Name") or "",
        pub.get("Description") or "",
        pub.get("Category") or "",
    ])).lower()
    return sum(1 for kw in keywords if kw in text)


# ── GraphQL queries ──────────────────────────────────────────────────────────

_LATEST_PUBLICATIONS_QUERY = """
query ThreatLatestPublications($from: Int!, $size: Int!) {
  threatLatestPublications(from: $from, size: $size) {
    id Type Name Description Published Category TLP
  }
}
"""

_INDUSTRY_QUERY = """
query IndustryIntel($vertical: String!) {
  threatIntelByVertical(vertical: $vertical) {
    topThreatActors { name tactics recentActivity }
    avgMttdHours avgMttrHours
    topInitialAccessMethods
    recentIncidentTrends { category count30d trend }
  }
  mdrBenchmarksByVertical(vertical: $vertical) {
    avgAlertsPerMonth analystCoverageRate humanEscalationRate
    breachesPreventedPct similarCompaniesOnMdr
  }
}
"""

_TENANT_QUERY = """
query TenantTelemetry($tenantId: ID!, $lookbackDays: Int!) {
  tenantAlertSummary(tenantId: $tenantId, lookbackDays: $lookbackDays) {
    totalAlerts highSeverityAlerts avgMttdHours avgMttrHours
    topThreatCategories { name count severity }
  }
  coverageGaps(tenantId: $tenantId) { surface area status risk }
  mdrActivity(tenantId: $tenantId, lookbackDays: $lookbackDays) {
    investigationsOpened investigationsClosed humanEscalations
    afterHoursEvents criticalIncidentsStopped
  }
}
"""

_CTPX_ALERTS_QUERY = """
query AlertsSearch($in: SearchRequestInput!) {
  alertsServiceSearch(in: $in) {
    status
    alerts {
      total_results
      list {
        id
        metadata { severity title }
      }
    }
  }
}
"""


# ── CTPX real CTU threat intel ───────────────────────────────────────────────

def _get_ctpx_industry_intel(vertical: str, token: str, base: str) -> Dict[str, Any]:
    """
    Fetch real CTU threat publications from CTPX and filter by industry.
    Returns a normalized intel dict Claude can use to generate a rich brief.
    """
    keywords = _industry_keywords(vertical)

    # Fetch the latest 50 CTU publications
    raw = _gql(_LATEST_PUBLICATIONS_QUERY, {"from": 0, "size": 50}, token, base)
    pubs = (raw.get("data") or {}).get("threatLatestPublications") or []

    # Score and sort by relevance to the industry
    scored = sorted(
        [{"pub": p, "score": _score_publication(p, keywords)} for p in pubs],
        key=lambda x: x["score"],
        reverse=True,
    )

    # Top 5 relevant, or top 5 generic if none scored
    relevant = [x["pub"] for x in scored if x["score"] > 0][:5]
    if not relevant:
        relevant = [x["pub"] for x in scored][:5]
        log.info("No industry-specific CTU publications found for '%s'; using most recent.", vertical)
    else:
        log.info("Found %d relevant CTU publications for '%s'.", len(relevant), vertical)

    publications = [
        {
            "title": p.get("Name") or "",
            "description": (p.get("Description") or "")[:400],
            "category": p.get("Category") or "",
            "type": p.get("Type") or "",
            "published": p.get("Published") or "",
            "tlp": p.get("TLP") or "",
        }
        for p in relevant
    ]

    # Derive top categories from all publications (not just filtered)
    category_counts: Dict[str, int] = {}
    for p in pubs:
        cat = p.get("Category") or "Uncategorized"
        category_counts[cat] = category_counts.get(cat, 0) + 1
    top_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "vertical": vertical,
        "source": "Taegis CTU Threat Intelligence",
        "ctu_publications": publications,
        "total_publications_fetched": len(pubs),
        "top_threat_categories": [{"category": c, "count": n} for c, n in top_categories],
        "top_threat_actors": [],         # not available via CTU pubs endpoint
        "avg_mttd_hours": 0.0,
        "avg_mttr_hours": 0.0,
        "industry_avg_mttr_hours": 0.0,
        "top_initial_access_methods": [],
        "mdr_benchmarks": {},
        "ctpx_ctu_intel": True,
    }


# ── CTPX customer telemetry via alertsServiceSearch ──────────────────────────

def _get_ctpx_customer_telemetry(tenant_id: str, token: str, base: str) -> Dict[str, Any]:
    """
    Fetch real alert data from CTPX using alertsServiceSearch (CQL).
    Returns a telemetry dict shaped like the standard tenant query output.
    """
    raw = _gql(
        _CTPX_ALERTS_QUERY,
        {"in": {"cql_query": f"FROM alert EARLIEST=-{_LOOKBACK_DAYS}d", "offset": 0, "limit": 50}},
        token, base,
    )
    resp = (raw.get("data") or {}).get("alertsServiceSearch") or {}
    alerts_data = resp.get("alerts") or {}
    total = alerts_data.get("total_results") or 0
    alert_list = alerts_data.get("list") or []

    high_sev = sum(
        1 for a in alert_list
        if (a.get("metadata") or {}).get("severity", 0) >= 0.6
    )

    title_counts: Dict[str, int] = {}
    for a in alert_list:
        title = (a.get("metadata") or {}).get("title") or "Unknown"
        title_counts[title] = title_counts.get(title, 0) + 1
    top_categories = sorted(title_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    log.info(
        "CTPX alerts for tenant %s: %d total, %d high-severity (from %d sampled).",
        tenant_id, total, high_sev, len(alert_list),
    )

    return {
        "tenant_id": tenant_id,
        "lookback_days": _LOOKBACK_DAYS,
        "total_alerts": total,
        "high_severity_alerts": high_sev,
        "avg_mttd_hours": 0.0,
        "avg_mttr_hours": 0.0,
        "industry_avg_mttr_hours": 0.0,
        "top_threat_categories": [
            {"name": t, "count": c, "severity": "mixed"} for t, c in top_categories
        ],
        "coverage_gaps": [],
        "mdr_activity": {},
        "ctpx_alerts_data": True,
    }


# ── public API ───────────────────────────────────────────────────────────────

def get_industry_intel(vertical: str) -> Optional[Dict[str, Any]]:
    """
    Fetch threat intel for a vertical (prospect mode).

    - Standard Taegis: uses aggregate threatIntelByVertical + mdrBenchmarksByVertical.
    - CTPX: uses real CTU threatLatestPublications, filtered by industry keywords.

    Returns None when credentials are absent or requests fail.
    """
    if not _has_creds():
        log.warning("Taegis credentials not set — skipping industry intel.")
        return None
    try:
        token, base = _get_token()
        if _is_ctpx(base):
            log.info("CTPX detected — using CTU Threat Intelligence publications for '%s'.", vertical)
            return _get_ctpx_industry_intel(vertical, token, base)

        raw = _gql(_INDUSTRY_QUERY, {"vertical": vertical}, token, base)
        ti = (raw.get("data") or {}).get("threatIntelByVertical") or {}
        bm = (raw.get("data") or {}).get("mdrBenchmarksByVertical") or {}
        return {
            "vertical": vertical,
            "top_threat_actors": [
                {"name": a.get("name"), "tactics": a.get("tactics"), "recent_activity": a.get("recentActivity")}
                for a in (ti.get("topThreatActors") or [])
            ],
            "avg_mttd_hours": float(ti.get("avgMttdHours") or 0),
            "avg_mttr_hours": float(ti.get("avgMttrHours") or 0),
            "industry_avg_mttr_hours": float(bm.get("avgMttrHours") or ti.get("avgMttrHours") or 0),
            "top_initial_access_methods": ti.get("topInitialAccessMethods") or [],
            "recent_incident_trends": [
                {"category": t.get("category"), "count_30d": t.get("count30d") or 0, "trend": t.get("trend")}
                for t in (ti.get("recentIncidentTrends") or [])
            ],
            "mdr_benchmarks": {
                "avg_alerts_per_month": int(bm.get("avgAlertsPerMonth") or 0),
                "analyst_coverage_rate": float(bm.get("analystCoverageRate") or 0),
                "human_escalation_rate": float(bm.get("humanEscalationRate") or 0),
                "breaches_prevented_pct": float(bm.get("breachesPreventedPct") or 0),
                "similar_companies_on_mdr": int(bm.get("similarCompaniesOnMdr") or 0),
            },
        }
    except Exception as exc:
        log.warning("Taegis industry-intel request failed: %s", exc)
        return None


def get_customer_telemetry(tenant_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch alert summary, coverage gaps, and MDR activity for a tenant (customer mode).

    - Standard Taegis: uses tenantAlertSummary, coverageGaps, mdrActivity.
    - CTPX: uses alertsServiceSearch with CQL (those aggregate queries are unavailable).

    Returns None when credentials are absent or requests fail.
    """
    if not _has_creds():
        log.warning("Taegis credentials not set — skipping customer telemetry.")
        return None
    try:
        token, base = _get_token()
        if _is_ctpx(base):
            log.info("CTPX detected — using alertsServiceSearch for tenant %s.", tenant_id)
            return _get_ctpx_customer_telemetry(tenant_id, token, base)

        raw = _gql(_TENANT_QUERY, {"tenantId": tenant_id, "lookbackDays": _LOOKBACK_DAYS}, token, base)
        root = raw.get("data") or {}
        summary = root.get("tenantAlertSummary") or {}
        gaps = root.get("coverageGaps") or []
        mdr = root.get("mdrActivity") or {}
        return {
            "tenant_id": tenant_id,
            "lookback_days": _LOOKBACK_DAYS,
            "total_alerts": int(summary.get("totalAlerts") or 0),
            "high_severity_alerts": int(summary.get("highSeverityAlerts") or 0),
            "avg_mttd_hours": float(summary.get("avgMttdHours") or 0),
            "avg_mttr_hours": float(summary.get("avgMttrHours") or 0),
            "industry_avg_mttr_hours": float(summary.get("industryAvgMttrHours") or 0),
            "top_threat_categories": [
                {"name": c.get("name"), "count": int(c.get("count") or 0), "severity": c.get("severity")}
                for c in (summary.get("topThreatCategories") or [])
            ],
            "coverage_gaps": [
                {"surface": g.get("surface"), "area": g.get("area"), "status": g.get("status"), "risk": g.get("risk")}
                for g in gaps
            ],
            "mdr_activity": {
                "investigations_opened": int(mdr.get("investigationsOpened") or 0),
                "investigations_closed": int(mdr.get("investigationsClosed") or 0),
                "human_escalations": int(mdr.get("humanEscalations") or 0),
                "after_hours_events": int(mdr.get("afterHoursEvents") or 0),
                "critical_incidents_stopped": int(mdr.get("criticalIncidentsStopped") or 0),
            },
        }
    except Exception as exc:
        log.warning("Taegis customer-telemetry request failed: %s", exc)
        return None
