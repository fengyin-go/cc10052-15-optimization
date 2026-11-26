"""评审材料工作流：把告警判定凭证带到结论评审，并处理依据变更时的冲突。

规则：
- 评审材料一领取就固化“本次依据”快照，之后基线或阈值变化不改写这份快照；
- 同一指标窗口内发生重新评估时，评审材料同时展示“本次依据”和“当前依据”，
  并明确标出重新评估状态，评审可以辨认两者差别；
- 接受办结必须绑定一条可交付且属于当前窗口的评估凭证；依据已过期时引导先重算；
- 新建评审记录独立记录自己的依据，不与已登记评审共用。
"""
from __future__ import annotations

from typing import Any

from app import decision_service as ds
from app.store import now_iso, next_id, store


class ReviewConflict(Exception):
    """评审材料与重新评估发生冲突时抛出，消息里带下一步处理。"""

    def __init__(self, message: str, next_step: str) -> None:
        super().__init__(message)
        self.message = message
        self.next_step = next_step


def _review_by_code(code: str) -> dict[str, Any] | None:
    for row in store.rows("conclusion_review"):
        if str(row.get("记录编号", "")) == code:
            return row
    return None


def _evaluation_by_ref(ref: str | int | None) -> dict[str, Any] | None:
    if ref in (None, ""):
        return None
    rows = store.rows("anomaly_evaluation")
    text = str(ref)
    for row in rows:
        if text in (str(row.get("id")), str(row.get("评估编号"))):
            return row
    return None


def _latest_evaluation(observation_code: str) -> dict[str, Any] | None:
    rows = [
        row for row in store.rows("anomaly_evaluation")
        if str(row.get("观测编号", "")) == observation_code
        and not row.get("来源评估编号")
    ]
    if not rows:
        return None
    return max(rows, key=lambda row: (str(row.get("判定时间") or ""), int(row.get("id", 0))))


def _evaluation_basis(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "评估编号": row.get("评估编号"),
        "凭证编号": row.get("凭证编号"),
        "基线版本": row.get("基线版本"),
        "阈值版本": row.get("阈值版本"),
        "阈值": row.get("阈值"),
        "基线值": row.get("基线值"),
        "观测值": row.get("观测值"),
        "原始偏差": row.get("原始偏差"),
        "偏差率文本": row.get("偏差率文本"),
        "偏差类型": row.get("偏差类型"),
        "判定": row.get("判定"),
        "结论": row.get("结论"),
        "可交付": row.get("可交付"),
        "判定时间": row.get("判定时间"),
        "指标窗口": row.get("指标窗口"),
        "适用范围": row.get("适用范围"),
    }


def _anomaly_rows(observation_code: str) -> list[dict[str, Any]]:
    """该观测关联的全部异常事件，含按评估编号回链的历史记录。"""
    evaluation_refs = {
        str(row.get("评估编号"))
        for row in store.rows("anomaly_evaluation")
        if str(row.get("观测编号", "")) == observation_code
    }
    return [
        row for row in store.rows("anomaly_metric")
        if str(row.get("观测编号", "")) == observation_code
        or (
            not row.get("观测编号")
            and str(row.get("评估编号", "")) in evaluation_refs
        )
    ]


def _anomaly_detail(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "异常编号": row.get("异常编号"),
        "指标编码": row.get("指标编码"),
        "观测编号": row.get("观测编号"),
        "观测值": row.get("观测值"),
        "基线版本": row.get("基线版本"),
        "阈值版本": row.get("阈值版本"),
        "阈值": row.get("阈值"),
        "原始偏差": row.get("原始偏差"),
        "评估编号": row.get("评估编号"),
        "状态": row.get("status"),
        "确认时间": row.get("确认时间"),
    }


def _claimed_basis(review: dict[str, Any]) -> dict[str, Any] | None:
    history = review.get("依据历史") or []
    return history[-1] if history else None


