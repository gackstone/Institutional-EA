"""
Verification and Integration Suite for Advanced MT5 Scalping Execution
and Self-Training AI Engine Closed-Loop Integration.
"""

import os
import tempfile
import time
from datetime import datetime, timezone, timedelta
import numpy as np
import pytest

from src.core.config import AppConfig, RiskConfig
from src.core.contracts import (
    AccountInfo,
    Candle,
    OrderType,
    Position,
    PositionManagementState,
    ProfitManagementMode,
    SetupType,
    SignalCandidate,
    SymbolInfo,
    Timeframe,
)
from src.core.orchestrator import TradingBotOrchestrator
from src.execution.continuous_scalper import ContinuousScalpingEngine
from src.intelligence.config import ATIConfig
from src.intelligence.contracts import CompletedPositionRecord
from src.intelligence.facade import AdaptiveTradingIntelligence
from src.intelligence.learning.feature_extractor import HistoricalFeatureExtractor
from src.intelligence.learning.model_engine import AIPatternLearningEngine
from src.risk.portfolio_capacity import DynamicPortfolioCapacityEngine
from src.risk.portfolio_risk import PortfolioRiskEngine


@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def create_sample_candle(close: float, dt: datetime) -> Candle:
    return Candle(
        time=dt,
        open=close - 0.5,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        tick_volume=100,
        complete=True,
    )


def test_ai_learning_engine_inference_and_scoring():
    """Verifies AI win probability estimation and setup score adjustments."""
    ai_engine = AIPatternLearningEngine()
    scalper = ContinuousScalpingEngine(
        symbols=["XAUUSD"],
        min_confluence_score=0.0,
        min_rr=0.0,
        ai_learning_engine=ai_engine,
    )

    now = datetime.now(timezone.utc)
    candle = create_sample_candle(2650.0, now)
    sym_info = SymbolInfo(
        symbol="XAUUSD",
        bid=2650.0,
        ask=2650.2,
        spread=20.0,
        digits=2,
        point=0.01,
        tick_value=1.0,
        tick_size=0.01,
        contract_size=100.0,
        min_lot=0.01,
        max_lot=100.0,
        lot_step=0.01,
        stops_level=5,
    )

    # 1. Untrained engine returns neutral 0.50 probability
    cand_untrained = scalper._build_scalp_candidate(
        symbol="XAUUSD",
        timeframe=Timeframe.M1,
        direction=OrderType.BUY,
        setup_type=SetupType.FAST_SCALP,
        model_name="MOMENTUM_CONTINUATION",
        last_candle=candle,
        raw_sl=2645.0,
        atr=2.0,
        score=70.0,
        rationale="Strong momentum breakout",
        symbol_info=sym_info,
    )
    assert cand_untrained is not None
    assert cand_untrained.score == 70.0
    assert cand_untrained.metadata["ai_win_probability"] == 0.50

    # 2. Train AI engine with synthetic historical wins
    X = []
    y = []
    base_time = now - timedelta(days=5)
    for i in range(25):
        is_win = 1 if i % 4 != 0 else 0
        feat = HistoricalFeatureExtractor.extract_features_from_context(
            entry_time=base_time + timedelta(hours=i),
            direction="BUY",
            spread_pts=15.0 if is_win else 45.0,
            adx=30.0 if is_win else 12.0,
            atr=2.0,
            rsi=55.0,
            momentum_pct=0.8 if is_win else -0.5,
            session_name="LONDON",
        )
        vec = [feat[k] for k in HistoricalFeatureExtractor.FEATURE_NAMES]
        X.append(vec)
        y.append(is_win)

    report = ai_engine.train_temporal(
        X=np.array(X, dtype=np.float64),
        y=np.array(y, dtype=np.int32),
        feature_names=HistoricalFeatureExtractor.FEATURE_NAMES,
    )
    assert report.status == "TRAINED"
    assert report.sample_size == 25

    # 3. Candidate generated with trained AI engine receives probability > 0.50 and positive adjustment
    cand_trained = scalper._build_scalp_candidate(
        symbol="XAUUSD",
        timeframe=Timeframe.M1,
        direction=OrderType.BUY,
        setup_type=SetupType.FAST_SCALP,
        model_name="MOMENTUM_CONTINUATION",
        last_candle=candle,
        raw_sl=2645.0,
        atr=2.0,
        score=70.0,
        rationale="Strong momentum breakout",
        symbol_info=sym_info,
    )
    assert cand_trained is not None
    ai_prob = cand_trained.metadata["ai_win_probability"]
    assert ai_prob > 0.50
    assert cand_trained.score > 70.0
    assert any("AI_WIN_PROB:" in r for r in cand_trained.reasons)


