from __future__ import annotations

import inspect


def test_weixin_bridge_runs_friday_agent():
    from friday.weixin import bridge

    source = inspect.getsource(bridge._run_agent)
    assert "FridayAgent" in source
    assert "agent.run" in source
