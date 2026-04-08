import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ========== 配置 ==========
export const configApi = {
  get: () => api.get('/config'),
  update: (data) => api.put('/config', data),
  getProviders: () => api.get('/config/providers'),
  fetchModels: (data) => api.post('/config/models', data),
}

// ========== 功能设置 ==========
export const settingsApi = {
  getFeeds: () => api.get('/settings/feeds'),
  addFeed: (data) => api.post('/settings/feeds', data),
  deleteFeed: (id) => api.delete(`/settings/feeds/${id}`),
  getSites: () => api.get('/settings/sites'),
  addSite: (data) => api.post('/settings/sites', data),
  updateSite: (id, data) => api.put(`/settings/sites/${id}`, data),
  deleteSite: (id) => api.delete(`/settings/sites/${id}`),
  getSchedule: () => api.get('/settings/schedule'),
  updateSchedule: (data) => api.put('/settings/schedule', data),
}

// ========== 新闻 ==========
export const newsApi = {
  getArticles: (params) => api.get('/news', { params }),
  getArticle: (id) => api.get(`/news/${id}`),
  getStats: () => api.get('/news/stats'),
  getSources: () => api.get('/news/sources'),
  runPipeline: () => api.post('/news/pipeline'),
  deleteArticles: (ids) => api.post('/news/batch-delete', { article_ids: ids }),
}

// ========== 简报 ==========
export const briefApi = {
  list: () => api.get('/briefs'),
  get: (filename) => api.get(`/briefs/${filename}`),
  generate: () => api.post('/briefs/generate'),
}

// ========== AI 问答 ==========
export const queryApi = {
  ask: (question, topK = 10) => api.post('/query', { question, top_k: topK }),
  askStream: (question, topK = 10) => {
    // SSE 流式请求
    return fetch('/api/query/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, top_k: topK }),
    })
  },
}

// ========== 健康检查 ==========
export const healthApi = {
  check: () => api.get('/health'),
}

export default api
