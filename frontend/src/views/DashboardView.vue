<template>
  <div class="dashboard-view">
    <header class="page-header">
      <div>
        <h1><SvgIcon name="dashboard" :size="24" /> 工作台</h1>
        <p class="subtitle">竞品情报、报告审批、任务状态和系统健康总览</p>
      </div>
      <div class="header-actions">
        <RoleGate min-role="analyst">
          <button class="btn btn-primary" @click="runPipeline" :disabled="pipelineRunning">
            <SvgIcon name="refresh" :size="16" />
            {{ pipelineRunning ? '采集中...' : '运行 Pipeline' }}
          </button>
        </RoleGate>
        <button class="btn" @click="loadDashboard" :disabled="loading">
          <SvgIcon name="refresh" :size="16" />
          刷新
        </button>
      </div>
    </header>

    <section class="kpi-grid">
      <article class="kpi-card">
        <span>竞品数量</span>
        <strong>{{ competitors.length }}</strong>
        <small>{{ componentState.competitors }}</small>
      </article>
      <article class="kpi-card">
        <span>7 日 facts</span>
        <strong>{{ recentFactCount }}</strong>
        <small>{{ componentState.facts }}</small>
      </article>
      <article class="kpi-card">
        <span>待处理报告</span>
        <strong>{{ pendingReports.length }}</strong>
        <small>待审批或需修订</small>
      </article>
      <article class="kpi-card">
        <span>失败任务</span>
        <strong>{{ failedTasks.length }}</strong>
        <small>{{ recentTasks.length ? '本机最近触发任务' : '待任务列表 API' }}</small>
      </article>
      <article class="kpi-card">
        <span>系统健康</span>
        <strong>{{ healthLabel }}</strong>
        <small>{{ componentState.health }}</small>
      </article>
    </section>

    <section class="action-row">
      <router-link class="quick-action" to="/intel">
        <SvgIcon name="intel" :size="20" />
        <span>进入情报筛选</span>
      </router-link>
      <router-link class="quick-action" to="/reports">
        <SvgIcon name="report" :size="20" />
        <span>查看报告审批</span>
      </router-link>
      <RoleGate min-role="analyst">
        <router-link class="quick-action" to="/query">
          <SvgIcon name="search" :size="20" />
          <span>开始智能分析</span>
        </router-link>
      </RoleGate>
      <RoleGate min-role="analyst">
        <router-link class="quick-action" to="/reports">
          <SvgIcon name="plus" :size="20" />
          <span>生成分析报告</span>
        </router-link>
      </RoleGate>
    </section>

    <div class="dashboard-grid">
      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>待处理队列</h2>
            <p>等待审批、需修订或人工复核的报告</p>
          </div>
          <router-link to="/reports" class="panel-link">全部报告</router-link>
        </div>
        <LoadingState v-if="loadingReports" message="加载报告..." />
        <EmptyState
          v-else-if="!pendingReports.length"
          icon="report"
          title="暂无待处理报告"
          message="质量通过后进入 waiting_review，质量失败会进入 revision_required。"
        />
        <div v-else class="item-list">
          <button v-for="report in pendingReports" :key="report.id" class="list-item" @click="$router.push('/reports')">
            <span class="item-title">{{ report.title }}</span>
            <span class="item-meta">
              <StatusBadge kind="report" :status="report.status" />
              <StatusBadge kind="review" :status="report.review_status" />
              <small v-if="report.quality_score !== null && report.quality_score !== undefined">
                {{ Math.round(Number(report.quality_score) * 100) }}
              </small>
            </span>
          </button>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>最新情报</h2>
            <p>最近返回的结构化 facts</p>
          </div>
          <router-link to="/intel" class="panel-link">进入 Intel</router-link>
        </div>
        <LoadingState v-if="loadingFacts" message="加载 facts..." />
        <EmptyState
          v-else-if="!facts.length"
          icon="intel"
          title="暂无结构化情报"
          message="运行 Pipeline 后会在这里展示最新 facts。"
        />
        <div v-else class="item-list">
          <router-link v-for="fact in facts.slice(0, 8)" :key="fact.id" class="list-item" to="/intel">
            <span class="item-title">{{ fact.fact_text }}</span>
            <span class="item-meta">
              <StatusBadge kind="fact" :status="fact.status" />
              <small>{{ fact.fact_type || 'general' }}</small>
              <small>{{ fact.dimension || 'general' }}</small>
            </span>
          </router-link>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>最近任务</h2>
            <p>任务历史、阶段和失败摘要</p>
          </div>
          <router-link to="/tasks" class="panel-link">任务追踪</router-link>
        </div>
        <EmptyState
          v-if="!recentTasks.length"
          icon="task"
          title="暂无任务记录"
          message="运行 Pipeline 或生成报告后会在这里展示最近任务。"
        />
        <div v-else class="task-list">
          <article v-for="task in recentTasks" :key="task.task_id || task.id" class="task-card">
            <div class="task-header">
              <div>
                <strong>{{ task.task_type || 'task' }}</strong>
                <small>{{ task.task_id || task.id }}</small>
              </div>
              <StatusBadge kind="task" :status="task.status || 'pending'" />
            </div>
            <TaskStageTimeline :stages="task.stages || []" />
          </article>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>系统健康</h2>
            <p>后端 health endpoint 降级摘要</p>
          </div>
          <StatusBadge kind="task" :status="healthOk ? 'succeeded' : 'failed'" :label="healthLabel" />
        </div>
        <pre class="health-json">{{ healthPreview }}</pre>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { dashboardApi, intelApi, rememberTask, tasksApi, waitForTask } from '../api'
