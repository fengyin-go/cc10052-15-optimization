/** 告警判定与评审材料的数据层：与后端 /api/decision 一一对应。 */

export type ThresholdRow = {
  id: number
  status: string
  阈值版本: string
  指标编码: string
  指标窗口: string
  阈值: string | number
  偏差类型: string
  适用范围: string
  生效时间: string
  停用时间: string | null
  备注: string
  [field: string]: unknown
}

export type BaselineRow = {
  id: number
  status: string
  基线版本: string
  指标编码: string
  实验编码: string
  指标窗口: string
  基线值: string | number
  阈值: string | number
  阈值版本: string
  适用范围: string
  生效时间: string
  停用时间: string | null
  修订号: string
  备注: string
  [field: string]: unknown
}

export type ObservationRow = {
  id: number
  status: string
  观测编号: string
  指标编码: string
  实验编码: string
  指标窗口: string
  观测值: string | number
  观测数: string | number
  适用范围: string
  对比基线区间: string
  当前评估编号: string | null
  当前判定: string | null
  评估状态: string
  [field: string]: unknown
}

export type Evaluation = {
  id: number
  评估编号: string
  观测编号: string
  指标编码: string
  实验编码: string
  指标窗口: string
  观测值: string | number
  观测数: string | number
  适用范围: string
  基线版本: string | null
  基线值: string | number | null
  阈值: number | null
  阈值版本: string | null
  原始偏差: number | null
  偏差率: number | null
  偏差率文本: string
  偏差类型: string
  判定: string
  结论: string
  可交付: boolean
  处理状态: string
  判定说明: string
  比较依据: string
  下一步: string
  凭证编号: string | null
  判定时间: string
  重算状态: string
  来源评估编号: string | null
  超阈值但已被新基线覆盖: boolean
  废弃原因: string | null
  [field: string]: unknown
}

export type Basis = {
  评估编号: string
  凭证编号: string | null
  基线版本: string | null
  阈值版本: string | null
  阈值: number | null
  基线值: number | null
  观测值: string | number
  原始偏差: number | null
  偏差率文本: string
  偏差类型: string
  判定: string
  结论: string
  可交付: boolean
  判定时间: string
  指标窗口: string
  适用范围: string
  材料版本?: string
  领取时间?: string
}

export type Material = {
  记录编号: string
  实验编码: string
  评审结论: string
  评审角色: string
  记录状态: string
  材料状态: string
  材料版本: string
  本次依据: Basis | null
  当前依据: Basis | null
  判定依据快照: Basis | null
  依据状态: string
  重新评估状态: {
    已重新评估: boolean
    评估编号: string | null
    判定: string | null
    阈值版本: string | null
    基线版本: string | null
    判定时间: string | null
    重算状态: string | null
  }
  异常明细: {
    异常编号: string
    指标编码: string
    观测编号: string
    观测值: string | number
    基线版本: string
    阈值版本: string
    阈值: string | number
    原始偏差: string
    评估编号: string
    状态: string
    确认时间: string
  }[]
  冲突提示: string | null
  下一步: string
}

export type EvaluationResponse = {
  ok: boolean
  message: string
  evaluation: Evaluation
  observation?: ObservationRow
}

export type PreviewResponse = {
  observation: ObservationRow
  baseline: BaselineRow | null
  preview: Evaluation
  versions: BaselineRow[]
}
