# Taegis Deal Whisperer

AI-powered pre-call battle card generator for Sales Engineers.
Pulls opportunity data from **Vivun**, threat intel from the **Taegis XDR API**, and OSINT via **Serper**, then synthesizes a personalized brief with **Claude AI** — all running locally.

**[Quick start](#quick-start) · [How it works](#how-it-works) · [Brief sections](#brief-output-sections) · [AI knowledge base](#ai-knowledge-base) · [Project structure](#project-structure)**

---

## Quick start

```bash
git clone <repo-url> && cd DealWisperer
cp .env.example .env          # add your API keys
pip3 install -r requirements.txt
bash run.sh                    # opens http://localhost:5001
```

Enter an opportunity name (e.g. `Smiths Cogwheels`) and click **Generate brief**, or use the **Manual input** tab for deals not yet in Vivun.

> **Demo mode:** With only `ANTHROPIC_API_KEY` set and all other keys blank, the app uses the bundled sample opportunity and still generates a full brief via Claude.

### Requirements

| Dependency | Required | Notes |
|-----------|----------|-------|
| Python 3.9+ | Yes | `python3` / `pip3` on macOS |
| [Anthropic API key](https://console.anthropic.com) | Yes | Powers AI synthesis (~$5–15/mo for 50–200 briefs) |
| Vivun API key | No | Falls back to sample data when missing |
| [Taegis OAuth2 credentials](https://docs.taegis.secureworks.com/magic/magic_overview/) | No | Threat intel skipped when missing |
| [Serper API key](https://serper.dev) | No | Free tier: 2,500 searches/month |

---

## How it works

```
Vivun  (opp data)     ─┐
Taegis (threat intel) ─┼──▶  Claude AI + SE knowledge base  ──▶  Browser UI (Export PDF)
Serper (OSINT)        ─┘
```

### Pipeline

1. **Vivun** — Pulls opportunity data: company profile, deal stage, competitor, SE notes, EDR landscape, technical win criteria. Falls back to `data/sample_opportunities.json` when `VIVUN_API_KEY` is not set.
2. **Taegis** — Fetches CTU threat intelligence publications for prospects (CTPX or standard API); customer telemetry and coverage gaps for existing customers.
3. **OSINT** *(prospects only)* — Searches job postings and cybersecurity news via Serper to infer security tools, hiring signals, and conversation hooks.
4. **Claude** — Synthesizes everything into a battle card using a comprehensive SE knowledge base prompt.
5. **Browser** — Renders the brief with one-click PDF export (print dialog → "Save as PDF").

### Two modes

|  | Prospect | Customer |
|--|----------|----------|
| **Data** | Vivun + Taegis industry intel + OSINT | Vivun + Taegis customer telemetry |
| **Focus** | Competitive positioning, ROI hook, demo flow, conversation hooks | QBR stats, renewal defense, expansion opportunity |
| **AI rules** | Deal-stage-aware, OSINT-driven hooks, numbered ROI claims | Real telemetry stats, risk-based expansion priority |

Auto-detected: opportunities with a `taegis_tenant_id` use **customer** mode; otherwise **prospect**.

### Graceful degradation

Every API is optional. When unavailable, the pipeline skips that step and continues:

| Source | Fallback |
|--------|----------|
| Vivun | Local sample data; returns 404 if no match |
| Taegis | Brief generated without threat intel |
| OSINT | Brief generated without job/news intel |
| Claude | Deterministic minimal brief (no AI) |

The UI shows a **No access** banner listing skipped sources.

### Language support

The app supports **English** and **Japanese** for both the UI and AI-generated brief content. Use the **EN / JA** toggle in the header.

---

## Brief output sections

Every generated brief includes up to 17 sections (auto-hidden when empty):

| Section | Description |
|---------|-------------|
| **Deal snapshot** | 2-3 sentence deal context from SE notes and business challenges |
| **ROI hook** | One sentence with real numbers — breach cost, headcount savings, MTTR delta |
| **Competitive angle** | Why Taegis beats the named incumbent, referencing specific EDR tools |
| **Industry proof point** | Third-party stat or CTU publication for this industry |
| **Objections & rebuttals** | 3+ pairs tailored to the specific competitor |
| **Technical win map** | Each win criterion mapped to a specific Taegis capability |
| **Demo flow** | 3-5 step plan with screens, durations, and talking points |
| **OSINT & conversation hook** | OSINT insight + opening statement for the call |
| **Key stakeholders** | Contacts from `edr_landscape` with location and inferred relevance |
| **Risk factors** | 2-4 deal risks with concrete mitigations |
| **Call objectives** | What the SE must achieve on this call |
| **Discovery questions** | 3-5 tailored questions based on gaps in SE notes |
| **Open action items** | Concrete next steps |
| **Follow-up email draft** | Post-call email referencing key pain points |
| **Expansion opportunity** | *(customer)* Surface, risk, and recommended product |
| **Renewal defense** | *(customer)* Narrative for defending the renewal |
| **QBR headline stats** | *(customer)* 3-5 stats from real telemetry |

---

## AI knowledge base

The synthesizer is powered by a system prompt (`agents/system_prompt.txt`) encoding domain expertise across six areas:

<details>
<summary><strong>View knowledge base areas</strong></summary>

| Area | What it covers |
|------|----------------|
| **Taegis platform** | XDR architecture (open, 400+ integrations), MDR SLAs (1-hour MTTC), CTU intel heritage, Sophos integration |
| **Secureworks → Sophos** | Acquisition messaging, customer continuity, combined portfolio value |
| **Competitive intel** | CrowdStrike, SentinelOne, Microsoft, Palo Alto, Splunk — specific win angles and rebuttals |
| **Industry threats** | Healthcare, Financial Services, Manufacturing/OT, Technology — attack patterns, compliance, proof points |
| **ROI framework** | Breach cost avoidance ($4.88M avg), headcount replacement (2-4 FTE), MTTD/MTTR benchmarks |
| **SE behavioral rules** | 12 rules: deal-stage matching, use numbers, reference named competitor, OSINT hooks, customer-mode telemetry, expansion priorities, migration angle, discovery questions, technical win mapping, stakeholder extraction, risk analysis, follow-up email drafting |

</details>

The prompt is stored as a plain-text file so it can be reviewed, versioned, and updated independently of the code.

---

## Project structure

```
DealWisperer/
├── app.py                        # Flask app and pipeline orchestration
├── agents/
│   ├── vivun_agent.py            # Vivun API + sample data fallback
│   ├── taegis_agent.py           # Taegis GraphQL (standard + CTPX)
│   ├── osint_agent.py            # Serper OSINT (jobs + news)
│   ├── synthesizer.py            # Claude AI brief generation + normalization
│   └── system_prompt.txt         # SE knowledge base prompt
├── templates/
│   └── index.html                # Single-page UI
├── static/
│   ├── favicon.svg               # Browser tab icon
│   └── no-brief-yet-icon.png     # Empty state illustration
├── data/
│   └── sample_opportunities.json # Demo opportunity (Smiths Cogwheels)
├── docs/
│   └── API_GUIDE.md              # API integration reference
├── .env.example                  # Environment variable template
├── requirements.txt              # Python dependencies
├── run.sh                        # macOS launcher script
└── SETUP.md                      # Detailed setup guide
```

---

## License

**Sophos** and the **Sophos logo** are registered trademarks of Sophos Ltd.

---

<p align="center">
  Built with ❤️ by Ștefan, with guidance from Claude and Cursor.
</p>
