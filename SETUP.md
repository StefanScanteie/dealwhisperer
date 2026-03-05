# Taegis Deal Whisperer — Setup Guide

Step-by-step setup for running the app locally on macOS.

---

## 1. Python

Install **Python 3.9+** from [python.org](https://www.python.org/downloads/) or via Homebrew:

```bash
brew install python@3.11
```

Always use `python3` and `pip3` on macOS (the system `python` is reserved).

```bash
python3 --version   # 3.9 or higher
pip3 install -r requirements.txt
```

---

## 2. Environment file

```bash
cp .env.example .env
```

Edit `.env` and fill in the keys below. Steps that cannot use an API (missing key or error) are skipped and show "No Access" in the brief.

---

## 3. Anthropic (Claude) — required

1. Go to [console.anthropic.com](https://console.anthropic.com).
2. Create an API key.
3. In `.env`: `ANTHROPIC_API_KEY=sk-ant-...`

Without this key, the synthesizer returns a minimal brief with "No Access" in AI-generated sections. The brief is still generated from Vivun/Taegis/OSINT data when those are available.

---

## 4. Vivun — optional

1. Log in to [app.vivun.com](https://app.vivun.com) → **Settings** → **API Keys**.
2. Create an API key and copy it.
3. In `.env`: `VIVUN_API_KEY=...` and optionally `VIVUN_BASE_URL=https://api.vivun.com/v1`.

When `VIVUN_API_KEY` is empty or unset, the agent loads from `data/sample_opportunities.json` instead (ships with a demo opportunity: `[TCU] Smiths Cogwheels Inc`).

---

## 5. Taegis (XDR / MDR API) — optional

Deal Whisperer uses the same **Taegis API** and credentials as the official Taegis tools. If you already use [Taegis Magic](https://docs.taegis.secureworks.com/magic/magic_overview/) (CLI / Jupyter), the same credentials work here.

1. In the **Taegis XDR** portal, go to **Settings → API Credentials** (see [Taegis docs](https://docs.taegis.secureworks.com/) → XDR → Your Account → Manage API Credentials).
2. Create OAuth2 client credentials (client ID + client secret).
3. In `.env`:
   - `TAEGIS_CLIENT_ID=<your client id>`
   - `TAEGIS_CLIENT_SECRET=<your client secret>`
   - `TAEGIS_BASE_URL=https://api.taegis.secureworks.com` (default)

### CTPX environments

If your tenant uses `https://api.ctpx.secureworks.com`, set that as `TAEGIS_BASE_URL`. The app auto-detects CTPX and uses the CTU Threat Intelligence publications API (`threatLatestPublications`) instead of the by-vertical aggregate queries (which are not available on CTPX). Customer telemetry is not available on CTPX.

### References

- [Taegis Magic Jupyter Integration](https://docs.taegis.secureworks.com/magic/magic_overview/)
- [Taegis Magic on GitHub](https://github.com/secureworks/taegis-magic)
- [Threat Intelligence API](https://docs.taegis.secureworks.com/apis/using_threat_intelligence_api/)

---

## 6. Serper (OSINT) — optional

1. Sign up at [serper.dev](https://serper.dev); free tier: 2,500 searches/month.
2. Get your API key.
3. In `.env`: `SERPER_API_KEY=...`

If unset, OSINT is skipped and the brief generates without job/news intelligence.

---

## 7. App settings

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `5001` | HTTP port (5000 is used by macOS AirPlay Receiver) |
| `SE_NAME` | `Sophos SE` | Name shown on generated briefs |

---

## 8. Running the app

```bash
bash run.sh
```

This checks Python and dependencies, then opens `http://localhost:5001` in your browser. Alternatively:

```bash
pip3 install -r requirements.txt
python3 app.py
```

---

## 9. macOS-specific notes

- **Port 5001**: On macOS Monterey+, port 5000 is used by AirPlay Receiver. The app defaults to 5001.
- **python3 vs python**: Always use `python3` / `pip3` to avoid the system Python.
- **Export PDF**: Click **Export PDF** in the app; the browser print dialog opens — choose **Save as PDF** (no plugins needed).

---

## 10. Troubleshooting

| Issue | Fix |
|-------|-----|
| `python3: command not found` | Install Python 3.9+ and add to PATH |
| Port 5001 in use | Set `PORT=5002` in `.env` |
| Vivun 404 | Check that the opportunity name matches Vivun, or leave `VIVUN_API_KEY` empty to use sample data |
| Taegis 400 on CTPX | Set `TAEGIS_BASE_URL=https://api.ctpx.secureworks.com` — the app handles CTPX automatically |
| Claude rate limit / credit error | Check your Anthropic plan at console.anthropic.com |
| Brief is empty / blank sections | Check the console log for Claude JSON parse errors; restart and retry |
