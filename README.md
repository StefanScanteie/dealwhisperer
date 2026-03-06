# Taegis Deal Whisperer

AI-powered pre-call battle card generator for Sales Engineers. Combines opportunity data from Vivun, threat intelligence from the Taegis XDR API, and OSINT via Serper, then synthesizes a personalized brief with Claude AI — all running locally on macOS.

## What it does

1. **Pulls opportunity data** from Vivun (company profile, deal stage, competitor, SE notes, EDR landscape, technical win criteria). Falls back to local sample data (`data/sample_opportunities.json`) when `VIVUN_API_KEY` is not set.
2. **Fetches Taegis threat intelligence** — industry-level CTU publications for prospects (including CTPX-specific `threatLatestPublications`); customer telemetry and coverage gaps for existing Taegis customers. Uses the same [Taegis XDR API credentials](https://docs.taegis.secureworks.com/magic/magic_overview/) as Taegis Magic.
3. **Runs OSINT** (prospects only) via Serper — job postings and news to infer security tools in use, hiring signals, and conversation starters.
4. **Synthesizes a battle card** with Claude — deal snapshot, ROI hook, competitive angle, objections & rebuttals, demo flow, conversation hook, action items (or QBR stats for customers).
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

Mode is **auto-detected**: if the opportunity has a `taegis_tenant_id`, the app uses **customer** mode; otherwise **prospect**.

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
                         ┌─────────────────┐
                         │   Claude AI     │
                         │  (synthesis)    │
                         └────────┬────────┘
                                  ▼
                         ┌─────────────────┐
                         │   Browser UI    │
                         │  (Export PDF)   │
                         └─────────────────┘
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
│   └── synthesizer.py      # Claude AI brief generation + normalization
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

## ⚖️ License

**Sophos** and the **Sophos logo** are registered trademarks of Sophos Ltd.

---

<p align="center">
  Built with ❤️ by Ștefan, with guidance from Claude and Cursor.
</p>