def material_view(review: dict[str, Any]) -> dict[str, Any]:
    """组装评审材料：本次依据、当前依据、重新评估状态和异常明细分开显示。"""
    observation_code = str(review.get("观测编号", ""))
    claimed = _claimed_basis(review)
    latest = _latest_evaluation(observation_code) if observation_code else None
    latest_basis = _evaluation_basis(latest)
    anomaly_details = [
        _anomaly_detail(row) for row in _anomaly_rows(observation_code)
    ] if observation_code else []

    if not observation_code:
        basis_state = "无判定依据"
        next_step = "该评审记录不是指标异常来源，按原流程评审。"
    elif claimed is None and latest is None:
        basis_state = "待评估"
        next_step = "该观测尚无告警判定凭证，请先在检测入口提交评估。"
    elif review.get("材料状态") == "需重新领取":
        basis_state = "需重新领取"
        next_step = "材料依据已过期，请重新领取材料后再接受办结或要求重算。"
    elif claimed is None:
        basis_state = "未领取"
        next_step = "先领取评审材料，固化本次判定依据后再接受办结。"
    elif latest is not None and str(latest.get("评估编号")) != str(claimed.get("评估编号")):
        basis_state = "依据已变更"
        next_step = "同一窗口已经重新评估，请要求重算并重新领取材料，不要沿用旧依据办结。"
    elif latest is None:
        basis_state = "待评估"
        next_step = "本次依据引用的评估已不在库中，请按当前基线重新评估。"
    elif not latest.get("可交付"):
        basis_state = "依据不可交付"
        next_step = "当前评估不可交付（基线/样本问题），按材料里的下一步补录后重新提交评估。"
    else:
        basis_state = "一致"
        next_step = "依据一致，可按本次凭证接受办结或要求重算。"

    conflict = review.get("冲突提示")
    return {
        "记录编号": review.get("记录编号"),
        "实验编码": review.get("实验编码"),
        "评审结论": review.get("评审结论"),
        "评审角色": review.get("评审角色"),
        "记录状态": review.get("status"),
        "材料状态": review.get("材料状态", "未领取"),
        "材料版本": str(review.get("材料版本", "0")),
        "本次依据": claimed,
        "当前依据": latest_basis,
        "判定依据快照": review.get("判定依据快照"),
        "依据状态": basis_state,
        "重新评估状态": {
            "已重新评估": bool(
                latest and claimed and str(latest.get("评估编号")) != str(claimed.get("评估编号"))
            ),
            "评估编号": (latest or {}).get("评估编号"),
            "判定": (latest or {}).get("判定"),
            "阈值版本": (latest or {}).get("阈值版本"),
            "基线版本": (latest or {}).get("基线版本"),
            "判定时间": (latest or {}).get("判定时间"),
            "重算状态": review.get("重算状态"),
        },
        "异常明细": anomaly_details,
        "冲突提示": conflict,
        "下一步": next_step,
    }


def claim_material(code: str) -> dict[str, Any]:
    """领取评审材料：把当前可交付的评估固化成本次依据。"""
    review = _review_by_code(code)
    if review is None:
        raise ReviewConflict(f"评审记录 {code} 不存在", "确认记录编号后重试。")
    if review.get("status") != "待评审":
        raise ReviewConflict(
            f"记录 {code} 已{str(review.get('status', '')).replace('已', '')}，不能领取材料",
            "只能领取待评审记录的材料。",
        )
    observation_code = str(review.get("观测编号", ""))
    if not observation_code:
        raise ReviewConflict(
            "该评审记录不是指标异常来源，没有判定材料",
            "按原评审流程处理，不需要领取检测材料。",
        )
    latest = _latest_evaluation(observation_code)
    if latest is None:
        raise ReviewConflict(
            f"观测 {observation_code} 还没有可交付的评估凭证",
            "先在检测入口提交该窗口的评估，再领取评审材料。",
        )
    if not latest.get("可交付"):
        raise ReviewConflict(
            f"观测 {observation_code} 的当前评估不可交付：{latest.get('判定说明')}",
            str(latest.get("下一步") or "补齐基线后重新提交评估。"),
        )
    claimed = _claimed_basis(review)
    unchanged = (
        review.get("材料状态") == "已领取"
        and claimed is not None
        and str(claimed.get("评估编号")) == str(latest.get("评估编号"))
    )
    if unchanged:
        return material_view(review)

    basis = _evaluation_basis(latest)
    history = list(review.get("依据历史") or [])
    history.append(
        {
            **basis,
            "材料版本": str(int(str(review.get("材料版本", "0") or 0)) + 1),
            "领取时间": now_iso(),
        }
    )
    review["依据历史"] = history
    review["材料版本"] = history[-1]["材料版本"]
    review["材料状态"] = "已领取"
    review["判定依据快照"] = dict(basis)
    review["当前依据评估编号"] = latest.get("评估编号")
    review.pop("冲突提示", None)
    return material_view(review)


