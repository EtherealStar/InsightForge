<template>
  <div class="intel-view">
    <header class="page-header">
      <div>
        <h1><SvgIcon name="intel" :size="24" /> 结构化情报</h1>
        <p class="subtitle">facts 筛选、证据复核、竞品和产品归因</p>
      </div>
      <button v-if="canAnalyze" class="btn btn-primary" @click="runPipeline" :disabled="pipelineRunning">
        <SvgIcon name="refresh" :size="16" />
        {{ pipelineRunning ? '提交中...' : '执行情报采集' }}
      </button>
    </header>

    <section class="filters">
      <input v-model="filters.keyword" class="input wide" placeholder="关键词" @keyup.enter="applyFilters" />
      <select v-model="filters.competitor_id" class="input" @change="applyFilters">
        <option value="">全部竞品</option>
        <option v-for="comp in competitors" :key="comp.id" :value="String(comp.id)">{{ comp.name }}</option>
      </select>
      <input v-model="filters.product_id" class="input" placeholder="产品 ID" @keyup.enter="applyFilters" />
      <select v-model="filters.fact_type" class="input" @change="applyFilters">
        <option value="">全部类型</option>
        <option v-for="item in factTypes" :key="item" :value="item">{{ item }}</option>
      </select>
      <select v-model="filters.dimension" class="input" @change="applyFilters">
        <option value="">全部维度</option>
        <option v-for="item in dimensions" :key="item" :value="item">{{ item }}</option>
      </select>
      <select v-model="filters.status" class="input" @change="applyFilters">
        <option value="">全部状态</option>
        <option value="draft">draft</option>
        <option value="active">active</option>
        <option value="rejected">rejected</option>
        <option value="archived">archived</option>
      </select>
      <input v-model="filters.date_from" class="input" type="date" @change="applyFilters" />
      <input v-model="filters.date_to" class="input" type="date" @change="applyFilters" />
    </section>

    <section class="score-filters">
      <label>最低重要度 <input v-model.number="filters.min_importance" class="input" type="number" min="0" max="1" step="0.05" @change="applyFilters" /></label>
      <label>最低置信度 <input v-model.number="filters.min_confidence" class="input" type="number" min="0" max="1" step="0.05" @change="applyFilters" /></label>
      <button class="btn" @click="applyFilters" :disabled="loading">刷新</button>
    </section>

    <div class="table-wrap">
      <LoadingState v-if="loading" message="加载 facts..." />
      <EmptyState
        v-else-if="!filteredFacts.length"
        icon="intel"
        title="暂无结构化 facts"
        message="调整筛选条件或执行情报采集。"
      />
      <table v-else class="facts-table">
        <thead>
          <tr>
            <th>Fact</th>
            <th>竞品/产品</th>
            <th>类型</th>
            <th>维度</th>
            <th>分数</th>
            <th>状态</th>
            <th>日期</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="fact in filteredFacts" :key="fact.id">
            <td>
              <strong>{{ fact.fact_text }}</strong>
              <small>{{ fact.subject }} · {{ fact.predicate }} <span v-if="fact.object">· {{ fact.object }}</span></small>
            </td>
            <td>
              <span>{{ formatIds(fact.competitor_ids) }}</span>
              <small>{{ formatIds(fact.product_ids) }}</small>
            </td>
            <td>{{ fact.fact_type || 'general' }}</td>
            <td>{{ fact.dimension || 'general' }}</td>
            <td>
              <span>I {{ formatScore(fact.importance_score) }}</span>
              <small>C {{ formatScore(fact.confidence_score) }}</small>
            </td>
            <td><StatusBadge kind="fact" :status="fact.status" /></td>
            <td>{{ fact.event_date || fact.observed_at || '未标注' }}</td>
            <td><button class="btn btn-sm" @click="loadFactDetail(fact.id)">详情</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <aside v-if="selectedFact" class="fact-drawer">
      <div class="drawer-header">
        <div>
          <h2>Fact 详情</h2>
          <StatusBadge kind="fact" :status="selectedFact.status" />
        </div>
        <button class="btn btn-sm" @click="selectedFact = null">
          <SvgIcon name="close" :size="14" />
          关闭
        </button>
      </div>
      <p class="drawer-fact-text">{{ selectedFact.fact_text }}</p>

      <dl class="fact-fields">
        <div><dt>类型</dt><dd>{{ selectedFact.fact_type || 'general' }}</dd></div>
        <div><dt>维度</dt><dd>{{ selectedFact.dimension || 'general' }}</dd></div>
        <div><dt>竞品</dt><dd>{{ formatIds(selectedFact.competitor_ids) }}</dd></div>
        <div><dt>产品</dt><dd>{{ formatIds(selectedFact.product_ids) }}</dd></div>
        <div><dt>重要度</dt><dd>{{ formatScore(selectedFact.importance_score) }}</dd></div>
        <div><dt>置信度</dt><dd>{{ formatScore(selectedFact.confidence_score) }}</dd></div>
      </dl>

      <section v-if="canAnalyze" class="review-actions">
        <select v-model="factStatus" class="input">
          <option value="draft">draft</option>
          <option value="rejected">rejected</option>
          <option value="archived">archived</option>
        </select>
        <button class="btn btn-sm" @click="updateSelectedStatus">更新状态</button>
        <input v-model.number="linkCompetitorId" class="input" type="number" placeholder="竞品 ID" />
        <button class="btn btn-sm" @click="linkCompetitor">关联竞品</button>
        <input v-model.number="linkProductId" class="input" type="number" placeholder="产品 ID" />
        <button class="btn btn-sm" @click="linkProduct">关联产品</button>
      </section>

      <EvidencePanel :items="selectedEvidence" title="Fact Evidence" />
      <section class="claims-panel">
        <h3>关联 Claims</h3>
        <EmptyState
          v-if="!relatedClaims.length"
          icon="quality"
          title="暂无关联 claims"
          message="当前 fact 详情未返回关联 claim。"
        />
        <template v-else>
          <div v-for="claim in relatedClaims" :key="claim.id || claim.claim_id" class="claim-item">
            {{ claim.claim || claim.text || claim.claim_id }}
          </div>
        </template>
      </section>
    </aside>

    <div v-if="toast.show" :class="['toast', 'toast-' + toast.type]">{{ toast.message }}</div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { competitorApi, intelApi, rememberTask } from '../api'
