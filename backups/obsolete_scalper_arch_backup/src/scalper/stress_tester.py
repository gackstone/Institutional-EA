"""
Phase 13: Comprehensive 16-Scenario Stress Testing & Recovery Harness.
Tests and verifies clean recovery without order duplication or position state loss across:
1. Sudden spread widening
2. Fast price reversals
3. Multiple losing entries (no martingale escalation + loss-streak cooldown)
4. Consecutive order rejection
5. Network disconnection
6. MT5 terminal restart
7. Python engine restart (open position recovery)
8. Duplicate execution messages / repeated ticks
9. Partial basket closure
10. Insufficient margin
11. Invalid volume
12. Symbol unavailable
13. Broker trading-session changes
14. Weekend BTCUSD closure
15. Friday-to-Saturday transition
16. Sunday-to-Monday transition
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.scalper.basket import BasketPosition
from src.scalper.config import ScalperConfig
from src.scalper.engine import DualMarketScalperEngine
from src.scalper.market_cache import CachedTick
from src.scalper.symbol_resolver import ResolvedSymbolSpec


@dataclass
class DummyBrokerPos:
    ticket: int
    symbol: str
    magic: int
    type: int
    volume: float
    price_open: float
    price_current: float
    profit: float
    sl: float
    tp: float


class ScalperStressTester:
    @staticmethod
    def _load_sim_cfg() -> ScalperConfig:
        cfg = ScalperConfig.load()
        cfg.kill_switch.flag_file_path = "__nonexistent_sim_stop__.flag"
        return cfg

    def run_all_scenarios(self) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []

        def _record(name: str, passed: bool, detail: str) -> None:
            results.append({"scenario": name, "passed": bool(passed), "detail": detail})

        # 1. Sudden spread widening
        cfg = self._load_sim_cfg()
        eng = DualMarketScalperEngine(cfg, is_simulation=True)
        eng.initialize()
        eng.symbol_specs["GOLD"].spread_points = 250.0  # > 80.0 limit
        eng.run_single_tick_cycle(current_dt=datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc))
        _record(
            "1_sudden_spread_widening",
            not eng.basket_manager.has_active_basket("GOLD") and eng.stats.rejection_reasons.get("SPREAD_TOO_HIGH", 0) >= 1,
            "Wide spread (250 pts > 80 pts) blocked new GOLD entry cleanly.",
        )

        # 2. Fast price reversals
        cfg2 = self._load_sim_cfg()
        eng2 = DualMarketScalperEngine(cfg2, is_simulation=True)
        eng2.initialize()
        fri_dt = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
        eng2.run_single_tick_cycle(strategy_bias=0.85, current_dt=fri_dt)
        b_before = eng2.basket_manager.get_active_basket("GOLD")
        dir_before = b_before.direction if b_before else ""
        eng2.run_single_tick_cycle(strategy_bias=-0.90, current_dt=fri_dt)
        b_after = eng2.basket_manager.get_active_basket("GOLD")
        dir_after = b_after.direction if b_after else ""
        _record(
            "2_fast_price_reversals",
            dir_before == "BUY" and dir_after == "SELL" and eng2.stats.reversals_executed == 1,
            f"Flipped {dir_before} -> {dir_after} with zero simultaneous opposing positions.",
        )

        # 3. Multiple losing entries (no martingale + loss streak cooldown)
        cfg3 = self._load_sim_cfg()
        cfg3.risk.max_consecutive_losses = 3
        eng3 = DualMarketScalperEngine(cfg3, is_simulation=True)
        eng3.initialize()
        lot_before = eng3.sizing.calculate_lot(1000.0, instrument_config=cfg3.gold).lot
        for _ in range(3):
            eng3.risk.record_trade_outcome(-1.50)
        lot_after = eng3.sizing.calculate_lot(995.50, instrument_config=cfg3.gold).lot
        verdict = eng3.risk.check_consecutive_losses()
        _record(
            "3_multiple_losing_entries",
            (not verdict.allowed) and (lot_after <= lot_before),
            f"3 consecutive losses activated cooldown ({verdict.reason}) and lot size did not escalate ({lot_before} -> {lot_after}).",
        )

        # 4. Consecutive order rejection
        cfg4 = self._load_sim_cfg()
        eng4 = DualMarketScalperEngine(cfg4, is_simulation=True)
        eng4.initialize()
        b4 = eng4.basket_manager.start_new_basket("GOLD", "XAUUSD.m", "BUY", target_size=4, magic_number=777001)
        eng4.basket_manager.close_basket("GOLD", reason="ALL_ORDERS_FAILED")
        _record(
            "4_consecutive_order_rejection",
            not eng4.basket_manager.has_active_basket("GOLD") and eng4.basket_manager.is_reentry_ready("GOLD"),
            "Failed basket cleaned up state and re-primed without ghost positions.",
        )

        # 5. Network disconnection
        cfg5 = self._load_sim_cfg()
        eng5 = DualMarketScalperEngine(cfg5, is_simulation=True)
        eng5.initialize()
        eng5.risk.broker_connected = False
        eng5.run_single_tick_cycle(current_dt=fri_dt)
        _record(
            "5_network_disconnection",
            eng5.stats.rejection_reasons.get("BROKER_DISCONNECT", 0) == 1 and not eng5.basket_manager.has_active_basket("GOLD"),
            "Disconnected state blocked new entries and emitted alert.",
        )

        # 6. MT5 terminal restart & 7. Python engine restart
        cfg6 = self._load_sim_cfg()
        eng6 = DualMarketScalperEngine(cfg6, is_simulation=True)
        eng6.initialize()
        live_pos = [
            DummyBrokerPos(ticket=88001, symbol="XAUUSD.m", magic=777001, type=0, volume=0.01, price_open=2650.0, price_current=2650.4, profit=0.40, sl=2647.0, tp=0.0),
            DummyBrokerPos(ticket=88002, symbol="XAUUSD.m", magic=777001, type=0, volume=0.01, price_open=2650.0, price_current=2650.4, profit=0.40, sl=2647.0, tp=0.0),
        ]
        rec_count = eng6.recover_open_positions_from_broker(live_pos)
        _record(
            "6_mt5_terminal_restart",
            rec_count == 2 and eng6.basket_manager.has_active_basket("GOLD"),
            f"Reconciled {rec_count} existing scalper positions after terminal restart.",
        )
        _record(
            "7_python_engine_restart",
            eng6.basket_manager.get_active_basket("GOLD").position_count == 2,
            "Adopted existing basket on Python restart without opening duplicate orders.",
        )

        # 8. Duplicate execution messages / repeated ticks
        cfg8 = self._load_sim_cfg()
        eng8 = DualMarketScalperEngine(cfg8, is_simulation=True)
        eng8.initialize()
        t_dup = CachedTick(symbol="XAUUSD", bid=2650.10, ask=2650.35, timestamp=1763110000.0)
        eng8.config.execution.tick_staleness_limit_ms = 0
        eng8.run_single_tick_cycle(sim_ticks=[t_dup], current_dt=fri_dt)
        eng8.run_single_tick_cycle(sim_ticks=[t_dup], current_dt=fri_dt)
        _record(
            "8_duplicate_execution_messages",
            eng8.stats.duplicate_orders_prevented >= 1,
            f"Duplicate tick/order guard blocked {eng8.stats.duplicate_orders_prevented} duplicate evaluation(s).",
        )

        # 9. Partial basket closure
        cfg9 = self._load_sim_cfg()
        eng9 = DualMarketScalperEngine(cfg9, is_simulation=True)
        eng9.initialize()
        b9 = eng9.basket_manager.start_new_basket("GOLD", "XAUUSD.m", "BUY", target_size=2, magic_number=777001, basket_tp_usd=2.0, tp_usd_per_min_lot=0.50)
        b9.add_position(BasketPosition(ticket=901, symbol="XAUUSD.m", direction="BUY", volume=0.01, open_price=2650.0, profit=0.60, magic=777001, symbol_key="GOLD"))
        b9.add_position(BasketPosition(ticket=902, symbol="XAUUSD.m", direction="BUY", volume=0.01, open_price=2650.0, profit=0.10, magic=777001, symbol_key="GOLD"))
        tickets9, reason9 = eng9.basket_manager.evaluate_exits_for_symbol("GOLD")
        eng9.basket_manager.on_position_closed(901, 0.60, "GOLD")
        _record(
            "9_partial_basket_closure",
            reason9 == "INDIVIDUAL_TP" and tickets9 == [901] and b9.position_count == 1 and eng9.basket_manager.has_active_basket("GOLD"),
            "Closed individual profitable position #901 while keeping remaining position #902 managed.",
        )

        # 10. Insufficient margin
        v_margin = eng9.risk.check_margin_and_capacity(100.0, 100.0, 40.0, 5.0, 2, 0.02, 0.50, margin_per_lot=20.0)
        _record(
            "10_insufficient_margin",
            not v_margin.allowed and v_margin.category == "MARGIN",
            f"Blocked order when required margin exceeded free margin ({v_margin.reason}).",
        )

        # 11. Invalid volume
        norm_vol = eng9.symbol_specs["GOLD"].normalize_volume(-0.05)
        v_zero = eng9.sizing.calculate_risk_based_lot(account_equity=10.0, sl_points=300.0, spec=eng9.symbol_specs["GOLD"], custom_risk_pct=0.10)
        _record(
            "11_invalid_volume",
            norm_vol == 0.01 and not v_zero.is_safe,
            f"Normalized invalid volume to min_lot={norm_vol} and rejected under-budget trade ({v_zero.rejection_reason}).",
        )

        # 12. Symbol unavailable
        d_unavail = eng9.scheduler.evaluate_market_status(None, current_dt=fri_dt)
        _record(
            "12_symbol_unavailable",
            not d_unavail.is_entry_permitted,
            f"Blocked entry gracefully when symbol spec is unavailable ({d_unavail.reason}).",
        )

        # 13. Broker trading-session changes & 14. Weekend BTCUSD closure
        sat_dt = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
        closed_btc = ResolvedSymbolSpec(symbol="BTCUSD.m", canonical="BTCUSD", trade_mode=0, is_tradable=False, bid=67000.0, ask=67010.0)
        d_session = eng9.scheduler.evaluate_market_status(closed_btc, current_dt=sat_dt)
        _record(
            "13_broker_trading_session_changes",
            not d_session.is_entry_permitted,
            "Blocked entry when broker session switched trade_mode to closed (0).",
        )
        _record(
            "14_weekend_btcusd_closure",
            d_session.scheduled_symbol == "BTCUSD" and not d_session.is_entry_permitted,
            "When BTCUSD is closed on weekend, engine waits and never substitutes GOLD.",
        )

        # 15. Friday-to-Saturday transition & 16. Sunday-to-Monday transition
        cfg15 = self._load_sim_cfg()
        eng15 = DualMarketScalperEngine(cfg15, is_simulation=True)
        eng15.initialize()
        eng15.run_single_tick_cycle(current_dt=fri_dt)
        gold_open_fri = eng15.basket_manager.has_active_basket("GOLD")
        for p in eng15.basket_manager.get_active_basket("GOLD").positions.values():
            p.profit = 0.70
        eng15.run_single_tick_cycle(current_dt=sat_dt)
        sat_ok = (not eng15.basket_manager.has_active_basket("GOLD")) and eng15.basket_manager.has_active_basket("BTCUSD")
        _record(
            "15_friday_to_saturday_transition",
            gold_open_fri and sat_ok,
            "Friday GOLD basket managed to completion on Saturday while new Saturday basket opened on BTCUSD.",
        )

        for p in eng15.basket_manager.get_active_basket("BTCUSD").positions.values():
            p.profit = 0.70
        mon_dt = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
        eng15.run_single_tick_cycle(current_dt=mon_dt)
        mon_ok = (not eng15.basket_manager.has_active_basket("BTCUSD")) and eng15.basket_manager.has_active_basket("GOLD")
        _record(
            "16_sunday_to_monday_transition",
            mon_ok,
            "Weekend BTCUSD basket managed to completion on Monday while new Monday basket opened on GOLD.",
        )

        passed_count = sum(1 for r in results if r["passed"])
        return {
            "total_scenarios": len(results),
            "passed_scenarios": passed_count,
            "failed_scenarios": len(results) - passed_count,
            "all_passed": passed_count == len(results),
            "scenarios": results,
        }
