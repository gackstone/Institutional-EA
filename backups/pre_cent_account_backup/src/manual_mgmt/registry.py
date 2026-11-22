"""
Manual Position Registry and State Persistence Engine.
Tracks adopted positions, detects user overrides, enforces 30-minute lockout, and
persists state atomically to state/manual_positions.json.
Tags: [SAFETY], [ASSUMPTION]
"""

from __future__ import annotations
import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

from src.core.contracts import Position, OrderType
from src.manual_mgmt.contracts import ManualPositionRecord, ManagementMode

logger = logging.getLogger("ManualPositionRegistry")


class ManualPositionRegistry:
    def __init__(
        self,
        state_file: str = "state/manual_positions.json",
        history_file: str = "state/manual_positions_history.json",
        lockout_minutes: int = 30
    ):
        self.state_file = state_file
        self.history_file = history_file
        self.lockout_minutes = lockout_minutes
        self._lock = threading.RLock()
        self._records: Dict[int, ManualPositionRecord] = {}
        self._load_state()

    def _load_state(self) -> None:
        """Loads active manual positions from persistent storage."""
        with self._lock:
            if not os.path.exists(self.state_file):
                self._records = {}
                return
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._records = {
                        int(k): ManualPositionRecord.from_dict(v)
                        for k, v in data.items()
                    }
                logger.info(f"[REGISTRY_LOADED] Restored {len(self._records)} manual positions from {self.state_file}")
            except Exception as e:
                logger.error(f"[REGISTRY_LOAD_ERROR] Failed reading {self.state_file}: {e}")
                self._records = {}

    def save_state(self) -> None:
        """Atomically saves active positions to state/manual_positions.json [SAFETY]."""
        with self._lock:
            os.makedirs(os.path.dirname(os.path.abspath(self.state_file)), exist_ok=True)
            data = {str(k): v.to_dict() for k, v in self._records.items()}

            dirname = os.path.dirname(os.path.abspath(self.state_file))
            try:
                with tempfile.NamedTemporaryFile("w", dir=dirname, delete=False, encoding="utf-8") as tf:
                    json.dump(data, tf, indent=2)
                    temp_name = tf.name
                os.replace(temp_name, self.state_file)
            except Exception as e:
                logger.error(f"[REGISTRY_SAVE_ERROR] Failed atomic save to {self.state_file}: {e}")

    def get_record(self, ticket: int) -> Optional[ManualPositionRecord]:
        with self._lock:
            return self._records.get(int(ticket))

    def get_all_records(self) -> List[ManualPositionRecord]:
        with self._lock:
            return list(self._records.values())

    def adopt_position(
        self,
        pos: Position,
        mode: ManagementMode = ManagementMode.OBSERVE
    ) -> ManualPositionRecord:
        """Adopts a manual position into the registry idempotently."""
        with self._lock:
            ticket = int(pos.ticket)
            if ticket in self._records:
                return self._records[ticket]

            now_iso = datetime.now(timezone.utc).isoformat()
            vol = float(pos.volume)
            record = ManualPositionRecord(
                ticket=ticket,
                symbol=pos.symbol,
                direction=pos.order_type,
                volume=vol,
                open_price=float(pos.open_price),
                initial_sl=float(pos.stop_loss),
                current_sl=float(pos.stop_loss),
                initial_tp=float(pos.take_profit),
                current_tp=float(pos.take_profit),
                adoption_time=now_iso,
                assigned_mode=mode.value if isinstance(mode, ManagementMode) else str(mode),
                initial_volume=vol,
                notes=[f"Adopted at {now_iso} in mode {mode.value}"]
            )
            self._records[ticket] = record
            logger.info(f"[ADOPTED] Manual ticket #{ticket} ({pos.symbol} {pos.order_type.value} {pos.volume}L) in {mode.value} mode")

        self.save_state()
        return record

    def update_position_state(
        self,
        pos: Position,
        now: Optional[datetime] = None
    ) -> Tuple[ManualPositionRecord, bool]:
        """
        Reconciles broker state against registry.
        Detects user manual overrides (SL/TP changes not made by bot) [SAFETY].
        Returns (record, user_override_detected).
        """
        current_time = now or datetime.now(timezone.utc)
        now_iso = current_time.isoformat()
        ticket = int(pos.ticket)
        user_override = False

        with self._lock:
            record = self._records.get(ticket)
            if not record:
                # Not yet adopted
                return self.adopt_position(pos), False

            # Check if user manually modified Stop Loss
            broker_sl = float(pos.stop_loss)
            if abs(broker_sl - record.current_sl) > 1e-5:
                # Did bot perform this modification?
                last_bot_sl = record.last_bot_sl_update
                if last_bot_sl is None or abs(broker_sl - last_bot_sl) > 1e-5:
                    user_override = True
                    record.user_override_detected = True
                    lockout_dt = current_time + timedelta(minutes=self.lockout_minutes)
                    record.lockout_until = lockout_dt.isoformat()
                    override_note = (
                        f"User override detected at {now_iso}: SL changed from "
                        f"{record.current_sl:.5f} to {broker_sl:.5f}. "
                        f"Locked out until {record.lockout_until} [SAFETY]."
                    )
                    record.notes.append(override_note)
                    logger.warning(f"[USER_OVERRIDE] Ticket #{ticket}: {override_note}")

                record.current_sl = broker_sl

            # Check if user manually modified Take Profit
            broker_tp = float(pos.take_profit)
            if abs(broker_tp - record.current_tp) > 1e-5:
                last_bot_tp = record.last_bot_tp_update
                if last_bot_tp is None or abs(broker_tp - last_bot_tp) > 1e-5:
                    user_override = True
                    record.user_override_detected = True
                    lockout_dt = current_time + timedelta(minutes=self.lockout_minutes)
                    record.lockout_until = lockout_dt.isoformat()
                    override_note = (
                        f"User override detected at {now_iso}: TP changed from "
                        f"{record.current_tp:.5f} to {broker_tp:.5f}. "
                        f"Locked out until {record.lockout_until} [SAFETY]."
                    )
                    record.notes.append(override_note)
                    logger.warning(f"[USER_OVERRIDE] Ticket #{ticket}: {override_note}")

                record.current_tp = broker_tp

            # Update volume and detect partial close
            cur_vol = float(pos.volume)
            if cur_vol < record.volume - 1e-5:
                partial_note = f"Partial close detected at {now_iso}: volume reduced from {record.volume:.2f} to {cur_vol:.2f}"
                record.notes.append(partial_note)
                logger.info(f"[PARTIAL_CLOSE] Ticket #{ticket}: {partial_note}")
            record.volume = cur_vol

        if user_override:
            self.save_state()
        return record, user_override

    def record_bot_modification(
        self,
        ticket: int,
        new_sl: Optional[float] = None,
        new_tp: Optional[float] = None,
        action_note: str = ""
    ) -> None:
        """Records a successful modification performed by the bot to prevent false override triggers."""
        with self._lock:
            record = self._records.get(int(ticket))
            if not record:
                return
            now_iso = datetime.now(timezone.utc).isoformat()
            if new_sl is not None:
                record.last_bot_sl_update = float(new_sl)
                record.current_sl = float(new_sl)
            if new_tp is not None:
                record.last_bot_tp_update = float(new_tp)
                record.current_tp = float(new_tp)
            record.last_bot_update_time = now_iso
            if action_note:
                record.notes.append(f"{now_iso}: {action_note}")

        self.save_state()

    def record_add_on(self, ticket: int, add_on_lots: float, note: str = "") -> None:
        """Records a scale-in on an active position."""
        with self._lock:
            record = self._records.get(int(ticket))
            if not record:
                return
            record.add_ons_count += 1
            now_iso = datetime.now(timezone.utc).isoformat()
            record.notes.append(f"{now_iso}: Add-on +{add_on_lots:.2f} lots. {note}")

        self.save_state()

    def close_and_archive(self, ticket: int, reason: str = "") -> None:
        """Removes a closed position from active registry and archives to history file."""
        archived_record = None
        with self._lock:
            ticket = int(ticket)
            if ticket in self._records:
                archived_record = self._records.pop(ticket)
                now_iso = datetime.now(timezone.utc).isoformat()
                archived_record.notes.append(f"Closed and archived at {now_iso}: {reason}")

        if archived_record:
            self.save_state()
            self._append_to_history(archived_record)
            logger.info(f"[ARCHIVED] Manual ticket #{ticket} removed from active registry: {reason}")

    def _append_to_history(self, record: ManualPositionRecord) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.history_file)), exist_ok=True)
        try:
            history = []
            if os.path.exists(self.history_file):
                with open(self.history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
            history.append(record.to_dict())
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            logger.error(f"[HISTORY_ARCHIVE_ERROR] Could not archive #{record.ticket}: {e}")
