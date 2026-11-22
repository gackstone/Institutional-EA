"""
Automated Regression Tests for Dynamic Position Layering & Removal of 3-Position Ceiling (Institutional EA).
Covers Scenarios A through L in Phase 9.
"""

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
import tempfile

import pytest

from src.core.config import AppConfig
from src.core.contracts import (
    AccountInfo, ExecutionMode, OrderType, Position,
    ProfitManagementMode, SetupType, SignalCandidate, SymbolInfo, Timeframe
)
from src.execution.order_manager import OrderManager
from src.execution.transaction_manager import TransactionManager
from src.risk.portfolio_capacity import DynamicPortfolioCapacityEngine
from src.risk.portfolio_risk import PortfolioRiskEngine
from src.risk.position_sizing import PositionSizingEngine
from src.risk.trade_management import TradeManagementEngine


def _acc(equity: float = 20000.0, free_margin: float = 18000.0, margin: float = 500.0) -> AccountInfo:
    return AccountInfo(
        account_number=123456,
        balance=equity,
        equity=equity,
        free_margin=free_margin,
        margin=margin,
        margin_level=(equity / margin * 100.0) if margin > 0 else 0.0,
        trade_mode="DEMO",
        trading_enabled=True,
    )


def _sinfo(sym: str) -> SymbolInfo:
    if "BTC" in sym:
        bid, pt, digits = 90000.0, 0.01, 2
    elif "JPY" in sym:
        bid, pt, digits = 150.0, 0.001, 3
    else:
        bid, pt, digits = 2000.0, 0.01, 2
    return SymbolInfo(
        symbol=sym,
        bid=bid,
        ask=bid + 10 * pt,
        spread=10,
        point=pt,
        digits=digits,
        tick_size=pt,
        tick_value=1.0,
        contract_size=1.0,
        min_lot=0.01,
        max_lot=50.0,
        lot_step=0.01,
    )


def _cand(sym: str, cid: str, dt: Optional[datetime] = None, direction: OrderType = OrderType.BUY) -> SignalCandidate:
    if "BTC" in sym:
        entry, dist = 90000.0, 50.0
    elif "JPY" in sym:
        entry, dist = 150.0, 1.0
    else:
        entry, dist = 2000.0, 10.0
    sl = entry - dist if direction == OrderType.BUY else entry + dist
    tp = entry + 2 * dist if direction == OrderType.BUY else entry - 2 * dist
    return SignalCandidate(
        id=cid,
        symbol=sym,
        timeframe=Timeframe.M15,
        direction=direction,
        setup_type=SetupType.M15_SMC_OTE,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        risk_reward=2.0,
        score=82.0,
        timestamp=dt or datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc),  # Monday
        status="APPROVED",
    )


def _pos(ticket: int, sym: str, risk_usd: float = 100.0, profit: float = 0.0, volume: float = 0.10) -> Position:
    return Position(
        ticket=ticket,
        symbol=sym,
        order_type=OrderType.BUY,
        volume=volume,
        open_price=2000.0,
        current_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        profit=profit,
        magic=100101,
        open_time=datetime.now(timezone.utc),
        initial_risk_amount=risk_usd,
    )


def _make_om(cfg: Optional[AppConfig] = None, bridge: Optional[MagicMock] = None, ledger_path: Optional[str] = None) -> OrderManager:
    c = cfg or AppConfig.load_from_dir("config")
    c.risk.risk_percentage = 0.5
    c.risk.max_aggregate_open_risk_percent = 6.0
    c.risk.max_symbol_risk_percent = 6.0
    b = bridge or MagicMock()
    b.ping.return_value = True
    b.check_symbol_session.return_value = {"status": "SUCCESS", "market_open": True}
    b.send_request.return_value = {"status": "SUCCESS", "data": []}
    tm = TransactionManager(ledger_file=ledger_path or "data/test_dyn_tx.json")
    return OrderManager(c, b, PositionSizingEngine(0.5), PortfolioRiskEngine(c), transaction_manager=tm)


