"""In-adapter recovery must replay what was refused while the send path was degraded.

A weekly LAN drop made a cron failure alert fail with ``send_path_degraded``; it was queued for
"redelivery once the live adapter reconnects". Telegram polling then recovered inside the adapter
("getUpdates progressing"), which never ran the runner's reconnect sweep, so the row stayed
``failed`` until the boot sweep abandoned it two days later.
"""
import asyncio
from unittest.mock import AsyncMock

import pytest

from gateway.config import Platform, PlatformConfig
from plugins.platforms.telegram.adapter import TelegramAdapter


class _Runner:
    def __init__(self):
        self._redeliver_failed_obligations_for_platform = AsyncMock(return_value=1)


def _degraded_adapter(runner):
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="***"))
    adapter.gateway_runner = runner
    adapter._running = True
    generation, _ = adapter._begin_polling_generation()
    return adapter, generation


@pytest.mark.asyncio
async def test_polling_recovery_sweeps_reconnect_only_rows():
    runner = _Runner()
    adapter, generation = _degraded_adapter(runner)
    adapter.set_owner_profile("house")

    assert adapter._record_polling_progress(generation) is True
    await asyncio.gather(*adapter._background_tasks)

    assert adapter._send_path_degraded is False
    runner._redeliver_failed_obligations_for_platform.assert_awaited_once_with(
        Platform.TELEGRAM, profile="house")


@pytest.mark.asyncio
async def test_progress_on_a_healthy_path_does_not_sweep_again():
    runner = _Runner()
    adapter, generation = _degraded_adapter(runner)
    adapter._record_polling_progress(generation)
    await asyncio.gather(*adapter._background_tasks)

    adapter._record_polling_progress(generation)
    await asyncio.gather(*adapter._background_tasks)

    assert runner._redeliver_failed_obligations_for_platform.await_count == 1
