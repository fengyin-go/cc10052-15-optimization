"""告警判定工作区服务：基线登记与观测评估的编排。

判定规则放在 `app.decision`，这里只负责读写仓库、维护修订号并生成评估凭证。
所有判定都以“指标 + 实验 + 指标窗口”为单位，基线变化只追加版本，不改历史凭证。
"""
from __future__ import annotations

from typing import Any

from app.decision import (
    MIN_OBSERVATIONS,
    as_float,
    evaluate,
    normalize_scope,
    snapshot_from_evaluation,
    version_number,
)
from app.store import now_iso, next_id, store


def list_baselines(metric_code: str = "", experiment_code: str = "") -> list[dict[str, Any]]:
    rows = store.rows("anomaly_baseline")
    return [
        row for row in rows
        if (not metric_code or row.get("指标编码") == metric_code)
        and (not experiment_code or row.get("实验编码") == experiment_code)
    ]


def list_active_baselines(metric_code: str = "", experiment_code: str = "") -> list[dict[str, Any]]:
    return [
        row for row in list_baselines(metric_code, experiment_code)
        if row.get("status") == "已生效"
    ]


def effective_baseline(
    metric_code: str, experiment_code: str, window: str
) -> dict[str, Any] | None:
    """取同一指标窗口下版本最高、且仍然生效的基线。"""
    candidates = [
        row for row in list_active_baselines(metric_code, experiment_code)
        if str(row.get("指标窗口", "")) == window
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda row: (version_number(row.get("基线版本")), str(row.get("生效时间") or "")),
    )


def resolve_baseline_for(observation: dict[str, Any]) -> dict[str, Any] | None:
    """为一条观测挑当前适用基线，并把当前阈值版本一并锁定。

    基线只有在自己绑定的阈值版本仍是当前发布版本时才适用；阈值版本一变，
    旧基线就不再被新评估借用，新基线必须重新生效并绑定新阈值。
    """
    metric_code = str(observation.get("指标编码", ""))
    experiment_code = str(observation.get("实验编码", ""))
    window = str(observation.get("指标窗口", ""))
    baseline = effective_baseline(metric_code, experiment_code, window)
    if baseline is None:
        return None
    current = effective_threshold(metric_code, window, baseline.get("适用范围"))
    bound = str(baseline.get("阈值版本") or "")
    current_version = str((current or {}).get("阈值版本") or "")
    if current is not None:
        if bound and current_version and bound != current_version:
            # 基线绑定的阈值版本已经停用：这条基线不适用于新评估。
            return None
        baseline = {
            **baseline,
            "阈值": current.get("阈值"),
            "阈值版本": current_version,
            "适用范围": current.get("适用范围") or baseline.get("适用范围"),
            "当前阈值版本": current_version,
        }
    return baseline


def list_thresholds(metric_code: str = "", window: str = "") -> list[dict[str, Any]]:
    return [
        row for row in store.rows("anomaly_threshold")
        if (not metric_code or row.get("指标编码") == metric_code)
        and (not window or str(row.get("指标窗口", "")) == window)
    ]


def effective_threshold(
    metric_code: str, window: str, scope: str | None = None
) -> dict[str, Any] | None:
    """按版本号取当前发布中的阈值，阈值版本变化后再评估就会落到新版本。

    传入 scope 时优先选适用范围覆盖该范围的版本。
    """
    candidates = [
        row for row in list_thresholds(metric_code, window)
        if row.get("status") == "已发布" and not row.get("停用时间")
    ]
    if scope:
        covered = [
            row for row in candidates
            if normalize_scope(row.get("适用范围")) in ("全部分组", normalize_scope(scope))
        ]
        candidates = covered or candidates
    if not candidates:
        return None
    return max(candidates, key=lambda row: version_number(row.get("阈值版本")))


def baseline_snapshot(baseline: dict[str, Any]) -> dict[str, Any]:
    snapshot = {
        field: baseline.get(field)
        for field in (
            "基线版本", "指标编码", "实验编码", "指标窗口", "基线值", "观测数",
            "阈值", "阈值版本", "适用范围", "生效时间", "停用时间", "发布人",
            "备注", "修订号",
        )
    }
    snapshot["状态"] = baseline.get("状态") or baseline.get("status")
    return snapshot


