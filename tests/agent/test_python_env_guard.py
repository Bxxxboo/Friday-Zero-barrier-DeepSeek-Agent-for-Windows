from __future__ import annotations

from unittest.mock import MagicMock

from friday.agent import FridayAgent
from friday.storage import UserSettings


def _make_agent(monkeypatch) -> FridayAgent:
    monkeypatch.setattr(
        "friday.api_connect.build_openai_client",
        lambda *args, **kwargs: MagicMock(),
    )
    return FridayAgent(UserSettings(api_key="sk-test"), lambda _pending: True)


def test_python_env_info_second_call_short_circuits(monkeypatch):
    agent = _make_agent(monkeypatch)
    agent._python_env_info_used = True
    result = agent._execute_single_tool("python_env_info", {}, 1, 1, None)
    assert "已调用过" in result


def test_python_env_info_first_call_marks_used(monkeypatch):
    agent = _make_agent(monkeypatch)
    monkeypatch.setattr("friday.agent.execute_tool", lambda *a, **k: "env ok")
    monkeypatch.setattr("friday.agent.log_operation", lambda *a, **k: {})
    result = agent._execute_single_tool("python_env_info", {}, 1, 1, None)
    assert result == "env ok"
    assert agent._python_env_info_used is True
