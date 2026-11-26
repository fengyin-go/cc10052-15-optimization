import { request } from './client'
import type {
  BaselineRow,
  Evaluation,
  EvaluationResponse,
  Material,
  ObservationRow,
  PreviewResponse,
  ThresholdRow,
} from '@/data/decision-types'

async function readJson<T>(response: Response): Promise<T> {
  const payload = await response.json()
  if (!response.ok) {
    const detail = payload?.detail
    if (detail && typeof detail === 'object' && 'message' in detail) {
      const next = (detail as { next_step?: string }).next_step
      throw new Error(next ? `${detail.message}；下一步：${next}` : String(detail.message))
    }
    throw new Error(typeof detail === 'string' ? detail : `接口返回 ${response.status}`)
  }
  return payload as T
}

export async function listBaselines(metricCode = '', experimentCode = '') {
  const query = new URLSearchParams({ metric_code: metricCode, experiment_code: experimentCode })
  return readJson<{
    items: BaselineRow[]
    thresholds: ThresholdRow[]
    min_observations: number
  }>(await request(`/api/decision/baselines?${query}`))
}

export async function createBaseline(values: Record<string, string>) {
  return readJson<{ ok: boolean; message: string; entry?: BaselineRow }>(
    await request('/api/decision/baselines', {
      method: 'POST',
      body: JSON.stringify({ values }),
    }),
  )
}

export async function createThreshold(values: Record<string, string>) {
  return readJson<{ ok: boolean; message: string; entry?: ThresholdRow }>(
    await request('/api/decision/thresholds', {
      method: 'POST',
      body: JSON.stringify({ values }),
    }),
  )
}

export async function listObservations() {
  return readJson<{ items: ObservationRow[] }>(await request('/api/decision/observations'))
}

export async function loadPreview(observationId: number) {
  return readJson<PreviewResponse>(
    await request(`/api/decision/observations/${observationId}/preview`),
  )
}

export async function listObservationEvaluations(observationId: number) {
  return readJson<{ items: Evaluation[] }>(
    await request(`/api/decision/observations/${observationId}/evaluations`),
  )
}

export async function submitEvaluation(observationId: number, requestId: string) {
  return readJson<EvaluationResponse>(
    await request('/api/decision/evaluate', {
      method: 'POST',
      body: JSON.stringify({ observation_id: observationId, client_request_id: requestId }),
    }),
  )
}

export async function recalculateEvaluation(ref: string) {
  return readJson<{ ok: boolean; message: string; evaluation: Evaluation }>(
    await request(`/api/decision/evaluations/${ref}/recalculate`, { method: 'POST' }),
  )
}

export async function loadMaterial(code: string) {
  return readJson<Material>(await request(`/api/decision/reviews/${code}/material`))
}

export async function claimMaterial(code: string) {
  return readJson<{ ok: boolean; message: string; material: Material }>(
    await request(`/api/decision/reviews/${code}/claim`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),
  )
}

export async function recalculateReview(code: string) {
  return readJson<{
    ok: boolean
    message: string
    evaluation: Evaluation
    material: Material
  }>(
    await request(`/api/decision/reviews/${code}/recalculate`, {
      method: 'POST',
      body: JSON.stringify({ client_request_id: `review-${code}-${Date.now()}` }),
    }),
  )
}

export async function acceptReview(code: string, basis?: string, comment?: string) {
  return readJson<{ ok: boolean; message: string; review: Record<string, unknown> }>(
    await request(`/api/decision/reviews/${code}/accept`, {
      method: 'POST',
      body: JSON.stringify({ basis: basis ?? null, comment: comment ?? null }),
    }),
  )
}

export async function rejectReview(code: string, reason: string, basis?: string) {
  return readJson<{ ok: boolean; message: string }>(
    await request(`/api/decision/reviews/${code}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason, basis: basis ?? null }),
    }),
  )
}