def _store_evaluation(
    observation: dict[str, Any],
    baseline: dict[str, Any] | None,
    evaluation: dict[str, Any],
    client_request_id: str,
    *,
    threshold_version: str | None = None,
) -> dict[str, Any]:
    rows = store.rows("anomaly_evaluation")
    revision = store.revision_for("anomaly_baseline")
    record = {
        "id": next_id(rows),
        "评估编号": f"EV-{next_id(rows):04d}",
        "观测编号": observation.get("观测编号", ""),
        "指标编码": observation.get("指标编码", ""),
        "实验编码": observation.get("实验编码", ""),
        "指标窗口": observation.get("指标窗口", ""),
        "观测值": observation.get("观测值"),
        "观测数": observation.get("观测数"),
        "适用范围": evaluation.get("适用范围") or normalize_scope(observation.get("适用范围")),
        "基线快照": baseline_snapshot(baseline) if baseline else None,
        "基线版本": evaluation.get("基线版本"),
        "基线值": evaluation.get("基线值"),
        "阈值": evaluation.get("阈值"),
        "阈值版本": threshold_version or evaluation.get("阈值版本") or (baseline or {}).get("阈值版本"),
        "原始偏差": evaluation.get("原始偏差"),
        "偏差率": evaluation.get("偏差率"),
        "偏差率文本": evaluation.get("偏差率文本"),
        "偏差类型": evaluation.get("偏差类型"),
        "判定": evaluation.get("判定"),
        "结论": evaluation.get("结论"),
        "是否超阈值": evaluation.get("是否超阈值"),
        "可交付": evaluation.get("可交付", False),
        "处理状态": evaluation.get("处理状态", "待处理"),
        "判定说明": evaluation.get("判定说明"),
        "比较依据": evaluation.get("比较依据"),
        "下一步": evaluation.get("下一步"),
        "凭证编号": evaluation.get("凭证编号"),
        "凭证摘要": evaluation.get("凭证摘要"),
        "判定时间": now_iso(),
        "判定依据修订": revision,
        "客户端请求号": client_request_id,
        "异常事件编号": None,
        "评审记录编号": None,
        "重算状态": "未重算",
        "来源评估编号": None,
        "超阈值但已被新基线覆盖": False,
        "废弃原因": None,
        "status": "已判定" if evaluation.get("可交付") else "待处理",
        "pending": not evaluation.get("可交付"),
        "abnormal": evaluation.get("判定") == "超阈值",
    }
    rows.append(record)
    return record


def _touch_observation(observation: dict[str, Any], record: dict[str, Any]) -> None:
    observation["当前评估编号"] = record["评估编号"]
    observation["当前判定"] = record["判定"]
    observation["评估状态"] = record["status"]
    if record.get("可交付"):
        observation["status"] = "已评估"
        observation["pending"] = False
        observation["abnormal"] = record.get("判定") == "超阈值"
    elif record.get("处理状态") == "已挂起":
        observation["status"] = "已挂起"
        observation["pending"] = True
        observation["abnormal"] = False
    else:
        observation["status"] = "待评估"
        observation["pending"] = True
        observation["abnormal"] = False


def evaluate_observation(
    observation: dict[str, Any],
    *,
    baseline_id: int | None = None,
    client_request_id: str = "",
) -> dict[str, Any]:
    """按同一指标窗口重新评估一条观测，返回本次评估凭证。

    新评估只认当前生效基线与阈值版本，不会复用已经不适用的旧阈值；
    旧评估记录保持不变，可各自复算。
    """
    metric_code = str(observation.get("指标编码", ""))
    experiment_code = str(observation.get("实验编码", ""))
    window = str(observation.get("指标窗口", ""))
    scope = normalize_scope(observation.get("适用范围"))
    observed = as_float(observation.get("观测值"))
    sample_size = observation.get("观测数")
    try:
        sample_int: int | None = int(float(str(sample_size)))
    except (TypeError, ValueError):
        sample_int = 0 if sample_size in (None, "") else None

    baseline = None
    if baseline_id is not None:
        candidate = store.find("anomaly_baseline", baseline_id)
        if candidate is not None:
            baseline = candidate
    else:
        baseline = resolve_baseline_for(observation)

    current_threshold = effective_threshold(
        metric_code, window, (baseline or {}).get("适用范围")
    )
    other_windows = sorted({
        str(row.get("指标窗口", ""))
        for row in list_baselines(metric_code, experiment_code)
    })
    snapshot = baseline_snapshot(baseline) if baseline else None
    evaluation = evaluate(
        {
            "指标编码": metric_code,
            "实验编码": experiment_code,
            "指标窗口": window,
            "观测值": observed,
            "观测数": sample_int,
            "适用范围": scope,
        },
        baseline,
        threshold=current_threshold,
        other_windows=other_windows,
    )

    record = _store_evaluation(
        observation, baseline, evaluation, client_request_id,
        threshold_version=str(
            evaluation.get("阈值版本") or (current_threshold or {}).get("阈值版本") or ""
        ),
    )
    record["基线快照"] = snapshot
    _sync_observation_baseline(observation, baseline)
    _touch_observation(observation, record)
    # 迟到的导入：评审工作流依赖本服务，这里只在写库后同步材料状态。
    from app.review_workflow import mark_reviews_after_evaluation

    mark_reviews_after_evaluation(record)
    return record


