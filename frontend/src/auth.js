import { reactive } from 'vue'

const API_KEY_STORAGE = 'insightforge_api_key'

export const authState = reactive({
  apiKey: localStorage.getItem(API_KEY_STORAGE) || '',
  actor: '',
  role: '',
  apiKeyId: '',
  ready: false,
})

export function getApiKey() {
  return authState.apiKey || localStorage.getItem(API_KEY_STORAGE) || ''
}

export function setApiKey(value) {
  authState.apiKey = value || ''
  if (authState.apiKey) {
    localStorage.setItem(API_KEY_STORAGE, authState.apiKey)
  } else {
    localStorage.removeItem(API_KEY_STORAGE)
  }
}

export function setActor(data) {
  authState.actor = data?.actor || ''
  authState.role = data?.role || ''
  authState.apiKeyId = data?.api_key_id || ''
  authState.ready = true
}

export function clearAuth() {
  setApiKey('')
  setActor(null)
}

export function hasRole(minRole) {
  const rank = { viewer: 10, analyst: 20, admin: 30 }
  return (rank[authState.role] || 0) >= (rank[minRole] || 0)
}
