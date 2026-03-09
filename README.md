# Taegis Deal Whisperer

AI-powered pre-call battle card generator for Sales Engineers. Combines opportunity data from Vivun, threat intelligence from the Taegis XDR API, and OSINT via Serper, then synthesizes a personalized brief with Claude AI — all running locally on macOS.

## What it does

1. **Pulls opportunity data** from Vivun (company profile, deal stage, competitor, SE notes, EDR landscape, technical win criteria). Falls back to local sample data (`data/sample_opportunities.json`) when `VIVUN_API_KEY` is not set.
2. **Fetches Taegis threat intelligence** — industry-level CTU publications for prospects (including CTPX-specific `threatLatestPublications`); customer telemetry and coverage gaps for existing Taegis customers. Uses the same [Taegis XDR API credentials](https://docs.taegis.secureworks.com/magic/magic_overview/) as Taegis Magic.
3. **Runs OSINT** (prospects only) via Serper — job postings and news to infer security tools in use, hiring signals, and conversation starters.
4. **Synthesizes a battle card** with Claude, driven by a comprehensive SE knowledge base that includes:
   - **Taegis platform knowledge** — XDR (open platform, 400+ integrations, CTU intel), MDR (24/7 SOC, 1-hour MTTC SLA), and the Secureworks-to-Sophos acquisition narrative.
   - **Competitive intelligence** — win angles and objection rebuttals for CrowdStrike, SentinelOne, Microsoft Defender/Sentinel, Palo Alto Cortex/XSIAM, and Splunk SIEM.
   - **Industry threat context** — sector-specific attack patterns, compliance requirements, and proof points for Healthcare, Financial Services, Manufacturing/OT, and Technology.
   - **ROI framework** — breach cost avoidance, headcount replacement math, and anonymized Taegis MDR benchmarks (MTTD, MTTR, containment rates).
   - **SE behavioral rules** — deal-stage matching, competitor-specific rebuttals, OSINT hook prioritization, customer-mode telemetry requirements, and expansion priority ordering.
5. **Displays the brief in the browser** with a single-click **Export PDF** (browser print dialog → "Save as PDF", no plugins needed).

## Quick start

```bash
git clone <repo-url> && cd DealWisperer
cp .env.example .env        # edit .env and add your API keys (see SETUP.md)
pip3 install -r requirements.txt
bash run.sh                  # opens http://localhost:5001
```

Enter the **opportunity name** (e.g. `Smiths Cogwheels`); the app looks it up in Vivun and generates the brief. Use the **Manual input** tab when the deal is not yet in Vivun.

### Demo mode (no API keys)

With only `ANTHROPIC_API_KEY` set and all other keys blank, the app uses the bundled sample opportunity (`[TCU] Smiths Cogwheels Inc`) and still generates a full brief via Claude. Set `VIVUN_API_KEY=` (empty) in `.env` to activate the sample data fallback.

## No Access behavior

When an API cannot be reached (missing credentials or request failure), that step is **skipped** and the pipeline continues with the data it has. The UI shows a **No access** banner listing the skipped sources.

| Source | Behavior when unavailable |
|--------|---------------------------|
| Vivun  | Falls back to `data/sample_opportunities.json`; if no match, returns 404 |
| Taegis | Skipped; brief still generated without threat intel |
| OSINT  | Skipped; brief still generated without job/news intel |
| Claude | Falls back to a deterministic minimal brief |

## Two modes

|  | **Prospect** | **Customer** |
|--|--------------|--------------|
| **Data sources** | Vivun + Taegis industry intel + OSINT | Vivun + Taegis customer telemetry |
| **Brief sections** | Competitive angle, ROI hook, demo flow, conversation hook, objections | QBR stats, coverage gaps, renewal defense, expansion opportunity |
| **AI behavior** | Deal-stage-aware competitive positioning, OSINT-driven conversation hooks, numbered ROI claims | Real telemetry stats (not benchmarks), expansion priority ordering by risk, renewal defense narrative |

Mode is **auto-detected**: if the opportunity has a `taegis_tenant_id`, the app uses **customer** mode; otherwise **prospect**.

## Brief output sections

Every generated brief includes these sections (sections auto-hide when empty):

| Section | Description |
|---------|-------------|
| **Deal snapshot** | 2-3 sentence summary of the deal context, referencing SE notes and business challenges |
| **ROI hook** | One compelling sentence with real numbers — breach cost, headcount replacement, MTTR delta |
| **Competitive angle** | Why Taegis beats the named incumbent, referencing the specific EDR tools in the landscape |
| **Industry proof point** | Third-party stat or CTU publication relevant to the prospect's industry |
| **Objections & rebuttals** | 3+ objection/rebuttal pairs tailored to the specific competitor |
| **Technical win criteria map** | Each item from `technical_win_criteria` mapped to a specific Taegis capability |
| **Demo flow** | 3-5 step demo plan with screen names, durations, and talking points |
| **OSINT & conversation hook** | OSINT-driven insight and an opening statement for the call |
| **Key stakeholders** | Contacts extracted from `edr_landscape` with location and inferred relevance |
| **Risk factors & mitigations** | 2-4 deal risks from SE notes with concrete mitigation strategies |
| **Call objectives** | What the SE must achieve on this call |
| **Discovery questions** | 3-5 tailored questions based on gaps in existing SE notes |
| **Open action items** | Concrete next steps for the deal |
| **Follow-up email draft** | A short post-call email the SE can send, referencing key pain points |
| **Expansion opportunity** | *(customer only)* — surface, risk, and recommended Sophos product |
| **Renewal defense** | *(customer only)* — narrative for defending the renewal |
| **QBR headline stats** | *(customer only)* — 3-5 stats from real telemetry |

## AI knowledge base

The synthesizer is powered by a comprehensive system prompt (`agents/system_prompt.txt`) that encodes domain expertise across six areas:

| Area | What it covers |
|------|----------------|
| **Taegis platform** | XDR architecture, MDR SLAs, CTU intel heritage, Sophos integration points |
| **Secureworks → Sophos** | Acquisition messaging, continuity for existing customers, combined portfolio value |
| **Competitive intel** | CrowdStrike, SentinelOne, Microsoft, Palo Alto, Splunk — specific win angles and objection rebuttals |
| **Industry threats** | Healthcare, Financial Services, Manufacturing/OT, Technology — attack patterns, compliance, proof points |
| **ROI framework** | Breach cost avoidance ($4.88M avg), headcount replacement (2-4 FTE), Taegis MTTD/MTTR benchmarks |
| **SE behavioral rules** | 12 rules: deal-stage matching, use numbers, reference named competitor, OSINT hooks, customer-mode telemetry, expansion priorities, migration angle, discovery questions, technical win mapping, stakeholder extraction, risk analysis, follow-up email drafting |

The prompt is stored as a plain-text file so it can be reviewed, versioned, and updated independently of the Python code.

## Architecture

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│   Vivun     │   │   Taegis    │   │   Serper    │
│   (opp)     │   │ (threat     │   │   (OSINT)   │
│             │   │      intel) │   │             │
└──────┬──────┘   └──────┬──────┘   └──────┬──────┘
       │                 │                 │
       └─────────────────┴────────┬────────┘
                                  ▼
                     ┌────────────────────┐
                     │     Claude AI      │
                     │  + SE knowledge    │
                     │    base prompt     │
                     └─────────┬──────────┘
                               ▼
                     ┌────────────────────┐
                     │    Browser UI      │
                     │   (Export PDF)     │
                     └────────────────────┘
```

## Project structure

```
DealWisperer/
├── app.py                  # Flask application and pipeline orchestration
├── agents/
│   ├── __init__.py
│   ├── vivun_agent.py      # Vivun API + sample data fallback
│   ├── taegis_agent.py     # Taegis GraphQL (standard + CTPX)
│   ├── osint_agent.py      # Serper OSINT (jobs + news)
│   ├── synthesizer.py      # Claude AI brief generation + normalization
│   └── system_prompt.txt   # SE knowledge base (platform, competitive, industry, ROI, rules)
├── templates/
│   └── index.html          # Single-page UI
├── static/
│   └── empty-state-icon.png
├── data/
│   └── sample_opportunities.json   # Demo opportunity (Smiths Cogwheels)
├── docs/
│   └── API_GUIDE.md        # API integration reference
├── .env.example            # Environment variable template
├── requirements.txt        # Python dependencies
├── run.sh                  # macOS launcher script
├── SETUP.md                # Detailed setup guide
└── README.md
```

## Requirements

- **Python 3.9+** (`python3` / `pip3` on macOS)
- **Anthropic** API key — [console.anthropic.com](https://console.anthropic.com) (required for AI synthesis)
- **Vivun** API key — app.vivun.com → Settings → API Keys (optional; sample data used when missing)
- **Taegis** OAuth2 credentials — XDR portal → Settings → API Credentials (optional; see [SETUP.md](SETUP.md))
- **Serper** API key — [serper.dev](https://serper.dev) (optional; free tier: 2,500 searches/month)

## Cost estimate

| Service | Typical use | Est. cost/month |
|---------|-------------|-----------------|
| Anthropic | ~50–200 briefs | ~$5–15 |
| Serper | Free tier (2,500 searches) | $0 |
| Vivun / Taegis | Existing org credentials | $0 |

## License

**Sophos** and the **Sophos logo** are registered trademarks of Sophos Ltd.

---

<p align="center">
  Built with ❤️ by Ștefan, with guidance from Claude and Cursor.
</p>
