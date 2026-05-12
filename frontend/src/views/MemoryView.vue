<template>
  <div class="memory-view">
    <div class="page-header">
      <div>
        <h1>记忆管理</h1>
        <p class="subtitle">确认候选记忆，维护 MEMORY 索引和核心记忆版本</p>
      </div>
      <button class="btn btn-sm" @click="refreshAll" :disabled="loading">刷新</button>
    </div>

    <section class="toolbar card">
      <div class="filter-group">
        <span class="filter-label">状态</span>
        <button
          v-for="item in statusOptions"
          :key="item.value"
          class="btn btn-sm"
          :class="{ 'btn-primary': statusFilter === item.value }"
          @click="statusFilter = item.value; fetchPersistent()"
        >
          {{ item.label }}
        </button>
      </div>
      <div class="filter-group">
        <span class="filter-label">类型</span>
        <button
          v-for="item in typeOptions"
          :key="item.value"
          class="btn btn-sm"
          :class="{ 'btn-primary': typeFilter === item.value }"
          @click="typeFilter = item.value; fetchPersistent()"
        >
          {{ item.label }}
        </button>
      </div>
    </section>

    <section class="memory-layout">
      <div class="memory-main">
        <div class="section-header">
          <h2>持久记忆</h2>
          <button class="btn btn-sm" @click="showCreatePersistent = !showCreatePersistent">
            {{ showCreatePersistent ? '收起' : '手动新增' }}
          </button>
        </div>

        <form v-if="showCreatePersistent" class="memory-form card" @submit.prevent="createPersistent">
          <select v-model="persistentForm.memory_type" class="input">
            <option value="user">用户偏好</option>
            <option value="feedback">反馈</option>
            <option value="project">项目</option>
          </select>
          <input v-model="persistentForm.title" class="input" placeholder="标题" required />
          <input v-model="persistentForm.summary" class="input" placeholder="MEMORY 索引摘要" required />
          <textarea v-model="persistentForm.content" class="input" placeholder="正文" required></textarea>
          <button class="btn btn-primary" :disabled="loading">创建 pending 记忆</button>
        </form>

        <div v-if="loading" class="empty-state">加载中...</div>
        <div v-else-if="!persistentItems.length" class="empty-state">暂无匹配记忆</div>
        <div v-else class="memory-list">
          <article v-for="item in persistentItems" :key="item.id" class="memory-card card">
            <div class="memory-card-header">
              <div>
                <div class="memory-title">
                  <span class="type-pill">{{ typeLabel(item.memory_type) }}</span>
                  <span>{{ item.title }}</span>
                </div>
                <p class="memory-summary">{{ item.summary }}</p>
              </div>
              <span class="status-pill" :class="item.status">{{ statusLabel(item.status) }}</span>
            </div>
            <p class="memory-content">{{ item.content }}</p>
            <div class="memory-meta">
              <span>来源：{{ item.source_session_id || '手动' }}</span>
              <span>置信度：{{ formatConfidence(item.confidence) }}</span>
              <span>{{ formatTime(item.updated_at || item.created_at) }}</span>
            </div>
            <div class="memory-actions">
              <button v-if="item.status !== 'active'" class="btn btn-sm btn-primary" @click="updateStatus(item.id, 'active')">
                确认
              </button>
              <button v-if="item.status !== 'archived'" class="btn btn-sm" @click="updateStatus(item.id, 'archived')">
                归档
              </button>
              <button class="btn btn-sm btn-danger" @click="deleteMemory(item.id)">删除</button>
            </div>
          </article>
        </div>
      </div>

      <aside class="memory-side">
        <section class="card side-section">
          <div class="section-header compact">
            <h2>MEMORY 索引</h2>
          </div>
          <div v-if="!indexItems.length" class="empty-state small">暂无 active 记忆</div>
          <div v-else class="index-list">
            <div v-for="item in indexItems" :key="item.id" class="index-line">
              {{ item.line }}
            </div>
          </div>
        </section>

        <section class="card side-section">
          <div class="section-header compact">
            <h2>核心记忆</h2>
          </div>
          <div class="filter-group wrap">
            <button
              v-for="item in coreKindOptions"
              :key="item.value"
              class="btn btn-sm"
              :class="{ 'btn-primary': coreKindFilter === item.value }"
              @click="coreKindFilter = item.value; fetchCore()"
            >
              {{ item.label }}
            </button>
          </div>
          <form class="core-form" @submit.prevent="createCore">
            <select v-model="coreForm.kind" class="input">
              <option v-for="item in coreKindOptions.slice(1)" :key="item.value" :value="item.value">
                {{ item.label }}
              </option>
            </select>
            <input v-model="coreForm.title" class="input" placeholder="版本标题" required />
            <textarea v-model="coreForm.content" class="input" placeholder="核心记忆内容" required></textarea>
            <button class="btn btn-primary" :disabled="loading">创建新版本</button>
          </form>
          <div v-if="!coreItems.length" class="empty-state small">暂无核心记忆</div>
          <div v-else class="core-list">
            <article v-for="item in coreItems" :key="item.id" class="core-item">
              <div class="core-title">{{ item.title }} <span>v{{ item.version }}</span></div>
              <div class="core-kind">{{ coreKindLabel(item.kind) }}</div>
              <p>{{ item.content }}</p>
            </article>
          </div>
        </section>
      </aside>
    </section>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { memoryApi } from '../api'

const loading = ref(false)
const statusFilter = ref('pending')
const typeFilter = ref('all')
const coreKindFilter = ref('all')
const persistentItems = ref([])
const coreItems = ref([])
const indexItems = ref([])
const showCreatePersistent = ref(false)

const persistentForm = ref({
  memory_type: 'user',
  title: '',
  summary: '',
  content: '',
})

