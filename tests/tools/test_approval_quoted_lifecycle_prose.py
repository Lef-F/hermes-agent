"""Gateway-lifecycle and self-termination rules must not fire on quoted prose.

Same contract as the #93392 hardline fix: a quoted argument is data, so searching notes or logs
for "hermes gateway restart" needs no approval, while every executed spelling still prompts.
"""
import pytest

from tools.approval_detection import detect_dangerous_command


@pytest.mark.parametrize("command", [
    'grep -n "hermes gateway restart" notes.md',
    'journalctl --user -u hermes-gateway | grep "hermes gateway stop"',
    'rg "pkill hermes" docs/',
    "rg 'killall gateway' docs/",
    'git commit -m "docs: never run hermes update from a cron job"',
    'echo "nohup hermes gateway run &"',
    "echo 'kill $(pgrep hermes)'",
])
def test_quoted_prose_is_not_a_lifecycle_command(command):
    assert detect_dangerous_command(command) == (False, None, None)


@pytest.mark.parametrize("command", [
    "hermes -p house gateway restart",
    "~/.local/bin/hermes gateway restart",
    "uv run hermes update",
    "pkill -f hermes",
    'pkill -f "hermes gateway"',
    'killall "hermes"',
    "true | xargs pkill hermes",
    'kill $(pgrep -f "hermes gateway")',
    "nohup hermes gateway run &",
    'grep "pkill" notes.md; pkill hermes',
    'sh -c "hermes gateway restart"',
    'bash -c "pkill -f hermes"',
    "eval 'hermes gateway stop'",
    "echo 'hermes gateway restart' | sh",
])
def test_executed_lifecycle_commands_still_prompt(command):
    is_dangerous, _key, description = detect_dangerous_command(command)
    assert is_dangerous, command
    assert "gateway" in description or "self-termination" in description or "hermes" in description
