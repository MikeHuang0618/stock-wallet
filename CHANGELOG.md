# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Asset-history overhaul** — the wallet now *records* history instead of only
  recomputing it from live prices ([docs/asset-history-gaps.md](docs/asset-history-gaps.md)):
  - **Daily snapshots** — each session writes an immutable per-currency net-worth
    snapshot (`snapshots` table, same-day UPSERT). The value history now reads
    snapshot-first, so a delisted/renamed ticker or a Yahoo price revision no longer
    rewrites the past. Snapshot/recompute divergence >1% is surfaced, never silently
    applied (`wallet.merge_snapshot_history`).
  - **Dividends** — cash dividends (`side=dividend`, amount in the price field) and
    stock dividends / bonus shares (`side=stock_dividend`, lowers average cost);
    both feed portfolio value, returns, and a new "累計股息" total.
  - **Fees & transaction tax** — optional `fee` per transaction (into cost on buy,
    off realized P&L on sell); a "≈稅費" button estimates TW broker fee + securities tax.
  - **Splits / share adjustments** (`side=adjust`, signed) — average cost preserved,
    no history cliff (snapshots need no back-adjustment).
  - **Combined net-worth curve** — a single USD-denominated total line across USD/TWD
    (`wallet.combine_history`); FX forward-filled, missing FX shows a break, never 0.
  - **Other (manual) assets** — record valuations of non-market assets (deposits,
    insurance, gold, property) toward net worth and the total curve.
  - **XIRR** — money-weighted annualized return alongside the simple return
    (`wallet.compute_xirr`; hidden under 30 days / no solution).
  - **Automatic backups** — `wallet.db` is copied to `backups\` once per day on
    startup (keep 30) via the SQLite backup API; restore + open-folder in Settings.
  - **Period reports** — monthly / yearly net-worth summaries plus a yearly
    realized-P&L-with-dividends table (`wallet.summarize_periods`, `realized_by_year`).
  - **Broker CSV import** — generic column-mapped import with duplicate skipping
    (`wallet.parse_csv_transactions`).
  - Export/import bumped to version 2 (covers `fee`, new sides, and manual assets;
    still reads version-1 backups).
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

### Fixed
- Wallet DB migrations (`side`/`fee`/`currency` back-fill) are now explicitly committed;
  previously the `UPDATE`s that convert legacy signed quantities to buy/sell rows could roll
  back on connection close, leaving old databases un-migrated.
- Daily snapshots are skipped for a currency when any of its holdings is missing a quote —
  a network/Yahoo outage can no longer record an understated market value as the immutable
  history (the old guard checked a sum that could never be `None`).
- Snapshot-vs-recompute divergence detection now scans **all** overlapping dates and reports
  the earliest mismatch; previously only the first overlap was checked, so a back-filled
  old transaction diverging mid-range went unreported.
- Adding a transaction dated before the latest snapshot now returns a `backdated` flag and
  the UI says the chart keeps following recorded snapshots (no silent history rewrite).
- New `tests/test_api_wallet_db.py` covers the DB layer against a temp `APPDATA`
  (migration persistence, snapshot guard/UPSERT, manual assets, backup prune/restore).

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