def _sync_observation_baseline(
    observation: dict[str, Any], baseline: dict[str, Any] | None
) -> None:
    """把本次实际比较的基线版本写回观测，便于页面核对适用基线与版本。"""
    if baseline is None:
        observation["对比基线版本"] = None
        return
    observation["对比基线版本"] = baseline.get("基线版本")
    observation["对比阈值版本"] = baseline.get("阈值版本")
    observation["对比基线值"] = baseline.get("基线值")
    observation["对比阈值"] = baseline.get("阈值")


def recalculate(record: dict[str, Any], *, client_request_id: str = "") -> dict[str, Any]:
    """重算一条旧评估：按它当时的窗口、观测和基线版本重新比较，不换用新版本。"""
    baseline_snapshot = record.get("基线快照") or {}
    baseline = None
    version = baseline_snapshot.get("基线版本")
    if version:
        baseline = next(
            (
                row for row in list_baselines()
                if row.get("基线版本") == version
                and row.get("指标窗口") == baseline_snapshot.get("指标窗口")
                and row.get("指标编码") == baseline_snapshot.get("指标编码")
            ),
            None,
        )
    if baseline is None and version:
        # 旧版本被清理时用凭证里的快照复算，保证旧结果仍然可追溯。
        baseline = {
            **baseline_snapshot,
            "基线值": baseline_snapshot.get("基线值"),
            "阈值": baseline_snapshot.get("阈值"),
        }
    observation = {
        "观测编号": record.get("观测编号", ""),
        "指标编码": record.get("指标编码", ""),
        "实验编码": record.get("实验编码", ""),
        "指标窗口": record.get("指标窗口", ""),
        "观测值": record.get("观测值"),
        "观测数": record.get("观测数"),
        "适用范围": record.get("适用范围"),
    }
    historical_threshold = {
        "阈值": baseline_snapshot.get("阈值"),
        "阈值版本": baseline_snapshot.get("阈值版本"),
    }
    evaluation = evaluate(observation, baseline or None, threshold=historical_threshold)
    recomputed = _store_evaluation(
        observation, baseline or None, evaluation, client_request_id,
        threshold_version=baseline_snapshot.get("阈值版本"),
    )
    recomputed["来源评估编号"] = record.get("评估编号")
    recomputed["重算状态"] = "已重算"
    recomputed["基线快照"] = baseline_snapshot or recomputed.get("基线快照")
    # 重算结果与旧凭证的差异单独说明，旧记录本体不动。
    record["重算状态"] = "已复算"
    record["最近复算编号"] = recomputed["评估编号"]
    record["复算差异"] = _diff_text(record, recomputed)
    return recomputed


def _diff_text(old: dict[str, Any], new: dict[str, Any]) -> str:
    old_verdict = str(old.get("判定") or "无法判定")
    new_verdict = str(new.get("判定") or "无法判定")
    if old_verdict == new_verdict:
        return f"复算与凭证一致（判定 {old_verdict}），凭证仍可复核"
    return (
        f"复算判定 {new_verdict} 与凭证判定 {old_verdict} 不同，"
        "说明该凭证的判定依据已经发生变化，需要重新评估而不是沿用"
    )