import EmptyState from '../components/EmptyState.vue'
import LoadingState from '../components/LoadingState.vue'
import RoleGate from '../components/RoleGate.vue'
import StatusBadge from '../components/StatusBadge.vue'
import TaskStageTimeline from '../components/TaskStageTimeline.vue'
import SvgIcon from '../components/icons/SvgIcon.vue'

const competitors = ref([])
const reports = ref([])
const facts = ref([])
const health = ref(null)
const recentTasks = ref([])
const loading = ref(false)
const loadingReports = ref(false)
const loadingFacts = ref(false)
const pipelineRunning = ref(false)
const componentState = ref({
  competitors: '未加载',
  facts: '未加载',
  reports: '未加载',
  health: '未加载',
  tasks: '未加载',
})

const pendingReports = computed(() => reports.value.filter((report) => (
  ['waiting_review', 'revision_required'].includes(report.status)
  || ['failed', 'needs_human'].includes(report.review_status)
)))
const recentFactCount = computed(() => facts.value.filter((fact) => {
  const value = fact.event_date || fact.observed_at || fact.created_at
  if (!value) return true
  const timestamp = new Date(value).getTime()
  return Number.isFinite(timestamp) && timestamp >= Date.now() - 7 * 24 * 60 * 60 * 1000
}).length)
const failedTasks = computed(() => recentTasks.value.filter((task) => ['failed', 'FAILURE'].includes(task.status)))
const healthOk = computed(() => Boolean(health.value && !health.value.error))
const healthLabel = computed(() => (healthOk.value ? '正常' : '降级'))
const healthPreview = computed(() => {
  if (!health.value) return '暂无 health 数据'
  try {
    return JSON.stringify(health.value, null, 2)
  } catch {
    return String(health.value)
  }
})

function readSettled(result, key, fallback) {
  if (result.status !== 'fulfilled') {
    componentState.value[key] = '加载失败'
    return fallback
  }
  componentState.value[key] = '已加载'
  return result.value?.data || result.value || fallback
}

async function loadRecentTaskStatuses() {
  const localTasks = tasksApi.getRecentLocal()
  if (!localTasks.length) {
    recentTasks.value = []
    return
  }
  const settled = await Promise.allSettled(localTasks.slice(0, 5).map((task) => tasksApi.getStatus(task.task_id)))
  recentTasks.value = localTasks.slice(0, 5).map((task, index) => {
    const result = settled[index]
    if (result.status !== 'fulfilled') return { ...task, status: 'failed', stages: [] }
    return {
      ...task,
      status: result.value.data.status || result.value.data.celery_status,
      stages: result.value.data.stages || [],
      error: result.value.data.error,
    }
  })
}

