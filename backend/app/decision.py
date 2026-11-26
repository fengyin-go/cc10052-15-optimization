"""告警判定规则：把观测、基线与阈值收敛成可复核的判定结论与判定凭证。

本模块保持纯函数，不依赖内存仓库，示例数据与服务层共用同一套规则：
- 基线、观测值和阈值必须落在同一个指标窗口；
- 零基线不做除法，只比较绝对偏差；
- 观测不足的窗口单独挂起，绝不返回“已达标”；
- 每次可交付的判定都生成稳定的凭证编号，便于评审追溯当时所用的阈值版本。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

MIN_OBSERVATIONS = 30
ALL_SCOPE_ALIASES = ("", "全部分组", "全部", "ALL", "all")


def as_float(value: Any) -> float | None:
    """把仓库里可能存成字符串的数值安全转成 float。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def as_int(value: Any) -> int | None:
    number = as_float(value)
    return None if number is None else int(number)


def normalize_scope(scope: Any) -> str:
    return str(scope or "").strip() or "全部分组"


def scope_covers(baseline_scope: Any, observation_scope: Any) -> bool:
    """基线的适用范围覆盖观测范围时才算适用。"""
    base = normalize_scope(baseline_scope)
    target = normalize_scope(observation_scope)
    if base in ALL_SCOPE_ALIASES:
        return True
    return base == target


def version_number(version: Any) -> int:
    """从版本名里取最后一段数字，兼容 v3、TH-v3、BL-12-20261125 三种写法。"""
    text = str(version or "").strip()
    digits = ""
    for char in reversed(text):
        if char.isdigit():
            digits = char + digits
        elif digits:
            break
    return int(digits) if digits else 0


def percent_text(value: float | None) -> str:
    if value is None:
        return "不适用（零基线不做除法）"
    return f"{value:.2%}"


def _empty_decision(
    *, status: str, verdict: str, next_step: str, reason: str, deliverable: bool = False
) -> dict[str, Any]:
    return {
        "判定": verdict,
        "结论": "无法判定",
        "是否超阈值": None,
        "可交付": deliverable,
        "处理状态": status,
        "判定说明": reason,
        "下一步": next_step,
        "凭证编号": None,
        "凭证摘要": None,
    }


