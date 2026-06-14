"""按域拆分的 HTTP 路由注册。"""

from friday.api.routes.chat import register_chat_routes
from friday.api.routes.diagnostics import register_diagnostics_routes
from friday.api.routes.plugins import register_plugins_routes
from friday.api.routes.sessions import register_sessions_routes
from friday.api.routes.settings import register_settings_routes
from friday.api.routes.static_pages import register_static_routes

__all__ = [
    "register_chat_routes",
    "register_diagnostics_routes",
    "register_plugins_routes",
    "register_sessions_routes",
    "register_settings_routes",
    "register_static_routes",
]
