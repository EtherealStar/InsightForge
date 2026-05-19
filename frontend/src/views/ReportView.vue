<template>
  <div class="report-view">
    <header class="page-header">
      <div>
        <h1><SvgIcon name="report" :size="24" /> 分析报告</h1>
        <p class="subtitle">报告正文、证据、质量门禁和审批审计工作流</p>
      </div>
      <div class="header-actions">
        <button class="btn" @click="fetchReports" :disabled="loadingList">
          <SvgIcon name="refresh" :size="16" />
          刷新
        </button>
        <button v-if="canAnalyze" class="btn btn-primary" @click="showGenerator = !showGenerator">
          <SvgIcon name="plus" :size="16" />
          生成报告
        </button>
      </div>
    </header>

    <section v-if="showGenerator && canAnalyze" class="generator-panel">
      <div class="generator-grid">
        <label>
          <span>竞品</span>
          <select v-model="form.selectedCompetitorId" class="input">
            <option value="">选择竞品</option>
            <option v-for="comp in competitors" :key="comp.id" :value="String(comp.id)">{{ comp.name }}</option>
          </select>
        </label>
        <label>
          <span>高级竞品 ID</span>
          <input v-model="form.competitor_ids" class="input" placeholder="可填多个，逗号分隔" />
        </label>
        <label>
          <span>报告类型</span>
          <select v-model="form.report_type" class="input">
            <option value="overview">竞品概览</option>
            <option value="comparison">竞品对比</option>
            <option value="briefing">市场动态</option>
          </select>
        </label>
        <label class="focus-field">
          <span>分析重点</span>
          <input v-model="form.focus" class="input" placeholder="可选" />
        </label>
        <button class="btn btn-primary" @click="generateReport" :disabled="generating">
          {{ generating ? '生成中...' : '提交生成' }}
        </button>
      </div>
    </section>

    <section class="filters">
      <select v-model="filters.report_type" class="input" @change="applyFilters">
        <option value="">全部类型</option>
        <option value="overview">overview</option>
        <option value="comparison">comparison</option>
        <option value="briefing">briefing</option>
      </select>
      <select v-model="filters.status" class="input" @change="applyFilters">
        <option value="">全部报告状态</option>
        <option value="draft">draft</option>
        <option value="revision_required">revision_required</option>
        <option value="waiting_review">waiting_review</option>
        <option value="approved">approved</option>
        <option value="published">published</option>
        <option value="rejected">rejected</option>
      </select>
      <select v-model="filters.review_status" class="input" @change="applyFilters">
        <option value="">全部质检状态</option>
        <option value="not_reviewed">not_reviewed</option>
        <option value="passed">passed</option>
        <option value="failed">failed</option>
        <option value="needs_human">needs_human</option>
      </select>
      <input v-model.number="filters.min_quality" class="input" type="number" min="0" max="1" step="0.05" placeholder="最低质量分" @change="applyFilters" />
      <input v-model="filters.updated_from" class="input" type="date" @change="applyFilters" />
    </section>

    <div class="report-workbench">
      <aside class="report-list">
        <LoadingState v-if="loadingList" message="加载报告..." />
        <EmptyState v-else-if="!filteredReports.length" icon="report" title="暂无报告" message="没有匹配当前筛选条件的报告。" />
        <template v-else>
          <button
            v-for="report in filteredReports"
            :key="report.id"
            class="report-item"
            :class="{ active: selectedReport?.id === report.id }"
            @click="loadReport(report.id)"
          >
            <strong>{{ report.title }}</strong>
            <span class="badge-line">
              <StatusBadge kind="report" :status="report.status" />
              <StatusBadge kind="review" :status="report.review_status" />
            </span>
            <small>质量分 {{ report.quality_score == null ? '未评分' : formatScore(report.quality_score) }}</small>
            <small>{{ formatTime(report.updated_at || report.created_at) }}</small>
          </button>
        </template>
      </aside>

      <main class="report-reader">
        <LoadingState v-if="loadingContent" message="加载报告详情..." />
        <EmptyState v-else-if="!selectedReport" icon="report" title="选择报告" message="从左侧选择报告查看正文、证据和审计。" />
        <article v-else>
          <div class="content-header">
            <div>
              <h2>{{ selectedReport.title }}</h2>
              <div class="badge-line">
                <span>{{ selectedReport.report_type }}</span>
                <StatusBadge kind="report" :status="selectedReport.status" />
                <StatusBadge kind="review" :status="selectedReport.review_status" />
              </div>
            </div>
            <div class="actions">
              <button v-if="canAnalyze" class="btn btn-sm" @click="reviewQuality" :disabled="working">
                <SvgIcon name="quality" :size="14" />
                重新质检
              </button>
              <button v-if="showApprove" class="btn btn-sm" @click="approveReport" :disabled="working">
                <SvgIcon name="approve" :size="14" />
                审批
              </button>
              <button v-if="showReject" class="btn btn-sm" @click="rejectReport" :disabled="working">
                <SvgIcon name="reject" :size="14" />
                退回
              </button>
              <button v-if="showPublish" class="btn btn-sm btn-primary" @click="publishReport" :disabled="working">
                <SvgIcon name="publish" :size="14" />
                发布
              </button>
              <button v-if="isAdmin" class="btn btn-sm btn-danger" @click="deleteReport" :disabled="working">删除</button>
            </div>
          </div>

          <section class="quality-summary">
            <div>
              <span>质量分</span>
              <strong>{{ selectedReport.quality_score == null ? '未评分' : formatScore(selectedReport.quality_score) }}</strong>
            </div>
            <div>
              <span>质量摘要</span>
              <p>{{ selectedReport.quality_summary || '无质量摘要' }}</p>
            </div>
          </section>

          <div class="reader-grid">
            <nav class="outline">
              <strong>章节</strong>
              <button v-for="heading in headings" :key="heading.id" @click="scrollToHeading(heading.id)">
                {{ heading.text }}
              </button>
            </nav>
            <div ref="contentRef" class="markdown-body" v-html="renderedContent" @click="handleContentClick"></div>
          </div>
        </article>
      </main>

      <aside class="side-panel">
        <QualityIssueList :issues="qualityIssues" title="质量问题" @select="selectIssue" />
        <EvidencePanel :items="evidenceRefs" title="Report Evidence" :active-key="activeEvidenceKey" @select="selectEvidence" />
        <AuditTimeline :items="auditTrail" title="Audit" />
      </aside>
    </div>

    <div v-if="toast.show" :class="['toast', 'toast-' + toast.type]">{{ toast.message }}</div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { marked } from 'marked'
