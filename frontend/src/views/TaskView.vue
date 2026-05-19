<template>
  <div class="task-view">
    <header class="page-header">
      <div>
        <h1><SvgIcon name="task" :size="24" /> 任务追踪</h1>
        <p class="subtitle">查看异步任务历史、阶段进度、事件和失败原因</p>
      </div>
      <button class="btn" @click="loadTasks" :disabled="loading">
        <SvgIcon name="refresh" :size="16" />
        刷新
      </button>
    </header>

    <section class="filters">
      <input v-model="filters.task_id" class="input" placeholder="任务 ID" @keyup.enter="applyFilters" />
      <select v-model="filters.task_type" class="input" @change="applyFilters">
        <option value="">全部类型</option>
        <option value="intel_pipeline">intel_pipeline</option>
        <option value="pipeline">pipeline</option>
        <option value="upload_batch">upload_batch</option>
        <option value="report">report</option>
      </select>
      <select v-model="filters.status" class="input" @change="applyFilters">
        <option value="">全部状态</option>
        <option value="pending">pending</option>
        <option value="running">running</option>
        <option value="succeeded">succeeded</option>
        <option value="failed">failed</option>
        <option value="cancelled">cancelled</option>
      </select>
      <input v-model="filters.date_from" class="input" type="date" @change="applyFilters" />
      <input v-model="filters.date_to" class="input" type="date" @change="applyFilters" />
    </section>

    <div class="task-layout">
      <aside class="task-list-panel">
        <LoadingState v-if="loading" message="加载任务..." />
        <EmptyState
          v-else-if="!tasks.length"
          icon="task"
          title="暂无任务"
          message="没有匹配当前筛选条件的任务记录。"
        />
        <template v-else>
          <button
            v-for="task in tasks"
            :key="task.id"
            class="task-row"
            :class="{ active: selectedTask?.task_id === task.id || selectedTask?.run?.id === task.id }"
            @click="selectTask(task.id)"
          >
            <div>
              <strong>{{ task.task_type }}</strong>
              <small>{{ task.id }}</small>
            </div>
            <StatusBadge kind="task" :status="task.status" />
            <span>{{ formatTime(task.created_at) }}</span>
          </button>
        </template>
      </aside>

      <main class="task-detail-panel">
        <LoadingState v-if="detailLoading" message="加载任务详情..." />
        <EmptyState
          v-else-if="!selectedTask"
          icon="task"
          title="选择任务"
          message="从左侧选择一条任务查看阶段、事件和错误。"
        />
        <template v-else>
          <div class="detail-header">
            <div>
              <h2>{{ selectedTask.run?.task_type || selectedTask.task_id }}</h2>
              <p>{{ selectedTask.task_id }}</p>
            </div>
            <StatusBadge kind="task" :status="selectedTask.status" />
          </div>

          <section class="summary-grid">
            <div>
              <span>创建时间</span>
              <strong>{{ formatTime(selectedTask.run?.created_at) }}</strong>
            </div>
            <div>
              <span>耗时</span>
              <strong>{{ formatDuration(selectedTask.run) }}</strong>
            </div>
            <div>
              <span>尝试次数</span>
              <strong>{{ selectedTask.run?.attempt ?? 0 }}</strong>
            </div>
            <div>
              <span>Celery</span>
              <strong>{{ selectedTask.celery_status || 'unknown' }}</strong>
            </div>
          </section>

          <section v-if="selectedTask.error" class="error-box">
            <strong>失败原因</strong>
            <pre>{{ formatJson(selectedTask.error) }}</pre>
          </section>

          <div class="detail-grid">
            <section class="panel">
              <h3>阶段进度</h3>
              <TaskStageTimeline :stages="selectedTask.stages || []" />
            </section>

            <section class="panel">
              <h3>事件日志</h3>
              <EmptyState
                v-if="!selectedTask.events?.length"
                icon="task"
                title="暂无事件"
                message="该任务尚未返回事件记录。"
              />
              <ol v-else class="event-list">
                <li v-for="event in selectedTask.events" :key="event.id">
                  <strong>{{ event.event_type }}</strong>
                  <span>{{ formatTime(event.created_at) }}</span>
                  <pre>{{ formatJson(event.payload) }}</pre>
                </li>
              </ol>
            </section>
          </div>
        </template>
      </main>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { tasksApi } from '../api'
