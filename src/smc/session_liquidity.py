"""
Institutional Session Liquidity and Asia Range Engine.
Computes daily Asian Session High, Low, and Midpoint (00:00 - 09:00 UTC).
Registers institutional liquidity pools and detects London Asian-Range Sweeps (Judas Swings).
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, time, timezone, timedelta
from typing import List, Optional, Tuple, Dict, Any

from src.core.contracts import Candle, Timeframe, OrderType, LiquidityZone


@dataclass(frozen=True)
class AsiaRangeLevels:
    symbol: str
    date: str  # YYYY-MM-DD
    asia_high: float
    asia_low: float
    asia_mid: float
    range_pips: float
    bars_count: int


@dataclass(frozen=True)
class AsiaSweepEvent:
    symbol: str
    sweep_type: str  # 'SWEEP_HIGH' or 'SWEEP_LOW'
    sweep_price: float
    asia_level: float
    sweep_distance_pips: float
    direction_bias: OrderType  # BUY for low sweep, SELL for high sweep
    candle_time: datetime
    confirmed: bool
    description: str


class SessionLiquidityEngine:
    """
    Manages session-level liquidity levels and sweep detection.
    """
    def __init__(self, pip_multiplier: float = 10000.0):
        self.pip_multiplier = pip_multiplier

    def calculate_asia_range(
        self,
        symbol: str,
        m15_candles: List[Candle],
        target_date: Optional[datetime] = None
    ) -> Optional[AsiaRangeLevels]:
        """
        Calculates the Asian Session High, Low, and Midpoint for target date (00:00 to 09:00 UTC).
        """
        if not m15_candles:
            return None

        dt_ref = target_date or m15_candles[-1].time
        if dt_ref.tzinfo is None:
            dt_ref = dt_ref.replace(tzinfo=timezone.utc)
        target_day_str = dt_ref.strftime("%Y-%m-%d")

        # Extract bars belonging to Asian session on this date
        asia_candles = []
        for c in m15_candles:
            c_time = c.time if c.time.tzinfo else c.time.replace(tzinfo=timezone.utc)
            if c_time.strftime("%Y-%m-%d") == target_day_str:
                if time(0, 0) <= c_time.time() < time(9, 0):
                    asia_candles.append(c)

        if not asia_candles:
            return None

        h = max(c.high for c in asia_candles)
        l = min(c.low for c in asia_candles)
        mid = round((h + l) / 2.0, 5)
        range_pips = round((h - l) * self.pip_multiplier, 1)

        return AsiaRangeLevels(
            symbol=symbol,
            date=target_day_str,
            asia_high=h,
            asia_low=l,
            asia_mid=mid,
            range_pips=range_pips,
            bars_count=len(asia_candles)
        )

    def register_asia_liquidity_zones(
        self,
        asia_range: AsiaRangeLevels,
        pip_size: float = 0.0001
    ) -> List[LiquidityZone]:
        """
        Creates BSL (Buy-Side Liquidity) at Asia High and SSL (Sell-Side Liquidity) at Asia Low.
        """
        zones: List[LiquidityZone] = []
        tolerance = 2.0 * pip_size

        # Asia High BSL
        zones.append(
            LiquidityZone(
                id=f"{asia_range.symbol}_ASIA_BSL_{asia_range.date}",
                symbol=asia_range.symbol,
                timeframe=Timeframe.M15,
                level_type="BSL",
                price=asia_range.asia_high,
                high=asia_range.asia_high + tolerance,
                low=asia_range.asia_high,
                formation_time=datetime.strptime(asia_range.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            )
        )

        # Asia Low SSL
        zones.append(
            LiquidityZone(
                id=f"{asia_range.symbol}_ASIA_SSL_{asia_range.date}",
                symbol=asia_range.symbol,
                timeframe=Timeframe.M15,
                level_type="SSL",
                price=asia_range.asia_low,
                high=asia_range.asia_low,
                low=asia_range.asia_low - tolerance,
                formation_time=datetime.strptime(asia_range.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            )
        )

        return zones

    def detect_london_asia_sweep(
        self,
        symbol: str,
        m15_candles: List[Candle],
        asia_range: AsiaRangeLevels,
        pip_size: float = 0.0001
    ) -> Optional[AsiaSweepEvent]:
        """
        Evaluates whether current London candle swept Asia High or Low and rejected.
        """
        if not m15_candles or not asia_range:
            return None

        curr = m15_candles[-1]
        c_time = curr.time if curr.time.tzinfo else curr.time.replace(tzinfo=timezone.utc)

        # Must be in London session (06:00 to 12:00 UTC under reference profile)
        if not (time(6, 0) <= c_time.time() < time(12, 0)):
            return None

        # 1. Bearish Judas Swing: Sweeps Asia High then closes back below it
        if curr.high > asia_range.asia_high and curr.close < asia_range.asia_high:
            dist_pips = round((curr.high - asia_range.asia_high) / pip_size, 1)
            return AsiaSweepEvent(
                symbol=symbol,
                sweep_type="SWEEP_HIGH",
                sweep_price=curr.high,
                asia_level=asia_range.asia_high,
                sweep_distance_pips=dist_pips,
                direction_bias=OrderType.SELL,
                candle_time=c_time,
                confirmed=True,
                description=f"London Judas Swing: Swept Asia High {asia_range.asia_high:.5f} by {dist_pips} pips and rejected"
            )

        # 2. Bullish Judas Swing: Sweeps Asia Low then closes back above it
        if curr.low < asia_range.asia_low and curr.close > asia_range.asia_low:
            dist_pips = round((asia_range.asia_low - curr.low) / pip_size, 1)
            return AsiaSweepEvent(
                symbol=symbol,
                sweep_type="SWEEP_LOW",
                sweep_price=curr.low,
                asia_level=asia_range.asia_low,
                sweep_distance_pips=dist_pips,
                direction_bias=OrderType.BUY,
                candle_time=c_time,
                confirmed=True,
                description=f"London Judas Swing: Swept Asia Low {asia_range.asia_low:.5f} by {dist_pips} pips and rejected"
            )

        return None

    def compute_session_key_levels(
        self,
        symbol: str,
        intraday_candles: List[Candle],
        daily_candles: Optional[List[Candle]] = None,
        target_date: Optional[datetime] = None,
        broker_utc_offset_sec: int = 0,
    ) -> Optional["SessionKeyLevels"]:
        """
        Computes session & daily key levels exposed to the SMC layer [VIDEO: scriptedge_-20261114-0001]:
        - Asian High / Low / Midpoint
        - London High / Low
        - Previous-Day High / Low / Midpoint (PDH, PDL, PD Mid)
        - Morning (NY AM 07:00-12:00 NY local) High / Low
        Recomputed cleanly on each new session/day using DST-aware NY time for morning bounds.
        """
        if not intraday_candles:
            return None

        import zoneinfo

        ny_tz = zoneinfo.ZoneInfo("America/New_York")

        def _to_utc(dt: datetime) -> datetime:
            if broker_utc_offset_sec != 0:
                return (dt.replace(tzinfo=None) - timedelta(seconds=int(broker_utc_offset_sec))).replace(tzinfo=timezone.utc)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

        ref_utc = _to_utc(target_date or intraday_candles[-1].time)
        target_day = ref_utc.date()
        prev_day = target_day - timedelta(days=1)

        asia_bars: List[Candle] = []
        london_bars: List[Candle] = []
        morning_bars: List[Candle] = []
        prev_day_bars: List[Candle] = []

        for c in intraday_candles:
            cu = _to_utc(c.time)
            c_day = cu.date()
            c_t = cu.time()
            if c_day == target_day:
                if time(0, 0) <= c_t < time(8, 0):
                    asia_bars.append(c)
                if time(7, 0) <= c_t < time(13, 0):
                    london_bars.append(c)
                c_ny = cu.astimezone(ny_tz)
                if c_ny.date() == ref_utc.astimezone(ny_tz).date() and time(7, 0) <= c_ny.time() < time(12, 0):
                    morning_bars.append(c)
            elif c_day == prev_day:
                prev_day_bars.append(c)

        # Fallback for previous trading day (e.g. Monday -> Friday)
        if not prev_day_bars and not daily_candles:
            earlier = [c for c in intraday_candles if _to_utc(c.time).date() < target_day]
            if earlier:
                last_prev_day = _to_utc(earlier[-1].time).date()
                prev_day_bars = [c for c in earlier if _to_utc(c.time).date() == last_prev_day]

        pdh: Optional[float] = None
        pdl: Optional[float] = None
        if daily_candles and len(daily_candles) >= 2:
            prev_d = daily_candles[-2]
            pdh = prev_d.high
            pdl = prev_d.low
        elif prev_day_bars:
            pdh = max(c.high for c in prev_day_bars)
            pdl = min(c.low for c in prev_day_bars)

        pd_mid = round((pdh + pdl) / 2.0, 5) if (pdh is not None and pdl is not None) else None

        asian_high = max(c.high for c in asia_bars) if asia_bars else None
        asian_low = min(c.low for c in asia_bars) if asia_bars else None
        asian_mid = (
            round((asian_high + asian_low) / 2.0, 5)
            if (asian_high is not None and asian_low is not None)
            else None
        )
        london_high = max(c.high for c in london_bars) if london_bars else None
        london_low = min(c.low for c in london_bars) if london_bars else None
        morning_high = max(c.high for c in morning_bars) if morning_bars else None
        morning_low = min(c.low for c in morning_bars) if morning_bars else None

        return SessionKeyLevels(
            symbol=symbol,
            date=target_day.isoformat(),
            asian_high=asian_high,
            asian_low=asian_low,
            asian_mid=asian_mid,
            london_high=london_high,
            london_low=london_low,
            pdh=pdh,
            pdl=pdl,
            pd_mid=pd_mid,
            morning_high=morning_high,
            morning_low=morning_low,
        )


@dataclass(frozen=True)
class SessionKeyLevels:
    """Session and previous-day key reference levels [VIDEO: scriptedge_-20261114-0001]."""

    symbol: str
    date: str
    asian_high: Optional[float] = None
    asian_low: Optional[float] = None
    asian_mid: Optional[float] = None
    london_high: Optional[float] = None
    london_low: Optional[float] = None
    pdh: Optional[float] = None
    pdl: Optional[float] = None
    pd_mid: Optional[float] = None
    morning_high: Optional[float] = None
    morning_low: Optional[float] = None

    def to_liquidity_zones(self, pip_size: float = 0.01) -> List[LiquidityZone]:
        """Converts populated key levels into LiquidityZone targets for P9/P10."""
        tol = 2.0 * pip_size
        base_dt = datetime.strptime(self.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        mapping = [
            ("ASIA_HIGH", "BSL", self.asian_high),
            ("ASIA_LOW", "SSL", self.asian_low),
            ("LONDON_HIGH", "BSL", self.london_high),
            ("LONDON_LOW", "SSL", self.london_low),
            ("PDH", "BSL", self.pdh),
            ("PDL", "SSL", self.pdl),
            ("PD_MID", "PD_MID", self.pd_mid),
            ("MORNING_HIGH", "BSL", self.morning_high),
            ("MORNING_LOW", "SSL", self.morning_low),
        ]
        zones: List[LiquidityZone] = []
        for tag, ltype, px in mapping:
            if px is None:
                continue
            zones.append(
                LiquidityZone(
                    id=f"{self.symbol}_{tag}_{self.date}",
                    symbol=self.symbol,
                    timeframe=Timeframe.M15,
                    level_type=ltype,
                    price=px,
                    high=px + tol if ltype == "BSL" else px,
                    low=px - tol if ltype == "SSL" else px,
                    formation_time=base_dt,
                )
            )
        return zones