def mark_reviews_after_evaluation(evaluation: dict[str, Any]) -> None:
    """重新评估落库后，同步所有引用同一观测且仍在待评审的评审材料。"""
    observation_code = str(evaluation.get("观测编号", ""))
    if not observation_code:
        return
    for review in store.rows("conclusion_review"):
        if review.get("status") != "待评审":
            continue
        if str(review.get("观测编号", "")) != observation_code:
            continue
        claimed = _claimed_basis(review)
        if claimed is None:
            continue
        if str(claimed.get("评估编号")) == str(evaluation.get("评估编号")):
            continue
        if str(claimed.get("指标窗口", "")) != str(evaluation.get("指标窗口", "")):
            continue
        review["材料状态"] = "需重新领取"
        review["重算状态"] = "已重新评估"
        review["冲突提示"] = (
            f"材料领取与重新评估发生在同一指标窗口 {evaluation.get('指标窗口', '')}；"
            f"本次依据 {claimed.get('评估编号')}（阈值 {claimed.get('阈值版本')}）"
            f"已被 {evaluation.get('评估编号')}（阈值 {evaluation.get('阈值版本')}）取代，"
            "接受办结前必须重新领取材料。"
        )


def request_recalculation(code: str, client_request_id: str = "") -> dict[str, Any]:
    """按当前生效基线重算该评审关联的观测，并标记材料需重新领取。"""
    review = _review_by_code(code)
    if review is None:
        raise ReviewConflict(f"评审记录 {code} 不存在", "确认记录编号后重试。")
    if review.get("status") != "待评审":
        raise ReviewConflict(
            f"记录 {code} 已{str(review.get('status', '')).replace('已', '')}，不能要求重算",
            "只能对待评审记录要求重算。",
        )
    observation_code = str(review.get("观测编号", ""))
    observation = next(
        (row for row in store.rows("anomaly_observation") if row.get("观测编号") == observation_code),
        None,
    )
    if observation is None:
        raise ReviewConflict(
            f"没有找到观测 {observation_code}",
            "确认观测编号后重新提交评估。",
        )
    record = ds.evaluate_observation(observation, client_request_id=client_request_id)
    review["材料状态"] = "需重新领取"
    review["重算状态"] = "已重新评估"
    review["最近重算评估编号"] = record.get("评估编号")
    if not record.get("可交付"):
        review["冲突提示"] = (
            f"重算未产生可交付凭证：{record.get('判定')}（{record.get('处理状态')}）。"
            f"{record.get('下一步')}"
        )
    else:
        review["冲突提示"] = (
            f"已按当前生效基线 {record.get('基线版本')}、阈值版本 {record.get('阈值版本')} "
            f"重新评估得到 {record.get('评估编号')}（{record.get('判定')}）；"
            "请重新领取材料后再接受办结。"
        )
    return {"review": review, "evaluation": record}