def preview_observation(observation: dict[str, Any]) -> dict[str, Any]:
    """只读预览：用当前生效基线算一遍，不落库。"""
    metric_code = str(observation.get("指标编码", ""))
    experiment_code = str(observation.get("实验编码", ""))
    window = str(observation.get("指标窗口", ""))
    baseline = resolve_baseline_for(observation)
    other_windows = sorted({
        str(row.get("指标窗口", ""))
        for row in list_baselines(metric_code, experiment_code)
    })
    sample = as_float(observation.get("观测数"))
    return evaluate(
        {
            "指标编码": metric_code,
            "实验编码": experiment_code,
            "指标窗口": window,
            "观测值": as_float(observation.get("观测值")),
            "观测数": None if sample is None else int(sample),
            "适用范围": observation.get("适用范围"),
        },
        baseline,
        threshold=effective_threshold(metric_code, window),
        other_windows=other_windows,
    )


def baseline_history(metric_code: str, experiment_code: str, window: str) -> list[dict[str, Any]]:
    rows = [
        row for row in list_baselines(metric_code, experiment_code)
        if str(row.get("指标窗口", "")) == window
    ]
    rows.sort(key=lambda row: (str(row.get("生效时间") or ""), version_number(row.get("基线版本"))))
    return [baseline_snapshot(row) for row in rows]


