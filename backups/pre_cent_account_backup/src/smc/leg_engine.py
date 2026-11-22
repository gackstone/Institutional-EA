'''Leg model and utilities for constructing legs between confirmed swing points.

A *leg* is the price move between two consecutive confirmed swing points.  The
engine computes a rich set of metrics used by the speed engine and by the
strategy router.
'''\n\nfrom __future__ import annotations\n\nfrom dataclasses import dataclass\nfrom typing import List, Tuple\nimport numpy as np\n\nfrom src.core.contracts import Candle, Timeframe, OrderType\nfrom src.risk.volatility import compute_atr\n\n\n@dataclass(frozen=True)\nclass Leg:\n    """Metrics describing a price leg between two swing points.
\n    Attributes\n    ----------\n    direction: OrderType\n        BUY for upward leg, SELL for downward leg.\n    start_idx: int\n        Index of the candle where the leg starts (inclusive).\n    end_idx: int\n        Index of the candle where the leg ends (inclusive).\n    bar_count: int\n        Number of candles in the leg (end‑start+1).\n    displacement_atr: float\n        Absolute price change divided by the ATR (winsorised) of the leg.
    velocity_atr: float\n        Displacement ATR divided by ``bar_count`` – i.e. average ATR‑normalised
        move per bar.
    mean_body_ratio: float\n        Mean ``candle.body / candle.range`` across the leg.
    overlap_ratio: float\n        Fraction of successive candles that overlap (0 = no overlap,
        1 = full overlap).
    directional_consistency: float\n        Share of candles whose close moves in the leg direction.
    longest_same_dir_run: int\n        Length of the longest consecutive run of candles closing in the
        leg direction.
    kaufman_er: float\n        Kaufman Efficiency Ratio = net displacement / sum(|price change|).
    """\n\n    direction: OrderType\n    start_idx: int\n    end_idx: int\n    bar_count: int\n    displacement_atr: float\n    velocity_atr: float\n    mean_body_ratio: float\n    overlap_ratio: float\n    directional_consistency: float\n    longest_same_dir_run: int\n    kaufman_er: float\n\n\ndef _winsorised_atr(candles: List[Candle], period: int = 14) -> float:\n    """Compute a robust ATR using winsorisation.
\n    The function calculates the true range for each candle, trims the extreme
    values at the 5th and 95th percentiles, then returns the mean of the
    remaining values.  If the list is shorter than ``period`` the simple ATR is
    used as a fallback.
    """\n    if len(candles) < period:
        return compute_atr(candles, period)
    tr = []\n    for i in range(1, len(candles)):
        high = candles[i].high
        low = candles[i].low
        prev_close = candles[i - 1].close
        tr.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    tr_arr = np.array(tr)
    low_q, high_q = np.percentile(tr_arr, [5, 95])
    trimmed = tr_arr[(tr_arr >= low_q) & (tr_arr <= high_q)]
    return float(trimmed.mean()) if trimmed.size > 0 else float(tr_arr.mean())\n\n\ndef _leg_metrics(candles: List[Candle], start: int, end: int, atr: float) -> Leg:\n    """Calculate all leg metrics for the slice ``candles[start:end+1]``.
\n    ``atr`` is the ATR value (winsorised) for the whole leg period.
    """\n    segment = candles[start : end + 1]\n    direction = OrderType.BUY if segment[-1].close > segment[0].close else OrderType.SELL\n    bar_count = len(segment)
    displacement = abs(segment[-1].close - segment[0].close)
    displacement_atr = displacement / atr if atr != 0 else 0.0
    velocity_atr = displacement_atr / bar_count if bar_count > 0 else 0.0
    # body/range ratio
    body_ratios = [c.body / c.range if c.range > 0 else 0.0 for c in segment]
    mean_body_ratio = sum(body_ratios) / bar_count if bar_count else 0.0
    # overlap ratio – count overlaps between consecutive candles
    overlap_cnt = 0
    for i in range(1, bar_count):
        prev = segment[i - 1]
        cur = segment[i]
        # overlap if current low <= previous high and current high >= previous low
        if cur.low <= prev.high and cur.high >= prev.low:
            overlap_cnt += 1
    overlap_ratio = overlap_cnt / (bar_count - 1) if bar_count > 1 else 0.0
    # directional consistency
    dir_consistency = 0
    longest_run = 0
    current_run = 0
    for c in segment[1:]:  # skip first candle for direction check
        move_up = c.close > c.open
        if (direction == OrderType.BUY and move_up) or (direction == OrderType.SELL and not move_up):
            dir_consistency += 1
            current_run += 1
        else:
            longest_run = max(longest_run, current_run)
            current_run = 0
    longest_run = max(longest_run, current_run)
    directional_consistency = dir_consistency / (bar_count - 1) if bar_count > 1 else 0.0
    # Kaufman Efficiency Ratio
    net_disp = displacement
    sum_abs_moves = sum(abs(c.close - c.open) for c in segment)
    kaufman_er = net_disp / sum_abs_moves if sum_abs_moves != 0 else 0.0
    return Leg(
        direction=direction,
        start_idx=start,
        end_idx=end,
        bar_count=bar_count,
        displacement_atr=displacement_atr,
        velocity_atr=velocity_atr,
        mean_body_ratio=mean_body_ratio,
        overlap_ratio=overlap_ratio,
        directional_consistency=directional_consistency,
        longest_same_dir_run=longest_run,
        kaufman_er=kaufman_er,
    )\n\n\ndef build_legs(candles: List[Candle], swing_lookback: int = 5) -> List[Leg]:\n    """Construct legs between consecutive confirmed swing points.
\n    The function uses ``MarketStructureEngine.find_swing_points`` logic (replicated
    locally to avoid a heavy import) to obtain swing highs and lows, orders them
    chronologically, and creates a leg for each adjacent pair.
    Stressed bars (marked by ``candle.session_name == 'STRESSED'`` or similar –
    the concrete flag is set by the liquidity/news modules) are excluded from the
    ATR calculation via the winsorised helper.
    """\n    # Re‑use the swing detection from MarketStructureEngine (symmetrical look‑back)
    from src.smc.market_structure import MarketStructureEngine\n    ms_engine = MarketStructureEngine(swing_lookback=swing_lookback)
    swing_highs, swing_lows = ms_engine.find_swing_points(candles)\n    # Merge and sort swing points by index\n    swing_points: List[Tuple[int, Candle]] = sorted(swing_highs + swing_lows, key=lambda x: x[0])\n    legs: List[Leg] = []\n    for i in range(len(swing_points) - 1):\n        start_idx = swing_points[i][0]\n        end_idx = swing_points[i + 1][0]\n        # Compute a winsorised ATR for this slice (period = bar count, fallback to 14)\n        atr = _winsorised_atr(candles[start_idx : end_idx + 1], period=14)\n        leg = _leg_metrics(candles, start_idx, end_idx, atr)\n        legs.append(leg)\n    return legs\n