const coreForm = ref({
  kind: 'system_prompt',
  title: '',
  content: '',
})

const statusOptions = [
  { value: 'pending', label: '待确认' },
  { value: 'active', label: '已启用' },
  { value: 'archived', label: '已归档' },
  { value: 'all', label: '全部' },
]

const typeOptions = [
  { value: 'user', label: '用户' },
  { value: 'feedback', label: '反馈' },
  { value: 'project', label: '项目' },
  { value: 'all', label: '全部' },
]

const coreKindOptions = [
  { value: 'all', label: '全部' },
  { value: 'system_prompt', label: '系统提示' },
  { value: 'tool_guide', label: '工具指南' },
  { value: 'session_template', label: '会话模板' },
  { value: 'full_compact_template', label: '压缩模板' },
]

function statusLabel(status) {
  return { pending: '待确认', active: '已启用', archived: '已归档', deleted: '已删除' }[status] || status
}

function typeLabel(type) {
  return { user: '用户', feedback: '反馈', project: '项目' }[type] || type
}

function coreKindLabel(kind) {
  return coreKindOptions.find(item => item.value === kind)?.label || kind
}

function formatConfidence(value) {
  if (value === null || value === undefined) return '未提供'
  return `${Math.round(Number(value) * 100)}%`
}

function formatTime(value) {
  if (!value) return ''
  try { return new Date(value).toLocaleString() } catch { return '' }
}

async function fetchPersistent() {
  loading.value = true
  try {
    const params = {}
    if (statusFilter.value !== 'all') params.status = statusFilter.value
    if (typeFilter.value !== 'all') params.memory_type = typeFilter.value
    const res = await memoryApi.listPersistent(params)
    persistentItems.value = res.data.items || []
  } finally {
    loading.value = false
  }
}

async function fetchCore() {
  const kind = coreKindFilter.value === 'all' ? undefined : coreKindFilter.value
  const res = await memoryApi.listCore(kind)
  coreItems.value = res.data.items || []
}

async function fetchIndex() {
  const res = await memoryApi.getIndex()
  indexItems.value = res.data.items || []
}

async function refreshAll() {
  await Promise.all([fetchPersistent(), fetchCore(), fetchIndex()])
}

async function updateStatus(id, status) {
  await memoryApi.updatePersistentStatus(id, status)
  await refreshAll()
}

async function deleteMemory(id) {
  if (!confirm('确定删除这条记忆？')) return
  await memoryApi.deletePersistent(id)
  await refreshAll()
}

async function createPersistent() {
  await memoryApi.createPersistent(persistentForm.value)
  persistentForm.value = { memory_type: 'user', title: '', summary: '', content: '' }
  showCreatePersistent.value = false
  statusFilter.value = 'pending'
  await refreshAll()
}

async function createCore() {
  await memoryApi.createCore(coreForm.value)
  coreForm.value = { kind: coreForm.value.kind, title: '', content: '' }
  await refreshAll()
}

onMounted(refreshAll)
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-md);
  padding: var(--space-md);
  margin-bottom: var(--space-lg);
}
.filter-group {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}
.filter-group.wrap {
  flex-wrap: wrap;
  align-items: flex-start;
}
.filter-label {
  color: var(--text-muted);
  font-size: 0.875rem;
  font-weight: 600;
}
.memory-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: var(--space-lg);
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-md);
}
.section-header.compact {
  margin-bottom: var(--space-sm);
}
.section-header h2 {
  margin: 0;
  font-size: 1.125rem;
}
.memory-form,
.side-section {
  padding: var(--space-md);
}
.memory-form,
.core-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin-bottom: var(--space-md);
}
.memory-form textarea,
.core-form textarea {
  min-height: 110px;
  resize: vertical;
}
.memory-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}
.memory-card {
  padding: var(--space-md);
}
.memory-card-header {
  display: flex;
  justify-content: space-between;
  gap: var(--space-md);
}
.memory-title {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  color: var(--text-primary);
  font-weight: 700;
}
.memory-summary {
  margin: 6px 0 0;
  color: var(--text-secondary);
}
.memory-content {
  margin: var(--space-md) 0;
  color: var(--text-primary);
  line-height: 1.7;
  white-space: pre-wrap;
}
.memory-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-md);
  color: var(--text-muted);
  font-size: 0.8rem;
}
.memory-actions {
  display: flex;
  gap: var(--space-sm);
  margin-top: var(--space-md);
}
.type-pill,
.status-pill {
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  font-weight: 700;
}
.type-pill {
  background: var(--bg-secondary);
  color: var(--text-secondary);
}
.status-pill.pending {
  background: rgba(245, 158, 11, 0.14);
  color: #f59e0b;
}
.status-pill.active {
  background: rgba(16, 185, 129, 0.14);
  color: #10b981;
}
.status-pill.archived {
  background: rgba(148, 163, 184, 0.14);
  color: #94a3b8;
}
.memory-side {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}
.index-list,
.core-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}
.index-line {
  padding: var(--space-sm);
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 0.85rem;
  line-height: 1.5;
}
.core-item {
  padding: var(--space-sm) 0;
  border-top: 1px solid var(--border-color);
}
.core-title {
  color: var(--text-primary);
  font-weight: 700;
}
.core-title span,
.core-kind {
  color: var(--text-muted);
  font-size: 0.75rem;
}
.core-item p {
  margin: 6px 0 0;
  color: var(--text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
}
.empty-state {
  padding: var(--space-xl);
  color: var(--text-muted);
  text-align: center;
}
.empty-state.small {
  padding: var(--space-md);
}

@media (max-width: 1100px) {
  .memory-layout {
    grid-template-columns: 1fr;
  }
}
</style>
