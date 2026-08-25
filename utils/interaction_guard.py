"""Small helpers that make Telegram callback processing idempotent."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator


@dataclass
class _LockEntry:
    lock: asyncio.Lock
    refs: int = 0


_callback_locks: dict[tuple[int, int, int, str], _LockEntry] = {}


def callback_action_key(callback: Any, action: str) -> tuple[int, int, int, str]:
    """Build a stable key for one button action in one Telegram message."""
    user_id = getattr(getattr(callback, 'from_user', None), 'id', 0) or 0
    message = getattr(callback, 'message', None)
    chat = getattr(message, 'chat', None)
    chat_id = getattr(chat, 'id', user_id) or user_id
    message_id = getattr(message, 'message_id', 0) or 0
    return chat_id, user_id, message_id, action


@asynccontextmanager
async def callback_action_lock(callback: Any, action: str) -> AsyncIterator[None]:
    """Serialize duplicate callbacks from the same user/message/action."""
    key = callback_action_key(callback, action)
    entry = _callback_locks.get(key)
    if entry is None:
        entry = _LockEntry(lock=asyncio.Lock())
        _callback_locks[key] = entry

    entry.refs += 1
    await entry.lock.acquire()
    try:
        yield
    finally:
        entry.lock.release()
        entry.refs -= 1
        if entry.refs == 0:
            _callback_locks.pop(key, None)


async def is_expected_state(state: Any, expected_state: Any) -> bool:
    expected = getattr(expected_state, 'state', expected_state)
    return await state.get_state() == expected
