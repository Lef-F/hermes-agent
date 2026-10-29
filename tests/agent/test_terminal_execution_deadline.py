"""The generic sequential deadline must not cut a foreground terminal call short of its own cap.

Terminal advertises ``timeout`` up to ``FOREGROUND_MAX_TIMEOUT`` (600s) while the executor's
default sequential deadline is 420s, so calls asking for 420-600s were reported as
``timed out after 420.0s`` with the command possibly still running.
"""
import json
import threading

from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageToolCall

from tools.registry import registry


def test_terminal_deadline_covers_foreground_cap():
    from agent.tool_dispatch_helpers import _extend_tool_timeout
    from agent.tool_executor import _DEFAULT_CONCURRENT_TOOL_TIMEOUT_S
    from tools.terminal_tool import FOREGROUND_MAX_TIMEOUT

    assert _extend_tool_timeout("terminal", _DEFAULT_CONCURRENT_TOOL_TIMEOUT_S) > FOREGROUND_MAX_TIMEOUT


def test_terminal_call_outlives_shorter_sequential_deadline(monkeypatch):
    from agent.tool_executor import execute_tool_calls_sequential
    from hermes_cli.config import atomic_config_write, get_config_path
    from run_agent import AIAgent

    # A 2s generic deadline stands in for the 420s default; terminal's own budget must win.
    atomic_config_write(get_config_path(), {"timeouts": {"tools": {"sequential_call": 2}}})
    release = threading.Event()
    timer = threading.Timer(4, release.set)

    def slow_terminal(args, **kwargs):
        timer.start()
        release.wait(15)
        return json.dumps({"output": "released", "exit_code": 0})

    entry = registry.get_entry("terminal")
    assert entry is not None
    monkeypatch.setattr(entry, "handler", slow_terminal)
    agent = AIAgent(model="test-model", provider="openai", api_key="unused-test-key",
                    base_url="http://127.0.0.1:9/v1", enabled_toolsets=["terminal"],
                    quiet_mode=True, skip_context_files=True, skip_memory=True,
                    save_trajectories=False)
    call = ChatCompletionMessageToolCall.model_validate({
        "id": "terminal-deadline", "type": "function",
        "function": {"name": "terminal", "arguments": json.dumps({"command": "true", "timeout": 500})}})
    message = ChatCompletionMessage(role="assistant", content=None, tool_calls=[call])
    messages = []
    try:
        execute_tool_calls_sequential(agent, message, messages, "terminal-deadline", finalize=False)
    finally:
        release.set()
        timer.cancel()
    result = messages[-1]["content"]
    assert "released" in result, result
    assert "timed out" not in result
