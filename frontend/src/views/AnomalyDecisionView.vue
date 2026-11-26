<template>
  <section class="page decision-page" data-testid="anomaly-decision">
    <header class="page-head">
      <div>
        <h2>告警判定工作台</h2>
        <p class="page-desc">
          按指标窗口核对适用基线、阈值版本与判定凭证；观测、适用范围和实际判定分开显示。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" data-testid="decision-refresh" type="button" @click="reloadAll">
          刷新数据
        </button>
      </div>
    </header>

    <p v-if="errorMessage" class="error-text" data-testid="decision-error">{{ errorMessage }}</p>
    <p v-if="notice" class="notice-text" data-testid="decision-notice">{{ notice }}</p>

    <div class="decision-grid">
      <section class="decision-panel">
        <h3>指标窗口观测</h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>观测编号</th>
              <th>指标 / 实验</th>
              <th>指标窗口</th>
              <th>观测值</th>
              <th>观测数</th>
              <th>适用范围</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in observations"
              :key="row.id"
              :data-testid="`obs-row-${row.观测编号}`"
              :class="{ selected: selected?.id === row.id }"
            >
              <td>{{ row.观测编号 }}</td>
              <td>{{ row.指标编码 }} / {{ row.实验编码 }}</td>
              <td>{{ row.指标窗口 }}</td>
              <td>{{ row.观测值 }}</td>
              <td>{{ row.观测数 }}</td>
              <td>
                <span class="scope-tag">{{ row.适用范围 }}</span>
              </td>
              <td>
                {{ row.status }}
                <span v-if="row.当前判定" class="verdict-tag" :data-verdict="row.当前判定">
                  {{ row.当前判定 }}
                </span>
              </td>
              <td class="row-actions">
                <button
                  class="link"
                  type="button"
                  :data-testid="`obs-preview-${row.观测编号}`"
                  @click="selectObservation(row)"
                >
                  核对基线
                </button>
                <button
                  class="link"
                  type="button"
                  :data-testid="`obs-evaluate-${row.观测编号}`"
                  @click="evaluate(row)"
                >
                  提交评估
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <section v-if="selected" class="decision-panel" data-testid="observation-detail">
        <h3>
          观测 {{ selected.观测编号 }}：观测 / 适用范围 / 实际判定
        </h3>
        <dl class="detail-grid">
          <div>
            <dt>观测窗口</dt>
            <dd>{{ selected.指标窗口 }}</dd>
          </div>
          <div>
            <dt>观测值</dt>
            <dd>{{ selected.观测值 }}（{{ selected.观测数 }} 条）</dd>
          </div>
          <div>
            <dt>观测适用范围</dt>
            <dd>
              <span class="scope-tag">{{ selected.适用范围 }}</span>
            </dd>
          </div>
          <div>
            <dt>基线适用范围</dt>
            <dd>
              <span v-if="preview?.baseline" class="scope-tag">
                {{ preview.baseline.适用范围 }}
              </span>
              <span v-else class="muted">无适用基线</span>
            </dd>
          </div>
          <div>
            <dt>实际判定</dt>
            <dd>
              <span
                class="verdict-tag"
                :data-verdict="preview?.preview?.判定 ?? '未判定'"
                :data-testid="'preview-verdict'"
              >
                {{ preview?.preview?.判定 ?? '未判定' }}
              </span>
            </dd>
          </div>
          <div>
            <dt>本次依据</dt>
            <dd data-testid="preview-basis">
              <template v-if="preview?.baseline">
                基线 {{ preview.baseline.基线版本 }}（{{ preview.baseline.status }}），
                阈值 {{ preview.baseline.阈值版本 }} = {{ preview.preview.阈值文本 }}
              </template>
              <span v-else class="muted">无适用基线</span>
            </dd>
          </div>
        </dl>

        <p class="basis-line" data-testid="preview-comparison">
          {{ preview?.preview?.判定说明 }}
        </p>
        <p v-if="preview?.preview?.下一步" class="next-step" data-testid="preview-next">
          下一步：{{ preview?.preview?.下一步 }}
        </p>

        <h4>该窗口的基线版本</h4>
        <table class="data-table compact">
          <thead>
            <tr>
              <th>基线版本</th>
              <th>基线值</th>
              <th>阈值版本</th>
              <th>阈值</th>
              <th>适用范围</th>
              <th>生效 / 停用</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="version in preview?.versions ?? []"
              :key="version.基线版本"
              :data-testid="`version-${version.基线版本}`"
            >
              <td>{{ version.基线版本 }}</td>
              <td>{{ version.基线值 }}</td>
              <td>{{ version.阈值版本 }}</td>
              <td>{{ version.阈值 }}</td>
              <td>{{ version.适用范围 }}</td>
              <td>{{ shortTime(version.生效时间) }} / {{ shortTime(version.停用时间) }}</td>
              <td>{{ version.status }}</td>
            </tr>
          </tbody>
        </table>

        <h4>评估记录</h4>
        <table class="data-table compact">
          <thead>
            <tr>
              <th>评估编号</th>
              <th>判定</th>
              <th>基线 / 阈值版本</th>
              <th>原始偏差</th>
              <th>凭证编号</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="ev in evaluationsForSelected"
              :key="ev.评估编号"
              :data-testid="`eval-${ev.评估编号}`"
            >
              <td>
                {{ ev.评估编号 }}
                <span v-if="ev.来源评估编号" class="muted">（复算自 {{ ev.来源评估编号 }}）</span>
              </td>
              <td>
                <span class="verdict-tag" :data-verdict="ev.判定">{{ ev.判定 }}</span>
              </td>
              <td>{{ ev.基线版本 }} / {{ ev.阈值版本 }}</td>
              <td>{{ ev.原始偏差 }}（{{ ev.偏差类型 }}，{{ ev.偏差率文本 }}）</td>
              <td>{{ ev.凭证编号 ?? '—' }}</td>
              <td>
                <button
                  class="link"
                  type="button"
                  :data-testid="`eval-recalc-${ev.评估编号}`"
                  @click="recalculate(ev)"
                >
                  按原依据复算
                </button>
              </td>
            </tr>
            <tr v-if="!evaluationsForSelected.length">
              <td colspan="6" class="empty-state">该观测暂时没有评估记录</td>
            </tr>
          </tbody>
        </table>
        <p v-if="lastRecalc" class="notice-text" data-testid="recalc-result">
          复算结果：{{ lastRecalc.评估编号 }} 判定 {{ lastRecalc.判定 }}，
          凭证 {{ lastRecalc.凭证编号 }}（基线 {{ lastRecalc.基线版本 }} / 阈值
          {{ lastRecalc.阈值版本 }}）
        </p>
      </section>
    </div>

    <section class="decision-panel" data-testid="baseline-panel">
      <h3>基线登记（同窗口新版本只产生可区分的评估）</h3>
      <form class="inline-form" @submit.prevent="submitBaseline">
        <label v-for="field in baselineFields" :key="field" :class="{ wide: field === '指标窗口' }">
          <span>{{ field }}</span>
          <input v-model="baselineDraft[field]" :data-testid="`baseline-${field}`" />
        </label>
        <button class="btn primary" data-testid="baseline-submit" type="submit">登记基线</button>
      </form>
      <table class="data-table compact">
        <thead>
          <tr>
            <th>基线版本</th>
            <th>指标 / 实验 / 窗口</th>
            <th>基线值</th>
            <th>阈值版本</th>
            <th>适用范围</th>
            <th>修订号</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in baselines" :key="row.id">
            <td>{{ row.基线版本 }}</td>
            <td>{{ row.指标编码 }} / {{ row.实验编码 }} / {{ row.指标窗口 }}</td>
            <td>{{ row.基线值 }}</td>
            <td>{{ row.阈值版本 }} = {{ row.阈值 }}</td>
            <td>{{ row.适用范围 }}</td>
            <td>{{ row.修订号 }}</td>
            <td>{{ row.status }}</td>
          </tr>
        </tbody>
      </table>

      <h3>阈值版本</h3>
      <form class="inline-form" @submit.prevent="submitThreshold">
        <label v-for="field in thresholdFields" :key="field" :class="{ wide: field === '指标窗口' }">
          <span>{{ field }}</span>
          <input v-model="thresholdDraft[field]" :data-testid="`threshold-${field}`" />
        </label>
        <button class="btn" data-testid="threshold-submit" type="submit">发布阈值</button>
      </form>
      <table class="data-table compact">
        <thead>
          <tr>
            <th>阈值版本</th>
            <th>指标 / 窗口</th>
            <th>阈值</th>
            <th>偏差类型</th>
            <th>适用范围</th>
            <th>生效</th>
            <th>停用</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in thresholds" :key="row.id">
            <td>{{ row.阈值版本 }}</td>
            <td>{{ row.指标编码 }} / {{ row.指标窗口 }}</td>
            <td>{{ row.阈值 }}</td>
            <td>{{ row.偏差类型 }}</td>
            <td>{{ row.适用范围 }}</td>
            <td>{{ shortTime(row.生效时间) }}</td>
            <td>{{ shortTime(row.停用时间) }}</td>
            <td>{{ row.status }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="decision-panel" data-testid="review-material-panel">
      <header class="panel-head">
        <h3>结评审材料</h3>
        <div class="inline-form tight">
          <label>
            <span>评审记录编号</span>
            <input v-model="reviewCode" data-testid="review-code" placeholder="例如 RV-AN-1" />
          </label>
          <button class="btn" data-testid="review-load" type="button" @click="loadReview">
            读取材料
          </button>
          <button
            class="btn"
            data-testid="review-claim"
            type="button"
            :disabled="!material"
            @click="claim"
          >
            领取材料
          </button>
          <button
            class="btn"
            data-testid="review-recalc"
            type="button"
            :disabled="!material"
            @click="recalcReview"
          >
            要求重算
          </button>
        </div>
      </header>

      <div v-if="material" class="material-layout" data-testid="review-material">
        <div class="material-meta">
          <span>材料状态：<strong data-testid="material-state">{{ material.材料状态 }}</strong></span>
          <span>材料版本：v{{ material.材料版本 }}</span>
          <span>依据状态：<strong data-testid="basis-state">{{ material.依据状态 }}</strong></span>
          <span v-if="material.重新评估状态.已重新评估" class="warn-tag" data-testid="reeval-tag">
            已重新评估：{{ material.重新评估状态.评估编号 }}（{{
              material.重新评估状态.判定
            }}）
          </span>
        </div>

        <p v-if="material.冲突提示" class="conflict-text" data-testid="material-conflict">
          {{ material.冲突提示 }}
        </p>

        <div class="basis-columns">
          <article class="basis-card" data-testid="claimed-basis">
            <h4>本次依据（材料领取时固化）</h4>
            <dl v-if="material.本次依据" class="detail-grid single">
              <div><dt>评估编号</dt><dd>{{ material.本次依据.评估编号 }}</dd></div>
              <div><dt>凭证编号</dt><dd>{{ material.本次依据.凭证编号 }}</dd></div>
              <div><dt>基线版本</dt><dd>{{ material.本次依据.基线版本 }}</dd></div>
              <div><dt>阈值版本</dt><dd>{{ material.本次依据.阈值版本 }} = {{ material.本次依据.阈值 }}</dd></div>
              <div><dt>原始偏差</dt><dd>{{ material.本次依据.原始偏差 }}（{{ material.本次依据.偏差率文本 }}）</dd></div>
              <div><dt>判定</dt><dd>{{ material.本次依据.判定 }}</dd></div>
            </dl>
            <p v-else class="muted">尚未领取材料</p>
          </article>

          <article class="basis-card" data-testid="current-basis">
            <h4>当前依据（按现在生效基线重算）</h4>
            <dl v-if="material.当前依据" class="detail-grid single">
              <div><dt>评估编号</dt><dd>{{ material.当前依据.评估编号 }}</dd></div>
              <div><dt>凭证编号</dt><dd>{{ material.当前依据.凭证编号 }}</dd></div>
              <div><dt>基线版本</dt><dd>{{ material.当前依据.基线版本 }}</dd></div>
              <div><dt>阈值版本</dt><dd>{{ material.当前依据.阈值版本 }} = {{ material.当前依据.阈值 }}</dd></div>
              <div><dt>原始偏差</dt><dd>{{ material.当前依据.原始偏差 }}（{{ material.当前依据.偏差率文本 }}）</dd></div>
              <div><dt>判定</dt><dd>{{ material.当前依据.判定 }}</dd></div>
            </dl>
            <p v-else class="muted">当前没有可交付的评估</p>
          </article>
        </div>

        <h4>参与出结论的异常明细</h4>
        <table class="data-table compact">
          <thead>
            <tr>
              <th>异常编号</th>
              <th>观测</th>
              <th>触发基线版本</th>
              <th>阈值版本</th>
              <th>原始偏差</th>
              <th>评估编号</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in material.异常明细" :key="row.异常编号" data-testid="anomaly-detail">
              <td>{{ row.异常编号 }}</td>
              <td>{{ row.观测编号 }}</td>
              <td>{{ row.基线版本 }}</td>
              <td>{{ row.阈值版本 }} = {{ row.阈值 }}</td>
              <td>{{ row.原始偏差 }}</td>
              <td>{{ row.评估编号 }}</td>
              <td>{{ row.状态 }}</td>
            </tr>
            <tr v-if="!material.异常明细.length">
              <td colspan="7" class="empty-state">没有关联的异常明细</td>
            </tr>
          </tbody>
        </table>

        <p class="next-step" data-testid="material-next">下一步：{{ material.下一步 }}</p>

        <form class="inline-form" @submit.prevent="accept">
          <label class="wide">
            <span>办结依据评估编号（留空按本次依据）</span>
            <input v-model="acceptBasis" data-testid="accept-basis" placeholder="EV-0001" />
          </label>
          <label class="wide">
            <span>评审意见</span>
            <input v-model="acceptComment" data-testid="accept-comment" />
          </label>
          <button class="btn primary" data-testid="review-accept" type="submit">接受办结</button>
        </form>
        <form class="inline-form" @submit.prevent="reject">
          <label class="wide">
            <span>驳回原因</span>
            <input v-model="rejectReason" data-testid="reject-reason" />
          </label>
          <button class="btn" data-testid="review-reject" type="submit">要求重算并驳回</button>
        </form>
        <p v-if="reviewResult" class="notice-text" data-testid="review-result">{{ reviewResult }}</p>
      </div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  acceptReview,
  claimMaterial,
  createBaseline,
  createThreshold,
  listBaselines,
  listObservationEvaluations,
  listObservations,
  loadMaterial,
  loadPreview,
  recalculateEvaluation,
  recalculateReview,
  rejectReview,
  submitEvaluation,
} from '@/api/decision'
import type {
  BaselineRow,
  Evaluation,
  Material,
  ObservationRow,
  PreviewResponse,
  ThresholdRow,
} from '@/data/decision-types'

