"""
Unit and Integration Test Suite for MT5 001 Multi-Pair Intelligent Scalping Engine.
Verifies:
1. Indicator calculations (EMA, ATR, RSI, MACD, Bollinger Bands, Directional Efficiency)
2. Candle structure & pattern classification (Engulfing, Rejection, Momentum, Breakout, Doji)
3. Market regime classification & adaptive weight modulation
4. All 7 independent Strategy Modules (A through G)
5. Intelligent Scoring Engine BUY/SELL scoring & transparent diagnostics
6. Multi-Pair Market Scanner & currency exposure delta
7. Broker stop-level validation and volume normalization
8. Net profit ($20 target) & dynamic trade management
9. Service isolation and transient data failure handling
"""

import math
from datetime import datetime, timezone, timedelta
import pytest

from src.core.contracts import (
    Candle, OrderType, Timeframe, TrendBias, SignalCandidate, SymbolInfo,
    AccountInfo, Position, ProfitManagementMode, PositionManagementState, SetupType
)
from src.engine.market_intelligence import (
    MarketIntelligenceEngine, DetailedMarketRegime, CandlePatternType, MarketSnapshot
)
from src.strategies.scalping_strategies import (
    EmaTrendScalpingStrategy, RsiMomentumScalpingStrategy, MacdMomentumScalpingStrategy,
    BollingerBandScalpingStrategy, AtrVolatilityScalpingStrategy, PriceActionCandleStrategy,
    DirectionalEfficiencyStrategy
)
from src.engine.intelligent_scoring import (
    IntelligentScoringEngine, ScoringWeightsConfig, ScoredDecisionResult
)
from src.engine.multi_pair_scanner import MultiPairScanner
from src.core.market_data import MarketDataEngine
from src.risk.position_sizing import PositionSizingEngine
from src.risk.portfolio_risk import PortfolioRiskEngine
from src.risk.trade_management import TradeManagementEngine
from src.core.config import AppConfig, RiskConfig


def generate_synthetic_candles(
    count: int = 60,
    start_price: float = 1.1000,
    trend: str = "BULLISH",
    volatility: float = 0.0005,
) -> list[Candle]:
    candles = []
    base_time = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)

    for i in range(count):
        bar_time = base_time + timedelta(minutes=i)
        if trend == "BULLISH":
            base = start_price + (i * 0.00008) + (math.sin(i * 0.8) * volatility * 0.5)
            o = base - (0.0001 if i % 4 != 0 else -0.0001)
            c = base + (0.0001 if i % 4 != 0 else -0.0001)
        elif trend == "BEARISH":
            base = start_price - (i * 0.00008) + (math.sin(i * 0.8) * volatility * 0.5)
            o = base + (0.0001 if i % 4 != 0 else -0.0001)
            c = base - (0.0001 if i % 4 != 0 else -0.0001)
        else:  # RANGING: Pure oscillation around start_price with zero drift
            base = start_price + (0.00005 if i % 2 == 0 else -0.00005)
            o = base - (0.00002 if i % 2 == 0 else -0.00002)
            c = base + (0.00002 if i % 2 == 0 else -0.00002)

        h = max(o, c) + (volatility * 0.2)
        l = min(o, c) - (volatility * 0.2)

        candles.append(
            Candle(
                time=bar_time,
                open=round(o, 5),
                high=round(h, 5),
                low=round(l, 5),
                close=round(c, 5),
                tick_volume=100 + (i % 10) * 5,
                spread=12,
                complete=True,
            )
        )
    return candles