import { hasRole } from '../auth'
import EmptyState from '../components/EmptyState.vue'
import EvidencePanel from '../components/EvidencePanel.vue'
import LoadingState from '../components/LoadingState.vue'
import StatusBadge from '../components/StatusBadge.vue'
import SvgIcon from '../components/icons/SvgIcon.vue'

const route = useRoute()
const router = useRouter()
const facts = ref([])
const competitors = ref([])
const loading = ref(false)
const pipelineRunning = ref(false)
const selectedFact = ref(null)
const selectedEvidence = ref([])
const relatedClaims = ref([])
const factStatus = ref('draft')
const linkCompetitorId = ref(null)
const linkProductId = ref(null)
const toast = ref({ show: false, message: '', type: 'info' })
const canAnalyze = computed(() => hasRole('analyst'))
const filters = reactive({
  keyword: '',
  competitor_id: '',
  product_id: '',
  fact_type: '',
  dimension: '',
  status: '',
  date_from: '',
  date_to: '',
  min_importance: null,
  min_confidence: null,
})
const factTypes = ['feature', 'pricing', 'strategy', 'partnership', 'hiring', 'funding', 'market', 'review', 'security', 'legal', 'general']
const dimensions = ['product', 'technology', 'go_to_market', 'pricing', 'customer', 'ecosystem', 'risk', 'financial', 'talent', 'general']
const filteredFacts = computed(() => facts.value.filter((fact) => {
  if (filters.min_importance !== null && filters.min_importance !== '' && Number(fact.importance_score || 0) < Number(filters.min_importance)) return false
  if (filters.min_confidence !== null && filters.min_confidence !== '' && Number(fact.confidence_score || 0) < Number(filters.min_confidence)) return false
  return true
}))

function showToast(message, type = 'info') {
  toast.value = { show: true, message, type }
  setTimeout(() => { toast.value.show = false }, 3000)
}

function syncFromRoute() {
  for (const key of Object.keys(filters)) {
    filters[key] = route.query[key] ?? (key.startsWith('min_') ? null : '')
  }
}

function apiParams() {
  return Object.fromEntries(
    Object.entries(filters)
      .filter(([key, value]) => value !== '' && value !== null && !key.startsWith('min_'))
      .map(([key, value]) => [key, ['competitor_id', 'product_id'].includes(key) ? Number(value) : value])
  )
}

function applyFilters() {
  const query = Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== '' && value !== null))
  router.replace({ path: '/intel', query })
  fetchFacts()
}

async function fetchFacts() {
  loading.value = true
  try {
    const res = await intelApi.listFacts({ ...apiParams(), limit: 100 })
    facts.value = res.data.facts || []
  } catch (e) {
    showToast(e.response?.data?.detail || '加载 facts 失败', 'error')
  } finally {
    loading.value = false
  }
}

async function fetchCompetitors() {
  try {
    const res = await competitorApi.list()
    competitors.value = res.data.competitors || []
  } catch {
    competitors.value = []
  }
}

async function runPipeline() {
  pipelineRunning.value = true
  try {
    const res = await intelApi.runPipeline()
    const taskId = res.data.task_id
    if (!taskId) throw new Error('未返回任务 ID')
    rememberTask(taskId, 'intel_pipeline')
    showToast('情报采集任务已提交，正在跳转任务追踪。', 'success')
    router.push({ path: '/tasks', query: { task_id: taskId } })
  } catch (e) {
    showToast(e.response?.data?.detail || e.message || '情报采集失败', 'error')
  } finally {
    pipelineRunning.value = false
  }
}

