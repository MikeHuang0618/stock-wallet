# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Command palette (Ctrl/⌘+K, or `/`): jump to any page or search any ticker symbol
  (local watchlist/gold + Yahoo search) and open its detail page; keyboard navigable.
- Ticker detail: line / candlestick toggle for the price chart (candles show OHLC in the
  crosshair tooltip; MA overlays drawn on top).
- Dashboard watchlist: card / heatmap view toggle (tiles colored green↔red by % change).
- Ticker detail: automatic technical-signal detection (MA golden/death cross &
  trend alignment, KD cross, RSI overbought/oversold, MACD histogram flip, Bollinger
  breakout, gap) shown as colored badges. Pure `signals.py` module with golden tests.
- Gold Signals page: US/TW market toggle (synced with the global market switch).
  TW gold uses Yuanta leveraged/inverse ETFs — 00708L (+2x long) and 00674R (−1x short);
  added a volatility-decay warning for these daily-reset products.

### Changed
- Releases now ship a PyInstaller **onedir** build (installer + portable zip) instead of a
  single-file exe, which trips far fewer antivirus false positives; documented Windows
  Defender / SmartScreen handling in the README.

### Todo
- Mocked data-layer tests for `api.py` (Yahoo timeout / missing-value fallbacks).

## [0.7.0] - 2026-07-01

First public release. Consolidates the iterative development below and adds the
engineering scaffolding needed for an open-source repository.

### Added
- `tests/` suite (52 golden tests) covering `indicators`, `analysis`, and `wallet`
  pure functions against hand-computed values, including edge cases.
- GitHub Actions: `ci.yml` (ruff lint + pytest on push/PR, Python 3.11–3.13) and
  `release.yml` (tag `v*` → build portable exe + Inno Setup installer → attach to Release).
- Windows installer script (`installer/StockWallet.iss`) producing `StockWallet-Setup.exe`
  with Start Menu / desktop shortcuts and an uninstaller.
- `LICENSE` (MIT), `THIRD-PARTY-LICENSES.md`, `pyproject.toml`, `requirements*.txt`,
  `.gitignore`, and this changelog.
- Wallet buy/sell selector (positive quantity + side) replacing signed-quantity input.

### Changed
- Extracted all wallet money-math into pure, tested functions in `wallet.py`
  (`enrich_holding`, `summarize_currency`, `combine_currencies`); `api.py` now only
  does I/O and delegates the math.

### Fixed
- FX conversion no longer silently converts TWD assets to 0 when the USD/TWD rate is
  unavailable; the combined total is marked unavailable (backend and UI) instead.
- Major-events page: the add-event input row no longer scrolls with the list's
  scrollbar and is no longer hidden when the list is collapsed.

### Development history (pre-1.0, iterative)
- **Portfolio & multi-currency** — SQLite-backed holdings, deposits/withdrawals,
  USD/TWD blocks with live FX, realized + unrealized P&L, average-cost method,
  holdings pie, and portfolio value / daily-P&L history charts.
- **Rebrand** to *Stock Wallet* (from *GoldSignal*); data now under
  `%APPDATA%\StockWallet\` with one-time migration from the old folder.
- **Frontend/backend split** — HTML/CSS/JS moved to `web/`; Python split into
  `app.py` (entry) + `api.py` + pure modules.
- **AI analysis** — optional buy/watch/sell + target-price via Claude / OpenAI /
  Gemini (bring-your-own key, stored locally); auto-runs once per day per symbol
  with a manual re-evaluate button; result shown in the ticker header.
- **Ticker detail** — configurable technical charts (price line fixed + two of
  volume / KD / RSI / MACD / OBV / Bollinger), MA5/10/20/60 overlays, selectable
  timeframes and custom date ranges, and an interactive crosshair. Moving averages
  fetch warm-up history so MA60 spans the whole visible range.
- **Market dashboard** — major indices, Yahoo symbol search + watchlist, and a
  macro-event calendar (CPI / non-farm payrolls / FOMC) plus watched-stock earnings.
- **Gold signals** — GLL / UGL calendar and key-price alerts with Windows toast
  notifications.

[Unreleased]: https://github.com/MikeHuang0618/stock-wallet/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/MikeHuang0618/stock-wallet/releases/tag/v0.7.0
