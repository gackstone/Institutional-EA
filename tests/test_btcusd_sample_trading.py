"""
Comprehensive test suite for BTCUSD DEMO Sample Trading (`BTCUSD_DEMO_SAMPLE_MODE`),
independent risk authorization, broker-side MT5 execution confirmation,
Telegram notifications & commands, and Control Service HTTP endpoints.
"""

from __future__ import annotations

import json
import shutil
import threading
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from companion.database import CompanionRepository
from companion.service.api.server import build_control_server
from companion.service.configuration.config_service import ConfigurationService
from companion.service.events.event_bus import EventBus
from companion.service.mt5.sync_service import MT5SyncService
from companion.service.orchestration.engine_controller import EngineController
from companion.service.trading.btcusd_sample_service import BTCUSDSampleTradingService
from src.notifications.telegram_config import TelegramConfig
from src.notifications.telegram_service import TelegramCommandHandler, TelegramNotifier


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _copy_config_dir(tmp_path: Path) -> Path:
    cfg_dst = tmp_path / "config"
    shutil.copytree(PROJECT_ROOT / "config", cfg_dst)
    return cfg_dst


def _no_bridge():
    return SimpleNamespace(connect=lambda: False, is_connected=lambda: False)


class _MockBTCMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 2
    ACCOUNT_MARGIN_MODE_HEDGING = 2
    TIMEFRAME_M5 = 5
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009

    def __init__(self, trade_mode: int = 0, trend: str = "BUY"):
        self.trade_mode = trade_mode
        self.trend = trend
        self.open_positions = []
        self.deals = []
        self.sent_orders = []
        self.next_ticket = 50001

    def initialize(self) -> bool:
        return True

    def shutdown(self) -> None:
        pass

    def account_info(self):
        return SimpleNamespace(
            login=999002,
            company="Just Global Markets Ltd.",
            currency="USD",
            balance=10000.0,
            equity=10000.0,
            margin=0.0,
            margin_free=10000.0,
            margin_level=0.0,
            leverage=500,
            trade_mode=self.trade_mode,
            margin_mode=2,
        )

    def symbol_select(self, sym: str, enable: bool) -> bool:
        return sym == "BTCUSD.m"

    def symbol_info(self, sym: str):
        if sym != "BTCUSD.m":
            return None
        return SimpleNamespace(
            name="BTCUSD.m",
            visible=True,
            trade_mode=4,
            digits=2,
            point=0.01,
            trade_tick_size=0.01,
            trade_tick_value=0.01,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            trade_stops_level=0,
            spread=850,
            bid=67100.0,
            ask=67108.5,
        )

    def symbol_info_tick(self, sym: str):
        if sym != "BTCUSD.m":
            return None
        return SimpleNamespace(bid=67100.0, ask=67108.5, time=1700000000)

    def copy_rates_from_pos(self, sym: str, tf: int, start: int, count: int):
        # Construct 30 bars with a clean EMA5/EMA15 crossover on the last closed bar (-2)
        bars = []
        base = 67000.0
        for i in range(count):
            if self.trend == "BUY":
                c = base - (i * 5.0) if i < count - 2 else base + 200.0
            else:
                c = base + (i * 5.0) if i < count - 2 else base - 200.0
            bars.append({"time": 1700000000 + i * 300, "open": c - 5, "high": c + 25, "low": c - 25, "close": c})
        return bars

    def order_send(self, req: dict):
        self.sent_orders.append(req)
        ticket = self.next_ticket
        self.next_ticket += 1
        pos = SimpleNamespace(
            ticket=ticket,
            identifier=ticket,
            symbol=req["symbol"],
            type=req["type"],
            volume=req["volume"],
            price_open=req["price"],
            price_current=req["price"],
            sl=req["sl"],
            tp=req["tp"],
            profit=0.0,
            magic=req["magic"],
            comment=req["comment"],
        )
        self.open_positions.append(pos)
        return SimpleNamespace(retcode=10009, order=ticket, deal=ticket, price=req["price"], comment="Request executed")

    def positions_get(self, symbol: str = None):
        if symbol:
            return [p for p in self.open_positions if p.symbol == symbol]
        return list(self.open_positions)

    def orders_get(self):
        return []

    def history_deals_get(self, position: int = 0):
        return [d for d in self.deals if getattr(d, "position_id", 0) == position]


