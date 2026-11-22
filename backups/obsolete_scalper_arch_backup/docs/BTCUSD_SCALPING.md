# BTCUSD Weekend Scalping Engine (`src/scalper/`)

## Overview

The BTCUSD scalping module extends the proven high-frequency basket architecture to trade Bitcoin (`BTCUSD`) exclusively on **Saturdays and Sundays** when XAUUSD markets are closed. Because Bitcoin has fundamentally different contract specifications, price scale, tick velocity, and bid-ask spread characteristics compared to Gold, `BTCUSD` operates under its own dedicated profile in `config/scalper.yaml` and isolated magic number (`777002`).

---

## Automatic BTCUSD Symbol Resolution

`BtcSymbolResolver` (`src/scalper/symbol_resolver.py`) inspects the connected MetaTrader 5 terminal's symbol list and resolves the broker's Bitcoin instrument in priority order:

1. Exact canonical match (`BTCUSD`)
2. Configured broker aliases (`BTCUSDm`, `BTCUSD.m`, `BTCUSD.a`, `BTCUSD#`, `BTCUSD.`, `BTCUSDpro`, `BTCUSD.raw`, `BTCUSD.std`, `BTC/USD`, `BITCOIN`)
3. Fuzzy prefix match (`BTC*USD*`)
4. Verification of `trade_mode == 4` (`SYMBOL_TRADE_MODE_FULL`), live `bid > 0` / `ask > 0`, filling mode (`FOK` / `IOC` / `RETURN`), contract size, and volume constraints.

---

## Live Broker Contract Specifications (`JustMarkets-Demo3`)

| Specification | GOLD (`XAUUSD.m`) | BITCOIN (`BTCUSD.m`) | Architectural Impact |
|---|---|---|---|
| **Resolved Broker Symbol** | `XAUUSD.m` | `BTCUSD.m` | Auto-resolved at startup |
| **Digits / Point** | `2` (`0.01`) | `2` (`0.01`) | 100 points = $1.00 price move |
| **Contract Size** | `100.0` oz | `1.0` BTC | On `0.01` lot: $1 move = $1.00 on Gold vs $0.01 on BTC ($100 move = $1.00 on BTC) |
| **Min / Max / Step Lot** | `0.01 / 100.0 / 0.01` | `0.01 / 100.0 / 0.01` | Identical volume quantization |
| **Filling Mode** | `1` (`ORDER_FILLING_FOK`) | `1` (`ORDER_FILLING_FOK`) | Auto-detected by `GoldOrderExecutor` |
| **Typical Live Spread** | `~20–30` points ($0.20–$0.30) | `~850–1200` points ($8.50–$12.00) | Requires symbol-specific spread filter |
| **Weekend Trade Mode** | Closed (`0`) | Full Trading (`4`) | Verified live on Saturday |

---

## Calibration Comparison: GOLD vs. BTCUSD

| Parameter | GOLD (`symbols.GOLD`) | BTCUSD (`symbols.BTCUSD`) | Engineering Rationale |
|---|---|---|---|
| `magic_number` | `777001` | `777002` | Strict order & position isolation between markets |
| `comment_prefix` | `GS_GOLD` | `GS_BTC` | Clear audit trail in MT5 trade history |
| `basket_size` | `4` (max `10`) | `4` (max `10`) | Rapid multi-position burst in selected direction |
| `lot_step_balance` | `50.0` | `50.0` | `floor(balance / 50.0) * 0.01` ($5 micro account -> `0.01` lot) |
| `tp_usd_per_min_lot` | `$0.50` | `$0.50` | Net individual position take-profit per `0.01` lot |
| `basket_tp_usd` | `$2.00` | `$2.00` | Aggregate net floating profit target to close entire basket |
| `max_hold_seconds` | `180`s | `180`s | Time-stop exiting breakeven/small controlled loss after 3 minutes |
| `sl_points` | `300.0` pts ($3.00) | `5000.0` pts ($50.00) | $50 BTC move on `0.01` lot (`contract_size=1.0`) = `$0.50` risk per position |
| `spread_max_points` | `80.0` pts ($0.80) | `3000.0` pts ($30.00) | Accommodates normal `850–1200` pt BTC spread while blocking illiquid spikes |
| `velocity_saturation` | `$0.50` / `$1.00` | `$25.00` / `$50.00` | Calibrates tick and M1 momentum scoring to BTCUSD's ~50x nominal price scale |

---

## Account-Wide Risk Protections Applied to BTCUSD

All global protections in `AccountRiskManager` (`src/scalper/risk.py`) govern BTCUSD alongside GOLD:

- **Maximum Open Positions**: `12` combined across all symbols.
- **Maximum Total Volume**: `1.00` lot combined across all symbols.
- **Minimum Margin Level**: `300.0%` required before and after projected basket margin.
- **Aggregate Drawdown Stop**: `30.0%` floating equity drawdown liquidates all open scalper positions and triggers a 60-minute pause.
- **Emergency Kill Switch**: Instant halt and liquidation when `STOP.flag` is present.
- **Demo/Live Guard**: `DEMO_MODE: true` by default; refuses real-money execution unless explicitly unlocked.