async function loadFactDetail(id) {
  try {
    const [detail, evidence] = await Promise.all([intelApi.getFact(id), intelApi.listEvidence(id)])
    selectedFact.value = detail.data
    selectedEvidence.value = evidence.data.evidence_refs || evidence.data.items || detail.data.evidence_refs || []
    relatedClaims.value = detail.data.claims || detail.data.related_claims || []
    factStatus.value = detail.data.status === 'active' ? 'draft' : (detail.data.status || 'draft')
    linkCompetitorId.value = null
    linkProductId.value = null
  } catch (e) {
    showToast(e.response?.data?.detail || e.message || '加载 fact 详情失败', 'error')
  }
}

async function updateSelectedStatus() {
  if (!selectedFact.value?.id) return
  try {
    const res = await intelApi.updateFactStatus(selectedFact.value.id, factStatus.value)
    selectedFact.value = res.data
    showToast('状态已更新', 'success')
    await fetchFacts()
  } catch (e) {
    showToast(e.response?.data?.detail || e.message || '状态更新失败', 'error')
  }
}

async function linkCompetitor() {
  if (!selectedFact.value?.id || !linkCompetitorId.value) return
  try {
    const res = await intelApi.linkCompetitor(selectedFact.value.id, { competitor_id: Number(linkCompetitorId.value) })
    selectedFact.value = res.data
    showToast('竞品关联已更新', 'success')
    await fetchFacts()
  } catch (e) {
    showToast(e.response?.data?.detail || e.message || '竞品关联失败', 'error')
  }
}

async function linkProduct() {
  if (!selectedFact.value?.id || !linkProductId.value) return
  try {
    const res = await intelApi.linkProduct(selectedFact.value.id, { product_id: Number(linkProductId.value) })
    selectedFact.value = res.data
    showToast('产品关联已更新', 'success')
    await fetchFacts()
  } catch (e) {
    showToast(e.response?.data?.detail || e.message || '产品关联失败', 'error')
  }
}

function formatScore(value) { return Number(value || 0).toFixed(2) }
function formatIds(values) { return values?.length ? values.join(', ') : '未关联' }

watch(() => route.query, syncFromRoute, { deep: true })
onMounted(async () => {
  syncFromRoute()
  await Promise.all([fetchCompetitors(), fetchFacts()])
})
</script>

<style scoped>
.intel-view {
  max-width: 1440px;
  margin: 0 auto;
  padding: var(--space-lg);
}
.page-header {
  display: flex;
  justify-content: space-between;
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}
.filters {
  display: grid;
  grid-template-columns: minmax(220px, 1.2fr) 180px 120px 150px 160px 140px 150px 150px;
  gap: var(--space-sm);
  margin-bottom: var(--space-sm);
}
.score-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-lg);
}
.score-filters label {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  color: var(--text-muted);
  font-size: 0.8125rem;
}
.score-filters input {
  width: 120px;
}
.table-wrap {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  overflow: auto;
}
.facts-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 1080px;
}
.facts-table th,
.facts-table td {
  padding: var(--space-sm);
  border-bottom: 1px solid var(--border-color);
  text-align: left;
  vertical-align: top;
}
.facts-table th {
  color: var(--text-muted);
  font-size: 0.75rem;
  text-transform: uppercase;
}
.facts-table strong,
.facts-table small,
.facts-table span {
  display: block;
}
.facts-table small {
  margin-top: 4px;
  color: var(--text-muted);
}
.fact-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 180;
  width: min(520px, 100vw);
  padding: var(--space-lg);
  border-left: 1px solid var(--border-color);
  background: var(--bg-secondary);
  box-shadow: var(--shadow-lg);
  overflow-y: auto;
}
.drawer-header {
  display: flex;
  justify-content: space-between;
  gap: var(--space-md);
  margin-bottom: var(--space-md);
}
.drawer-fact-text {
  margin-bottom: var(--space-lg);
  color: var(--text-secondary);
  line-height: 1.6;
}
.fact-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-sm);
  margin-bottom: var(--space-lg);
}
.fact-fields div,
.claim-item {
  padding: var(--space-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
}
.fact-fields dt {
  color: var(--text-muted);
  font-size: 0.75rem;
}
.fact-fields dd {
  margin: 4px 0 0;
}
.review-actions {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: var(--space-sm);
  margin-bottom: var(--space-lg);
}
.claims-panel {
  margin-top: var(--space-lg);
}
.claims-panel h3 {
  margin-bottom: var(--space-sm);
}
@media (max-width: 1100px) {
  .filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 720px) {
  .intel-view {
    padding: var(--space-sm);
  }
  .page-header,
  .filters,
  .review-actions {
    grid-template-columns: 1fr;
    flex-direction: column;
  }
  .fact-drawer {
    top: 56px;
  }
}
</style>