const observations = ref<ObservationRow[]>([])
const baselines = ref<BaselineRow[]>([])
const thresholds = ref<ThresholdRow[]>([])
const selected = ref<ObservationRow | null>(null)
const preview = ref<PreviewResponse | null>(null)
const evaluations = ref<Evaluation[]>([])
const lastRecalc = ref<Evaluation | null>(null)
const errorMessage = ref('')
const notice = ref('')

const baselineFields = ['指标编码', '实验编码', '指标窗口', '基线值', '阈值', '基线版本', '适用范围']
const thresholdFields = ['指标编码', '指标窗口', '阈值', '阈值版本', '适用范围']
const baselineDraft = ref<Record<string, string>>({})
const thresholdDraft = ref<Record<string, string>>({})

const reviewCode = ref('RV-AN-1')
const material = ref<Material | null>(null)
const acceptBasis = ref('')
const acceptComment = ref('')
const rejectReason = ref('')
const reviewResult = ref('')

const evaluationsForSelected = computed(() => {
  if (!selected.value) return []
  return evaluations.value
    .filter((item) => item.观测编号 === selected.value?.观测编号)
    .sort((a, b) => (a.判定时间 < b.判定时间 ? 1 : -1))
})

function shortTime(value: string | null | undefined) {
  if (!value) return '—'
  return String(value).replace('T', ' ').slice(0, 16)
}