def test_ai_candidate_ranking_prioritization():
    """Verifies that candidates with higher AI win probability are prioritized in ranking."""
    scalper = ContinuousScalpingEngine(symbols=["XAUUSD", "BTCUSD"])
    now = datetime.now(timezone.utc)

    c1 = SignalCandidate(
        id="SCALP_1",
        symbol="XAUUSD",
        timeframe=Timeframe.M1,
        direction=OrderType.BUY,
        setup_type=SetupType.FAST_SCALP,
        entry_price=2650.0,
        stop_loss=2645.0,
        take_profit=2660.0,
        risk_reward=2.0,
        score=75.0,
        timestamp=now,
        status="APPROVED",
        reasons=["MODEL:MOMENTUM"],
        metadata={"ai_win_probability": 0.40},
    )

    c2 = SignalCandidate(
        id="SCALP_2",
        symbol="BTCUSD",
        timeframe=Timeframe.M1,
        direction=OrderType.BUY,
        setup_type=SetupType.FAST_SCALP,
        entry_price=90000.0,
        stop_loss=89500.0,
        take_profit=91000.0,
        risk_reward=2.0,
        score=75.0,
        timestamp=now,
        status="APPROVED",
        reasons=["MODEL:MOMENTUM"],
        metadata={"ai_win_probability": 0.72},
    )

    ranked = scalper.rank_scalp_opportunities([c1, c2])
    # c2 must rank higher than c1 because of superior AI win probability (+6.6 bonus vs -3.0 penalty)
    assert ranked[0].id == "SCALP_2"
    assert ranked[1].id == "SCALP_1"


def test_closed_loop_trade_ingestion_audit_and_retraining(temp_db_path):
    """Verifies that closed trades are recorded into ATI SQLite repository, audited, and trigger retraining."""
    ati_cfg = ATIConfig(database_path=temp_db_path, enabled=True)
    ati = AdaptiveTradingIntelligence(config=ati_cfg)

    app_cfg = AppConfig()
    app_cfg.ati = ati_cfg
    app_cfg.symbols = ["XAUUSD"]

    orchestrator = TradingBotOrchestrator(config=app_cfg)
    orchestrator.ati = ati
    orchestrator.continuous_scalper.ai_learning_engine = ati.learning_engine

    # Seed 14 historical trades directly into ATI repo
    base_time = datetime.now(timezone.utc) - timedelta(days=2)
    for i in range(14):
        p = CompletedPositionRecord(
            position_id=1000 + i,
            canonical_symbol="XAUUSD",
            broker_symbol="XAUUSD",
            direction="BUY",
            open_time=base_time + timedelta(hours=i),
            close_time=base_time + timedelta(hours=i, minutes=15),
            open_price=2650.0,
            close_price=2655.0 if i % 2 == 0 else 2648.0,
            volume=0.05,
            initial_sl=2645.0,
            initial_tp=2660.0,
            realized_gross_profit=25.0 if i % 2 == 0 else -10.0,
            realized_net_profit=20.0 if i % 2 == 0 else -12.0,
            commission=2.0,
            swap=0.0,
            exit_reason="TP hit ($20 Net Profit Target)",
            strategy_id="SMC_SCALPER",
            features_snapshot={"spread_pts": 15.0, "adx": 28.0, "atr": 2.0, "rsi": 52.0},
        )
        ati.repo.upsert_completed_position(p)

    assert len(ati.repo.list_completed_positions(limit=50)) == 14
    assert ati.learning_engine.latest_report is None or ati.learning_engine.latest_report.status == "OBSERVATION_ONLY_INSUFFICIENT_DATA"

    # Now close 15th position via orchestrator._record_completed_trade
    pos_15 = Position(
        ticket=1015,
        symbol="XAUUSD",
        order_type=OrderType.BUY,
        volume=0.05,
        open_price=2650.0,
        current_price=2655.0,
        stop_loss=2645.0,
        take_profit=2660.0,
        profit=22.0,
        open_time=base_time + timedelta(hours=15),
        initial_risk_amount=25.0,
        features_snapshot={"spread_pts": 14.0, "adx": 32.0, "atr": 2.1, "rsi": 54.0},
    )

    orchestrator._record_completed_trade(
        pos=pos_15,
        realized_pnl=20.50,
        deal_profit=22.0,
        deal_comm=1.50,
        deal_swap=0.0,
        close_reason="$20 Net Profit Target Reached",
    )

    # 1. Verify saved in SQLite repository
    saved_15 = ati.repo.get_completed_position(1015)
    assert saved_15 is not None
    assert saved_15.realized_net_profit == 20.50
    assert saved_15.canonical_symbol == "XAUUSD"

    # 2. Verify audited
    audit_rep = ati.repo.get_trade_audit(1015)
    assert audit_rep is not None
    assert audit_rep.trade_id == 1015

    # 3. Verify retraining triggered (sample_size == 15)
    assert ati.learning_engine.latest_report is not None
    assert ati.learning_engine.latest_report.status == "TRAINED"
    assert ati.learning_engine.latest_report.sample_size == 15
    assert ati.learning_engine.latest_report.brier_score >= 0.0