class _FakeNotifier:
    def __init__(self):
        self.config = SimpleNamespace(enabled=True, bot_token="fake:token", chat_id="12345")
        self.messages = []
        self.seen_ids = set()
        self.delivery_count = 0
        self.failed_count = 0
        self.last_notification = None

    def send_deduplicated(self, event_id: str, text: str, disable_notification: bool = False, parse_mode: str = "HTML") -> bool:
        if event_id in self.seen_ids:
            return False
        self.seen_ids.add(event_id)
        self.messages.append((event_id, text))
        self.delivery_count += 1
        self.last_notification = {"timestamp": "now", "preview": text[:60], "status": "DELIVERED"}
        return True

    def verify_connection(self):
        return True, "Connected as @fake_bot"

    def send_raw_html(self, text: str):
        self.messages.append(("raw", text))
        self.delivery_count += 1


def _build_service(tmp_path: Path, mt5_mock: _MockBTCMT5):
    cfg_dir = _copy_config_dir(tmp_path)
    repo = CompanionRepository(tmp_path / "db.sqlite")
    events = EventBus()
    cfg_svc = ConfigurationService(cfg_dir, repo)
    mt5_sync = MT5SyncService(repo, events, mt5_module=mt5_mock, bridge_client=_no_bridge())
    engine = EngineController(tmp_path, repo, events, cfg_svc, mt5_sync)
    notifier = _FakeNotifier()
    svc = BTCUSDSampleTradingService(tmp_path, repo, events, cfg_svc, mt5_sync, engine, telegram_notifier=notifier)
    return svc, notifier, repo, engine


def test_btcusd_demo_lock_blocks_live_account(tmp_path: Path):
    svc, _notif, _repo, _eng = _build_service(tmp_path, _MockBTCMT5(trade_mode=2))
    res = svc.start()
    assert res["success"] is False
    assert "LIVE/REAL" in res["message"]
    assert svc.state == "BLOCKED"


def test_btcusd_buy_and_sell_execution_with_broker_confirmation_and_closure(tmp_path: Path):
    # 1. BUY execution & confirmation + closure
    mt5_buy = _MockBTCMT5(trade_mode=0, trend="BUY")
    svc, notif, repo, _eng = _build_service(tmp_path, mt5_buy)

    ok, _msg, specs = svc.verify_activation_preconditions()
    assert ok is True and specs is not None
    assert svc.broker_symbol == "BTCUSD.m"

    sig = svc.evaluate_btcusd_signal(mt5_buy, specs)
    assert sig is not None and sig["direction"] == "BUY"

    exec_res = svc.authorize_and_execute(sig)
    assert exec_res["success"] is True, exec_res
    assert len(mt5_buy.sent_orders) == 1
    assert any("BTCUSD BUY EXECUTED" in m[1] for m in notif.messages)

    # Duplicate signal must be blocked
    dup_res = svc.authorize_and_execute(sig)
    assert dup_res["success"] is False

    # Close position on broker side -> cycle detects closure & notifies
    svc.active = True
    ticket = exec_res["trade"]["ticket"]
    mt5_buy.open_positions.clear()
    mt5_buy.deals.append(SimpleNamespace(position_id=ticket, entry=1, price=67250.0, profit=1.41, commission=-0.05, swap=0.0))
    svc.run_cycle()
    assert any("BTCUSD POSITION CLOSED" in m[1] for m in notif.messages)
    svc.stop()

    # 2. SELL execution via manual DEMO test order (passes through risk manager)
    mt5_sell = _MockBTCMT5(trade_mode=0, trend="SELL")
    svc_sell, notif_sell, _r2, _e2 = _build_service(tmp_path / "sell", mt5_sell)
    sell_res = svc_sell.place_manual_test_order("SELL")
    assert sell_res["success"] is True
    assert sell_res["trade"]["direction"] == "SELL"
    assert any("BTCUSD SELL EXECUTED" in m[1] for m in notif_sell.messages)