import { competitorApi, reportApi } from '../api'
import { hasRole } from '../auth'
import AuditTimeline from '../components/AuditTimeline.vue'
import EmptyState from '../components/EmptyState.vue'
import EvidencePanel from '../components/EvidencePanel.vue'
import LoadingState from '../components/LoadingState.vue'
import QualityIssueList from '../components/QualityIssueList.vue'
import StatusBadge from '../components/StatusBadge.vue'
import SvgIcon from '../components/icons/SvgIcon.vue'

const route = useRoute()
const router = useRouter()
const reports = ref([])
const competitors = ref([])
const selectedReport = ref(null)
const auditTrail = ref([])
const loadingList = ref(false)
const loadingContent = ref(false)
const generating = ref(false)
const working = ref(false)
const showGenerator = ref(false)
const contentRef = ref(null)
const activeEvidenceKey = ref('')
const toast = ref({ show: false, message: '', type: 'info' })
const filters = reactive({ report_type: '', status: '', review_status: '', min_quality: null, updated_from: '' })
const form = reactive({ selectedCompetitorId: '', competitor_ids: '', report_type: 'overview', focus: '' })

const canAnalyze = computed(() => hasRole('analyst'))
const isAdmin = computed(() => hasRole('admin'))
const evidenceRefs = computed(() => selectedReport.value?.evidence_refs || selectedReport.value?.source_refs || [])
const qualityIssues = computed(() => (selectedReport.value?.quality_reviews || []).flatMap((review) => review.issues || []))
const showApprove = computed(() => isAdmin.value && selectedReport.value?.status === 'waiting_review' && selectedReport.value?.review_status === 'passed')
const showReject = computed(() => isAdmin.value && selectedReport.value?.status === 'waiting_review')
const showPublish = computed(() => isAdmin.value && selectedReport.value?.status === 'approved' && selectedReport.value?.review_status === 'passed')
const filteredReports = computed(() => reports.value.filter((report) => {
  if (filters.review_status && report.review_status !== filters.review_status) return false
  if (filters.min_quality !== null && filters.min_quality !== '' && Number(report.quality_score ?? -1) < Number(filters.min_quality)) return false
  if (filters.updated_from) {
    const ts = new Date(report.updated_at || report.created_at || 0).getTime()
    if (!Number.isFinite(ts) || ts < new Date(filters.updated_from).getTime()) return false
  }
  return true
}))
const renderedContent = computed(() => {
  const content = selectedReport.value?.content || ''
  return marked(content, { mangle: false, headerIds: true })
})
const headings = computed(() => {
  const content = selectedReport.value?.content || ''
  return [...content.matchAll(/^#{1,3}\s+(.+)$/gm)].map((match, index) => ({
    id: `heading-${index}`,
    text: match[1].replace(/[#`]/g, '').trim(),
  })).slice(0, 12)
})

function showToast(message, type = 'info') {
  toast.value = { show: true, message, type }
  setTimeout(() => { toast.value.show = false }, 3000)
}

function syncFiltersFromRoute() {
  Object.assign(filters, {
    report_type: route.query.report_type || '',
    status: route.query.status || '',
    review_status: route.query.review_status || '',
    min_quality: route.query.min_quality || null,
    updated_from: route.query.updated_from || '',
  })
}

function applyFilters() {
  const query = Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== '' && value !== null))
  if (selectedReport.value?.id) query.report_id = selectedReport.value.id
  router.replace({ path: '/reports', query })
  fetchReports()
}

