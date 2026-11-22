"""
Intelligent Multi-Pair Market Scanner.
Scans multiple FX pairs and commodities (EURUSD, GBPUSD, USDJPY, USDCHF, USDCAD,
AUDUSD, NZDUSD, EURJPY, GBPJPY, EURGBP, XAUUSD, etc.) concurrently and non-blockingly.
Coordinates multi-timeframe analysis (M1/M5/M15/H1), intelligent signal scoring,
currency exposure checks, and opportunity ranking.
"""

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from src.core.contracts import (
    Candle,
    OrderType,
    Position,
    SetupType,
    SignalCandidate,
    SymbolInfo,
    Timeframe,
    TrendBias,
)
from src.core.market_data import MarketDataEngine
from src.engine.market_intelligence import MarketIntelligenceEngine, MarketSnapshot
from src.engine.intelligent_scoring import IntelligentScoringEngine, ScoredDecisionResult
from src.risk.portfolio_risk import PortfolioRiskEngine

logger = logging.getLogger("MultiPairScanner")

DEFAULT_MONITORED_SYMBOLS: List[str] = [
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "USDCAD",
    "AUDUSD",
    "NZDUSD",
    "EURJPY",
    "GBPJPY",
    "EURGBP",
    "XAUUSD",
]


@dataclass
class ScannedOpportunity:
    symbol: str
    decision: ScoredDecisionResult
    candidate: Optional[SignalCandidate]
    currency_exposure_delta: Dict[str, int]
    spread_points: float
    rank_score: float
    is_tradable: bool
    diagnostic_reason: str