async function reloadAll() {
  errorMessage.value = ''
  try {
    const [obs, base] = await Promise.all([listObservations(), listBaselines()])
    observations.value = obs.items
    baselines.value = base.items
    thresholds.value = base.thresholds
    await refreshEvaluations()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '读取告警判定数据失败'
  }
}

async function refreshEvaluations() {
  // 评估记录按观测查询；这里借预览接口顺带把该窗口的评估带回页面。
  if (!selected.value) return
  const detail = await loadPreview(selected.value.id)
  preview.value = detail
  evaluations.value = await fetchEvaluations(selected.value.id)
}

async function fetchEvaluations(observationId: number): Promise<Evaluation[]> {
  const payload = await listObservationEvaluations(observationId)
  return payload.items ?? []
}

async function selectObservation(row: ObservationRow) {
  errorMessage.value = ''
  lastRecalc.value = null
  selected.value = row
  try {
    await refreshEvaluations()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '核对基线失败'
  }
}

async function evaluate(row: ObservationRow) {
  errorMessage.value = ''
  notice.value = ''
  lastRecalc.value = null
  try {
    const result = await submitEvaluation(row.id, `ui-${row.观测编号}-${Date.now()}`)
    notice.value = `已提交评估：${result.evaluation.评估编号}（${result.evaluation.判定}）`
    selected.value = row
    await reloadAll()
    await selectObservation(row)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '提交评估失败'
  }
}