async function fetchReports() {
  loadingList.value = true
  try {
    const params = Object.fromEntries(Object.entries({
      report_type: filters.report_type,
      status: filters.status,
      limit: 50,
    }).filter(([, value]) => value))
    const res = await reportApi.list(params)
    reports.value = res.data.reports || []
    const reportId = Number(route.query.report_id)
    if (reportId) await loadReport(reportId)
    else if (!selectedReport.value && reports.value.length) await loadReport(reports.value[0].id)
  } catch (e) {
    showToast(e.response?.data?.detail || e.message || '加载报告列表失败', 'error')
  } finally {
    loadingList.value = false
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

async function loadReport(id) {
  loadingContent.value = true
  try {
    const [detail, audit] = await Promise.all([reportApi.get(id), reportApi.getAudit(id)])
    selectedReport.value = detail.data
    auditTrail.value = audit.data.audit_trail || []
    activeEvidenceKey.value = ''
    await nextTick()
    tagHeadings()
    router.replace({ path: '/reports', query: { ...route.query, report_id: id } })
  } catch (e) {
    showToast(e.response?.data?.detail || e.message || '加载报告失败', 'error')
  } finally {
    loadingContent.value = false
  }
}

function parseCompetitorIds() {
  const selected = form.selectedCompetitorId ? [Number(form.selectedCompetitorId)] : []
  const manual = form.competitor_ids.split(',').map((item) => Number(item.trim())).filter((item) => Number.isInteger(item) && item > 0)
  return [...new Set([...selected, ...manual])]
}

async function generateReport() {
  const competitorIds = parseCompetitorIds()
  if (!competitorIds.length) return showToast('请选择或填写有效竞品 ID', 'error')
  generating.value = true
  try {
    const res = await reportApi.generate({ competitor_ids: competitorIds, report_type: form.report_type, focus: form.focus })
    showToast('报告生成完成', 'success')
    await fetchReports()
    if (res.data.report_id) await loadReport(res.data.report_id)
  } catch (e) {
    showToast(e.response?.data?.detail || e.message || '报告生成失败', 'error')
  } finally {
    generating.value = false
  }
}

async function runReportAction(action, message, clearSelection = false) {
  if (!selectedReport.value?.id) return
  const id = selectedReport.value.id
  working.value = true
  try {
    await action()
    showToast(message, 'success')
    if (clearSelection) selectedReport.value = null
    else await loadReport(id)
    await fetchReports()
  } catch (e) {
    showToast(e.response?.data?.detail || e.message || '操作失败', 'error')
  } finally {
    working.value = false
  }
}

function reviewQuality() { return runReportAction(() => reportApi.reviewQuality(selectedReport.value.id), '质量门禁已重新运行') }
function approveReport() { return runReportAction(() => reportApi.approve(selectedReport.value.id), '报告已审批') }
function rejectReport() { return runReportAction(() => reportApi.reject(selectedReport.value.id, window.prompt('退回原因（可选）') || ''), '报告已退回修订') }
function publishReport() { return runReportAction(() => reportApi.publish(selectedReport.value.id), '报告已发布') }
function deleteReport() {
  if (!window.confirm('确定删除这份报告？')) return
  return runReportAction(() => reportApi.delete(selectedReport.value.id), '报告已删除', true)
}

function selectEvidence(item) {
  activeEvidenceKey.value = String(item.id || item.evidence_ref_id || item.citation_label || item.url || '')
}

function selectIssue(issue) {
  const key = issue.evidence_ref_id || issue.evidence_ref || issue.citation_label
  if (key) activeEvidenceKey.value = String(key)
  if (issue.section_key) scrollToSectionText(issue.section_key)
}

function handleContentClick(event) {
  const text = event.target?.textContent || ''
  const match = text.match(/\[[A-Za-z0-9_-]+\]/)
  if (!match) return
  const label = match[0].slice(1, -1)
  const evidence = evidenceRefs.value.find((item) => item.citation_label === label || item.evidence_ref_id === label)
  if (evidence) selectEvidence(evidence)
}

function tagHeadings() {
  if (!contentRef.value) return
  contentRef.value.querySelectorAll('h1,h2,h3').forEach((node, index) => {
    node.id = `heading-${index}`
  })
}

function scrollToHeading(id) {
  contentRef.value?.querySelector(`#${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function scrollToSectionText(text) {
  const target = [...(contentRef.value?.querySelectorAll('h1,h2,h3') || [])].find((node) => node.textContent?.includes(text))
  target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function formatScore(score) { return `${Math.round(Number(score) * 100)}` }
function formatTime(value) {
  if (!value) return '未知'
  try { return new Date(value).toLocaleString('zh-CN') } catch { return String(value) }
}

watch(() => route.query, syncFiltersFromRoute, { deep: true })
onMounted(async () => {
  syncFiltersFromRoute()
  await Promise.all([fetchCompetitors(), fetchReports()])
})
</script>

<style scoped>
.report-view {
  max-width: 1600px;
  margin: 0 auto;
  padding: var(--space-lg);
}
.page-header,
.header-actions,
.badge-line,
.actions {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}
.page-header {
  justify-content: space-between;
  margin-bottom: var(--space-lg);
}
.header-actions,
.actions {
  flex-wrap: wrap;
  justify-content: flex-end;
}
.generator-panel,
.report-list,
.report-reader,
.side-panel,
.quality-summary {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-card);
}
.generator-panel {
  padding: var(--space-md);
  margin-bottom: var(--space-md);
}
.generator-grid,
.filters {
  display: grid;
  gap: var(--space-sm);
}
.generator-grid {
  grid-template-columns: 200px 220px 160px minmax(220px, 1fr) auto;
  align-items: end;
}
.generator-grid label span {
  display: block;
  margin-bottom: 4px;
  color: var(--text-muted);
  font-size: 0.8125rem;
}
.filters {
  grid-template-columns: 170px 190px 190px 150px 160px;
  margin-bottom: var(--space-md);
}
.report-workbench {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr) 340px;
  gap: var(--space-lg);
}
.report-list,
.report-reader,
.side-panel {
  min-width: 0;
  padding: var(--space-md);
}
.report-list,
.side-panel {
  max-height: calc(100vh - 220px);
  overflow: auto;
}
.side-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}
.report-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
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
.report-item:hover,
.report-item.active {
  border-color: var(--accent-primary);
}
.report-item small,
.badge-line span {
  color: var(--text-muted);
  font-size: 0.8125rem;
}
.content-header {
  display: flex;
  justify-content: space-between;
  gap: var(--space-md);
  margin-bottom: var(--space-md);
}
.content-header h2 {
  margin-bottom: var(--space-xs);
  font-size: 1.25rem;
}
.quality-summary {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: var(--space-md);
  padding: var(--space-md);
  margin-bottom: var(--space-md);
}
.quality-summary span,
.quality-summary p {
  color: var(--text-muted);
}
.reader-grid {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: var(--space-md);
}
.outline {
  position: sticky;
  top: var(--space-md);
  align-self: start;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: var(--space-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
}
.outline strong {
  margin-bottom: 4px;
}
.outline button {
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  text-align: left;
  cursor: pointer;
}
.outline button:hover {
  color: var(--accent-primary);
}
.markdown-body {
  min-width: 0;
  line-height: 1.75;
}
@media (max-width: 1180px) {
  .report-workbench,
  .reader-grid {
    grid-template-columns: 1fr;
  }
  .report-list,
  .side-panel {
    max-height: none;
  }
}
@media (max-width: 760px) {
  .report-view {
    padding: var(--space-sm);
  }
  .page-header,
  .content-header,
  .quality-summary {
    flex-direction: column;
    align-items: stretch;
  }
  .generator-grid,
  .filters,
  .quality-summary {
    grid-template-columns: 1fr;
  }
}
</style>
