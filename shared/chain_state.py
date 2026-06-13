"""Lightweight per-room chain state.

Band delivers full room history to each agent, so the transcript is the primary
source of truth. This store is a thin guard layer: it records which stages have
completed for a room and lets an agent ignore duplicate / already-processed
messages (Band may redeliver, and agents shouldn't double-act).

In-memory by default (sufficient for a single-process agent or the demo). Swap the
backing dict for Redis if agents are scaled horizontally.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class RoomState:
    room_id: str
    stages_done: set[str] = field(default_factory=set)
    processed_messages: set[str] = field(default_factory=set)


class ChainStateStore:
    def __init__(self) -> None:
        self._rooms: dict[str, RoomState] = {}
        self._lock = threading.Lock()

    def _room(self, room_id: str) -> RoomState:
        with self._lock:
            return self._rooms.setdefault(room_id, RoomState(room_id=room_id))

    def already_processed(self, room_id: str, message_id: str) -> bool:
        """True if this message was already handled (idempotency guard)."""
        room = self._room(room_id)
        with self._lock:
            if message_id in room.processed_messages:
                return True
            room.processed_messages.add(message_id)
            return False

    def mark_stage(self, room_id: str, stage: str) -> None:
        self._room(room_id).stages_done.add(stage)

    def stage_done(self, room_id: str, stage: str) -> bool:
        return stage in self._room(room_id).stages_done

    def reset(self, room_id: str) -> None:
        with self._lock:
            self._rooms.pop(room_id, None)


# Process-wide singleton used by agents.
store = ChainStateStore()
