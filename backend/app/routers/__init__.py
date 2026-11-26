"""业务路由汇总：所有模块共用一套资源路由，由领域服务完成分派。

告警判定接口带固定前缀，必须排在通用的 `/api/{module}` 资源路由之前，
否则 `/api/decision/...` 会被资源路由当成模块名截走。
"""
from __future__ import annotations

from app.routers import decision, resource

ROUTERS = [decision, resource]