def accept(
    code: str, *, basis_ref: str | int | None = None, comment: str = ""
) -> dict[str, Any]:
    """按带依据的异常结果接受办结；依据必须是最新且可交付的评估。"""
    review = _review_by_code(code)
    if review is None:
        raise ReviewConflict(f"评审记录 {code} 不存在", "确认记录编号后重试。")
    if review.get("status") != "待评审":
        raise ReviewConflict(
            f"记录 {code} 状态为 {review.get('status')}，不能重复办结",
            "只有待评审记录可以接受办结。",
        )
    observation_code = str(review.get("观测编号", ""))
    if not observation_code:
        review["status"] = "已通过"
        review["pending"] = False
        review["评审时间"] = now_iso()
        review["评审意见"] = comment or "同意采纳"
        return {"review": review, "evaluation": None}

    if review.get("材料状态") != "已领取":
        conflict = str(review.get("冲突提示") or "").strip()
        raise ReviewConflict(
            conflict
            or "评审材料当前未领取（或依据已过期需要重新领取），无法确认本次判定依据",
            "先按当前依据重新领取材料，再接受办结。",
        )
    claimed = _claimed_basis(review)
    if claimed is None:
        raise ReviewConflict(
            "尚未领取评审材料，无法确认本次判定依据",
            "先领取材料固化依据，再接受办结。",
        )
    latest = _latest_evaluation(observation_code)
    if latest is None:
        raise ReviewConflict(
            f"观测 {observation_code} 当前没有评估凭证",
            "先在检测入口提交评估。",
        )
    if not latest.get("可交付"):
        raise ReviewConflict(
            f"当前评估 {latest.get('评估编号')} 不可交付：{latest.get('判定说明')}",
            str(latest.get("下一步") or "补齐基线后重新提交评估。"),
        )
    if basis_ref not in (None, ""):
        chosen = _evaluation_by_ref(basis_ref)
        if chosen is None:
            raise ReviewConflict(
                f"找不到依据评估 {basis_ref}",
                "传入材料里的评估编号后重试。",
            )
        if str(chosen.get("评估编号")) != str(latest.get("评估编号")):
            raise ReviewConflict(
                f"依据 {chosen.get('评估编号')} 已被 {latest.get('评估编号')} 取代，不能据此办结",
                "按当前依据重新领取材料，或要求重算后再办结。",
            )
    elif str(claimed.get("评估编号")) != str(latest.get("评估编号")):
        raise ReviewConflict(
            f"本次依据 {claimed.get('评估编号')} 与当前依据 {latest.get('评估编号')} 不一致",
            "依据已变更：请要求重算并重新领取材料，或显式按当前依据办结。",
        )
    else:
        chosen = latest

    review["status"] = "已通过"
    review["pending"] = False
    review["评审时间"] = now_iso()
    review["评审意见"] = comment or f"按依据 {latest.get('评估编号')} 办结"
    review["材料状态"] = "已办结"
    review["办结依据评估编号"] = latest.get("评估编号")
    review["办结依据凭证"] = latest.get("凭证编号")
    review["办结时判定"] = latest.get("判定")
    review["办结说明"] = (
        f"依据 {latest.get('评估编号')}（凭证 {latest.get('凭证编号')}，"
        f"基线 {latest.get('基线版本')}，阈值 {latest.get('阈值版本')}）"
        f"判定 {latest.get('判定')}，异常按当前基线结论办结。"
    )
    archive_rows = store.rows("exp_archive")
    archive_rows.append({
        "id": next_id(archive_rows),
        "实验编码": review.get("实验编码", ""),
        "结束时间": now_iso(),
        "结论摘要": f"评审通过：{review.get('评审结论', '')}（依据 {latest.get('评估编号')}）",
        "归档位置": f"review/{review.get('记录编号', '')}",
        "保留等级": "标准",
        "status": "待归档",
        "pending": True,
        "abnormal": False,
        "评估编号": latest.get("评估编号"),
        "凭证编号": latest.get("凭证编号"),
    })
    # 已确认异常记录补上办结依据，原始阈值版本与原始偏差保持不动。
    for anomaly in store.rows("anomaly_metric"):
        if str(anomaly.get("观测编号", "")) == observation_code:
            anomaly["办结依据评估编号"] = latest.get("评估编号")
            anomaly["办结判定"] = latest.get("判定")
    return {"review": review, "evaluation": latest}


def reject(code: str, reason: str, *, basis_ref: str | int | None = None) -> dict[str, Any]:
    review = _review_by_code(code)
    if review is None:
        raise ReviewConflict(f"评审记录 {code} 不存在", "确认记录编号后重试。")
    if review.get("status") != "待评审":
        raise ReviewConflict(
            f"记录 {code} 状态为 {review.get('status')}，不能驳回",
            "只有待评审记录可以驳回。",
        )
    if not reason.strip():
        raise ReviewConflict("驳回必须填写原因", "补充驳回原因后重试。")
    chosen = _evaluation_by_ref(basis_ref) if basis_ref not in (None, "") else _claimed_basis(review)
    review["status"] = "已驳回"
    review["pending"] = False
    review["abnormal"] = True
    review["驳回原因"] = reason
    review["材料状态"] = "已办结"
    if chosen:
        review["驳回依据评估编号"] = chosen.get("评估编号")
        review["驳回依据凭证"] = chosen.get("凭证编号")
    exp_code = str(review.get("实验编码", ""))
    stalled = [
        row for row in store.rows("report_dist")
        if exp_code and exp_code in str(row.get("报告编码", "")) and row.get("status") == "排队中"
    ]
    for row in stalled:
        row["status"] = "送达失败"
        row["abnormal"] = True
        row["失败原因"] = "结论被驳回，停止分发"
    return {"review": review, "evaluation": chosen, "stalled": len(stalled)}


def review_material(code: str) -> dict[str, Any]:
    review = _review_by_code(code)
    if review is None:
        raise ReviewConflict(f"评审记录 {code} 不存在", "确认记录编号后重试。")
    return material_view(review)
