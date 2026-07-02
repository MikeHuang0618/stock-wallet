# Stock Wallet · 個人投資儀表板

[![CI](https://github.com/MikeHuang0618/stock-wallet/actions/workflows/ci.yml/badge.svg)](https://github.com/MikeHuang0618/stock-wallet/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A portable Windows desktop dashboard for personal investing. Track indices and a
watchlist, drill into any ticker for technical charts (MA, KD, RSI, MACD, Bollinger,
volume) with an interactive crosshair, follow a macro-event calendar (CPI / NFP /
FOMC / earnings), and manage a dual-currency (USD/TWD) portfolio with realized and
unrealized P&L. Optional AI analysis via Claude, OpenAI, or Gemini (bring your own key).

> ⚠️ **Not investment advice.** Quotes are delayed data from Yahoo Finance. This tool
> is for personal research and record-keeping only. See [Disclaimers](#-legal--disclaimers).

---

## Features

- **Dashboard** — major indices (Nasdaq, S&P 500, Dow, Russell 2000, SOX, VIX),
  Yahoo symbol search + personal watchlist.
- **Ticker detail** — price line (fixed) plus two selectable sub-panels from
  volume / KD / RSI / MACD / OBV / Bollinger; MA5/10/20/60 overlays; timeframes and
  custom date ranges; interactive crosshair.
- **Major events** — CPI / non-farm payrolls / FOMC calendar, watched-stock earnings
  dates, and user-defined custom events.
- **Wallet** — SQLite-backed holdings (average-cost), buy/sell transactions,
  deposits/withdrawals, USD/TWD currency blocks with live FX, holdings pie, and
  portfolio value / daily-P&L history charts.
- **Gold signals** — GLL / UGL calendar and key-price alerts with Windows toast
  notifications.
- **AI analysis** *(optional)* — buy / watch / sell + target price from your chosen
  provider; auto-runs once per day per symbol; manual re-evaluate button.

---

## Install (end users)

Download from [**Releases**](https://github.com/MikeHuang0618/stock-wallet/releases):

| Option | File | Notes |
|--------|------|-------|
| 🅰 Installer (recommended) | `StockWallet-Setup.exe` | Wizard; adds Start Menu / desktop shortcuts; uninstall via *Add or remove programs* |
| 🅱 Portable | `StockWallet.exe` | Single file, double-click to run, USB-friendly |

Requires 64-bit Windows 10/11 (WebView2 is built in).

## Run from source (developers)

```bash
git clone https://github.com/MikeHuang0618/stock-wallet.git
cd stock-wallet
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt
python app.py
```

### Test (release gate — must be green before packaging)

```bash
pip install -r requirements-dev.txt
ruff check .        # lint
pytest              # golden tests: indicators / analysis / wallet
```

### Build the exe + installer

```bash
python make_icon.py
pyinstaller --noconfirm --onefile --windowed --name StockWallet ^
  --icon icon.ico --add-data "icon.ico;." --add-data "web;web" ^
  --collect-all webview --collect-all winotify app.py
ISCC.exe installer\StockWallet.iss     # needs Inno Setup → installer\Output\StockWallet-Setup.exe
```

CI automates this: pushing a `v*` tag (e.g. `git tag v0.7.0 && git push origin v0.7.0`)
runs the tests, builds the exe and installer, and attaches both to a GitHub Release.

---

## Architecture

```
app.py            Entry point: creates the window, loads web/
api.py            Backend Api (js_api): quotes / wallet / AI / import-export I/O
indicators.py     Pure technical indicators (SMA/EMA/RSI/KD/MACD/Bollinger/OBV)
analysis.py       Pure: chart range resolver + AI provider request builders
wallet.py         Pure: holdings, realized P&L, currency aggregation, value history
web/              Frontend: index.html · styles.css · app.js
tests/            Golden tests (asserted against hand-computed values)
installer/        Inno Setup installer script
```

Design principle: **all money and indicator math are pure functions** (no network, no
side effects); I/O is isolated in `api.py`. This keeps tests fast and the numbers trustworthy.

---

## Data storage & privacy

- All app data lives **locally** in `%APPDATA%\StockWallet\`: `wallet.db` (transactions),
  `watchlist.json`, `alerts.json`, `events.json`, `ai_config.json`, `ai_cache.json`.
- **No telemetry, no accounts, no data collection.** Nothing is sent anywhere except
  (a) requests to Yahoo Finance for quotes and (b), only if you enable AI, requests to the
  AI provider you selected.
- **API keys** you enter are stored in plaintext in `ai_config.json` on your machine
  (they are not encrypted and are never uploaded by this app). Treat that file accordingly;
  do not commit it. Revoke a key from the provider's console if it is exposed.

## AI providers (bring your own key)

AI analysis is **off by default** (`None`). To use it, add your own API key for Claude
(Anthropic), OpenAI, or Gemini (Google) in **Settings**. Requests go directly from the app
to that provider's official API and **incur costs on your account** per their pricing. AI
output is a model estimate, not advice.

---

## ⚖️ Legal & disclaimers

- **Not investment advice.** Nothing in this software is a recommendation to buy or sell
  any security. Markets involve risk, including loss of principal. Do your own research.
- **Data source.** Market quotes, historical prices, earnings dates, and FX rates are
  retrieved from Yahoo Finance via an **unofficial, undocumented endpoint**. This project is
  **not affiliated with, endorsed by, or sponsored by Yahoo**. Data may be delayed,
  incomplete, or unavailable, and is provided "as is". Use is intended for **personal,
  non-commercial research**; redistribution of the data or commercial use may violate
  Yahoo's Terms of Service — you are responsible for your own compliance.
- **Leveraged products.** UGL / GLL are daily-reset ±2× leveraged ETFs subject to
  compounding/volatility decay; their long-term returns can diverge substantially from
  twice the underlying. Understand these risks before trading them.
- **AI output.** Analysis produced via third-party AI providers is an automated estimate,
  may be wrong, and is not advice. You are responsible for provider costs and terms.
- **Trademarks.** *Yahoo Finance*, *Anthropic/Claude*, *OpenAI*, *Google/Gemini*,
  *Microsoft/WebView2/Windows*, and *ProShares/UGL/GLL* are trademarks of their respective
  owners. Their use here is nominative only and implies no affiliation or endorsement.
- **Warranty.** Provided "as is" without warranty of any kind (see [LICENSE](LICENSE)).

---

## License

Stock Wallet is released under the [MIT License](LICENSE).

Bundled third-party open-source components and their license texts are listed in
[THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md). PyInstaller (the build tool) is GPLv2
**with an exception** that permits distributing proprietary applications, so it places no
license obligation on this project.

See [CHANGELOG.md](CHANGELOG.md) for release history.

## Contributing

Issues and pull requests are welcome. Please keep the pure/tested-function discipline:
money and indicator logic goes in the pure modules with a matching golden test in `tests/`,
and `ruff check . && pytest` must pass before a PR is merged.