def test_btcusd_risk_rejection_blocks_execution_and_notifies(tmp_path: Path):
    mt5 = _MockBTCMT5(trade_mode=0, trend="BUY")
    svc, notif, _repo, engine = _build_service(tmp_path, mt5)
    svc.start()

    # Trigger kill switch in risk engine
    engine.risk_engine.trigger_kill_switch("Simulated daily loss cap")
    res = svc.authorize_and_execute({
        "signal_id": "SIG_RISK_TEST",
        "symbol": "BTCUSD.m",
        "direction": "BUY",
        "entry_price": 67108.5,
        "stop_loss": 66950.0,
        "take_profit": 67390.0,
    })
    assert res["success"] is False
    assert len(mt5.sent_orders) == 0
    assert any("BTCUSD TRADE REJECTED" in m[1] for m in notif.messages)
    svc.stop()


def test_telegram_commands_auth_and_deduplication(tmp_path: Path):
    cfg = TelegramConfig()
    cfg.bot_token = "fake:token"
    cfg.chat_id = "999888"
    cfg.enabled = False  # Don't start network polling thread in unit test

    notifier = TelegramNotifier(config=cfg)
    sent_texts = []
    notifier.send_message = lambda text, disable_notification=False, parse_mode="HTML": sent_texts.append(text)

    # Deduplication check
    assert notifier.send_deduplicated("evt_1", "Hello 1") is True
    assert notifier.send_deduplicated("evt_1", "Hello 1 dup") is False
    assert len(sent_texts) == 1

    handler = TelegramCommandHandler(config=cfg, notifier=notifier)
    replies = []
    handler._reply = lambda text: replies.append(text)
    handler.btc_provider = lambda: {"symbol": "BTCUSD.m", "bid": 67100.0, "ask": 67108.5, "spread_points": 850, "status": "CONNECTED", "sample_state": "MONITORING"}
    handler.risk_provider = lambda: {"kill_switch_active": False, "daily_pnl": 0.0, "consecutive_losses": 0, "max_positions": 1}

    # Unauthorized chat rejected
    handler._process_message({"chat": {"id": "111222"}, "from": {"first_name": "Attacker"}, "text": "/btc"})
    assert len(replies) == 0

    # Authorized /btc and /risk succeed
    handler._process_message({"chat": {"id": "999888"}, "from": {"first_name": "Owner"}, "text": "/btc"})
    handler._process_message({"chat": {"id": "999888"}, "from": {"first_name": "Owner"}, "text": "/risk"})
    assert len(replies) == 2
    assert "BTCUSD.m" in replies[0]
    assert "DEMO LOCKED" in replies[1]


def test_http_btcusd_endpoints(tmp_path: Path):
    _copy_config_dir(tmp_path)
    mt5 = _MockBTCMT5(trade_mode=0, trend="BUY")
    server, ctx = build_control_server(
        project_root=tmp_path,
        host="127.0.0.1",
        port=0,
        db_path=tmp_path / "control.db",
        token="btc-http-token",
        mt5_module=mt5,
        enable_telegram_polling=False,
    )
    ctx.mt5_sync.bridge = _no_bridge()
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/btcusd/start",
            data=b"{}",
            method="POST",
            headers={"Authorization": "Bearer btc-http-token", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["success"] is True
            assert data["status"]["broker_symbol"] == "BTCUSD.m"
            assert data["status"]["demo_verified"] is True

        ctx.btcusd_sample.stop()
    finally:
        server.shutdown()
        server.server_close()
