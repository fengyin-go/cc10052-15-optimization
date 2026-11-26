"""演示场景：O12 在新基线生效前已经确认异常并提交了评审申请。

场景状态固定为“评审申请已提交、材料尚未领取”，随后由接口完成：
领取材料 → 从检测入口重新提交评估。历史凭证用 `app.decision` 真实复算生成，
不是手写常量，所以凭证编号可以被再次校验。
"""
from __future__ import annotations

from typing import Any

from app.decision import as_float, evaluate

O12_EVALUATED_AT = "2026-11-24T10:00:00+00:00"
O12_REVIEWED_AT = "2026-11-24T10:05:00+00:00"


def _historical_baseline() -> dict[str, Any]:
    return {
        "基线版本": "BL-12-20261101",
        "指标编码": "M-12",
        "实验编码": "EXP_-0012",
        "指标窗口": "2026-10-20~2026-10-26",
        "基线值": "0.1000",
        "观测数": "9600",
        "阈值": "0.10",
        "阈值版本": "TH-v3",
        "适用范围": "全部分组",
        "生效时间": "2026-11-01T08:00:00+00:00",
        "状态": "已失效",
        "发布人": "口径负责人",
        "备注": "O12 场景初始基线，偏差 12% 刚超过 10% 阈值",
        "修订号": "1",
    }


def apply(tables: dict[str, list[dict[str, Any]]]) -> None:
    observation = next(
        (row for row in tables.get("anomaly_observation", []) if row.get("观测编号") == "O12"),
        None,
    )
    if observation is None:
        return
    baseline = _historical_baseline()
    evaluation = evaluate(
        {
            "指标编码": "M-12",
            "实验编码": "EXP_-0012",
            "指标窗口": "2026-10-20~2026-10-26",
            "观测值": as_float(observation.get("观测值")),
            "观测数": 9800,
            "适用范围": observation.get("适用范围"),
        },
        baseline,
        threshold={"阈值": "0.10", "阈值版本": "TH-v3"},
    )
    record = {
        "id": 1,
        "评估编号": "EV-0001",
        "观测编号": "O12",
        "指标编码": "M-12",
        "实验编码": "EXP_-0012",
        "指标窗口": "2026-10-20~2026-10-26",
        "观测值": observation.get("观测值"),
        "观测数": "9800",
        "适用范围": "全部分组",
        "基线快照": dict(baseline),
        "基线版本": baseline["基线版本"],
        "基线值": baseline["基线值"],
        "阈值": "0.10",
        "阈值版本": "TH-v3",
        "原始偏差": evaluation.get("原始偏差"),
        "偏差率": evaluation.get("偏差率"),
        "偏差率文本": evaluation.get("偏差率文本"),
        "偏差类型": evaluation.get("偏差类型"),
        "判定": evaluation.get("判定"),
        "结论": evaluation.get("结论"),
        "是否超阈值": evaluation.get("是否超阈值"),
        "可交付": True,
        "处理状态": "已确认",
        "判定说明": evaluation.get("判定说明"),
        "比较依据": evaluation.get("比较依据"),
        "下一步": "异常已确认并提交结论评审。",
        "凭证编号": evaluation.get("凭证编号"),
        "凭证摘要": evaluation.get("凭证摘要"),
        "判定时间": O12_EVALUATED_AT,
        "判定依据修订": 1,
        "客户端请求号": "seed-o12-initial",
        "异常事件编号": "AN-DV-M-12-20261124",
        "评审记录编号": "RV-AN-1",
        "重算状态": "未重算",
        "来源评估编号": None,
        "超阈值但已被新基线覆盖": True,
        "废弃原因": (
            "新基线 BL-12-20261125 生效后，同一观测偏差为 6.67%，低于阈值；"
            "本凭证只代表 BL-12-20261101/TH-v3 下的判定"
        ),
        "status": "已判定",
        "pending": False,
        "abnormal": True,
    }
    tables.setdefault("anomaly_evaluation", []).append(record)

    observation.update({
        "status": "已确认",
        "pending": False,
        "abnormal": True,
        "当前评估编号": "EV-0001",
        "当前判定": "超阈值",
        "评估状态": "已确认待评审",
        "新基线判定预览": "未超阈值（待重新评估）",
    })

    anomalies = tables.setdefault("anomaly_metric", [])
    anomalies.append({
        "id": max((int(row.get("id", 0)) for row in anomalies), default=0) + 1,
        "status": "已确认",
        "pending": False,
        "abnormal": False,
        "异常编号": "AN-DV-M-12-20261124",
        "指标编码": "M-12",
        "基线区间": "2026-10-20~2026-10-26",
        "观测值": "0.112",
        "异常评分": "0.12",
        "观测编号": "O12",
        "实验编码": "EXP_-0012",
        "评估编号": "EV-0001",
        "凭证编号": evaluation.get("凭证编号"),
        "基线版本": "BL-12-20261101",
        "阈值版本": "TH-v3",
        "阈值": "0.10",
        "原始偏差": str(evaluation.get("原始偏差")),
        "偏差率": evaluation.get("偏差率文本"),
        "确认时间": O12_REVIEWED_AT,
        "评审记录编号": "RV-AN-1",
    })

    reviews = tables.setdefault("conclusion_review", [])
    reviews.append({
        "id": max((int(row.get("id", 0)) for row in reviews), default=0) + 1,
        "status": "待评审",
        "pending": True,
        "abnormal": False,
        "记录编号": "RV-AN-1",
        "实验编码": "EXP_-0012",
        "评审结论": "指标异常 O12（M-12）待评审处置",
        "评审角色": "数据质量",
        "评审时间": O12_REVIEWED_AT,
        "来源类型": "指标异常",
        "异常编号": "AN-DV-M-12-20261124",
        "观测编号": "O12",
        "评估编号": "EV-0001",
        "材料状态": "未领取",
        "材料版本": "0",
        "判定依据修订": "1",
    })
