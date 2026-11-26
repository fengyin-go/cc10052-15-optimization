"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
告警判定相关的表（基线、观测、阈值、评估）带一份整理过的示例数据，并且支持
reset() 回到初始状态，方便复现“旧结果可复算、新评估不复用旧阈值”的场景。
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from app.seed import SEED_ROWS
from app.seed_scenario import apply as apply_seed_scenario

DECISION_TABLES = (
    "anomaly_baseline",
    "anomaly_observation",
    "anomaly_threshold",
    "anomaly_evaluation",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def next_id(rows: list[dict[str, Any]]) -> int:
    return max((int(row.get("id", 0)) for row in rows), default=0) + 1


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}
        self._revisions: dict[str, int] = {}
        self.reset()

    def reset(self) -> None:
        """把全部模块恢复成示例数据的初始状态，并清空修订流水。"""
        self._tables = {
            name: copy.deepcopy(rows) for name, rows in SEED_ROWS.items()
        }
        self._revisions = {}
        for name in DECISION_TABLES:
            self._tables.setdefault(name, [])
        apply_seed_scenario(self._tables)

    def module_names(self) -> list[str]:
        return sorted(
            name for name in self._tables if name not in DECISION_TABLES
        )

    def table_names(self) -> list[str]:
        """包含告警判定内部表在内的全部表名，供调试与导出使用。"""
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    # ---- 修订追踪：判定依据变化只追加记录，不回写历史 ----

    def revision_base(self, module: str) -> int:
        return self._revisions.get(module, 0)

    def bump_revision(self, module: str) -> int:
        self._revisions[module] = self.revision_base(module) + 1
        return self._revisions[module]

    def revision_for(self, module: str, at_least: int = 0) -> int:
        return max(self.revision_base(module), at_least)

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
