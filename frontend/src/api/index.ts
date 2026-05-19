import axios, { AxiosInstance } from 'axios'
import { getApiKey } from '../auth'

const api: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
})

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

const RECENT_TASKS_STORAGE = 'insightforge_recent_tasks'

function authHeaders() {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const apiKey = getApiKey()
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`
  return headers
}

export function rememberTask(taskId: string, taskType = 'task') {
  if (!taskId) return
  const current = getRecentTasks()
  const next = [
    { task_id: taskId, task_type: taskType, created_at: new Date().toISOString() },
    ...current.filter((item: any) => item.task_id !== taskId),
  ].slice(0, 10)
  localStorage.setItem(RECENT_TASKS_STORAGE, JSON.stringify(next))
}

export function getRecentTasks() {
  try {
    const parsed = JSON.parse(localStorage.getItem(RECENT_TASKS_STORAGE) || '[]')
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

api.interceptors.request.use((config) => {
  const apiKey = getApiKey()
  if (apiKey) {
    config.headers.Authorization = `Bearer ${apiKey}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      error.message = '认证失败，请检查 API Key'
    } else if (error.response?.status === 403) {
      error.message = '当前角色无权执行该操作'
    }
    return Promise.reject(error)
  },
)

// ========== 认证 ==========
export const authApi = {
  me: () => api.get('/auth/me'),
}

// ========== 异步任务 ==========
export const tasksApi = {
  list: (params?: any) => api.get('/tasks', { params }),
  getStatus: (taskId: string) => api.get(`/tasks/${taskId}`),
  getEvents: (taskId: string, params?: any) => api.get(`/tasks/${taskId}`, { params }),
  getRecentLocal: () => getRecentTasks(),
}

export async function waitForTask(
  taskId: string,
  options: { intervalMs?: number; timeoutMs?: number } = {},
) {
  const intervalMs = options.intervalMs ?? 2000
  const timeoutMs = options.timeoutMs ?? 10 * 60 * 1000
  const startedAt = Date.now()

  while (Date.now() - startedAt < timeoutMs) {
    const res = await tasksApi.getStatus(taskId)
    const data = res.data

    if (data.ready || data.status === 'SUCCESS' || data.status === 'FAILURE') {
      if (data.status === 'FAILURE') {
        throw new Error(data.error || '任务执行失败')
      }
      return data.result
    }

    await sleep(intervalMs)
  }

  throw new Error('任务执行超时，请稍后查看结果')
}

// ========== 配置 ==========
export const configApi = {
  get: () => api.get('/config'),
  update: (data: any) => api.put('/config', data),
  audit: (params?: any) => api.get('/config/audit', { params }),
  reload: () => api.post('/config/reload'),
  getProviders: () => api.get('/config/providers'),
  fetchModels: (data: any) => api.post('/config/models', data),
}

// ========== 功能设置 ==========
export const settingsApi = {
  getFeeds: () => api.get('/settings/feeds'),
  addFeed: (data: any) => api.post('/settings/feeds', data),
  deleteFeed: (id: string | number) => api.delete(`/settings/feeds/${id}`),
  getSites: () => api.get('/settings/sites'),
  addSite: (data: any) => api.post('/settings/sites', data),
  updateSite: (id: string | number, data: any) => api.put(`/settings/sites/${id}`, data),
  deleteSite: (id: string | number) => api.delete(`/settings/sites/${id}`),
  getSchedule: () => api.get('/settings/schedule'),
  updateSchedule: (data: any) => api.put('/settings/schedule', data),
}

// ========== 结构化情报 ==========
export const intelApi = {
  listFacts: (params?: any) => api.get('/intel/facts', { params }),
  getFact: (id: string) => api.get(`/intel/facts/${id}`),
  createFact: (data: any) => api.post('/intel/facts', data),
  updateFact: (id: string, data: any) => api.put(`/intel/facts/${id}`, data),
  updateFactStatus: (id: string, status: string) => api.patch(`/intel/facts/${id}/status`, { status }),
  linkCompetitor: (id: string, data: any) => api.post(`/intel/facts/${id}/competitors`, data),
  linkProduct: (id: string, data: any) => api.post(`/intel/facts/${id}/products`, data),
  listEvidence: (id: string) => api.get(`/intel/facts/${id}/evidence`),
  createEvidence: (id: string, data: any) => api.post(`/intel/facts/${id}/evidence`, data),
  runPipeline: () => api.post('/intel/pipeline'),
}

// ========== Webhook 推送 ==========
export const webhookApi = {
  getPlatforms: () => api.get('/webhook/platforms'),
  getChannels: () => api.get('/webhook/channels'),
  addChannel: (data: any) => api.post('/webhook/channels', data),
  updateChannel: (id: string | number, data: any) => api.put(`/webhook/channels/${id}`, data),
  deleteChannel: (id: string | number) => api.delete(`/webhook/channels/${id}`),
  testChannel: (id: string | number) => api.post(`/webhook/channels/${id}/test`),
  pushAll: () => api.post('/webhook/push'),
  pushToChannel: (id: string | number) => api.post(`/webhook/push/${id}`),
  getAutoPush: () => api.get('/webhook/auto-push'),
  setAutoPush: (enabled: boolean) => api.put('/webhook/auto-push', { auto_push: enabled }),
}

