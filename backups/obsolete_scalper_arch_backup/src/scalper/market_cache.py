"""
Phase 2 & Phase 11: Event-Driven Market Data & Incremental Indicator Cache.
Provides:
- TickCache per active instrument with duplicate-tick detection and staleness validation
- Incremental IndicatorCache avoiding redundant M1/M5/M15/H1 recalculation when market data has not changed
- Market Regime detection (TRENDING_EXPANSION, NORMAL_LIQUID, COMPRESSED_RANGE, EXTREME_VOLATILITY)
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
import math
import time
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple


@dataclass
class CachedTick:
    symbol: str
    bid: float
    ask: float
    timestamp: float
    volume: float = 1.0
    seq_id: int = 0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) * 0.5


@dataclass
class TickValidationResult:
    is_valid: bool
    is_new_tick: bool
    is_stale: bool
    age_ms: float
    spread_points: float
    reason: str = "OK"
    tick: Optional[CachedTick] = None


@dataclass
class IndicatorSnapshot:
    symbol_key: str
    computed_at: float
    tick_seq: int
    m1_bar_time: float = 0.0
    atr_m1: float = 0.0
    atr_m5: float = 0.0
    atr_m15: float = 0.0
    ema_fast_m1: float = 0.0
    ema_slow_m1: float = 0.0
    m1_trend_bias: float = 0.0     # [-1.0, +1.0]
    m5_structure_bias: float = 0.0 # [-1.0, +1.0]
    m15_market_bias: float = 0.0   # [-1.0, +1.0]
    h1_macro_bias: float = 0.0     # [-1.0, +1.0]
    rsi_m1: float = 50.0
    adx_m5: float = 20.0
    swing_high_m1: float = 0.0
    swing_low_m1: float = 0.0
    swing_high_m5: float = 0.0
    swing_low_m5: float = 0.0
    support_level: float = 0.0
    resistance_level: float = 0.0
    candle_displacement: float = 0.0
    tick_momentum: float = 0.0
    tick_activity_rate: float = 0.0
    spread_points: float = 0.0
    spread_to_atr_ratio: float = 0.0
    volatility_regime: str = "NORMAL_LIQUID"  # TRENDING_EXPANSION, NORMAL_LIQUID, COMPRESSED_RANGE, EXTREME_VOLATILITY


class TickCache:
    """
    Maintains a low-latency ring buffer of ticks per symbol, validating freshness
    and filtering duplicate ticks.
    """

    def __init__(self, max_ticks: int = 500):
        self.max_ticks = max_ticks
        self._buffers: Dict[str, Deque[CachedTick]] = {}
        self._seq_counters: Dict[str, int] = {}
        self.cache_hits: int = 0
        self.duplicate_ticks_filtered: int = 0
        self.stale_ticks_rejected: int = 0

    def push_tick(
        self,
        symbol: str,
        bid: float,
        ask: float,
        timestamp: Optional[float] = None,
        point: float = 0.01,
        staleness_limit_ms: int = 5000,
        now_override: Optional[float] = None,
    ) -> TickValidationResult:
        sym = symbol.upper()
        now_ts = now_override if now_override is not None else time.time()
        tick_ts = timestamp if timestamp is not None and timestamp > 0 else now_ts

        if bid <= 0 or ask <= 0 or ask < bid:
            return TickValidationResult(
                is_valid=False,
                is_new_tick=False,
                is_stale=False,
                age_ms=0.0,
                spread_points=0.0,
                reason=f"INVALID_QUOTES: bid={bid}, ask={ask}",
            )

        age_ms = max(0.0, (now_ts - tick_ts) * 1000.0)
        pt = point if point > 0 else 0.01
        spread_pts = round((ask - bid) / pt, 1)

        if staleness_limit_ms > 0 and age_ms > staleness_limit_ms:
            self.stale_ticks_rejected += 1
            return TickValidationResult(
                is_valid=False,
                is_new_tick=False,
                is_stale=True,
                age_ms=round(age_ms, 2),
                spread_points=spread_pts,
                reason=f"STALE_TICK: age {age_ms:.1f}ms > limit {staleness_limit_ms}ms",
            )

        buf = self._buffers.setdefault(sym, deque(maxlen=self.max_ticks))
        if buf:
            last = buf[-1]
            if abs(last.bid - bid) < 1e-9 and abs(last.ask - ask) < 1e-9 and abs(last.timestamp - tick_ts) < 1e-6:
                self.duplicate_ticks_filtered += 1
                return TickValidationResult(
                    is_valid=True,
                    is_new_tick=False,
                    is_stale=False,
                    age_ms=round(age_ms, 2),
                    spread_points=spread_pts,
                    reason="DUPLICATE_TICK",
                    tick=last,
                )

        seq = self._seq_counters.get(sym, 0) + 1
        self._seq_counters[sym] = seq
        ct = CachedTick(symbol=sym, bid=bid, ask=ask, timestamp=tick_ts, seq_id=seq)
        buf.append(ct)
        return TickValidationResult(
            is_valid=True,
            is_new_tick=True,
            is_stale=False,
            age_ms=round(age_ms, 2),
            spread_points=spread_pts,
            reason="OK",
            tick=ct,
        )

    def get_recent_ticks(self, symbol: str, count: int = 30) -> List[CachedTick]:
        buf = self._buffers.get(symbol.upper())
        if not buf:
            return []
        self.cache_hits += 1
        if count >= len(buf):
            return list(buf)
        return list(buf)[-count:]

    def get_latest_tick(self, symbol: str) -> Optional[CachedTick]:
        buf = self._buffers.get(symbol.upper())
        return buf[-1] if buf else None


class IndicatorCache:
    """
    Incremental multi-timeframe indicator cache.
    Reuses cached indicator calculations when neither the bar timestamp nor the tick sequence has advanced.
    """

    def __init__(self):
        self._snapshots: Dict[str, IndicatorSnapshot] = {}
        self.recalculations: int = 0
        self.cache_hits: int = 0

    @staticmethod
    def _extract_ohlc(bar: Any) -> Tuple[float, float, float, float, float]:
        if isinstance(bar, dict):
            o = float(bar.get("open", bar.get("close", 0.0)))
            h = float(bar.get("high", o))
            l = float(bar.get("low", o))
            c = float(bar.get("close", o))
            t = float(bar.get("time", 0.0))
            return o, h, l, c, t
        c = float(getattr(bar, "close", 0.0))
        o = float(getattr(bar, "open", c))
        h = float(getattr(bar, "high", max(o, c)))
        l = float(getattr(bar, "low", min(o, c)))
        t = float(getattr(bar, "time", 0.0))
        return o, h, l, c, t

    @classmethod
    def _compute_atr(cls, bars: Sequence[Any], period: int = 14, default_atr: float = 1.0) -> float:
        if not bars or len(bars) < 2:
            return default_atr
        subset = bars[-min(len(bars), period + 1):]
        trs: List[float] = []
        prev_c: Optional[float] = None
        for b in subset:
            o, h, l, c, _ = cls._extract_ohlc(b)
            if h <= 0 or l <= 0:
                h = max(o, c)
                l = min(o, c)
            if prev_c is None:
                tr = max(h - l, abs(c - o))
            else:
                tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            trs.append(max(0.0, tr))
            prev_c = c
        avg_tr = sum(trs) / len(trs) if trs else 0.0
        return avg_tr if avg_tr > 0 else default_atr

    @classmethod
    def _compute_ema(cls, closes: Sequence[float], period: int) -> float:
        if not closes:
            return 0.0
        k = 2.0 / (period + 1.0)
        ema = closes[0]
        for px in closes[1:]:
            ema = px * k + ema * (1.0 - k)
        return ema

    @classmethod
    def _compute_rsi(cls, closes: Sequence[float], period: int = 14) -> float:
        if len(closes) < 3:
            return 50.0
        subset = closes[-min(len(closes), period + 1):]
        gains = 0.0
        losses = 0.0
        for i in range(1, len(subset)):
            diff = subset[i] - subset[i - 1]
            if diff > 0:
                gains += diff
            else:
                losses += abs(diff)
        if gains + losses == 0:
            return 50.0
        rs = gains / max(1e-9, losses)
        return round(100.0 - (100.0 / (1.0 + rs)), 2)

    def get_or_update(
        self,
        symbol_key: str,
        ticks: Sequence[Any],
        m1_bars: Optional[Sequence[Any]] = None,
        m5_bars: Optional[Sequence[Any]] = None,
        m15_bars: Optional[Sequence[Any]] = None,
        h1_bars: Optional[Sequence[Any]] = None,
        point: float = 0.01,
        spread_points: float = 25.0,
    ) -> IndicatorSnapshot:
        sym_k = symbol_key.upper()
        is_btc = "BTC" in sym_k
        default_atr = 35.0 if is_btc else 0.80
        sat_scale = 25.0 if is_btc else 0.50

        tick_seq = getattr(ticks[-1], "seq_id", len(ticks)) if ticks else 0
        m1_last_t = 0.0
        if m1_bars:
            _, _, _, _, m1_last_t = self._extract_ohlc(m1_bars[-1])

        existing = self._snapshots.get(sym_k)
        if existing and existing.tick_seq == tick_seq and existing.m1_bar_time == m1_last_t and tick_seq > 0:
            self.cache_hits += 1
            return existing

        self.recalculations += 1

        # Extract M1 closes, highs, lows
        m1_closes: List[float] = []
        m1_highs: List[float] = []
        m1_lows: List[float] = []
        displacement = 0.0
        if m1_bars:
            for b in m1_bars[-30:]:
                o, h, l, c, _ = self._extract_ohlc(b)
                if c > 0:
                    m1_closes.append(c)
                    m1_highs.append(max(h, o, c))
                    m1_lows.append(min(l, o, c) if l > 0 else min(o, c))
            if m1_bars:
                o_last, _, _, c_last, _ = self._extract_ohlc(m1_bars[-1])
                displacement = c_last - o_last

        # Fallback to tick prices if M1 bars are not provided
        if not m1_closes and ticks:
            for t in ticks[-30:]:
                px = float(getattr(t, "bid", getattr(t, "price", 0.0)))
                if px > 0:
                    m1_closes.append(px)
                    m1_highs.append(px)
                    m1_lows.append(px)
            if len(m1_closes) >= 2:
                displacement = m1_closes[-1] - m1_closes[0]

        atr_m1 = self._compute_atr(m1_bars or [], 14, default_atr)
        if not m1_bars and len(m1_closes) >= 2:
            diffs = [abs(m1_closes[i] - m1_closes[i - 1]) for i in range(1, len(m1_closes))]
            atr_m1 = max(default_atr * 0.4, (sum(diffs) / len(diffs)) * 3.0)

        atr_m5 = self._compute_atr(m5_bars or [], 14, atr_m1 * 2.0)
        atr_m15 = self._compute_atr(m15_bars or [], 14, atr_m5 * 1.6)

        ema_fast = self._compute_ema(m1_closes[-12:], 5) if m1_closes else 0.0
        ema_slow = self._compute_ema(m1_closes[-25:], 13) if m1_closes else 0.0
        m1_bias = max(-1.0, min(1.0, (ema_fast - ema_slow) / max(1e-6, sat_scale))) if ema_Slow_ok(ema_fast, ema_slow) else 0.0

        # M5 structure bias
        m5_bias = m1_bias
        swing_h_m5 = max(m1_highs[-15:]) if m1_highs else 0.0
        swing_l_m5 = min(m1_lows[-15:]) if m1_lows else 0.0
        if m5_bars and len(m5_bars) >= 2:
            o0, _, _, _, _ = self._extract_ohlc(m5_bars[0])
            _, _, _, c1, _ = self._extract_ohlc(m5_bars[-1])
            m5_bias = max(-1.0, min(1.0, (c1 - o0) / max(1e-6, sat_scale * 2.0)))

        # M15 & H1 bias
        m15_bias = m5_bias
        if m15_bars and len(m15_bars) >= 2:
            o0, _, _, _, _ = self._extract_ohlc(m15_bars[0])
            _, _, _, c1, _ = self._extract_ohlc(m15_bars[-1])
            m15_bias = max(-1.0, min(1.0, (c1 - o0) / max(1e-6, sat_scale * 3.0)))

        h1_bias = m15_bias
        if h1_bars and len(h1_bars) >= 2:
            o0, _, _, _, _ = self._extract_ohlc(h1_bars[0])
            _, _, _, c1, _ = self._extract_ohlc(h1_bars[-1])
            h1_bias = max(-1.0, min(1.0, (c1 - o0) / max(1e-6, sat_scale * 5.0)))

        # Tick momentum & activity
        tick_mom = 0.0
        tick_rate = float(len(ticks))
        if ticks and len(ticks) >= 2:
            p0 = float(getattr(ticks[0], "bid", getattr(ticks[0], "price", 0.0)))
            p1 = float(getattr(ticks[-1], "bid", getattr(ticks[-1], "price", 0.0)))
            if p0 > 0 and p1 > 0:
                tick_mom = max(-1.0, min(1.0, (p1 - p0) / sat_scale))

        rsi_m1 = self._compute_rsi(m1_closes, 14)
        swing_h_m1 = max(m1_highs[-10:]) if m1_highs else 0.0
        swing_l_m1 = min(m1_lows[-10:]) if m1_lows else 0.0

        pt = point if point > 0 else 0.01
        atr_m1_pts = max(1.0, atr_m1 / pt)
        spread_to_atr = round(spread_points / atr_m1_pts, 4)

        # Volatility regime classification
        if spread_to_atr > 0.65 or atr_m1 > default_atr * 4.0:
            regime = "EXTREME_VOLATILITY"
        elif abs(tick_mom) >= 0.45 or abs(displacement) >= atr_m1 * 0.6:
            regime = "TRENDING_EXPANSION"
        elif atr_m1 < default_atr * 0.25 and abs(tick_mom) < 0.08:
            regime = "COMPRESSED_RANGE"
        else:
            regime = "NORMAL_LIQUID"

        snap = IndicatorSnapshot(
            symbol_key=sym_k,
            computed_at=time.time(),
            tick_seq=tick_seq,
            m1_bar_time=m1_last_t,
            atr_m1=round(atr_m1, 4),
            atr_m5=round(atr_m5, 4),
            atr_m15=round(atr_m15, 4),
            ema_fast_m1=round(ema_fast, 4),
            ema_slow_m1=round(ema_slow, 4),
            m1_trend_bias=round(m1_bias, 4),
            m5_structure_bias=round(m5_bias, 4),
            m15_market_bias=round(m15_bias, 4),
            h1_macro_bias=round(h1_bias, 4),
            rsi_m1=rsi_m1,
            adx_m5=round(20.0 + abs(m5_bias) * 25.0, 2),
            swing_high_m1=round(swing_h_m1, 4),
            swing_low_m1=round(swing_l_m1, 4),
            swing_high_m5=round(swing_h_m5, 4),
            swing_low_m5=round(swing_l_m5, 4),
            support_level=round(swing_l_m5, 4),
            resistance_level=round(swing_h_m5, 4),
            candle_displacement=round(displacement, 4),
            tick_momentum=round(tick_mom, 4),
            tick_activity_rate=tick_rate,
            spread_points=spread_points,
            spread_to_atr_ratio=spread_to_atr,
            volatility_regime=regime,
        )
        self._snapshots[sym_k] = snap
        return snap


def ema_Slow_ok(fast: float, slow: float) -> bool:
    return fast > 0 and slow > 0
