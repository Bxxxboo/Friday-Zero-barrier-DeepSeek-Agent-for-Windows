"""微信 ↔ 星期五桥接（文字指令 + 微信审批）。"""

from friday.weixin.bridge import handle_inbound

__all__ = ["handle_inbound"]