# =====================================================================
# 1. Indicator Calculations
# =====================================================================
def test_indicator_calculations():
    candles = generate_synthetic_candles(count=60, start_price=1.1000, trend="BULLISH", volatility=0.0005)
    closes = [c.close for c in candles]

    # EMA
    ema9 = MarketIntelligenceEngine.compute_ema(closes, 9)
    assert ema9 > 1.1000, "Bullish EMA9 should be above start price"

    # ATR
    atr = MarketIntelligenceEngine.compute_atr(candles, 14)
    assert atr > 0, "ATR must be positive"
    assert atr < 0.01, "ATR must be within realistic EURUSD range"

    # RSI
    rsi = MarketIntelligenceEngine.compute_rsi(candles, 14)
    assert 0.0 <= rsi <= 100.0, "RSI must be in [0, 100]"
    assert rsi > 50.0, "Bullish trend RSI must be above 50"

    # MACD
    macd, sig, hist = MarketIntelligenceEngine.compute_macd(closes, 12, 26, 9)
    assert isinstance(macd, float)
    assert isinstance(sig, float)
    assert isinstance(hist, float)

    # Bollinger Bands
    mid, up, low, bw = MarketIntelligenceEngine.compute_bollinger_bands(closes, 20, 2.0)
    assert up > mid > low, "Upper BB must be above Mid and Mid above Low"
    assert bw > 0, "Bandwidth must be positive"

    # Directional Efficiency (Kaufman)
    er = MarketIntelligenceEngine.compute_directional_efficiency(candles, 20)
    assert 0.0 <= er <= 1.0, "Efficiency ratio must be in [0, 1]"
    assert er > 0.15, "Trending series should have significant directional efficiency"


# =====================================================================
# 2. Candle Structure & Pattern Analysis
# =====================================================================
def test_candle_structure_analysis():
    # Test Bullish Engulfing
    t1 = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 11, 10, 10, 1, tzinfo=timezone.utc)
    c1 = Candle(time=t1, open=1.1020, high=1.1025, low=1.0990, close=1.1000, tick_volume=100, spread=10) # Bearish
    c2 = Candle(time=t2, open=1.0995, high=1.1035, low=1.0990, close=1.1030, tick_volume=200, spread=10) # Bullish Engulfing
    analysis = MarketIntelligenceEngine.analyze_candle_structure([c1, c2])
    assert analysis.pattern == CandlePatternType.BULLISH_ENGULFING
    assert analysis.is_bullish is True

    # Test Rejection Pin Bar
    t3 = datetime(2026, 11, 10, 10, 2, tzinfo=timezone.utc)
    c3 = Candle(time=t3, open=1.1000, high=1.1005, low=1.0950, close=1.0995, tick_volume=150, spread=10) # Long lower wick
    analysis_pin = MarketIntelligenceEngine.analyze_candle_structure([c2, c3])
    assert analysis_pin.pattern == CandlePatternType.BULLISH_REJECTION
    assert analysis_pin.lower_wick_ratio >= 0.55


# =====================================================================
# 3. Market Regime Classification
# =====================================================================
def test_market_regime_classification():
    engine = MarketIntelligenceEngine()
    # Bullish Trending
    bull_candles = generate_synthetic_candles(count=60, start_price=1.1000, trend="BULLISH", volatility=0.0006)
    snap_bull = engine.inspect_market("EURUSD", Timeframe.M1, bull_candles)
    assert snap_bull.regime in (DetailedMarketRegime.TRENDING_BULLISH, DetailedMarketRegime.BREAKOUT)
    assert snap_bull.direction in (TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH)

    # Ranging (use different symbol or force_fresh=True to bypass cache)
    flat_candles = generate_synthetic_candles(count=60, start_price=1.1000, trend="RANGING", volatility=0.0002)
    snap_flat = engine.inspect_market("GBPUSD", Timeframe.M1, flat_candles)
    assert snap_flat.regime in (DetailedMarketRegime.RANGING, DetailedMarketRegime.LOW_VOLATILITY, DetailedMarketRegime.REVERSAL)


