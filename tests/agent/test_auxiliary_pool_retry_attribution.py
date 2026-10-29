"""A failed post-rotation retry is charged to the key that sent it, not to the pool's current entry.

Seen in production: an approval aux call 401'd on a revoked key, the pool rotated to the working
key, the rebuilt client still carried the revoked key (the session endpoint pins its own key), the
retry 401'd again, and recovery marked ``current()``: the working key. A cron job starting in that
cooldown window found no usable entry and failed with a non-retryable 401.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent.auxiliary_client import call_llm


def _auth_error():
    err = Exception("Incorrect API key provided")
    err.status_code = 401
    return err


class _Pool:
    def __init__(self):
        self.rotate_calls = []

    def has_credentials(self):
        return True

    def try_refresh_current(self):
        return None

    def mark_exhausted_and_rotate(self, **kwargs):
        self.rotate_calls.append(kwargs)
        return SimpleNamespace(id="cred-good")


def _client(api_key):
    client = MagicMock()
    client.base_url = "https://api.openai.com/v1"
    client.api_key = api_key
    client.chat.completions.create.side_effect = _auth_error()
    return client


@pytest.mark.parametrize("retry_key", ["sk-revoked", "sk-good"])
def test_failed_retry_is_charged_to_the_key_that_sent_it(retry_key):
    first, retry = _client("sk-revoked"), _client(retry_key)
    pool = _Pool()
    with (
        patch("agent.auxiliary_client._resolve_task_provider_model",
              return_value=("openai-api", "gpt-5.6", None, None, None)),
        patch("agent.auxiliary_client._get_cached_client",
              side_effect=[(first, "gpt-5.6"), (retry, "gpt-5.6")]),
        patch("agent.auxiliary_client._refresh_provider_credentials", return_value=False),
        patch("agent.auxiliary_client.load_pool", return_value=pool),
        patch("agent.auxiliary_client._try_configured_fallback_chain", return_value=(None, None, "")),
        patch("agent.auxiliary_client._try_main_fallback_chain", return_value=(None, None, "")),
        patch("agent.auxiliary_client._try_payment_fallback", return_value=(None, None, "")),
        pytest.raises(Exception, match="Incorrect API key"),
    ):
        call_llm(task="approval", provider="openai-api", model="gpt-5.6",
                 messages=[{"role": "user", "content": "hi"}])

    assert retry.chat.completions.create.call_count == 1
    assert [c["api_key_hint"] for c in pool.rotate_calls] == ["sk-revoked", retry_key]
