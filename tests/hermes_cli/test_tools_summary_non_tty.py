"""`hermes tools --summary` only prints, so it must work without a terminal (scripts, cron, pipes)."""
import io
from argparse import Namespace

import pytest

from hermes_cli.main_agent_cmds import cmd_tools


def test_summary_runs_without_a_tty(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    cmd_tools(Namespace(tools_action=None, summary=True))
    out = capsys.readouterr().out
    assert "Tool Summary" in out


def test_interactive_tools_still_requires_a_tty(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    with pytest.raises(SystemExit) as exc:
        cmd_tools(Namespace(tools_action=None, summary=False))
    assert exc.value.code == 1
    assert "requires an interactive terminal" in capsys.readouterr().err