async function recalculate(record: Evaluation) {
  errorMessage.value = ''
  try {
    const result = await recalculateEvaluation(record.评估编号)
    lastRecalc.value = result.evaluation
    notice.value = result.message
    await reloadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '复算失败'
  }
}

async function submitBaseline() {
  errorMessage.value = ''
  notice.value = ''
  try {
    const result = await createBaseline(baselineDraft.value)
    notice.value = result.message
    if (result.ok) baselineDraft.value = {}
    await reloadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登记基线失败'
  }
}

async function submitThreshold() {
  errorMessage.value = ''
  notice.value = ''
  try {
    const result = await createThreshold(thresholdDraft.value)
    notice.value = result.message
    if (result.ok) thresholdDraft.value = {}
    await reloadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '发布阈值失败'
  }
}

async function loadReview() {
  errorMessage.value = ''
  reviewResult.value = ''
  try {
    material.value = await loadMaterial(reviewCode.value.trim())
  } catch (error) {
    material.value = null
    errorMessage.value = error instanceof Error ? error.message : '读取评审材料失败'
  }
}

async function claim() {
  errorMessage.value = ''
  reviewResult.value = ''
  try {
    const result = await claimMaterial(reviewCode.value.trim())
    material.value = result.material
    reviewResult.value = `材料已领取（v${result.material.材料版本}）`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '领取材料失败'
    await loadReview()
  }
}

