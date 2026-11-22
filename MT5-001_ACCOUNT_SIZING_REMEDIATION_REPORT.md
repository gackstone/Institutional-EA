# MT5-001 — ACCOUNT SIZING REMEDIATION REPORT

**Date:** 2026-11-16  
**Centralized Sizing Engine:** `src/risk/position_sizing.py` (`PositionSizingEngine`)

---

## 1. Legacy Account-Based Sizing Restrictions Removed

| File & Line | Old Restriction | Remediation |
|---|---|---|
| `src/risk/position_sizing.py:64` | `max_lot_cap: float = 0.5` hard-coded static lot cap | Defaulted `max_lot_cap: Optional[float] = None` so sizing scales dynamically up to broker `symbol_info.max_lot` and available margin/risk budget. |
| `src/risk/position_sizing.py:242-243` | `if capital_base < 500.0: effective_max_lot = min(effective_max_lot, symbol_info.min_lot * 3.0)` | Removed arbitrary `$500` balance lot cap. |

---

## 2. Retained Mandatory Sizing & Broker Protections

- **R9 Per-Trade Risk Hard Cap (`<= 2.0%`):** Preserved (`HARD_MAX_RISK_PCT = 2.0`, default `1.0%`).
- **Mandatory Stop-Loss Distance (`SL > 0`):** Preserved.
- **Broker Volume Quantization:** `symbol_info.min_lot`, `symbol_info.max_lot`, and `symbol_info.lot_step` (floored, never rounded up).
- **MT5 `order_calc_profit()` / Tick-Value Structural Risk:** Uses MT5 contract profit calculation when terminal is connected, falling back to `(sl_distance / tick_size) * tick_value`.
- **Margin Sufficiency:** Verified in both `PositionSizingEngine` and `DynamicPortfolioCapacityEngine`.

---

## 3. Test Verification

- `tests/test_position_sizing.py`: **2/2 PASSED**
- `tests/test_dynamic_position_layering.py`: **12/12 PASSED**
- `tests/test_unrestricted_positions_and_spread.py`: **8/8 PASSED**
