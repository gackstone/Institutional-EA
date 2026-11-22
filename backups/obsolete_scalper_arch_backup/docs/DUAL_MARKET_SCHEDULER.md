# Dual-Market Trading Scheduler (`MarketScheduler`)

## Overview

`MarketScheduler` (`src/scalper/scheduler.py`) governs the calendar-aware routing between **GOLD (`XAUUSD`)** on weekdays and **BITCOIN (`BTCUSD`)** on weekends. It ensures that new scalping baskets are only opened on the scheduled instrument when verified tradable by the MetaTrader 5 broker, while guaranteeing that existing positions on any outgoing instrument continue to be monitored and exited cleanly.

---

## Trading Schedule

| Day | GOLD (`XAUUSD`) | BITCOIN (`BTCUSD`) | New Basket Routing | Existing Position Monitoring |
|---|---|---|---|---|
| **Monday** | **ON** | OFF | `GOLD` (`777001`) | Both `GOLD` & `BTCUSD` |
| **Tuesday** | **ON** | OFF | `GOLD` (`777001`) | Both `GOLD` & `BTCUSD` |
| **Wednesday** | **ON** | OFF | `GOLD` (`777001`) | Both `GOLD` & `BTCUSD` |
| **Thursday** | **ON** | OFF | `GOLD` (`777001`) | Both `GOLD` & `BTCUSD` |
| **Friday** | **ON** | OFF | `GOLD` (`777001`) | Both `GOLD` & `BTCUSD` |
| **Saturday** | OFF | **ON** | `BTCUSD` (`777002`) | Both `GOLD` & `BTCUSD` |
| **Sunday** | OFF | **ON** | `BTCUSD` (`777002`) | Both `GOLD` & `BTCUSD` |

---

## How It Works

Each execution cycle (200–500ms) executes a 4-step evaluation inside `MarketScheduler.evaluate_market_status()`:

1. **Localized Timestamp Resolution**: Resolves current wall-clock time (or simulation timestamp override) in the configured timezone (`scheduler.timezone`, defaulting to `UTC` via standard `zoneinfo`).
2. **Calendar Day Lookup**: Maps the day name (`MONDAY`..`SUNDAY`) against `weekday_days` (`GOLD`) and `weekend_days` (`BTCUSD`).
3. **Transition Detection**: Compares the newly scheduled symbol against `last_active_symbol`. When a boundary is crossed (`GOLD -> BTCUSD` on Friday-to-Saturday or `BTCUSD -> GOLD` on Sunday-to-Monday), `is_transition_bar = True` is flagged and logged.
4. **Broker Availability Verification**: Before permitting new entries (`is_entry_permitted = True`), the scheduler verifies the broker's `ResolvedSymbolSpec`:
   - `symbol_spec` is resolved and present in Market Watch.
   - `trade_mode == 4` (`SYMBOL_TRADE_MODE_FULL`).
   - Live streaming quotes are valid (`bid > 0` and `ask > 0`).
   - If the scheduled symbol is closed or unavailable on the broker, the engine logs the status and waits—it **never** falls back to the inactive instrument.

---

## Transition Continuity Guarantee

In `DualMarketScalperEngine.run_single_tick_cycle()`:

- **Step 4 (Exit Evaluation)** iterates over `basket_manager.evaluate_all_exits()` across **all** active baskets (`GOLD` and `BTCUSD`) *before* consulting the scheduler for new entries.
- **Step 5 (New Entry Routing)** queries `MarketScheduler` and only opens new baskets on the currently scheduled symbol.
- Consequently, if a Friday `GOLD` basket remains open across the Saturday rollover (or a Sunday `BTCUSD` basket remains open into Monday), its individual TP, aggregate basket TP, protective SL, and maximum holding time exits remain 100% active until every position is closed.

---

## Configuration (`config/scalper.yaml`)

```yaml
scheduler:
  enabled: true
  timezone: "UTC"
  weekday_symbol: "GOLD"
  weekend_symbol: "BTCUSD"
  weekday_days:
    - "MONDAY"
    - "TUESDAY"
    - "WEDNESDAY"
    - "THURSDAY"
    - "FRIDAY"
  weekend_days:
    - "SATURDAY"
    - "SUNDAY"
  manage_existing_positions: true
  require_symbol_trading_availability: true
```