async function recalcReview() {
  errorMessage.value = ''
  reviewResult.value = ''
  try {
    const result = await recalculateReview(reviewCode.value.trim())
    material.value = result.material
    reviewResult.value = result.message
    await reloadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '要求重算失败'
    await loadReview()
  }
}

async function accept() {
  errorMessage.value = ''
  reviewResult.value = ''
  try {
    const result = await acceptReview(
      reviewCode.value.trim(),
      acceptBasis.value.trim() || undefined,
      acceptComment.value.trim() || undefined,
    )
    reviewResult.value = result.message
    await loadReview()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '接受办结失败'
    await loadReview()
  }
}

async function reject() {
  errorMessage.value = ''
  reviewResult.value = ''
  try {
    const result = await rejectReview(reviewCode.value.trim(), rejectReason.value.trim())
    reviewResult.value = result.message
    await loadReview()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '驳回失败'
    await loadReview()
  }
}

onMounted(reloadAll)
</script>

<style scoped>
.decision-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.decision-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}
@media (max-width: 1100px) {
  .decision-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
.decision-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  overflow-x: auto;
}
.decision-panel h3 {
  margin: 0 0 10px;
  font-size: 15px;
}
.decision-panel h4 {
  margin: 14px 0 6px;
  font-size: 13px;
  color: var(--muted);
}
.panel-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-end;
}
tr.selected {
  background: #eef5ff;
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 16px;
  margin: 0;
}
.detail-grid.single {
  grid-template-columns: minmax(0, 1fr);
}
.detail-grid dt {
  font-size: 12px;
  color: var(--muted);
}
.detail-grid dd {
  margin: 2px 0 0;
  font-size: 13px;
}
.scope-tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  background: #eef2f7;
  font-size: 12px;
}
.verdict-tag {
  display: inline-block;
  margin-left: 4px;
  padding: 1px 8px;
  border-radius: 10px;
  background: #e8f5ec;
  color: #19733a;
  font-size: 12px;
}
.verdict-tag[data-verdict='超阈值'],
.verdict-tag[data-verdict='无法匹配有效基线'],
.verdict-tag[data-verdict='窗口不一致'] {
  background: #fdecec;
  color: #b42318;
}
.verdict-tag[data-verdict='数据不足'],
.verdict-tag[data-verdict='观测数据不完整'] {
  background: #fff6e5;
  color: #9a6700;
}
.basis-line,
.next-step {
  font-size: 13px;
  margin: 10px 0 0;
}
.next-step {
  color: var(--brand);
}
.notice-text {
  margin: 0;
  padding: 6px 10px;
  border-radius: 6px;
  background: #eef5ff;
  font-size: 13px;
}
.conflict-text {
  margin: 8px 0;
  padding: 8px 10px;
  border-radius: 6px;
  background: #fff4e5;
  color: #9a6700;
  font-size: 13px;
}
.material-layout {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.material-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-size: 13px;
}
.warn-tag {
  padding: 1px 8px;
  border-radius: 10px;
  background: #fff4e5;
  color: #9a6700;
  font-size: 12px;
}
.basis-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 900px) {
  .basis-columns {
    grid-template-columns: minmax(0, 1fr);
  }
}
.basis-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 12px;
}
.basis-card h4 {
  margin: 0 0 6px;
  color: #1f2937;
}
.inline-form {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: flex-end;
  margin: 8px 0 12px;
}
.inline-form.tight {
  margin: 0;
}
.inline-form label {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
  color: var(--muted);
}
.inline-form label.wide {
  min-width: 240px;
}
.inline-form input {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
}
.data-table.compact th,
.data-table.compact td {
  padding: 5px 8px;
  font-size: 12px;
}
.muted {
  color: var(--muted);
}
</style>
