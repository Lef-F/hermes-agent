"""Replay reconnect-only deliveries when an adapter recovers on its own (split from
:mod:`gateway.platforms.base`).

A send rejected with ``send_path_degraded`` (a reply, or cron output queued by
``cron.scheduler_delivery._queue_for_live_reconnect``) waits in the delivery ledger for the
post-reconnect sweep. The runner sweeps after it reinstalls an adapter, but an adapter that heals
in place (Telegram polling resumes after a link drop) never goes through that path, so the row sat
``failed`` until the boot sweep abandoned it as stale.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


def schedule_send_path_redelivery(adapter) -> None:
    """Sweep *adapter*'s reconnect-only ledger rows in the background once its send path is proven
    again. Idempotent with the runner's own reconnect sweep: rows are claimed atomically."""
    redeliver = getattr(getattr(adapter, "gateway_runner", None), "_redeliver_failed_obligations_for_platform", None)
    if not callable(redeliver):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # no running loop: the runner's reconnect and boot sweeps still apply
        logger.debug("send-path redelivery for %s not scheduled: no running loop", adapter.platform.value)
        return
    task = loop.create_task(
        redeliver(adapter.platform, profile=getattr(adapter, "_owner_profile", None)),
        name=f"send-path-redelivery:{adapter.platform.value}")
    tasks = getattr(adapter, "_background_tasks", None)
    if isinstance(tasks, set):
        tasks.add(task)
        task.add_done_callback(tasks.discard)