// ========== AI 问答 (ReAct Agent) ==========
export const queryApi = {
  ask: (question: string, topK: number = 10, sessionId?: string | null) => (
    api.post('/query', { question, top_k: topK, session_id: sessionId || undefined })
  ),
  askStream: (question: string, topK: number = 10, sessionId?: string | null) => {
    // SSE 流式请求 — ReAct Agent 模式
    return fetch('/api/query/stream', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ question, top_k: topK, session_id: sessionId || undefined }),
    })
  },
  listSessions: (params?: any) => api.get('/query/sessions', { params }),
  getSession: (sessionId: string) => api.get(`/query/sessions/${sessionId}`),
}

// ========== 记忆管理 ==========
export const memoryApi = {
  listCore: (kind?: string) => api.get('/memory/core', { params: kind ? { kind } : undefined }),
  createCore: (data: any) => api.post('/memory/core', data),
  listPersistent: (params?: any) => api.get('/memory/persistent', { params }),
  createPersistent: (data: any) => api.post('/memory/persistent', data),
  updatePersistentStatus: (id: string, status: string) => api.put(`/memory/persistent/${id}/status`, { status }),
  deletePersistent: (id: string) => api.delete(`/memory/persistent/${id}`),
  getIndex: () => api.get('/memory/index'),
}

// ========== 深度研究 ==========
export const researchApi = {
  createPlan: (topic: string) => api.post('/research/sessions/plan', { topic }),
  updatePlan: (sessionId: string, data: any) => api.put(`/research/sessions/${sessionId}/plan`, data),
  getSession: (sessionId: string) => api.get(`/research/sessions/${sessionId}`),
  executeStream: (sessionId: string) => {
    return fetch(`/api/research/sessions/${sessionId}/execute/stream`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({}),
    })
  },
  list: () => api.get('/research'),
  get: (filename: string) => api.get(`/research/${filename}`),
  delete: (filename: string) => api.delete(`/research/${filename}`),
  batchDelete: (filenames: string[]) => api.post('/research/batch-delete', { filenames }),
  batchExport: (filenames: string[]) => api.post('/research/batch-export', { filenames }, { responseType: 'blob' }),
  push: (filename: string) => api.post(`/research/push/${filename}`),
}

// ========== 竞品管理 ==========
export const competitorApi = {
  list: (status = 'active') => api.get('/competitors', { params: { status } }),
  create: (data: any) => api.post('/competitors', data),
  get: (id: number) => api.get(`/competitors/${id}`),
  update: (id: number, data: any) => api.put(`/competitors/${id}`, data),
  delete: (id: number) => api.delete(`/competitors/${id}`),
  addProduct: (competitorId: number, data: any) => api.post(`/competitors/${competitorId}/products`, data),
  listProducts: (competitorId: number) => api.get(`/competitors/${competitorId}/products`),
  deleteProduct: (productId: number) => api.delete(`/competitors/products/${productId}`),
  getFacts: (competitorId: number, params?: any) => api.get(`/competitors/${competitorId}/facts`, { params }),
  getTimeline: (competitorId: number, params?: any) => api.get(`/competitors/${competitorId}/timeline`, { params }),
  compareFacts: (data: any) => api.post('/competitors/compare/facts', data),
  autoLink: () => api.post('/competitors/auto-link'),
}

// ========== 分析报告 ==========
export const reportApi = {
  list: (params?: any) => api.get('/reports', { params }),
  get: (id: number) => api.get(`/reports/${id}`),
  generate: (data: any) => api.post('/reports/generate', data),
  reviewQuality: (id: number) => api.post(`/reports/${id}/quality/review`),
  approve: (id: number) => api.post(`/reports/${id}/approve`),
  reject: (id: number, reason = '') => api.post(`/reports/${id}/reject`, { reason }),
  publish: (id: number) => api.post(`/reports/${id}/publish`),
  getAudit: (id: number) => api.get(`/reports/${id}/audit`),
  delete: (id: number) => api.delete(`/reports/${id}`),
}

// ========== 健康检查 ==========
export const healthApi = {
  check: () => api.get('/health'),
}

export const dashboardApi = {
  summary: async () => {
    const dateFrom = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
    const [competitors, reports, facts, health] = await Promise.allSettled([
      competitorApi.list(),
      reportApi.list({ limit: 30 }),
      intelApi.listFacts({ limit: 30, date_from: dateFrom }),
      healthApi.check(),
    ])
    const tasks = await Promise.allSettled([tasksApi.list({ limit: 10 })]).then((items) => items[0])
    return { competitors, reports, facts, health, tasks, recentTasks: getRecentTasks() }
  },
}

export default api