def evaluate(
    observation: dict[str, Any],
    baseline: dict[str, Any] | None,
    *,
    threshold: dict[str, Any] | None = None,
    other_windows: list[str] | None = None,
) -> dict[str, Any]:
    """按同一指标窗口比较观测与基线，返回结论、原始偏差和判定凭证。

    `observation` 至少包含：指标编码、实验编码、指标窗口、观测值、观测数、适用范围。
    `baseline` 为当前生效基线；为空表示找不到有效基线。
    `threshold` 为当前发布的阈值版本；缺省时退回基线登记时携带的阈值。
    """
    metric_code = str(observation.get("指标编码", ""))
    experiment_code = str(observation.get("实验编码", ""))
    window = str(observation.get("指标窗口", ""))
    observation_scope = normalize_scope(observation.get("适用范围"))
    observed = as_float(observation.get("观测值"))
    sample_size = as_int(observation.get("观测数"))

    if baseline is None:
        windows = [item for item in (other_windows or []) if item and item != window]
        if windows:
            distinct = "、".join(sorted(set(windows)))
            return _empty_decision(
                status="待处理",
                verdict="窗口不一致",
                reason=(
                    f"观测窗口 {window} 与现有基线窗口 {distinct} 不一致；"
                    "基线、观测值和阈值必须属于同一指标窗口，不能跨窗口比较。"
                ),
                next_step=(
                    f"为窗口 {window} 补录生效基线后重新提交评估；"
                    "或改用上述基线窗口的观测重新提交。"
                ),
            )
        return _empty_decision(
            status="待补录基线",
            verdict="无法匹配有效基线",
            reason=f"指标 {metric_code} 在实验 {experiment_code} 的窗口 {window} 没有生效基线。",
            next_step=(
                "先在基线管理中为该指标窗口补录或发布生效基线，再从检测入口重新提交评估；"
                "在此之前不会给出告警判定凭证。"
            ),
        )

    current_threshold = threshold or {
        "阈值": baseline.get("阈值"),
        "阈值版本": baseline.get("阈值版本"),
    }
    baseline_scope = normalize_scope(baseline.get("适用范围"))
    threshold_scope = normalize_scope(current_threshold.get("适用范围"))
    if threshold_scope not in ("全部分组", baseline_scope):
        return _empty_decision(
            status="待补录基线",
            verdict="无法匹配有效基线",
            reason=(
                f"阈值版本 {current_threshold.get('阈值版本', '')} 的适用范围是 "
                f"{threshold_scope}，不适用于基线范围 {baseline_scope}。"
            ),
            next_step=f"发布适用于「{baseline_scope}」的阈值版本后重新提交评估。",
        )

    baseline_window = str(baseline.get("指标窗口", ""))
    if baseline_window != window:
        return _empty_decision(
            status="待处理",
            verdict="窗口不一致",
            reason=(
                f"观测窗口 {window} 与基线 {baseline.get('基线版本', '')} 的窗口 "
                f"{baseline_window} 不一致；基线、观测值和阈值必须属于同一指标窗口。"
            ),
            next_step=(
                f"使用窗口 {baseline_window} 的观测重新提交，或为窗口 {window} 补录基线。"
            ),
        )

    if not scope_covers(baseline.get("适用范围"), observation_scope):
        return _empty_decision(
            status="待补录基线",
            verdict="无法匹配有效基线",
            reason=(
                f"基线 {baseline.get('基线版本', '')} 的适用范围是 "
                f"{normalize_scope(baseline.get('适用范围'))}，不覆盖观测范围 {observation_scope}。"
            ),
            next_step=(
                f"发布适用范围包含「{observation_scope}」的生效基线后重新提交评估。"
            ),
        )

    if sample_size is None:
        return _empty_decision(
            status="已挂起",
            verdict="数据不足",
            reason="观测数缺失，无法确认该窗口是否有足够样本。",
            next_step="补齐该窗口的观测数；无数据不能按已达标交付给消费者。",
        )
    if sample_size < MIN_OBSERVATIONS:
        return _empty_decision(
            status="已挂起",
            verdict="数据不足",
            reason=(
                f"窗口 {window} 仅有 {sample_size} 条观测，少于最小样本 {MIN_OBSERVATIONS}；"
                "已单独挂起，不代表已达标。"
            ),
            next_step=(
                f"等待该窗口补足至少 {MIN_OBSERVATIONS} 条观测后，从检测入口重新提交评估。"
            ),
        )

    base_value = as_float(baseline.get("基线值"))
    threshold_row = threshold or {
        "阈值": baseline.get("阈值"),
        "阈值版本": baseline.get("阈值版本"),
    }
    threshold_value = as_float(threshold_row.get("阈值"))
    if observed is None or base_value is None or threshold_value is None:
        return _empty_decision(
            status="待处理",
            verdict="观测数据不完整",
            reason="观测值、基线值或阈值缺失，无法计算偏差。",
            next_step="补齐观测值与基线阈值后重新提交评估。",
        )

    if base_value == 0:
        raw_deviation = abs(observed)
        ratio = None
        deviation_type = "绝对偏差"
        exceeds = raw_deviation > threshold_value
        comparison = (
            f"零基线不做除法，按绝对偏差 |{observed:.4f} - 0| = {raw_deviation:.4f} "
            f"{'>' if exceeds else '<='} 阈值 {threshold_value:.4f}"
        )
        threshold_text = f"{threshold_value:.2f}（绝对阈值）"
    else:
        raw_deviation = abs(observed - base_value)
        ratio = raw_deviation / abs(base_value)
        deviation_type = "相对偏差"
        exceeds = ratio > threshold_value
        comparison = (
            f"|{observed:.4f} - {base_value:.4f}| / |{base_value:.4f}| = {ratio:.2%} "
            f"{'>' if exceeds else '<='} 阈值 {threshold_value:.2%}"
        )
        threshold_text = f"{threshold_value:.2%}"

    verdict = "超阈值" if exceeds else "未超阈值"
    credential_payload = {
        "指标编码": metric_code,
        "实验编码": experiment_code,
        "指标窗口": window,
        "观测值": round(observed, 6),
        "观测数": sample_size,
        "基线值": round(base_value, 6),
        "基线版本": str(baseline.get("基线版本", "")),
        "阈值": round(threshold_value, 6),
        "阈值版本": str(threshold_row.get("阈值版本", "")),
        "适用范围": normalize_scope(baseline.get("适用范围")),
        "原始偏差": round(raw_deviation, 6),
        "偏差率": None if ratio is None else round(ratio, 6),
        "偏差类型": deviation_type,
        "判定": verdict,
    }
    digest = hashlib.sha256(
        json.dumps(credential_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        **credential_payload,
        "阈值文本": threshold_text,
        "偏差率文本": percent_text(ratio),
        "判定": verdict,
        "结论": "异常" if exceeds else "正常",
        "是否超阈值": exceeds,
        "可交付": True,
        "处理状态": "待确认" if exceeds else "已判定",
        "判定说明": comparison,
        "比较依据": (
            f"基线版本 {baseline.get('基线版本', '')}，"
            f"阈值版本 {threshold_row.get('阈值版本', '')}（{threshold_text}），"
            f"适用范围 {normalize_scope(baseline.get('适用范围'))}，"
            f"指标窗口 {window}，{deviation_type}，{comparison}"
        ),
        "下一步": (
            "由数据质量角色确认异常并提交结论评审。" if exceeds
            else "结论为正常，无需确认异常；如需复核可复算本次凭证。"
        ),
        "凭证编号": "DEC-" + digest[:16].upper(),
        "凭证摘要": digest,
    }


def snapshot_from_evaluation(evaluation: dict[str, Any]) -> dict[str, Any]:
    """固化评审材料所用的判定依据，后续基线变化不能改写这份快照。"""
    fields = (
        "评估编号", "观测编号", "指标编码", "实验编码", "指标窗口", "观测值",
        "观测数", "基线值", "基线版本", "阈值", "阈值版本", "阈值文本", "适用范围",
        "原始偏差", "偏差率", "偏差率文本", "偏差类型", "判定", "结论",
        "判定说明", "比较依据", "凭证编号", "凭证摘要", "判定时间",
    )
    return {field: evaluation.get(field) for field in fields}
