"""指标异常检测领域服务：管理指标值异常波动的基线对比、异常评分与误报标记。

数据链路位置：质量检测层，消费指标计算结果与时效监控告警，检测指标异常波动，
把确认异常推送给结论评审队列进入人工处置。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.base import BaseModuleService
from app.store import store


class AnomalyMetricService(BaseModuleService):
    MODULE = "anomaly_metric"
    ENTITY = "异常事件"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["异常编号", "指标编码", "基线区间", "观测值", "异常评分"]
    REQUIRED_FIELDS = ["异常编号", "指标编码", "基线区间"]
    STATUS_ORDER = ["待确认", "已确认", "误报"]
    ACTION_RULES = {"确认异常": "已确认", "标记误报": "误报"}
    NEGATIVE_ACTIONS = []

    # ---- 业务扩展：异常检测与人工处置 ----

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        """动作入口：确认异常必须带可追溯的告警判定凭证，误报必须写原因。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"
        if action == "确认异常":
            result = self.confirm_anomaly(entry_id)
            return entry, str(result.get("message"))
        if action == "标记误报":
            result = self.mark_false_positive(entry_id, str(entry.get("误报原因") or "人工标记误报"))
            return entry, str(result.get("message"))
        return super().run_action(entry_id, action)

    def _linked_evaluation(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        evaluation_ref = str(entry.get("评估编号") or "")
        observations = store.rows("anomaly_observation")
        observation_code = str(entry.get("观测编号") or "")
        if not observation_code and evaluation_ref:
            match = next(
                (e for e in store.rows("anomaly_evaluation")
                 if str(e.get("评估编号")) == evaluation_ref),
                None,
            )
            observation_code = str((match or {}).get("观测编号", ""))
        if not observation_code:
            return None
        observation = next(
            (o for o in observations if str(o.get("观测编号")) == observation_code),
            None,
        )
        if observation is None:
            return None
        candidates = [
            e for e in store.rows("anomaly_evaluation")
            if str(e.get("观测编号")) == observation_code
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda e: (str(e.get("判定时间") or ""), int(e.get("id", 0))))

    def confirm_anomaly(self, entry_id: int) -> dict[str, Any]:
        """确认异常：锁定判定凭证里的基线/阈值/原始偏差，再推送结论评审。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "待确认":
            return {"ok": False, "message": "仅待确认异常可确认"}
        evaluation = self._linked_evaluation(entry)
        if evaluation is None:
            return {
                "ok": False,
                "message": (
                    "该异常没有关联的评估凭证，请先从检测入口对该指标窗口的观测"
                    "提交评估，再回来确认"
                ),
            }
        if not evaluation.get("可交付"):
            return {
                "ok": False,
                "message": f"评估凭证 {evaluation.get('判定')} 不可确认异常：{evaluation.get('下一步')}",
            }
        if evaluation.get("判定") != "超阈值":
            return {
                "ok": False,
                "message": (
                    f"当前凭证判定为 {evaluation.get('判定')}，已不再支持确认异常；"
                    "如依据变化请重新评估"
                ),
            }
        now = datetime.now(timezone.utc).isoformat()
        entry["status"] = "已确认"
        entry["pending"] = False
        # 保留计算用过的阈值版本与原始偏差，后续基线变化不改写这些字段。
        entry["评估编号"] = evaluation.get("评估编号")
        entry["基线版本"] = evaluation.get("基线版本")
        entry["阈值版本"] = evaluation.get("阈值版本")
        entry["阈值"] = str(evaluation.get("阈值"))
        entry["原始偏差"] = str(evaluation.get("原始偏差"))
        entry["偏差率"] = evaluation.get("偏差率文本")
        entry["凭证编号"] = evaluation.get("凭证编号")
        entry["确认时间"] = now
        review_rows = store.rows("conclusion_review")
        review_id = max((int(r.get("id", 0)) for r in review_rows), default=0) + 1
        review_code = f"RV-AN-{entry_id}"
        entry["评审记录编号"] = review_code
        review_rows.append({
            "id": review_id,
            "记录编号": review_code,
            "实验编码": str(entry.get("实验编码") or ""),
            "评审结论": (
                f"指标异常 {entry.get('异常编号', '')} "
                f"（{entry.get('指标编码', '')}）待评审处置"
            ),
            "评审角色": "数据质量",
            "评审时间": now,
            "status": "待评审",
            "pending": True,
            "abnormal": False,
            "来源类型": "指标异常",
            "异常编号": entry.get("异常编号"),
            "观测编号": entry.get("观测编号"),
            "评估编号": evaluation.get("评估编号"),
            "材料状态": "未领取",
            "材料版本": "0",
            "判定依据修订": str(evaluation.get("判定依据修订") or ""),
        })
        evaluation["异常事件编号"] = entry.get("异常编号")
        evaluation["评审记录编号"] = review_code
        return {"ok": True, "message": f"异常 {entry.get('异常编号')} 已确认并进入评审"}

    def mark_false_positive(self, entry_id: int, reason: str) -> dict[str, Any]:
        """标记误报并把原因写回数据时效监控修正告警。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "待确认":
            return {"ok": False, "message": "仅待确认异常可标记误报"}
        if not reason.strip():
            return {"ok": False, "message": "标记误报必须填写原因"}
        entry["status"] = "误报"
        entry["pending"] = False
        entry["abnormal"] = True
        entry["误报原因"] = reason
        entry["误报时间"] = datetime.now(timezone.utc).isoformat()
        source = str(entry.get("异常编号", ""))
        if source.startswith("AN-DF-"):
            target_id = source.replace("AN-DF-", "").split("-")[0]
            if target_id.isdigit():
                fresh = store.find("data_freshness", int(target_id))
                if fresh is not None:
                    fresh["status"] = "新鲜"
                    fresh["时效等级"] = "新鲜"
                    fresh["pending"] = False
        return {"ok": True, "message": f"已标记误报（{reason}），来源告警已修正"}

    def detect_deviation(self, metric_code: str, observed: float, baseline: float) -> dict[str, Any]:
        """对比观测值与基线，偏差超阈值时登记新异常事件。

        这是不带窗口与阈值版本的旧入口，登记出来的事件没有判定凭证，
        不能直接确认；正式处置请走 /api/decision/evaluate 生成评估凭证。
        """
        if not metric_code:
            return {"ok": False, "message": "指标编码为空"}
        if baseline == 0:
            deviation = abs(observed)
        else:
            deviation = abs(observed - baseline) / abs(baseline)
        if deviation < 0.2:
            return {"ok": True, "message": f"偏差 {deviation:.2%} 未超阈值", "anomaly": False}
        rows = store.rows(self.MODULE)
        rows.append({
            "id": max((int(r.get("id", 0)) for r in rows), default=0) + 1,
            "异常编号": f"AN-DV-{metric_code}-{datetime.now(timezone.utc).timestamp():.0f}",
            "指标编码": metric_code,
            "基线区间": f"[{baseline}, {baseline}]",
            "观测值": str(observed),
            "异常评分": str(round(min(deviation, 1.0), 2)),
            "status": "待确认",
            "pending": True,
            "abnormal": False,
        })
        return {"ok": True, "message": f"偏差 {deviation:.2%} 超阈值，异常已登记", "anomaly": True}

    def batch_confirm(self) -> dict[str, Any]:
        """批量确认全部高分待确认异常。"""
        pending = [
            r for r in store.rows(self.MODULE)
            if r.get("status") == "待确认" and float(str(r.get("异常评分", "0")) or 0) >= 0.7
        ]
        done = sum(1 for r in pending if self.confirm_anomaly(int(r.get("id", 0))).get("ok"))
        return {"ok": True, "message": f"高分异常批量确认 {done} 条"}

    def consume_from_metric_compute(self, metric_code: str) -> list[float]:
        """读取指标计算层最近作业产出，构造观测值序列。"""
        values = []
        for r in store.rows("metric_compute"):
            if r.get("指标编码") == metric_code and r.get("status") == "已完成":
                value = str(r.get("作业名称", "")).split("-")[-1]
                if value.replace(".", "").isdigit():
                    values.append(float(value))
        return values

    def consume_from_metric_catalog(self, metric_code: str) -> dict[str, Any]:
        """读取指标口径中心的口径版本，锁定异常检测的口径上下文。"""
        metric = next((m for m in store.rows("metric_catalog") if m.get("指标编码") == metric_code), None)
        if metric is None:
            return {"ok": False, "message": "口径不存在"}
        return {"ok": True, "口径版本": metric.get("口径版本", ""), "聚合窗口": metric.get("聚合窗口", "")}

    def export_confirmed(self, metric_code: str) -> list[dict[str, Any]]:
        """导出已确认异常清单，保留确认时用过的阈值版本与原始偏差。"""
        return [
            {
                "异常编号": r.get("异常编号", ""),
                "观测编号": r.get("观测编号", ""),
                "观测值": r.get("观测值", ""),
                "异常评分": r.get("异常评分", ""),
                "基线版本": r.get("基线版本", ""),
                "阈值版本": r.get("阈值版本", ""),
                "阈值": r.get("阈值", ""),
                "原始偏差": r.get("原始偏差", ""),
                "评估编号": r.get("评估编号", ""),
                "凭证编号": r.get("凭证编号", ""),
                "确认时间": r.get("确认时间", ""),
            }
            for r in store.rows(self.MODULE)
            if r.get("指标编码") == metric_code and r.get("status") == "已确认"
        ]