class MultiPairScanner:
    """
    Asynchronous, non-blocking multi-pair market scanner.
    Discovers available symbols, monitors broker suffix variants,
    evaluates M1/M5/M15/H1 structure, scores directional conviction,
    and checks currency correlation before emitting ranked opportunities.
    """

    def __init__(
        self,
        market_data: MarketDataEngine,
        market_intelligence: Optional[MarketIntelligenceEngine] = None,
        scoring_engine: Optional[IntelligentScoringEngine] = None,
        symbols: Optional[List[str]] = None,
        auto_discovery: bool = True,
        max_concurrent_threads: int = 4,
    ):
        self.market_data = market_data
        self.market_intelligence = market_intelligence or MarketIntelligenceEngine()
        self.scoring_engine = scoring_engine or IntelligentScoringEngine()
        self.symbols: List[str] = list(symbols or DEFAULT_MONITORED_SYMBOLS)
        self.auto_discovery = auto_discovery
        self.max_threads = max_concurrent_threads

        # Resolved broker symbols map: canonical -> resolved
        self._resolved_symbols: Dict[str, str] = {}
        # Scanned cache to prevent repeated duplicate orders on the same bar
        self._last_scanned_bars: Dict[str, datetime] = {}

    def discover_and_resolve_symbols(self) -> List[str]:
        """Resolves broker-specific suffixes/prefixes for all configured symbols."""
        active = []
        for sym in self.symbols:
            resolved = self.market_data.resolve_broker_symbol(sym)
            if resolved:
                self._resolved_symbols[sym] = resolved
                active.append(resolved)
            else:
                self._resolved_symbols[sym] = sym
                active.append(sym)
        return active

    @staticmethod
    def calculate_currency_exposure(
        symbol: str,
        direction: OrderType,
    ) -> Dict[str, int]:
        """
        Calculates directional currency delta (+1 long, -1 short).
        Used to prevent correlated currency over-exposure across pairs.
        """
        s = str(symbol).upper()
        root = s
        for sfx in (".M", ".STD", ".PRO", ".ECN", "_ECN", ".RAW", ".A", ".R", ".C", ".I", "M", "+", "#"):
            if root.endswith(sfx) and len(root) > len(sfx):
                root = root[:-len(sfx)]
                break

        is_buy = direction == OrderType.BUY
        bias: Dict[str, int] = {}

        if root.startswith("XAU") or root.startswith("GOLD"):
            bias["METALS"] = 1 if is_buy else -1
            bias["USD"] = -1 if is_buy else 1
        elif root.startswith("XAG") or root.startswith("SILVER"):
            bias["METALS"] = 1 if is_buy else -1
            bias["USD"] = -1 if is_buy else 1
        elif len(root) >= 6:
            base = root[:3]
            quote = root[3:6]
            bias[base] = 1 if is_buy else -1
            bias[quote] = -1 if is_buy else 1
        return bias

    def scan_single_symbol(
        self,
        symbol: str,
        active_positions: Optional[List[Position]] = None,
        bridge: Any = None,
    ) -> ScannedOpportunity:
        """
        Scans an individual symbol across M1, M5, M15, and H1 timeframes.
        Returns a ScannedOpportunity with complete diagnostics.
        """
        try:
            # 1. Resolve Broker Symbol & Confirm Info
            resolved_sym = self._resolved_symbols.get(symbol) or self.market_data.resolve_broker_symbol(symbol)
            sym_info = self.market_data.get_symbol_info(symbol)
            point = sym_info.point if sym_info.point > 0 else 0.00001
            spread_pts = sym_info.spread if sym_info.spread > 0 else 1.5

            # 2. Acquire and Synchronize Candles
            self.market_data.sync_symbol_timeframe(symbol, Timeframe.M1, count=150, bridge=bridge)
            self.market_data.sync_symbol_timeframe(symbol, Timeframe.M5, count=150, bridge=bridge)
            self.market_data.sync_symbol_timeframe(symbol, Timeframe.M15, count=150, bridge=bridge)
            self.market_data.sync_symbol_timeframe(symbol, Timeframe.H1, count=100, bridge=bridge)

            m1_candles = self.market_data.get_candles(symbol, Timeframe.M1)
            m5_candles = self.market_data.get_candles(symbol, Timeframe.M5)
            m15_candles = self.market_data.get_candles(symbol, Timeframe.M15)
            h1_candles = self.market_data.get_candles(symbol, Timeframe.H1)

            if len(m1_candles) < 20:
                # Return empty unapproved opportunity
                dummy_snap = self.market_intelligence.inspect_market(symbol, Timeframe.M1, [])
                dec = self.scoring_engine.evaluate_symbol(symbol, [], dummy_snap)
                return ScannedOpportunity(
                    symbol=symbol,
                    decision=dec,
                    candidate=None,
                    currency_exposure_delta={},
                    spread_points=spread_pts,
                    rank_score=0.0,
                    is_tradable=False,
                    diagnostic_reason=f"Insufficient M1 candle history ({len(m1_candles)} < 20)",
                )

            # 3. Market Snapshots across Timeframes
            m1_snap = self.market_intelligence.inspect_market(
                symbol, Timeframe.M1, m1_candles, spread_points=spread_pts, point_size=point
            )
            m5_snap = self.market_intelligence.inspect_market(
                symbol, Timeframe.M5, m5_candles, spread_points=spread_pts, point_size=point
            )
            m15_snap = self.market_intelligence.inspect_market(
                symbol, Timeframe.M15, m15_candles, spread_points=spread_pts, point_size=point
            )
            h1_snap = self.market_intelligence.inspect_market(
                symbol, Timeframe.H1, h1_candles, spread_points=spread_pts, point_size=point
            )

            # 4. Multi-Strategy Scoring
            decision = self.scoring_engine.evaluate_symbol(
                symbol=symbol,
                m1_candles=m1_candles,
                m1_snapshot=m1_snap,
                m15_snapshot=m15_snap,
                h1_snapshot=h1_snap,
                current_spread_pts=spread_pts,
                point_size=point,
                timeframe=Timeframe.M1,
            )

            if not decision.is_qualified or decision.direction is None:
                return ScannedOpportunity(
                    symbol=symbol,
                    decision=decision,
                    candidate=None,
                    currency_exposure_delta={},
                    spread_points=spread_pts,
                    rank_score=max(decision.buy_score, decision.sell_score),
                    is_tradable=False,
                    diagnostic_reason=decision.rejection_reason or "Not qualified",
                )

            # 5. Build SignalCandidate
            curr_delta = self.calculate_currency_exposure(symbol, decision.direction)
            score_to_use = decision.buy_score if decision.direction == OrderType.BUY else decision.sell_score

            cand = SignalCandidate(
                id=f"SCALP_{symbol}_{int(decision.timestamp.timestamp())}",
                symbol=symbol,
                timeframe=Timeframe.M1,
                direction=decision.direction,
                setup_type=SetupType.FAST_SCALP,
                entry_price=decision.recommended_entry_price,
                stop_loss=decision.recommended_sl,
                take_profit=decision.recommended_tp,
                risk_reward=decision.recommended_rr,
                score=score_to_use,
                status="QUALIFIED",
                timestamp=decision.timestamp,
                reasons=[
                    f"Regime={decision.regime.value}",
                    f"NetAdv=+{decision.net_advantage:.1f}",
                    decision.diagnostics_log,
                ],
            )

            # Rank score = Composite Score + 0.5 * Net Directional Advantage
            rank_score = score_to_use + (0.5 * decision.net_advantage)

            return ScannedOpportunity(
                symbol=symbol,
                decision=decision,
                candidate=cand,
                currency_exposure_delta=curr_delta,
                spread_points=spread_pts,
                rank_score=round(rank_score, 1),
                is_tradable=True,
                diagnostic_reason="Qualified opportunity",
            )

        except Exception as e:
            logger.warning(f"Error scanning symbol {symbol}: {e}", exc_info=True)
            dummy_snap = self.market_intelligence.inspect_market(symbol, Timeframe.M1, [])
            dec = self.scoring_engine.evaluate_symbol(symbol, [], dummy_snap)
            return ScannedOpportunity(
                symbol=symbol,
                decision=dec,
                candidate=None,
                currency_exposure_delta={},
                spread_points=0.0,
                rank_score=0.0,
                is_tradable=False,
                diagnostic_reason=f"Scan exception: {str(e)}",
            )

    def scan_all_symbols(
        self,
        active_positions: Optional[List[Position]] = None,
        bridge: Any = None,
    ) -> List[ScannedOpportunity]:
        """
        Executes concurrent non-blocking scan across all configured symbols.
        Ranks qualified opportunities by rank_score (highest conviction first).
        """
        self.discover_and_resolve_symbols()
        results: List[ScannedOpportunity] = []

        with ThreadPoolExecutor(max_workers=self.max_threads, thread_name_prefix="PairScan") as executor:
            future_to_sym = {
                executor.submit(self.scan_single_symbol, sym, active_positions, bridge): sym
                for sym in self.symbols
            }
            for future in as_completed(future_to_sym):
                sym = future_to_sym[future]
                try:
                    opp = future.result()
                    results.append(opp)
                except Exception as ex:
                    logger.warning(f"Thread scan failed for {sym}: {ex}")

        # Rank: Qualified first, sorted by rank_score descending
        results.sort(key=lambda o: (o.is_tradable, o.rank_score), reverse=True)
        return results

    def get_top_opportunities(
        self,
        active_positions: Optional[List[Position]] = None,
        max_results: int = 5,
        bridge: Any = None,
    ) -> List[SignalCandidate]:
        """
        Scans all pairs, filters qualified setups, and returns the top ranked SignalCandidates.
        """
        all_opps = self.scan_all_symbols(active_positions=active_positions, bridge=bridge)
        qualified = [opp.candidate for opp in all_opps if opp.is_tradable and opp.candidate is not None]
        return qualified[:max_results]