async function loadDashboard() {
  loading.value = true
  loadingReports.value = true
  loadingFacts.value = true
  try {
    const summary = await dashboardApi.summary()
    const competitorData = readSettled(summary.competitors, 'competitors', {})
    const reportData = readSettled(summary.reports, 'reports', {})
    const factData = readSettled(summary.facts, 'facts', {})
    const healthData = readSettled(summary.health, 'health', null)

    competitors.value = competitorData.competitors || []
    reports.value = reportData.reports || []
    facts.value = factData.facts || []
    health.value = healthData
    const taskData = readSettled(summary.tasks, 'tasks', null)
    if (taskData?.items?.length) {
      recentTasks.value = taskData.items.slice(0, 5)
    } else {
      await loadRecentTaskStatuses()
    }
  } finally {
    loading.value = false
    loadingReports.value = false
    loadingFacts.value = false
  }
}

async function runPipeline() {
  pipelineRunning.value = true
  try {
    const res = await intelApi.runPipeline()
    const taskId = res.data.task_id
    if (taskId) {
      rememberTask(taskId, 'pipeline')
      await loadRecentTaskStatuses()
      waitForTask(taskId, { timeoutMs: 30 * 1000 }).then(loadDashboard).catch(loadDashboard)
    }
  } finally {
    pipelineRunning.value = false
  }
}

onMounted(loadDashboard)
</script>

<style scoped>
.dashboard-view {
  max-width: 1440px;
  margin: 0 auto;
  padding: var(--space-lg);
}
.header-actions,
.action-row,
.item-meta,
.task-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}
.kpi-card,
.panel,
.quick-action,
.task-card {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-card);
}
.kpi-card {
  padding: var(--space-md);
}
.kpi-card span,
.kpi-card small {
  display: block;
  color: var(--text-muted);
  font-size: 0.8125rem;
}
.kpi-card strong {
  display: block;
  margin: var(--space-xs) 0;
  font-size: 1.75rem;
  line-height: 1;
}
.action-row {
  flex-wrap: wrap;
  margin-bottom: var(--space-lg);
}
.quick-action {
  display: inline-flex;
  align-items: center;
  gap: var(--space-sm);
  min-height: 44px;
  padding: var(--space-sm) var(--space-md);
  color: var(--text-primary);
}
.quick-action:hover {
  border-color: var(--border-hover);
  background: var(--bg-card-hover);
}
.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--space-lg);
}
.panel {
  min-width: 0;
  padding: var(--space-md);
}
.panel-header {
  display: flex;
  justify-content: space-between;
  gap: var(--space-md);
  margin-bottom: var(--space-md);
}
.panel-header h2 {
  font-size: 1.125rem;
}
.panel-header p,
.panel-note {
  margin-top: 2px;
  color: var(--text-muted);
  font-size: 0.8125rem;
}
.panel-link {
  flex-shrink: 0;
  font-size: 0.8125rem;
}
.item-list,
.task-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}
.list-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  width: 100%;
  padding: var(--space-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
}
.list-item:hover {
  border-color: var(--border-hover);
}
.item-title {
  overflow: hidden;
  color: var(--text-primary);
  font-weight: 600;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.item-meta {
  flex-wrap: wrap;
}
.item-meta small {
  color: var(--text-muted);
}
.task-card {
  padding: var(--space-sm);
  background: var(--bg-input);
}
.task-header {
  justify-content: space-between;
  margin-bottom: var(--space-sm);
}
.task-header strong,
.task-header small {
  display: block;
}
.task-header small {
  max-width: 260px;
  overflow: hidden;
  color: var(--text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.health-json {
  max-height: 260px;
  overflow: auto;
  padding: var(--space-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-secondary);
  font-size: 0.8125rem;
  white-space: pre-wrap;
}
@media (max-width: 1100px) {
  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .dashboard-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 720px) {
  .dashboard-view {
    padding: var(--space-sm);
  }
  .page-header,
  .panel-header {
    flex-direction: column;
    align-items: stretch;
  }
  .header-actions {
    flex-wrap: wrap;
  }
  .kpi-grid {
    grid-template-columns: 1fr;
  }
}
</style>
