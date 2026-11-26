# ICT/SMC Market Intelligence Walk-Forward Validation Report (2026-11-26)

> **EMPIRICAL DISCLAIMER:** Chronological 60% In-Sample / 40% Out-of-Sample evaluation with spread, commission, and slippage deductions. New ICT intelligence remains deployed in **`SHADOW` mode** by default (`allow_live_orders: false`). Do not promote any model to `DEMO_EXECUTE` unless out-of-sample expectancy and Deflated Sharpe Ratio (DSR) meet promotion gates.

## XAUUSD (M15, 1400 bars total / 560 OOS bars)

### A / B / C Strategy Comparison (Net of Spread, Commission & Slippage)

| Cohort | Trades | Win Rate | Profit Factor | Expectancy (R) | Max DD (R) | Avg Win (R) | Avg Loss (R) | DSR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A. Existing Baseline (OOS) | 106 | 5.7% | 0.22 | -0.801 | 85.43 | 3.88 | -1.08 | 0.004 |
| B/C. ICT Intelligence (IS) | 166 | 19.3% | 0.46 | -0.46 | 89.73 | 2.02 | -1.05 | 0.0 |
| B/C. ICT Intelligence (OOS) | 101 | 18.8% | 0.47 | -0.458 | 46.24 | 2.14 | -1.06 | 0.0 |

- **Shadow Mode Diagnostics**: `2299` evaluated | `499` confirmed/high-quality | `487` rejected (`21.2%` rejection rate)
- **Top Rejection Reasons**: `{'ENTRY_TOO_FAR_FROM_ZONE': 256, 'TARGET_ALREADY_REACHED': 301, 'WICK_ONLY_BREAK': 77}`

### OOS Performance by Setup Model

| Model | Trades | Win Rate | Profit Factor | Expectancy (R) |
| --- | ---: | ---: | ---: | ---: |
| `OTE` | 48 | 37.5% | 1.253 | 0.1628 |
| `UNICORN` | 53 | 1.9% | 0.035 | -1.0198 |

### OOS Performance by Session & Volatility Regime
- **Sessions**: `{'ASIA': {'trades': 33, 'wins': 8, 'losses': 25, 'win_rate': 0.2424, 'expectancy_r': -0.26, 'profit_factor': 0.669, 'avg_win_r': 2.163, 'avg_loss_r': -1.035}, 'LONDON': {'trades': 27, 'wins': 11, 'losses': 16, 'win_rate': 0.4074, 'expectancy_r': 0.2149, 'profit_factor': 1.331, 'avg_win_r': 2.122, 'avg_loss_r': -1.096}, 'NEW_YORK': {'trades': 12, 'wins': 0, 'losses': 12, 'win_rate': 0.0, 'expectancy_r': -1.1059, 'profit_factor': 0.0, 'avg_win_r': 0.0, 'avg_loss_r': -1.106}, 'OFF_HOURS': {'trades': 29, 'wins': 0, 'losses': 29, 'win_rate': 0.0, 'expectancy_r': -1.0409, 'profit_factor': 0.0, 'avg_win_r': 0.0, 'avg_loss_r': -1.041}}`
- **Volatility Regimes**: `{'HIGH_VOL': {'trades': 12, 'wins': 3, 'losses': 9, 'win_rate': 0.25, 'expectancy_r': -0.1997, 'profit_factor': 0.741, 'avg_win_r': 2.286, 'avg_loss_r': -1.028}, 'LOW_VOL': {'trades': 10, 'wins': 0, 'losses': 10, 'win_rate': 0.0, 'expectancy_r': -1.0427, 'profit_factor': 0.0, 'avg_win_r': 0.0, 'avg_loss_r': -1.043}, 'NORMAL': {'trades': 79, 'wins': 16, 'losses': 63, 'win_rate': 0.2025, 'expectancy_r': -0.4229, 'profit_factor': 0.503, 'avg_win_r': 2.111, 'avg_loss_r': -1.067}}`

## BTCUSD (M15, 1400 bars total / 560 OOS bars)

### A / B / C Strategy Comparison (Net of Spread, Commission & Slippage)

| Cohort | Trades | Win Rate | Profit Factor | Expectancy (R) | Max DD (R) | Avg Win (R) | Avg Loss (R) | DSR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A. Existing Baseline (OOS) | 78 | 26.9% | 0.3 | -1.344 | 110.19 | 2.14 | -2.63 | 0.0 |
| B/C. ICT Intelligence (IS) | 113 | 37.2% | 1.23 | 0.157 | 47.32 | 2.3 | -1.11 | 0.099 |
| B/C. ICT Intelligence (OOS) | 93 | 35.5% | 1.1 | 0.072 | 37.6 | 2.15 | -1.07 | 0.034 |

- **Shadow Mode Diagnostics**: `2216` evaluated | `452` confirmed/high-quality | `535` rejected (`24.1%` rejection rate)
- **Top Rejection Reasons**: `{'WICK_ONLY_BREAK': 110, 'TARGET_ALREADY_REACHED': 314, 'ENTRY_TOO_FAR_FROM_ZONE': 267}`

### OOS Performance by Setup Model

| Model | Trades | Win Rate | Profit Factor | Expectancy (R) |
| --- | ---: | ---: | ---: | ---: |
| `OTE` | 51 | 60.8% | 3.113 | 0.8735 |
| `UNICORN` | 42 | 4.8% | 0.123 | -0.9003 |

### OOS Performance by Session & Volatility Regime
- **Sessions**: `{'ASIA': {'trades': 8, 'wins': 4, 'losses': 4, 'win_rate': 0.5, 'expectancy_r': 0.6125, 'profit_factor': 2.166, 'avg_win_r': 2.276, 'avg_loss_r': -1.051}, 'LONDON': {'trades': 14, 'wins': 9, 'losses': 5, 'win_rate': 0.6429, 'expectancy_r': 1.0358, 'profit_factor': 3.79, 'avg_win_r': 2.189, 'avg_loss_r': -1.039}, 'NEW_YORK': {'trades': 42, 'wins': 13, 'losses': 29, 'win_rate': 0.3095, 'expectancy_r': -0.0777, 'profit_factor': 0.895, 'avg_win_r': 2.135, 'avg_loss_r': -1.07}, 'OFF_HOURS': {'trades': 29, 'wins': 7, 'losses': 22, 'win_rate': 0.2414, 'expectancy_r': -0.3243, 'profit_factor': 0.605, 'avg_win_r': 2.055, 'avg_loss_r': -1.081}}`
- **Volatility Regimes**: `{'HIGH_VOL': {'trades': 3, 'wins': 0, 'losses': 3, 'win_rate': 0.0, 'expectancy_r': -1.0499, 'profit_factor': 0.0, 'avg_win_r': 0.0, 'avg_loss_r': -1.05}, 'LOW_VOL': {'trades': 3, 'wins': 0, 'losses': 3, 'win_rate': 0.0, 'expectancy_r': -1.0513, 'profit_factor': 0.0, 'avg_win_r': 0.0, 'avg_loss_r': -1.051}, 'NORMAL': {'trades': 87, 'wins': 33, 'losses': 54, 'win_rate': 0.3793, 'expectancy_r': 0.1499, 'profit_factor': 1.225, 'avg_win_r': 2.15, 'avg_loss_r': -1.072}}`
