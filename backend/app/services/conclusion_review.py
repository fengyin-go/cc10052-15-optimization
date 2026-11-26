"""结论评审队列领域服务：管理实验结论的评审流转、角色协同与办结归档。

数据链路位置：评审治理层，是实验结论进入业务决策前的最后一道人工关，消费
报告分发与异常处置的评审请求，把通过结论推送归档。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app import review_workflow as rw
from app.services.base import BaseModuleService
from app.store import store


class ConclusionReviewService(BaseModuleService):
    MODULE = "conclusion_review"
    ENTITY = "评审记录"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["记录编号", "实验编码", "评审结论", "评审角色", "评审时间"]
    REQUIRED_FIELDS = ["记录编号", "实验编码", "评审结论"]
    STATUS_ORDER = ["待评审", "已通过", "已驳回"]
    ACTION_RULES = {"通过记录": "已通过", "驳回记录": "已驳回"}
    NEGATIVE_ACTIONS = ["驳回记录"]

    # ---- 业务扩展：评审流转与结论归档 ----

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        """动作入口：异常来源的评审必须走带依据的办结流程。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"
        if action not in self.ACTION_RULES:
            return super().run_action(entry_id, action)
        if str(entry.get("来源类型", "")) != "指标异常":
            if action == "通过记录":
                result = self.approve(entry_id, "")
            else:
                result = self.reject(entry_id, str(entry.get("驳回原因") or "人工驳回"))
            return entry, str(result.get("message"))
        code = str(entry.get("记录编号", ""))
        if action == "驳回记录" and not str(entry.get("驳回原因") or "").strip():
            return entry, (
                "异常来源的评审必须带依据和驳回原因；"
                "请在评审材料页填写原因后调用驳回接口"
            )
        try:
            if action == "通过记录":
                rw.accept(code, comment="")
            else:
                rw.reject(code, str(entry.get("驳回原因") or ""), basis_ref=None)
        except rw.ReviewConflict as conflict:
            return entry, f"{conflict.message}；下一步：{conflict.next_step}"
        return entry, f"记录 {code} 已按告警判定凭证办结"

    def _review_conflict(self, conflict: rw.ReviewConflict) -> dict[str, Any]:
        return {"ok": False, "message": f"{conflict.message}；下一步：{conflict.next_step}"}

    def approve(
        self, entry_id: int, comment: str, *, basis: str | None = None
    ) -> dict[str, Any]:
        """通过评审记录：异常来源按判定凭证办结，其余直接推送归档。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "待评审":
            return {"ok": False, "message": "仅待评审记录可通过"}
        if str(entry.get("来源类型", "")) == "指标异常":
            try:
                result = rw.accept(
                    str(entry.get("记录编号", "")), basis_ref=basis, comment=comment
                )
            except rw.ReviewConflict as conflict:
                return self._review_conflict(conflict)
            return {
                "ok": True,
                "message": f"记录 {entry.get('记录编号')} 已按依据 "
                           f"{result['evaluation'].get('评估编号')} 办结",
                "entry": entry,
            }
        return self._approve_plain(entry, comment)

    def _approve_plain(self, entry: dict[str, Any], comment: str) -> dict[str, Any]:
        entry["status"] = "已通过"
        entry["pending"] = False
        entry["评审时间"] = datetime.now(timezone.utc).isoformat()
        entry["评审意见"] = comment or "同意采纳"
        archive_rows = store.rows("exp_archive")
        archive_rows.append({
            "id": max((int(r.get("id", 0)) for r in archive_rows), default=0) + 1,
            "实验编码": entry.get("实验编码", ""),
            "结束时间": datetime.now(timezone.utc).isoformat(),
            "结论摘要": f"评审通过：{entry.get('评审结论', '')}",
            "归档位置": f"review/{entry.get('记录编号', '')}",
            "保留等级": "标准",
            "status": "待归档",
            "pending": True,
            "abnormal": False,
        })
        return {"ok": True, "message": f"记录 {entry.get('记录编号')} 已通过并推送归档"}

    def reject(
        self, entry_id: int, reason: str, *, basis: str | None = None
    ) -> dict[str, Any]:
        """驳回评审记录并通知报告分发停止后续分发。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "待评审":
            return {"ok": False, "message": "仅待评审记录可驳回"}
        if not reason.strip():
            return {"ok": False, "message": "驳回必须填写原因"}
        if str(entry.get("来源类型", "")) == "指标异常":
            try:
                result = rw.reject(
                    str(entry.get("记录编号", "")), reason, basis_ref=basis
                )
            except rw.ReviewConflict as conflict:
                return self._review_conflict(conflict)
            return {
                "ok": True,
                "message": f"记录 {entry.get('记录编号')} 已驳回，联动停止 "
                           f"{result['stalled']} 条分发",
                "entry": entry,
            }
        entry["status"] = "已驳回"
        entry["pending"] = False
        entry["abnormal"] = True
        entry["驳回原因"] = reason
        exp_code = str(entry.get("实验编码", ""))
        stalled = [
            r for r in store.rows("report_dist")
            if exp_code and exp_code in str(r.get("报告编码", "")) and r.get("status") == "排队中"
        ]
        for row in stalled:
            row["status"] = "送达失败"
            row["abnormal"] = True
            row["失败原因"] = "结论被驳回，停止分发"
        return {"ok": True, "message": f"记录已驳回，联动停止 {len(stalled)} 条分发"}

    def batch_approve(self) -> dict[str, Any]:
        """批量通过全部待评审记录；没有判定凭证的异常记录会被跳过并说明原因。"""
        pending = [r for r in store.rows(self.MODULE) if r.get("status") == "待评审"]
        done, skipped = 0, []
        for row in pending:
            result = self.approve(int(row.get("id", 0)), "")
            if result.get("ok"):
                done += 1
            else:
                skipped.append(f"{row.get('记录编号')}：{result.get('message')}")
        message = f"批量通过 {done}/{len(pending)} 条评审"
        if skipped:
            message += "；跳过 " + "；".join(skipped)
        return {"ok": True, "message": message, "skipped": skipped}

    def claim_material(self, entry_id: int) -> dict[str, Any]:
        """领取评审材料：固化本次判定依据，供评审核对触发基线。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": f"评审记录 {entry_id} 不存在"}
        try:
            material = rw.claim_material(str(entry.get("记录编号", "")))
        except rw.ReviewConflict as conflict:
            return self._review_conflict(conflict)
        return {"ok": True, "message": "评审材料已领取", "material": material, "entry": entry}

    def request_recalculation(self, entry_id: int) -> dict[str, Any]:
        """评审认为依据已变化时要求重算，并回到“需重新领取”。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": f"评审记录 {entry_id} 不存在"}
        try:
            result = rw.request_recalculation(str(entry.get("记录编号", "")))
        except rw.ReviewConflict as conflict:
            return self._review_conflict(conflict)
        return {
            "ok": True,
            "message": str(entry.get("冲突提示") or "已重新评估"),
            "entry": entry,
            "evaluation": result["evaluation"],
        }

    def review_material(self, entry_id: int) -> dict[str, Any]:
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": f"评审记录 {entry_id} 不存在"}
        return {"ok": True, "material": rw.material_view(entry)}

    def consume_from_report_dist(self, exp_code: str) -> list[dict[str, Any]]:
        """读取报告分发的送达记录，作为评审证据材料。"""
        return [
            {"报告编码": r.get("报告编码", ""), "接收方": r.get("接收方", ""), "送达时间": r.get("送达时间", "")}
            for r in store.rows("report_dist")
            if exp_code and exp_code in str(r.get("报告编码", "")) and r.get("status") == "已送达"
        ]

    def consume_from_anomaly_metric(self, exp_code: str) -> list[dict[str, Any]]:
        """读取指标异常检测的已确认事件，带上触发基线与阈值版本供核对。"""
        return [
            {
                "异常编号": r.get("异常编号", ""),
                "异常评分": r.get("异常评分", ""),
                "观测编号": r.get("观测编号", ""),
                "基线版本": r.get("基线版本", ""),
                "阈值版本": r.get("阈值版本", ""),
                "原始偏差": r.get("原始偏差", ""),
                "评估编号": r.get("评估编号", ""),
            }
            for r in store.rows("anomaly_metric")
            if r.get("status") in ("待确认", "已确认")
            and exp_code in str(r.get("指标编码", ""))
        ]

    def reopen_rejected(self, entry_id: int) -> dict[str, Any]:
        """重开已驳回记录：修正结论后回到待评审。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "已驳回":
            return {"ok": False, "message": "仅已驳回记录可重开"}
        entry["status"] = "待评审"
        entry["pending"] = True
        entry["abnormal"] = False
        entry["重开次数"] = str(int(entry.get("重开次数", "0") or 0) + 1)
        if str(entry.get("来源类型", "")) == "指标异常":
            # 重开后必须按当时依据重新领取，不能沿用驳回前固化的材料。
            entry["材料状态"] = "需重新领取"
            entry["依据历史"] = list(entry.get("依据历史") or [])
        return {"ok": True, "message": f"记录已重开（第 {entry['重开次数']} 次）"}

    def export_review_queue(self) -> list[dict[str, Any]]:
        """导出待评审队列，供指标查询服务展示办结进度。"""
        return [
            {
                "记录编号": r.get("记录编号", ""),
                "实验编码": r.get("实验编码", ""),
                "评审角色": r.get("评审角色", ""),
                "进入时间": r.get("评审时间", ""),
            }
            for r in store.rows(self.MODULE) if r.get("status") == "待评审"
        ]
