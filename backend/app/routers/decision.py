"""告警判定与评审材料接口：给页面提供可核对的基线、凭证与冲突处理入口。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app import decision_service as ds
from app import review_workflow as rw
from app.store import store

router = APIRouter(prefix="/api/decision", tags=["告警判定"])


class BaselinePayload(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class ThresholdPayload(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class EvaluatePayload(BaseModel):
    observation_id: int | None = None
    baseline_id: int | None = None
    client_request_id: str = ""


class ClaimPayload(BaseModel):
    client_request_id: str = ""


class RecalculatePayload(BaseModel):
    client_request_id: str = ""


class AcceptPayload(BaseModel):
    basis: str | None = None
    comment: str | None = None


class RejectPayload(BaseModel):
    reason: str
    basis: str | None = None


def _observation(observation_id: int) -> dict[str, Any]:
    row = store.find("anomaly_observation", observation_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"观测 {observation_id} 不存在")
    return row


def _review(code: str) -> dict[str, Any]:
    row = next(
        (r for r in store.rows("conclusion_review") if str(r.get("记录编号", "")) == code),
        None,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"评审记录 {code} 不存在")
    return row


@router.get("/baselines")
def baselines(
    metric_code: str = Query(default=""), experiment_code: str = Query(default="")
) -> dict[str, Any]:
    return {
        "items": ds.list_baselines(metric_code, experiment_code),
        "thresholds": ds.list_thresholds(metric_code),
        "min_observations": ds.min_observations(),
    }


@router.post("/baselines")
def create_baseline(payload: BaselinePayload) -> dict[str, Any]:
    entry, message = ds.register_baseline(payload.values)
    if entry is None:
        return {"ok": False, "message": message}
    return {"ok": True, "message": message, "entry": entry}


@router.post("/baselines/{entry_id}/activate")
def activate_baseline(entry_id: int) -> dict[str, Any]:
    entry, message = ds.activate_baseline(entry_id)
    return {"ok": entry is not None, "message": message, "entry": entry}


@router.post("/thresholds")
def create_threshold(payload: ThresholdPayload) -> dict[str, Any]:
    entry, message = ds.register_threshold(payload.values)
    if entry is None:
        return {"ok": False, "message": message}
    return {"ok": True, "message": message, "entry": entry}


@router.get("/history")
def history(
    metric_code: str, experiment_code: str, window: str
) -> dict[str, Any]:
    return {"items": ds.baseline_history(metric_code, experiment_code, window)}


@router.get("/observations")
def observations() -> dict[str, Any]:
    return {"items": store.rows("anomaly_observation")}


@router.get("/observations/{observation_id}/preview")
def preview(observation_id: int) -> dict[str, Any]:
    observation = _observation(observation_id)
    return {
        "observation": observation,
        "baseline": ds.resolve_baseline_for(observation),
        "preview": ds.preview_observation(observation),
        "versions": ds.baseline_history(
            str(observation.get("指标编码", "")),
            str(observation.get("实验编码", "")),
            str(observation.get("指标窗口", "")),
        ),
    }


@router.get("/observations/{observation_id}/evaluations")
def observation_evaluations(observation_id: int) -> dict[str, Any]:
    """列出该观测的全部评估记录，旧凭证与重新评估各自独立可查。"""
    observation = _observation(observation_id)
    code = str(observation.get("观测编号", ""))
    items = [
        row for row in store.rows("anomaly_evaluation")
        if str(row.get("观测编号", "")) == code
    ]
    items.sort(key=lambda row: (str(row.get("判定时间") or ""), int(row.get("id", 0))), reverse=True)
    return {"items": items}


@router.post("/evaluate")
def evaluate(payload: EvaluatePayload) -> dict[str, Any]:
    """检测入口：对一条观测按当前生效基线重新评估并返回告警判定凭证。"""
    if payload.observation_id is None:
        return {"ok": False, "message": "必须指定观测"}
    observation = _observation(payload.observation_id)
    record = ds.evaluate_observation(
        observation,
        baseline_id=payload.baseline_id,
        client_request_id=payload.client_request_id,
    )
    return {
        "ok": record.get("可交付", False),
        "message": record.get("判定说明"),
        "evaluation": record,
        "observation": observation,
    }


@router.post("/evaluations/{ref}/recalculate")
def recalculate(ref: str) -> dict[str, Any]:
    rows = store.rows("anomaly_evaluation")
    record = next(
        (r for r in rows if str(r.get("评估编号")) == ref or str(r.get("id")) == ref),
        None,
    )
    if record is None:
        raise HTTPException(status_code=404, detail=f"评估 {ref} 不存在")
    recomputed = ds.recalculate(record)
    return {"ok": True, "message": "旧结果已按原依据复算", "evaluation": recomputed}


@router.get("/reviews/{code}/material")
def material(code: str) -> dict[str, Any]:
    return rw.material_view(_review(code))


@router.post("/reviews/{code}/claim")
def claim(code: str, payload: ClaimPayload) -> dict[str, Any]:
    """领取评审材料；与重新评估冲突时说明当前依据与下一步。"""
    try:
        view = rw.claim_material(code)
    except rw.ReviewConflict as conflict:
        raise HTTPException(
            status_code=409,
            detail={"message": conflict.message, "next_step": conflict.next_step},
        ) from conflict
    return {"ok": True, "message": "评审材料已领取", "material": view}


@router.post("/reviews/{code}/recalculate")
def recalculate_review(code: str, payload: RecalculatePayload) -> dict[str, Any]:
    try:
        result = rw.request_recalculation(code, payload.client_request_id)
    except rw.ReviewConflict as conflict:
        raise HTTPException(
            status_code=409,
            detail={"message": conflict.message, "next_step": conflict.next_step},
        ) from conflict
    return {
        "ok": bool(result["evaluation"].get("可交付")),
        "message": result["review"].get("冲突提示"),
        "evaluation": result["evaluation"],
        "material": rw.material_view(result["review"]),
    }


@router.post("/reviews/{code}/accept")
def accept(code: str, payload: AcceptPayload) -> dict[str, Any]:
    try:
        result = rw.accept(code, basis_ref=payload.basis, comment=payload.comment or "")
    except rw.ReviewConflict as conflict:
        raise HTTPException(
            status_code=409,
            detail={"message": conflict.message, "next_step": conflict.next_step},
        ) from conflict
    return {
        "ok": True,
        "message": result["review"].get("办结说明"),
        "review": result["review"],
        "evaluation": result["evaluation"],
    }


@router.post("/reviews/{code}/reject")
def reject(code: str, payload: RejectPayload) -> dict[str, Any]:
    try:
        result = rw.reject(code, payload.reason, basis_ref=payload.basis)
    except rw.ReviewConflict as conflict:
        raise HTTPException(
            status_code=409,
            detail={"message": conflict.message, "next_step": conflict.next_step},
        ) from conflict
    return {
        "ok": True,
        "message": f"记录已驳回，联动停止 {result['stalled']} 条分发",
        "review": result["review"],
        "evaluation": result["evaluation"],
    }
