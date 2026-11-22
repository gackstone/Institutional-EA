'''SMT (Same Market Trend) divergence detection utilities.

The SMT model looks for correlated symbol pairs where, at a sweep time, one
symbol (A) makes a new extreme (high for bullish, low for bearish) while the
paired symbol (B) fails to do so within a tolerance.  The correlation between
the pair must exceed a configurable threshold, otherwise the signal is ignored.

The implementation is pure‑function and can be unit‑tested with synthetic
candles.
'''\n\nfrom __future__ import annotations\n\nfrom dataclasses import dataclass\nfrom datetime import datetime, timedelta\nfrom typing import List, Tuple, Dict, Optional\n\nfrom src.core.contracts import Candle, OrderType\n\n\n@dataclass(frozen=True)\nclass SmtSignal:\n    """Result of an SMT divergence check.
\n    Attributes
    ----------
    symbol_a: str\n        Primary symbol where the extreme occurred.\n    symbol_b: str\n        Paired symbol that failed to follow.\n    direction: OrderType\n        BUY for bullish extreme, SELL for bearish extreme.\n    sweep_time: datetime\n        Timestamp of the sweep candle on symbol A.\n    extreme_price: float\n        The new high/low price on symbol A.\n    reference_price: float\n        The extreme price on symbol B at the same time (used for tolerance).\n    correlation: float\n        Rolling correlation coefficient at the time of the sweep.\n    """\n\n    symbol_a: str\n    symbol_b: str\n    direction: OrderType\n    sweep_time: datetime\n    extreme_price: float\n    reference_price: float\n    correlation: float\n\n\ndef _rolling_correlation(
    series_a: List[float], series_b: List[float], window: int
) -> List[float]:\n    """Compute simple rolling Pearson correlation.
\n    The function returns a list of correlation values aligned to the *end* of
    each window.  Values for the first ``window-1`` entries are ``0.0``.
    """\n    import math\n    if len(series_a) != len(series_b) or window <= 1:
        raise ValueError("Series must be equal length and window > 1")\n    corr: List[float] = []\n    for i in range(len(series_a)):\n        if i + 1 < window:\n            corr.append(0.0)\n            continue\n        window_a = series_a[i + 1 - window : i + 1]\n        window_b = series_b[i + 1 - window : i + 1]\n        mean_a = sum(window_a) / window\n        mean_b = sum(window_b) / window\n        num = sum((a - mean_a) * (b - mean_b) for a, b in zip(window_a, window_b))\n        den_a = sum((a - mean_a) ** 2 for a in window_a)\n        den_b = sum((b - mean_b) ** 2 for b in window_b)\n        den = math.sqrt(den_a * den_b)\n        corr.append(num / den if den != 0 else 0.0)\n    return corr\n\n\ndef detect_smt_divergence(\n    symbol_a: str,\n    candles_a: List[Candle],\n    symbol_b: str,\n    candles_b: List[Candle],\n    sweep_index: int,\n    tolerance_pips: float,\n    min_corr: float = 0.6,\n    corr_window: int = 30,\n) -> Optional[SmtSignal]:\n    """Detect SMT divergence at a specific sweep candle.
\n    Parameters\n    ----------\n    symbol_a, symbol_b\n        Symbols for the primary and paired instrument.\n    candles_a, candles_b\n        Chronological candle lists (must be aligned by time).\n    sweep_index\n        Index in ``candles_a`` representing the sweep candle (the candle
        that broke the liquidity pool).\n    tolerance_pips\n        Maximum price distance (in pips) that ``symbol_b`` may lag behind
        ``symbol_a`` and still be considered a divergence.
    min_corr\n        Minimum rolling correlation required to accept the signal.
    corr_window\n        Number of candles to use for the rolling correlation.
\n    Returns\n    -------\n    Optional[SmtSignal]\n        ``SmtSignal`` if divergence criteria are met, otherwise ``None``.
    """\n    # Basic validation\n    if sweep_index <= 0 or sweep_index >= len(candles_a):
        return None\n    # Align timestamps – we assume both lists are the same length and share the same time axis.
    # In practice, the bridge returns aligned data; a mismatch will be ignored.
    time_a = candles_a[sweep_index].time
    # Find matching index in B (nearest time not after the sweep)
    idx_b = next((i for i, c in enumerate(candles_b) if c.time <= time_a), None)
    if idx_b is None:
        return None\n    # Determine direction of sweep based on price movement relative to previous candle
    prev = candles_a[sweep_index - 1]
    cur = candles_a[sweep_index]
    direction = OrderType.BUY if cur.close > prev.close else OrderType.SELL\n    # Extreme price on A (high for bullish, low for bearish)
    extreme_price = cur.high if direction == OrderType.BUY else cur.low\n    # Reference price on B at same moment (use close)
    ref_price = candles_b[idx_b].close\n    # Tolerance check – convert pips to price using instrument's point size.
    # Assume both symbols share the same pip size for simplicity; otherwise retrieve from config.
    point = 0.0001  # fallback; could be fetched from InstrumentRegistry.
    tolerance = tolerance_pips * point\n    if direction == OrderType.BUY:
        lag = extreme_price - ref_price\n    else:
        lag = ref_price - extreme_price\n    if lag > tolerance:
        return None\n    # Compute rolling correlation up to sweep_index using close prices.
    closes_a = [c.close for c in candles_a[: sweep_index + 1]]\n    closes_b = [c.close for c in candles_b[: sweep_index + 1]]\n    corr_series = _rolling_correlation(closes_a, closes_b, corr_window)\n    corr_value = corr_series[-1] if corr_series else 0.0\n    if corr_value < min_corr:
        return None\n    return SmtSignal(
        symbol_a=symbol_a,
        symbol_b=symbol_b,
        direction=direction,
        sweep_time=time_a,
        extreme_price=extreme_price,
        reference_price=ref_price,
        correlation=corr_value,
    )\n