import axios, { AxiosInstance } from 'axios'

const api: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
})

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

// ========== 异步任务 ==========
export const tasksApi = {
  getStatus: (taskId: string) => api.get(`/tasks/${taskId}`),
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

// ========== 新闻 ==========
export const newsApi = {
  getArticles: (params?: any) => api.get('/news', { params }),
  getArticle: (id: string | number) => api.get(`/news/${id}`),
  getStats: () => api.get('/news/stats'),
  getSources: () => api.get('/news/sources'),
  runPipeline: () => api.post('/news/pipeline'),
  deleteArticles: (ids: (string | number)[]) => api.post('/news/batch-delete', { article_ids: ids }),
  resummarize: (ids: (string | number)[]) => api.post('/news/resummarize', { article_ids: ids }),
}

// ========== NewsAPI ==========
export const extNewsApi = {
  searchEverything: (params: any) => api.get('/newsapi/everything', { params }),
  searchTopHeadlines: (params: any) => api.get('/newsapi/top-headlines', { params }),
  saveArticle: (data: any) => api.post('/newsapi/save', data),
}

// ========== 简报 ==========
export const briefApi = {
  list: () => api.get('/briefs'),
  get: (filename: string) => api.get(`/briefs/${filename}`),
  generate: () => api.post('/briefs/generate'),
  batchDelete: (filenames: string[]) => api.post('/briefs/batch-delete', { filenames }),
  batchExport: (filenames: string[]) => api.post('/briefs/batch-export', { filenames }, { responseType: 'blob' }),
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
      headers: { 'Content-Type': 'application/json' },
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
      headers: { 'Content-Type': 'application/json' },
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

// ========== 健康检查 ==========
export const healthApi = {
  check: () => api.get('/health'),
}

export default api