class TestDynamicPositionLayering:
    def test_a_existing_three_positions_allows_fourth(self, tmp_path):
        bridge = MagicMock()
        om = _make_om(bridge=bridge, ledger_path=str(tmp_path / "tx.json"))
        acc = _acc()
        existing = [_pos(101, "XAUUSD", 100.0), _pos(102, "USDJPY", 100.0), _pos(103, "XAUUSD", 100.0)]
        cand4 = _cand("XAUUSD", "SIG_4")
        pos4 = _pos(104, "XAUUSD", 100.0)
        bridge.execute_trade.return_value = {"status": "SUCCESS", "ticket": 104, "retcode": 10009, "price": cand4.entry_price}
        bridge.get_positions.side_effect = [existing, existing + [pos4]]

        order = om.execute_signal(cand4, acc, _sinfo("XAUUSD"), existing)
        assert order is not None and order.status == "FILLED"
        assert order.ticket == 104

    def test_b_multiple_btc_positions_layered(self, tmp_path):
        cfg = AppConfig.load_from_dir("config")
        cfg.weekday_btc_fallback_enabled = True
        bridge = MagicMock()
        om = _make_om(cfg=cfg, bridge=bridge, ledger_path=str(tmp_path / "tx.json"))
        acc = _acc()
        sat = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)  # Saturday (BTC active)

        pos1 = _pos(201, "BTCUSD.m", 100.0)
        cand2 = _cand("BTCUSD.m", "BTC_LAYER_2", dt=sat)
        pos2 = _pos(202, "BTCUSD.m", 100.0)
        bridge.execute_trade.return_value = {"status": "SUCCESS", "ticket": 202, "retcode": 10009, "price": cand2.entry_price}
        bridge.get_positions.side_effect = [[pos1], [pos1, pos2]]

        order = om.execute_signal(cand2, acc, _sinfo("BTCUSD.m"), [pos1])
        assert order is not None and order.status == "FILLED"

    def test_c_multiple_authorized_instruments_coexist(self, tmp_path):
        cfg = AppConfig.load_from_dir("config")
        cfg.weekday_btc_fallback_enabled = True
        bridge = MagicMock()
        om = _make_om(cfg=cfg, bridge=bridge, ledger_path=str(tmp_path / "tx.json"))
        acc = _acc()
        existing = [_pos(301, "XAUUSD", 100.0), _pos(302, "BTCUSD.m", 100.0), _pos(303, "USDJPY.m", 100.0)]
        cand = _cand("XAUUSD", "SIG_MULTI_4")
        pos4 = _pos(304, "XAUUSD", 100.0)
        bridge.execute_trade.return_value = {"status": "SUCCESS", "ticket": 304, "retcode": 10009, "price": cand.entry_price}
        bridge.get_positions.side_effect = [existing, existing + [pos4]]

        order = om.execute_signal(cand, acc, _sinfo("XAUUSD"), existing)
        assert order is not None and order.status == "FILLED"

    def test_d_risk_budget_exhausted_rejects_regardless_of_count(self, tmp_path):
        om = _make_om(ledger_path=str(tmp_path / "tx.json"))
        acc = _acc(equity=10000.0, free_margin=9000.0)  # 6% agg budget = $600
        # 2 positions totaling $580 risk -> adding $50 exceeds $600
        existing = [_pos(401, "XAUUSD", 290.0), _pos(402, "USDJPY", 290.0)]
        cand = _cand("XAUUSD", "SIG_OVER_BUDGET")
        chk = om.run_pre_trade_checklist(cand, acc, _sinfo("XAUUSD"), existing)
        assert chk.passed is False
        assert any("RISK_BUDGET_EXHAUSTED" in r for r in chk.rejection_reasons)

    def test_e_duplicate_signal_prevented(self, tmp_path):
        bridge = MagicMock()
        om = _make_om(bridge=bridge, ledger_path=str(tmp_path / "tx.json"))
        acc = _acc()
        cand = _cand("XAUUSD", "DUP_SIG_1")
        pos = _pos(501, "XAUUSD", 100.0)
        bridge.execute_trade.return_value = {"status": "SUCCESS", "ticket": 501, "retcode": 10009, "price": cand.entry_price}
        bridge.get_positions.side_effect = [[], [pos]]

        first = om.execute_signal(cand, acc, _sinfo("XAUUSD"), [])
        assert first is not None and first.status == "FILLED"
        second = om.execute_signal(cand, acc, _sinfo("XAUUSD"), [pos])
        assert second is None
        assert bridge.execute_trade.call_count == 1

    def test_f_profitable_position_management_independent(self):
        cfg = AppConfig.load_from_dir("config")
        tm = TradeManagementEngine(cfg.risk)
        p = _pos(601, "XAUUSD", risk_usd=50.0, profit=25.0)
        p.profit_mode = ProfitManagementMode.QUICK_SCALP
        actions = tm.evaluate_position(p, _sinfo("XAUUSD"), [], scalp_mode=True)
        assert any(a.action_type == "FULL_CLOSE" and a.ticket == 601 for a in actions)

    def test_g_insufficient_margin_rejected(self, tmp_path):
        om = _make_om(ledger_path=str(tmp_path / "tx.json"))
        acc = _acc(equity=10000.0, free_margin=0.01, margin=9999.0)
        cand = _cand("XAUUSD", "LOW_MARGIN")
        chk = om.run_pre_trade_checklist(cand, acc, _sinfo("XAUUSD"), [])
        assert chk.passed is False
        assert any("INSUFFICIENT_MARGIN" in r or "margin" in r.lower() for r in chk.rejection_reasons)

    def test_h_instrument_whitelist_preserved(self, tmp_path):
        om = _make_om(ledger_path=str(tmp_path / "tx.json"))
        acc = _acc()
        for bad in ["EURUSD", "GBPUSD", "US30", "US100", "NAS100", "USDJPY"]:
            cand = _cand(bad, f"BAD_{bad}")
            chk = om.run_pre_trade_checklist(cand, acc, _sinfo(bad), [])
            assert chk.passed is False
            assert any("INSTRUMENT_NOT_ALLOWED" in r or "Universe Restriction" in r for r in chk.rejection_reasons)

    def test_i_config_persistence_no_3_position_limit(self):
        cfg = AppConfig.load_from_dir("config")
        assert cfg.strict_three_symbol_universe is True
        cap = DynamicPortfolioCapacityEngine(
            max_aggregate_open_risk_percent=cfg.risk.max_aggregate_open_risk_percent,
            max_symbol_risk_percent=cfg.risk.max_symbol_risk_percent,
        )
        assert cap.max_aggregate_open_risk_percent == cfg.risk.max_aggregate_open_risk_percent
        assert cap.max_symbol_risk_percent == cfg.risk.max_symbol_risk_percent

    def test_j_mt5_reconciliation(self, tmp_path):
        bridge = MagicMock()
        p1 = _pos(701, "XAUUSD", 100.0)
        p2 = _pos(702, "USDJPY", 100.0)
        bridge.get_positions.return_value = [p1, p2]
        om = _make_om(bridge=bridge, ledger_path=str(tmp_path / "tx.json"))
        active = om.get_active_positions()
        assert len(active) == 2
        assert {p.ticket for p in active} == {701, 702}

    def test_k_concurrent_execution_no_duplicate_same_signal(self, tmp_path):
        bridge = MagicMock()
        om = _make_om(bridge=bridge, ledger_path=str(tmp_path / "tx.json"))
        acc = _acc()
        cand = _cand("XAUUSD", "CONCURRENT_1")
        pos = _pos(801, "XAUUSD", 100.0)
        bridge.execute_trade.return_value = {"status": "SUCCESS", "ticket": 801, "retcode": 10009, "price": cand.entry_price}
        bridge.get_positions.return_value = [pos]

        with ThreadPoolExecutor(max_workers=4) as ex:
            results = list(ex.map(lambda _: om.execute_signal(cand, acc, _sinfo("XAUUSD"), []), range(4)))
        filled = [r for r in results if r is not None and r.status in ("FILLED", "PARTIALLY_FILLED")]
        assert len(filled) == 1

    def test_l_restart_recovery_persists_executed_signals(self, tmp_path):
        ledger = str(tmp_path / "tx_restart.json")
        bridge = MagicMock()
        om1 = _make_om(bridge=bridge, ledger_path=ledger)
        acc = _acc()
        cand = _cand("XAUUSD", "RESTART_SIG_1")
        pos = _pos(901, "XAUUSD", 100.0)
        bridge.execute_trade.return_value = {"status": "SUCCESS", "ticket": 901, "retcode": 10009, "price": cand.entry_price}
        bridge.get_positions.side_effect = [[], [pos]]
        assert om1.execute_signal(cand, acc, _sinfo("XAUUSD"), []) is not None

        # Simulate restart: new OrderManager reading same TransactionManager ledger
        om2 = _make_om(bridge=bridge, ledger_path=ledger)
        assert om2.execute_signal(cand, acc, _sinfo("XAUUSD"), [pos]) is None
        assert bridge.execute_trade.call_count == 1