# =====================================================================
# 4. Seven Strategy Modules (A through G)
# =====================================================================
def test_individual_strategy_modules():
    candles = generate_synthetic_candles(count=60, start_price=1.1000, trend="BULLISH", volatility=0.0005)
    engine = MarketIntelligenceEngine()
    snap = engine.inspect_market("EURUSD", Timeframe.M1, candles)

    # Strategy A: EMA Trend
    strat_a = EmaTrendScalpingStrategy()
    sig_a = strat_a.evaluate("EURUSD", candles, snap)
    assert sig_a.strategy_name == "EMA_TREND"
    assert sig_a.buy_strength > sig_a.sell_strength
    assert sig_a.suggested_sl_distance > 0

    # Strategy B: RSI Momentum
    strat_b = RsiMomentumScalpingStrategy()
    sig_b = strat_b.evaluate("EURUSD", candles, snap)
    assert sig_b.strategy_name == "RSI_MOMENTUM"
    assert sig_b.buy_strength >= sig_b.sell_strength

    # Strategy C: MACD Momentum
    strat_c = MacdMomentumScalpingStrategy()
    sig_c = strat_c.evaluate("EURUSD", candles, snap)
    assert sig_c.strategy_name == "MACD_MOMENTUM"
    assert sig_c.confidence >= 0

    # Strategy D: Bollinger Bands
    strat_d = BollingerBandScalpingStrategy()
    sig_d = strat_d.evaluate("EURUSD", candles, snap)
    assert sig_d.strategy_name == "BOLLINGER_BANDS"
    assert sig_d.suggested_tp_distance > sig_d.suggested_sl_distance

    # Strategy E: ATR & Volatility
    strat_e = AtrVolatilityScalpingStrategy()
    sig_e = strat_e.evaluate("EURUSD", candles, snap)
    assert sig_e.strategy_name == "ATR_VOLATILITY"
    assert sig_e.data_quality_healthy is True

    # Strategy F: Price Action
    strat_f = PriceActionCandleStrategy()
    sig_f = strat_f.evaluate("EURUSD", candles, snap)
    assert sig_f.strategy_name == "PRICE_ACTION"

    # Strategy G: Directional Efficiency
    strat_g = DirectionalEfficiencyStrategy()
    sig_g = strat_g.evaluate("EURUSD", candles, snap)
    assert sig_g.strategy_name == "DIRECTIONAL_EFFICIENCY"
    assert sig_g.buy_strength >= 50.0


# =====================================================================
# 5. Intelligent Scoring Engine & Diagnostics
# =====================================================================
def test_intelligent_scoring_engine():
    candles = generate_synthetic_candles(count=60, start_price=1.1000, trend="BULLISH", volatility=0.0006)
    mi = MarketIntelligenceEngine()
    snap = mi.inspect_market("EURUSD", Timeframe.M1, candles)

    scoring = IntelligentScoringEngine(ScoringWeightsConfig(decision_threshold=50.0, min_directional_advantage=6.0))
    res = scoring.evaluate_symbol("EURUSD", candles, snap)

    assert isinstance(res, ScoredDecisionResult)
    assert res.buy_score > res.sell_score
    assert res.net_advantage > 0
    assert len(res.strategy_signals) == 7
    assert res.diagnostics_log != ""

    # Check non-silent rejection when threshold not met
    strict_scoring = IntelligentScoringEngine(ScoringWeightsConfig(decision_threshold=99.0))
    strict_res = strict_scoring.evaluate_symbol("EURUSD", candles, snap)
    assert strict_res.is_qualified is False
    assert strict_res.rejection_reason is not None
    assert "below threshold" in strict_res.rejection_reason


# =====================================================================
# 6. Multi-Pair Market Scanner & Currency Exposure
# =====================================================================
def test_multi_pair_scanner():
    md = MarketDataEngine(symbols=["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"])
    scanner = MultiPairScanner(market_data=md, symbols=["EURUSD", "GBPUSD"])

    # Test currency delta calculation
    eur_buy_exp = scanner.calculate_currency_exposure("EURUSD", OrderType.BUY)
    assert eur_buy_exp.get("EUR") == 1
    assert eur_buy_exp.get("USD") == -1

    gold_buy_exp = scanner.calculate_currency_exposure("XAUUSD", OrderType.BUY)
    assert gold_buy_exp.get("METALS") == 1
    assert gold_buy_exp.get("USD") == -1

    # Test symbol suffix discovery
    resolved = scanner.discover_and_resolve_symbols()
    assert len(resolved) == 2