def test_effective_risk_break_even_and_capacity_freeing():
    """Verifies that moving a position to break-even eliminates its effective risk and frees capacity."""
    app_cfg = AppConfig()
    app_cfg.risk.max_account_risk_pct = 5.0
    app_cfg.risk.initial_account_balance = 1000.0

    risk_engine = PortfolioRiskEngine(config=app_cfg)
    capacity_engine = DynamicPortfolioCapacityEngine()

    # Position 1: Buy at 2650, SL at 2650 (Break-even secured)
    pos_be = Position(
        ticket=101,
        symbol="XAUUSD",
        order_type=OrderType.BUY,
        volume=0.02,
        open_price=2650.0,
        current_price=2658.0,
        stop_loss=2650.0,  # SL == entry price
        take_profit=2670.0,
        profit=16.0,
        break_even_activated=True,
        initial_risk_amount=20.0,
    )

    # Effective risk should be 0.0
    assert risk_engine._effective_position_risk(pos_be) == 0.0
    assert capacity_engine._estimate_position_risk_usd(pos_be) == 0.0

    # Position 2: Trailing in profit (Buy at 2650, SL at 2654)
    pos_profit_locked = Position(
        ticket=102,
        symbol="XAUUSD",
        order_type=OrderType.BUY,
        volume=0.02,
        open_price=2650.0,
        current_price=2660.0,
        stop_loss=2654.0,  # SL > entry price
        take_profit=2670.0,
        profit=20.0,
        break_even_activated=False,
        initial_risk_amount=20.0,
    )
    assert risk_engine._effective_position_risk(pos_profit_locked) == 0.0
    assert capacity_engine._estimate_position_risk_usd(pos_profit_locked) == 0.0


def test_consecutive_loss_circuit_breaker_recovery():
    """Verifies that consecutive loss circuit breaker automatically recovers after cooldown."""
    app_cfg = AppConfig()
    app_cfg.risk.max_consecutive_losses = 3
    risk_engine = PortfolioRiskEngine(config=app_cfg)

    # Trip the breaker with 3 consecutive losses
    for i in range(3):
        risk_engine.record_trade_result(profit=-15.0, volume=0.01, symbol="XAUUSD")

    assert risk_engine.consecutive_losses == 3
    assert risk_engine.circuit_breaker_active is True

    candidate = SignalCandidate(
        id="CAND_1",
        symbol="XAUUSD",
        timeframe=Timeframe.M1,
        direction=OrderType.BUY,
        setup_type=SetupType.FAST_SCALP,
        entry_price=2650.0,
        stop_loss=2645.0,
        take_profit=2660.0,
        risk_reward=2.0,
        score=75.0,
        timestamp=datetime.now(timezone.utc),
    )
    account = AccountInfo(balance=1000.0, equity=1000.0, free_margin=950.0)

    # Check permission immediately -> rejected
    allowed, reason = risk_engine.evaluate_new_order_permission(
        candidate=candidate,
        account=account,
        active_positions=[],
        proposed_monetary_risk=10.0,
        proposed_volume=0.01,
    )
    assert allowed is False
    assert "Circuit Breaker is ACTIVE" in str(reason)

    # Fast forward circuit breaker trip time past cooldown (e.g. 1 hour ago)
    past_time = datetime.now(timezone.utc) - timedelta(seconds=2000)
    risk_engine.circuit_breaker_trip_time = past_time

    # Re-evaluate -> breaker auto-recovers with proportional 50% risk scaling
    allowed_recovered, reason_recovered = risk_engine.evaluate_new_order_permission(
        candidate=candidate,
        account=account,
        active_positions=[],
        proposed_monetary_risk=10.0,
        proposed_volume=0.01,
    )
    assert risk_engine.circuit_breaker_active is False
    assert allowed_recovered is True
