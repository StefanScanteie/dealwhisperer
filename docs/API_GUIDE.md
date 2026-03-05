# Taegis Deal Whisperer — API Integration Reference

Technical reference for each external API used by the agents.

---

## Vivun

- **Auth**: `Authorization: Bearer <VIVUN_API_KEY>`
- **Base URL**: `VIVUN_BASE_URL` (default `https://api.vivun.com/v1`)
- **Endpoints**:
  - `GET /opportunities?search=<name>&limit=1` — find opportunity by name.
  - `GET /opportunities/<id>/notes` — SE notes for that opportunity.
- **Key fields**: id, name, account.name (company), stage, amount, close_date, primary_competitor, products_scoped, taegis_tenant_id (if customer), account_executive, technical_win_criteria. Notes normalized to `{date, author, note}`.
- **Fallback**: When `VIVUN_API_KEY` is not set, the agent loads from `data/sample_opportunities.json` for demo purposes. If the key is set but the API call fails, returns `None` (No Access).

---

## Taegis (Secureworks XDR)

Deal Whisperer uses the same authentication and GraphQL API as the official Taegis documentation. The same API credentials (from Taegis XDR → Settings → API Credentials) work for [Taegis Magic](https://docs.taegis.secureworks.com/magic/magic_overview/) and this app.

- **Official documentation**
  - [Taegis Magic Jupyter Integration](https://docs.taegis.secureworks.com/magic/magic_overview/) — overview, same credentials.
  - [Taegis Magic on GitHub](https://github.com/secureworks/taegis-magic) — CLI/Jupyter; `taegis configure` uses the same API.
  - [Taegis XDR API Guides](https://docs.taegis.secureworks.com/) → API Guides (GraphQL, authentication).
  - [Threat Intelligence API](https://docs.taegis.secureworks.com/apis/using_threat_intelligence_api/).
- **Auth**: OAuth2 client credentials.
  - `POST {TAEGIS_BASE_URL}/auth/api/v2/auth/token`
  - Body: `{ "client_id", "client_secret", "grant_type": "client_credentials" }`
  - Response: `{ "access_token" }`
- **API**: GraphQL at `{TAEGIS_BASE_URL}/graphql`, header `Authorization: Bearer <access_token>`.
- **Standard Taegis queries** (api.taegis.secureworks.com):
  - **Prospect**: `threatIntelByVertical(vertical)`, `mdrBenchmarksByVertical(vertical)` — top threat actors, MTTD/MTTR, initial access methods, incident trends, benchmarks.
  - **Customer**: `tenantAlertSummary(tenantId, lookbackDays)`, `coverageGaps(tenantId)`, `mdrActivity(tenantId, lookbackDays)` — alerts, coverage gaps, investigations (90-day lookback).
- **CTPX** (api.ctpx.secureworks.com): The by-vertical aggregate queries are not available. Instead, the agent fetches `threatLatestPublications(from, size)` to get real CTU threat intelligence publications, filters them by industry keywords, and returns the top 5 most relevant. Customer telemetry returns `None` on CTPX.
- **Error handling**: On failure or missing credentials, returns `None` (No Access).

---

## Serper (OSINT)

- **Auth**: Header `X-API-KEY: <SERPER_API_KEY>`
- **Endpoints**:
  - `POST https://google.serper.dev/search` — job postings search (company + security roles, LinkedIn/Indeed).
  - `POST https://google.serper.dev/news` — cybersecurity news (company/industry + breach/CISO, current and previous year).
- **Key fields**: Snippets from organic/news results used to detect security tools, hiring signals, urgency triggers, and conversation hooks.
- **Error handling**: If `SERPER_API_KEY` is missing or the API fails, returns `None` (No Access).

---

## Anthropic (Claude)

- **Auth**: `ANTHROPIC_API_KEY` (API key from console.anthropic.com).
- **Usage**: `messages.create(model="claude-sonnet-4-20250514", max_tokens=4096, system=..., messages=[...])`. Response is parsed as JSON; markdown code fences are stripped before parsing. A `_normalize_claude_brief()` function maps camelCase to snake_case and enforces the exact data shapes the UI expects.
- **Prompts**: The instruction includes an explicit `output_schema` listing every key and its expected type. When the opportunity includes `edr_landscape`, `business_challenges`, or `company_profile`, the prompt instructs Claude to use them. When Taegis CTPX provides real CTU publications, Claude is told to reference specific threat actors and categories.
- **Error handling**: If the key is missing or the call fails, the synthesizer returns a minimal brief with "No Access" in AI-generated fields. On JSON parse errors, the same minimal brief is used.