import EmptyState from '../components/EmptyState.vue'
import LoadingState from '../components/LoadingState.vue'
import StatusBadge from '../components/StatusBadge.vue'
import TaskStageTimeline from '../components/TaskStageTimeline.vue'
import SvgIcon from '../components/icons/SvgIcon.vue'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const detailLoading = ref(false)
const tasks = ref([])
const selectedTask = ref(null)
const filters = reactive({
  task_id: '',
  task_type: '',
  status: '',
  date_from: '',
  date_to: '',
})

function syncFromRoute() {
  Object.assign(filters, {
    task_id: route.query.task_id || '',
    task_type: route.query.task_type || '',
    status: route.query.status || '',
    date_from: route.query.date_from || '',
    date_to: route.query.date_to || '',
  })
}

function queryParams() {
  return Object.fromEntries(
    Object.entries(filters).filter(([key, value]) => key !== 'task_id' && value)
  )
}

function applyFilters() {
  const query = Object.fromEntries(Object.entries(filters).filter(([, value]) => value))
  router.replace({ path: '/tasks', query })
  loadTasks()
  if (filters.task_id) selectTask(filters.task_id)
}

async function loadTasks() {
  loading.value = true
  try {
    const res = await tasksApi.list({ ...queryParams(), limit: 50 })
    tasks.value = res.data.items || []
    if (!selectedTask.value && tasks.value.length) {
      await selectTask(filters.task_id || tasks.value[0].id)
    }
  } finally {
    loading.value = false
  }
}

async function selectTask(taskId) {
  if (!taskId) return
  detailLoading.value = true
  try {
    const res = await tasksApi.getStatus(taskId)
    selectedTask.value = res.data
    if (route.query.task_id !== taskId) {
      router.replace({ path: '/tasks', query: { ...route.query, task_id: taskId } })
    }
  } finally {
    detailLoading.value = false
  }
}

function formatTime(value) {
  if (!value) return '未知'
  try { return new Date(value).toLocaleString('zh-CN') } catch { return String(value) }
}

function formatDuration(run) {
  if (!run?.started_at) return '未开始'
  const end = run.finished_at || new Date().toISOString()
  const ms = new Date(end).getTime() - new Date(run.started_at).getTime()
  if (!Number.isFinite(ms) || ms < 0) return '未知'
  if (ms < 1000) return `${ms} ms`
  return `${Math.round(ms / 1000)} s`
}

function formatJson(value) {
  if (!value) return ''
  try { return JSON.stringify(value, null, 2) } catch { return String(value) }
}

watch(() => route.query, () => {
  syncFromRoute()
}, { deep: true })

onMounted(async () => {
  syncFromRoute()
  await loadTasks()
  if (filters.task_id) await selectTask(filters.task_id)
})
</script>

<style scoped>
.task-view {
  max-width: 1440px;
  margin: 0 auto;
  padding: var(--space-lg);
}
.page-header,
.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-md);
}
.filters {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) 180px 160px 150px 150px;
  gap: var(--space-sm);
  margin: var(--space-lg) 0;
}
.task-layout {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: var(--space-lg);
}
.task-list-panel,
.task-detail-panel,
.panel,
.error-box {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  padding: var(--space-md);
}
.task-list-panel {
  max-height: calc(100vh - 220px);
  overflow: auto;
}
.task-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--space-xs) var(--space-sm);
  width: 100%;
  margin-bottom: var(--space-xs);
  padding: var(--space-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
}
.task-row.active,
.task-row:hover {
  border-color: var(--accent-primary);
}
.task-row small,
.task-row span,
.detail-header p,
.summary-grid span {
  color: var(--text-muted);
  font-size: 0.8125rem;
}
.task-row small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-row > span {
  grid-column: 1 / -1;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-sm);
  margin: var(--space-md) 0;
}
.summary-grid div {
  padding: var(--space-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
}
.summary-grid span,
.summary-grid strong {
  display: block;
}
.detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
  gap: var(--space-md);
}
.panel h3 {
  margin-bottom: var(--space-sm);
}
.error-box {
  margin-bottom: var(--space-md);
  border-color: rgba(239, 68, 68, 0.4);
}
pre {
  max-height: 260px;
  margin: var(--space-xs) 0 0;
  overflow: auto;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}
.event-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  margin: 0;
  padding: 0;
  list-style: none;
}
.event-list li {
  padding: var(--space-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
}
.event-list strong,
.event-list span {
  display: block;
}
.event-list span {
  color: var(--text-muted);
  font-size: 0.75rem;
}
@media (max-width: 980px) {
  .filters,
  .task-layout,
  .detail-grid,
  .summary-grid {
    grid-template-columns: 1fr;
  }
  .task-list-panel {
    max-height: none;
  }
}
</style>
