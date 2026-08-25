import asyncio
import unittest

from utils.interaction_guard import callback_action_key, callback_action_lock, is_expected_state


class FakeUser:
    id = 42


class FakeChat:
    id = 100


class FakeMessage:
    chat = FakeChat()
    message_id = 7


class FakeCallback:
    from_user = FakeUser()
    message = FakeMessage()


class FakeExpectedState:
    state = 'Form:state'


class FakeState:
    async def get_state(self):
        return 'Form:state'


class InteractionGuardTests(unittest.IsolatedAsyncioTestCase):
    def test_callback_action_key(self):
        self.assertEqual(callback_action_key(FakeCallback(), 'confirm'), (100, 42, 7, 'confirm'))

    async def test_is_expected_state(self):
        self.assertTrue(await is_expected_state(FakeState(), FakeExpectedState))
        self.assertTrue(await is_expected_state(FakeState(), 'Form:state'))

    async def test_callback_action_lock_serializes_same_action(self):
        active_count = 0
        max_active_count = 0

        async def worker():
            nonlocal active_count, max_active_count
            async with callback_action_lock(FakeCallback(), 'confirm'):
                active_count += 1
                max_active_count = max(max_active_count, active_count)
                await asyncio.sleep(0)
                active_count -= 1

        await asyncio.gather(worker(), worker(), worker())
        self.assertEqual(max_active_count, 1)


if __name__ == '__main__':
    unittest.main()