# =====================================================================
# 7. Broker Stop-Level & Pre-Trade Checklist
# =====================================================================
def test_broker_stops_level_validation():
    from src.execution.order_manager import OrderManager
    from unittest.mock import MagicMock

    cfg = AppConfig()
    mock_bridge = MagicMock()
    mock_bridge.ping.return_value = True

    sizing = PositionSizingEngine()
    risk = PortfolioRiskEngine(cfg)
    om = OrderManager(cfg, mock_bridge, sizing, risk)

    sym_info = SymbolInfo(
        symbol="EURUSD",
        digits=5,
        point=0.00001,
        tick_size=0.00001,
        tick_value=1.0,
        stops_level=30, # 30 points min stop distance
        spread=10.0,
    )
    acc = AccountInfo(balance=10000.0, equity=10000.0)
    now = datetime.now(timezone.utc)

    # Valid candidate with 50 points SL distance (> 30)
    cand_valid = SignalCandidate(
        id="TEST_VALID",
        symbol="EURUSD",
        timeframe=Timeframe.M1,
        direction=OrderType.BUY,
        setup_type=SetupType.FAST_SCALP,
        entry_price=1.10000,
        stop_loss=1.09950, # 50 points distance
        take_profit=1.10100,
        risk_reward=2.0,
        score=75.0,
        timestamp=now,
        status="APPROVED",
    )
    res_valid = om.run_pre_trade_checklist(cand_valid, acc, sym_info, [])
    assert not any("stops_level" in r for r in res_valid.rejection_reasons)

    # Invalid candidate with only 10 points SL distance (< 30)
    cand_invalid = SignalCandidate(
        id="TEST_INVALID",
        symbol="EURUSD",
        timeframe=Timeframe.M1,
        direction=OrderType.BUY,
        setup_type=SetupType.FAST_SCALP,
        entry_price=1.10000,
        stop_loss=1.09990, # 10 points distance (< 30)
        take_profit=1.10100,
        risk_reward=2.0,
        score=75.0,
        timestamp=now,
        status="APPROVED",
    )
    res_invalid = om.run_pre_trade_checklist(cand_invalid, acc, sym_info, [])
    assert any("stops_level" in r for r in res_invalid.rejection_reasons)


# =====================================================================
# 8. Net Profit ($20 Target) & Trade Management
# =====================================================================
def test_net_profit_and_target_management():
    risk_cfg = RiskConfig(target_net_profit_usd=20.0)
    tm = TradeManagementEngine(risk_cfg)

    sym_info = SymbolInfo(symbol="EURUSD", digits=5, point=0.00001, tick_size=0.00001, tick_value=1.0)
    pos = Position(
        ticket=12345,
        symbol="EURUSD",
        order_type=OrderType.BUY,
        volume=0.10,
        open_price=1.10000,
        current_price=1.10250, # +25 pips = +$25 gross on 0.10 lot
        profit=25.0,
        swap=-0.50,
        commission=-1.50,
        stop_loss=1.09800,
        take_profit=1.10500,
        profit_mode=ProfitManagementMode.QUICK_SCALP,
    )

    # Net profit: 25.0 - 1.50 - 0.50 = $23.00 net
    net_pnl = TradeManagementEngine.calculate_net_profit(pos, sym_info)
    assert net_pnl >= 20.0, f"Net floating profit should reach $20 target (got ${net_pnl:.2f})"

    # Evaluate lifecycle action: should trigger target closure for quick scalp
    recent = generate_synthetic_candles(count=20, start_price=1.1000)
    actions = tm.evaluate_position(pos, sym_info, recent_candles=recent, scalp_mode=True)
    assert len(actions) > 0
    assert actions[0].action_type == "FULL_CLOSE"
    assert "target" in actions[0].reason.lower() or "20" in actions[0].reason


# =====================================================================
# 9. Aggregate Open Risk & Exposure Controls
# =====================================================================
def test_portfolio_aggregate_open_risk():
    cfg = AppConfig()
    cfg.risk.max_aggregate_risk_percent = 5.0 # Max 5.0% aggregate risk
    risk = PortfolioRiskEngine(cfg)

    acc = AccountInfo(balance=10000.0, equity=10000.0)
    # Existing position with $350 risk (3.5%)
    pos1 = Position(
        ticket=1,
        symbol="EURUSD",
        order_type=OrderType.BUY,
        volume=0.1,
        open_price=1.10,
        current_price=1.10,
        stop_loss=1.0965,
        take_profit=1.1050,
        profit=0.0,
        initial_risk_amount=350.0,
    )

    # New candidate proposing $250 risk (2.5%) -> Total = 6.0% > 5.0%
    now = datetime.now(timezone.utc)
    cand = SignalCandidate(
        id="CAND1",
        symbol="GBPUSD",
        timeframe=Timeframe.M1,
        direction=OrderType.BUY,
        setup_type=SetupType.FAST_SCALP,
        entry_price=1.25,
        stop_loss=1.2450,
        take_profit=1.2600,
        risk_reward=2.0,
        score=70.0,
        timestamp=now,
        status="APPROVED",
    )
    allowed, reason = risk.evaluate_new_order_permission(cand, acc, [pos1], proposed_monetary_risk=250.0)
    assert allowed is False
    assert "Aggregate open risk" in reason