def register_baseline(values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """登记一条新基线版本；同窗口旧版本自动失效但保留历史。"""
    metric_code = str(values.get("指标编码") or "").strip()
    experiment_code = str(values.get("实验编码") or "").strip()
    window = str(values.get("指标窗口") or "").strip()
    if not metric_code or not experiment_code or not window:
        return None, "指标编码、实验编码、指标窗口均为必填"
    base_value = as_float(values.get("基线值"))
    threshold = as_float(values.get("阈值"))
    if base_value is None or threshold is None:
        return None, "基线值与阈值必须是数值"
    if threshold < 0:
        return None, "阈值不能为负"
    rows = store.rows("anomaly_baseline")
    same_metric = [
        row for row in rows
        if row.get("指标编码") == metric_code and row.get("实验编码") == experiment_code
    ]
    latest = max((version_number(row.get("基线版本")) for row in same_metric), default=0)
    revision = store.bump_revision("anomaly_baseline")
    version = str(values.get("基线版本") or "").strip() or (
        f"BL-{metric_code}-{latest + 1}"
    )
    if any(row.get("基线版本") == version for row in rows):
        return None, f"基线版本 {version} 已存在"
    scope = normalize_scope(values.get("适用范围"))
    threshold_row = effective_threshold(metric_code, window)
    entry = {
        "id": next_id(rows),
        "status": "已生效",
        "pending": False,
        "abnormal": False,
        "基线版本": version,
        "指标编码": metric_code,
        "实验编码": experiment_code,
        "指标窗口": window,
        "基线值": str(base_value),
        "观测数": str(values.get("观测数") or "0"),
        "阈值": str(threshold),
        "阈值版本": str(values.get("阈值版本") or (threshold_row or {}).get("阈值版本") or "TH-自定义"),
        "适用范围": scope,
        "生效时间": now_iso(),
        "停用时间": None,
        "发布人": str(values.get("发布人") or "口径负责人"),
        "备注": str(values.get("备注") or "新登记基线"),
        "修订号": revision,
    }
    # 同窗口旧版本逐条失效，并记录被哪一版替换。
    for row in same_metric:
        if (
            str(row.get("指标窗口", "")) == window
            and row.get("status") == "已生效"
        ):
            row["status"] = "已失效"
            row["停用时间"] = now_iso()
            row["被替换为"] = version
    rows.append(entry)
    _mark_superseded(entry)
    return entry, f"基线 {version} 已生效，修订号 {revision}"


def _mark_superseded(new_baseline: dict[str, Any]) -> None:
    """新基线生效后，标记那些“按旧阈值超阈值、按新基线不超”的评估。"""
    metric_code = new_baseline.get("指标编码")
    experiment_code = new_baseline.get("实验编码")
    window = new_baseline.get("指标窗口")
    for observation in store.rows("anomaly_observation"):
        if not (
            observation.get("指标编码") == metric_code
            and observation.get("实验编码") == experiment_code
            and str(observation.get("指标窗口", "")) == window
        ):
            continue
        preview = evaluate(
            {
                "指标编码": metric_code,
                "实验编码": experiment_code,
                "指标窗口": window,
                "观测值": as_float(observation.get("观测值")),
                "观测数": observation.get("观测数"),
                "适用范围": observation.get("适用范围"),
            },
            new_baseline,
            threshold={
                "阈值": new_baseline.get("阈值"),
                "阈值版本": new_baseline.get("阈值版本"),
            },
        )
        observation["新基线判定预览"] = preview.get("判定") or preview.get("处理状态")
        for item in store.rows("anomaly_evaluation"):
            if item.get("观测编号") != observation.get("观测编号"):
                continue
            if item.get("判定") == "超阈值" and preview.get("判定") != "超阈值":
                item["超阈值但已被新基线覆盖"] = True
                item["废弃原因"] = (
                    f"新基线 {new_baseline.get('基线版本')} 生效后，同一观测的偏差不再超过阈值；"
                    "该凭证只代表旧阈值下的判定，需重新评估或按要求重算"
                )


def register_threshold(values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    metric_code = str(values.get("指标编码") or "").strip()
    window = str(values.get("指标窗口") or "").strip()
    threshold = as_float(values.get("阈值"))
    if not metric_code or not window:
        return None, "指标编码与指标窗口均为必填"
    if threshold is None or threshold < 0:
        return None, "阈值必须是非负数值"
    version = str(values.get("阈值版本") or "").strip()
    if not version:
        latest = max(
            (version_number(row.get("阈值版本")) for row in list_thresholds(metric_code, window)),
            default=0,
        )
        version = f"TH-v{latest + 1}"
    if any(
        row.get("阈值版本") == version
        for row in list_thresholds(metric_code, window)
    ):
        return None, f"阈值版本 {version} 已存在"
    bumped = store.bump_revision("anomaly_baseline")
    rows = store.rows("anomaly_threshold")
    for row in list_thresholds(metric_code, window):
        if row.get("status") == "已发布" and not row.get("停用时间"):
            row["status"] = "已停用"
            row["停用时间"] = now_iso()
            row["被替换为"] = version
    entry = {
        "id": next_id(rows),
        "status": "已发布",
        "pending": False,
        "abnormal": False,
        "阈值版本": version,
        "指标编码": metric_code,
        "指标窗口": window,
        "阈值": str(threshold),
        "偏差类型": str(values.get("偏差类型") or "相对偏差"),
        "比较方式": str(values.get("比较方式") or "严格大于"),
        "适用范围": normalize_scope(values.get("适用范围")),
        "生效时间": now_iso(),
        "停用时间": None,
        "发布人": str(values.get("发布人") or "口径负责人"),
        "备注": str(values.get("备注") or "新发布阈值"),
        "修订号": bumped,
    }
    rows.append(entry)
    return entry, f"阈值 {version} 已发布，修订号 {bumped}"


def activate_baseline(entry_id: int) -> tuple[dict[str, Any] | None, str]:
    """让一条待生效基线正式生效，并让同窗口旧版本退出适用。"""
    entry = store.find("anomaly_baseline", entry_id)
    if entry is None:
        return None, f"基线 {entry_id} 不存在"
    if entry.get("status") == "已生效":
        return entry, "基线已经生效，无需重复生效"
    if entry.get("status") != "待生效":
        return None, f"基线状态为 {entry.get('status')}，不能生效"
    revision = store.bump_revision("anomaly_baseline")
    for row in list_active_baselines(
        str(entry.get("指标编码", "")), str(entry.get("实验编码", ""))
    ):
        if str(row.get("指标窗口", "")) == str(entry.get("指标窗口", "")):
            row["status"] = "已失效"
            row["停用时间"] = now_iso()
            row["被替换为"] = entry.get("基线版本")
    entry["status"] = "已生效"
    entry["生效时间"] = now_iso()
    entry["停用时间"] = None
    entry["修订号"] = revision
    if not entry.get("阈值版本"):
        current = effective_threshold(
            str(entry.get("指标编码", "")), str(entry.get("指标窗口", ""))
        )
        if current:
            entry["阈值版本"] = current.get("阈值版本")
            entry["阈值"] = current.get("阈值")
    _mark_superseded(entry)
    return entry, f"基线 {entry.get('基线版本')} 已生效，修订号 {revision}"


def snapshot_material(record: dict[str, Any]) -> dict[str, Any]:
    """把评估记录整理成评审材料里的“判定依据”片段。"""
    return snapshot_from_evaluation(record)


def min_observations() -> int:
    return MIN_OBSERVATIONS
