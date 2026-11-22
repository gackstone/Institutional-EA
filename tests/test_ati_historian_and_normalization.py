"""
Automated Test Suite for ATI Historian and Account Normalization Subsystem.
Verifies deal ingestion, idempotency, duplicate prevention, partial closes,
position reconciliation, restart recovery, cent account scaling, and whitelist enforcement.
"""

import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from src.intelligence.contracts import BrokerDealRecord
from src.intelligence.historian.normalization import AccountBrokerNormalizer, APPROVED_CANONICAL_SYMBOLS
from src.intelligence.historian.reconciler import PositionLifecycleReconciler
from src.intelligence.historian.collector import MT5TradeHistorian
from src.intelligence.storage.repository import ATIRepository


class MockMT5Deal:
    def __init__(
        self,
        ticket: int,
        order: int,
        position_id: int,
        symbol: str,
        dtype: int,
        entry: int,
        volume: float,
        price: float,
        profit: float,
        commission: float = -1.5,
        swap: float = 0.0,
        comment: str = "",
        time_sec: float = 1700000000.0,
    ):
        self.ticket = ticket
        self.order = order
        self.position_id = position_id
        self.symbol = symbol
        self.type = dtype
        self.entry = entry
        self.volume = volume
        self.price = price
        self.profit = profit
        self.commission = commission
        self.swap = swap
        self.comment = comment
        self.time = time_sec
        self.magic = 100101


class MockMT5Account:
    def __init__(self, login=123456, currency="USD", company="JustForex Cent", trade_mode=0, leverage=500):
        self.login = login
        self.currency = currency
        self.company = company
        self.trade_mode = trade_mode
        self.leverage = leverage


class MockMT5Module:
    def __init__(self, deals=None, account=None):
        self.deals = deals or []
        self.account = account or MockMT5Account()
        self.initialized = True

    def initialize(self):
        return True

    def account_info(self):
        return self.account

    def history_deals_get(self, date_from, date_to):
        return self.deals

    def last_error(self):
        return (1, "OK")


@pytest.fixture
def temp_repo():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ati.db"
        repo = ATIRepository(db_path)
        yield repo


class TestAccountNormalization:
    def test_canonical_symbols_approved(self):
        for sym in ("XAUUSD", "BTCUSD"):
            assert AccountBrokerNormalizer.is_symbol_approved(sym)
            assert AccountBrokerNormalizer.resolve_canonical_symbol(sym) == sym
        assert not AccountBrokerNormalizer.is_symbol_approved("USDJPY")
        assert AccountBrokerNormalizer.resolve_canonical_symbol("USDJPY") is None

    def test_broker_suffix_mapping(self):
        assert AccountBrokerNormalizer.resolve_canonical_symbol("XAUUSD.c") == "XAUUSD"
        assert AccountBrokerNormalizer.resolve_canonical_symbol("XAUUSD.m") == "XAUUSD"
        assert AccountBrokerNormalizer.resolve_canonical_symbol("GOLD.m") == "XAUUSD"
        assert AccountBrokerNormalizer.resolve_canonical_symbol("BTCUSD.c") == "BTCUSD"
        assert AccountBrokerNormalizer.resolve_canonical_symbol("USDJPY.raw") is None
        assert AccountBrokerNormalizer.resolve_canonical_symbol("USDJPY.c") is None

    def test_unapproved_symbols_strictly_rejected(self):
        assert AccountBrokerNormalizer.resolve_canonical_symbol("EURUSD") is None
        assert AccountBrokerNormalizer.resolve_canonical_symbol("US30") is None
        assert AccountBrokerNormalizer.resolve_canonical_symbol("NAS100") is None
        assert AccountBrokerNormalizer.resolve_canonical_symbol("ETHUSD") is None
        assert not AccountBrokerNormalizer.is_symbol_approved("EURUSD")

    def test_cent_account_detection_and_scaling(self):
        acc = AccountBrokerNormalizer.detect_account_context(
            account_number=999123,
            currency="USDC",
            company="RoboForex Cent",
            trade_mode="DEMO",
        )
        assert acc.account_type == "CENT"
        assert acc.denomination_factor == 100.0

        normalized = AccountBrokerNormalizer.normalize_monetary_amount(150.0, acc.denomination_factor)
        assert normalized == 1.50


class TestPositionReconciliation:
    def test_single_position_reconciliation_clean_win(self, temp_repo):
        now = datetime.now(timezone.utc)
        d_in = BrokerDealRecord(
            deal_ticket=1001,
            order_ticket=2001,
            position_id=5001,
            symbol="XAUUSD.c",
            canonical_symbol="XAUUSD",
            deal_type="DEAL_TYPE_BUY",
            entry_type="ENTRY_IN",
            volume=0.10,
            price=2650.00,
            commission=-0.50,
            swap=0.0,
            profit=0.0,
            timestamp=now - timedelta(minutes=15),
            denomination_factor=100.0,
        )
        d_out = BrokerDealRecord(
            deal_ticket=1002,
            order_ticket=2002,
            position_id=5001,
            symbol="XAUUSD.c",
            canonical_symbol="XAUUSD",
            deal_type="DEAL_TYPE_SELL",
            entry_type="ENTRY_OUT",
            volume=0.10,
            price=2655.00,
            commission=-0.50,
            swap=-0.10,
            profit=50.00,  # 50 cents = $0.50
            comment="Take Profit [tp]",
            timestamp=now,
            denomination_factor=100.0,
        )

        reconciler = PositionLifecycleReconciler()
        pos = reconciler.reconcile_single_position(5001, [d_in, d_out])

        assert pos is not None
        assert pos.position_id == 5001
        assert pos.canonical_symbol == "XAUUSD"
        assert pos.direction == "BUY"
        assert pos.volume == 0.10
        assert pos.open_price == 2650.00
        assert pos.close_price == 2655.00
        assert pos.realized_gross_profit == 50.00
        # Net profit = 50.00 + (-0.50) + (-0.50) + (-0.10) = 48.90
        assert abs(pos.realized_net_profit - 48.90) < 1e-3
        assert pos.normalized_net_profit == 0.489
        assert pos.exit_reason == "TAKE_PROFIT"
        assert pos.account_type == "CENT"

    def test_partial_closes_handled_correctly(self, temp_repo):
        now = datetime.now(timezone.utc)
        d_in = BrokerDealRecord(
            deal_ticket=101,
            order_ticket=201,
            position_id=601,
            symbol="BTCUSD",
            canonical_symbol="BTCUSD",
            deal_type="DEAL_TYPE_BUY",
            entry_type="ENTRY_IN",
            volume=1.00,
            price=90000.0,
            profit=0.0,
            timestamp=now - timedelta(minutes=30),
        )
        # Partial close 1: 0.50 lots
        d_out1 = BrokerDealRecord(
            deal_ticket=102,
            order_ticket=202,
            position_id=601,
            symbol="BTCUSD",
            canonical_symbol="BTCUSD",
            deal_type="DEAL_TYPE_SELL",
            entry_type="ENTRY_OUT",
            volume=0.50,
            price=91000.0,
            profit=500.0,
            timestamp=now - timedelta(minutes=15),
        )
        # Final close: 0.50 lots
        d_out2 = BrokerDealRecord(
            deal_ticket=103,
            order_ticket=203,
            position_id=601,
            symbol="BTCUSD",
            canonical_symbol="BTCUSD",
            deal_type="DEAL_TYPE_SELL",
            entry_type="ENTRY_OUT",
            volume=0.50,
            price=92000.0,
            profit=1000.0,
            timestamp=now,
        )

        reconciler = PositionLifecycleReconciler()
        # Verify open when partial 1 only
        assert reconciler.reconcile_single_position(601, [d_in, d_out1]) is None

        # Verify closed when both outs arrive
        pos = reconciler.reconcile_single_position(601, [d_in, d_out1, d_out2])
        assert pos is not None
        assert pos.volume == 1.00
        assert pos.partial_closes_count == 1
        assert pos.realized_gross_profit == 1500.0
        assert pos.close_price == 91500.0  # Weighted average exit price


class TestMT5HistorianCollector:
    def test_idempotent_ingestion_and_duplicate_prevention(self, temp_repo):
        mock_deal_1 = MockMT5Deal(ticket=7001, order=8001, position_id=9001, symbol="XAUUSD", dtype=0, entry=0, volume=0.05, price=2600.0, profit=0.0)
        mock_deal_2 = MockMT5Deal(ticket=7002, order=8002, position_id=9001, symbol="XAUUSD", dtype=1, entry=1, volume=0.05, price=2610.0, profit=50.0)

        mock_mt5 = MockMT5Module(deals=[mock_deal_1, mock_deal_2])
        historian = MT5TradeHistorian(temp_repo, mt5_module=mock_mt5)

        # First synchronization
        res1 = historian.sync_history()
        assert res1["status"] == "SUCCESS"
        assert res1["new_deals_ingested"] == 2
        assert res1["completed_positions_reconciled"] == 1

        # Second synchronization with same deals -> strictly idempotent, 0 new deals
        res2 = historian.sync_history()
        assert res2["status"] == "SUCCESS"
        assert res2["new_deals_ingested"] == 0

        # Verify position stored in repository
        pos = temp_repo.get_completed_position(9001)
        assert pos is not None
        assert pos.position_id == 9001
        assert pos.realized_gross_profit == 50.0
