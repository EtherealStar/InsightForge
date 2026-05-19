<template>
  <div class="page-container">
    <header class="page-header">
      <h1><SvgIcon name="competitor" :size="24" /> 竞品管理</h1>
      <div v-if="canAnalyze" class="header-actions">
        <button class="btn btn-secondary" @click="autoLink" :disabled="linking">
          <SvgIcon name="link" :size="16" />
          {{ linking ? '关联中...' : '自动关联情报' }}
        </button>
        <button class="btn btn-primary" @click="showAddModal = true">
          <SvgIcon name="plus" :size="16" />
          添加竞品
        </button>
      </div>
    </header>

    <!-- 竞品列表 -->
    <div class="competitors-grid">
      <div v-if="loading" class="loading-state">加载中...</div>
      <div v-else-if="competitors.length === 0" class="empty-state">
        <p>暂无竞品记录，点击"添加竞品"开始监控。</p>
      </div>
      <div
        v-for="comp in competitors"
        :key="comp.id"
        class="competitor-card"
        :class="{ selected: selectedId === comp.id }"
        @click="selectCompetitor(comp.id)"
      >
        <div class="card-header">
          <h3>{{ comp.name }}</h3>
          <StatusBadge kind="fact" :status="comp.status" :label="comp.status" />
        </div>
        <p class="card-industry">{{ comp.industry || '未设置行业' }}</p>
        <p class="card-desc">{{ comp.description || '暂无描述' }}</p>
        <div class="card-tags" v-if="comp.tags?.length">
          <span class="tag" v-for="tag in comp.tags" :key="tag">{{ tag }}</span>
        </div>
        <div class="card-footer">
          <span class="card-meta">别名: {{ comp.aliases?.join(', ') || '无' }}</span>
          <div v-if="canAnalyze" class="card-actions">
            <button class="btn-icon" @click.stop="editCompetitor(comp)" title="编辑">
              <SvgIcon name="edit" :size="16" />
            </button>
            <button v-if="isAdmin" class="btn-icon danger" @click.stop="deleteCompetitor(comp.id)" title="删除">
              <SvgIcon name="delete" :size="16" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 竞品详情面板 -->
    <div v-if="detail" class="detail-panel">
      <div class="detail-header">
        <h2>{{ detail.competitor.name }}</h2>
        <a v-if="detail.competitor.website" :href="detail.competitor.website" target="_blank" class="website-link">
          <SvgIcon name="external" :size="14" />
          {{ detail.competitor.website }}
        </a>
      </div>

      <div class="detail-stats">
        <div class="stat-card">
          <span class="stat-number">{{ detail.products?.length || 0 }}</span>
          <span class="stat-label">产品线</span>
        </div>
        <div class="stat-card">
          <span class="stat-number">{{ detail.fact_count || facts.length || 0 }}</span>
          <span class="stat-label">关联 facts</span>
        </div>
      </div>

      <!-- 产品线 -->
      <div class="section">
        <div class="section-header">
          <h3>产品线</h3>
          <button v-if="canAnalyze" class="btn btn-sm" @click="showProductModal = true">
            <SvgIcon name="plus" :size="14" />
            添加
          </button>
        </div>
        <div v-if="detail.products?.length" class="products-list">
          <div v-for="p in detail.products" :key="p.id" class="product-item">
            <div class="product-info">
              <strong>{{ p.name }}</strong>
              <span v-if="p.category" class="product-category">{{ p.category }}</span>
            </div>
            <p v-if="p.description">{{ p.description }}</p>
            <p v-if="p.pricing_info" class="pricing">定价: {{ p.pricing_info }}</p>
            <button v-if="isAdmin" class="btn-icon danger btn-sm" @click="deleteProduct(p.id)">
              <SvgIcon name="delete" :size="14" />
            </button>
          </div>
        </div>
        <p v-else class="empty-hint">暂无产品线记录</p>
      </div>

      <div class="section">
        <div class="section-header">
          <h3>结构化 facts</h3>
          <div class="section-actions">
            <button class="btn btn-sm" @click="goIntel({ competitor_id: selectedId })">筛选 Intel</button>
            <button class="btn btn-sm" @click="loadFacts(selectedId)">刷新</button>
          </div>
        </div>
        <div class="aggregate-grid">
          <div v-for="item in aggregateItems" :key="item.key" class="aggregate-item">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
        <div v-if="facts.length" class="facts-list">
          <div v-for="fact in facts" :key="fact.id" class="fact-item clickable" @click="goIntel({ competitor_id: selectedId, fact_type: fact.fact_type, dimension: fact.dimension })">
            <strong>{{ fact.fact_text }}</strong>
            <div class="fact-meta">
              <span>{{ fact.fact_type }}</span>
              <span>{{ fact.dimension }}</span>
              <span>{{ fact.status }}</span>
              <span>evidence {{ fact.evidence_refs?.length || 0 }}</span>
            </div>
          </div>
        </div>
        <p v-else class="empty-hint">暂无关联 facts</p>
      </div>

      <div class="section">
        <div class="section-header">
          <h3>事件时间线</h3>
          <button class="btn btn-sm" @click="loadTimeline(selectedId)">刷新</button>
        </div>
        <div v-if="timeline.length" class="facts-list">
          <div v-for="fact in timeline" :key="fact.id" class="fact-item clickable" @click="goIntel({ competitor_id: selectedId, date_from: fact.event_date, date_to: fact.event_date })">
            <span class="timeline-date">{{ fact.event_date || fact.observed_at || '未标注日期' }}</span>
            <strong>{{ fact.fact_text }}</strong>
          </div>
        </div>
        <p v-else class="empty-hint">暂无事件时间线</p>
      </div>
    </div>

    <!-- 添加竞品 Modal -->
    <div v-if="showAddModal" class="modal-overlay" @click.self="showAddModal = false">
      <div class="modal">
        <h3>{{ editingComp ? '编辑竞品' : '添加竞品' }}</h3>
        <div class="form-group">
          <label>名称 *</label>
          <input v-model="form.name" placeholder="如 Cursor" />
        </div>
        <div class="form-group">
          <label>别名（逗号分隔）</label>
          <input v-model="form.aliasesStr" placeholder="如 Cursor IDE, cursor.com" />
        </div>
        <div class="form-group">
          <label>官网</label>
          <input v-model="form.website" placeholder="https://..." />
        </div>
        <div class="form-group">
          <label>行业</label>
          <input v-model="form.industry" placeholder="如 AI 编程工具" />
        </div>
        <div class="form-group">
          <label>简介</label>
          <textarea v-model="form.description" rows="2" placeholder="一句话描述"></textarea>
        </div>
        <div class="form-group">
          <label>标签（逗号分隔）</label>
          <input v-model="form.tagsStr" placeholder="如 AI, IDE, 编程" />
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showAddModal = false; editingComp = null">取消</button>
          <button class="btn btn-primary" @click="saveCompetitor" :disabled="!form.name">
            {{ editingComp ? '保存' : '创建' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 添加产品 Modal -->
    <div v-if="showProductModal" class="modal-overlay" @click.self="showProductModal = false">
      <div class="modal">
        <h3>添加产品线</h3>
        <div class="form-group">
          <label>产品名称 *</label>
          <input v-model="productForm.name" placeholder="如 Cursor Pro" />
        </div>
        <div class="form-group">
          <label>类别</label>
          <input v-model="productForm.category" placeholder="如 独立 IDE" />
        </div>
        <div class="form-group">
          <label>定价信息</label>
          <input v-model="productForm.pricing_info" placeholder="如 $20/月" />
        </div>
        <div class="form-group">
          <label>描述</label>
          <textarea v-model="productForm.description" rows="2"></textarea>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showProductModal = false">取消</button>
          <button class="btn btn-primary" @click="addProduct" :disabled="!productForm.name">添加</button>
        </div>
      </div>
    </div>

    <!-- Toast 通知 -->
    <div v-if="toast" class="toast" :class="toast.type">{{ toast.message }}</div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { competitorApi } from '../api/index.ts'
import { hasRole } from '../auth'
import StatusBadge from '../components/StatusBadge.vue'
import SvgIcon from '../components/icons/SvgIcon.vue'

const loading = ref(false)
const router = useRouter()
const linking = ref(false)
const canAnalyze = computed(() => hasRole('analyst'))
const isAdmin = computed(() => hasRole('admin'))
const competitors = ref([])
const selectedId = ref(null)
const detail = ref(null)
const facts = ref([])
const timeline = ref([])
const aggregates = ref({})
const showAddModal = ref(false)
const showProductModal = ref(false)
const editingComp = ref(null)
const toast = ref(null)

const form = reactive({
  name: '', aliasesStr: '', website: '', industry: '',
  description: '', tagsStr: '',
})

const productForm = reactive({
  name: '', category: '', pricing_info: '', description: '',
})

function showToast(message, type = 'success') {
  toast.value = { message, type }
  setTimeout(() => { toast.value = null }, 3000)
}

async function loadCompetitors() {
  loading.value = true
  try {
    const res = await competitorApi.list()
    competitors.value = res.data.competitors || []
  } catch (e) {
    showToast('加载竞品失败', 'error')
  } finally {
    loading.value = false
  }
}

async function selectCompetitor(id) {
  selectedId.value = id
  try {
    const res = await competitorApi.get(id)
    detail.value = res.data
    await Promise.all([loadFacts(id), loadTimeline(id)])
  } catch {
    showToast('加载详情失败', 'error')
  }
}

async function loadFacts(id) {
  if (!id) return
  const res = await competitorApi.getFacts(id, { limit: 20 })
  facts.value = res.data.facts || []
  aggregates.value = res.data.aggregates || buildAggregates(facts.value)
}

async function loadTimeline(id) {
  if (!id) return
  const res = await competitorApi.getTimeline(id, { limit: 20 })
  timeline.value = res.data.timeline || []
}

function editCompetitor(comp) {
  editingComp.value = comp
  form.name = comp.name
  form.aliasesStr = (comp.aliases || []).join(', ')
  form.website = comp.website || ''
  form.industry = comp.industry || ''
  form.description = comp.description || ''
  form.tagsStr = (comp.tags || []).join(', ')
  showAddModal.value = true
}

async function saveCompetitor() {
  const data = {
    name: form.name,
    aliases: form.aliasesStr.split(',').map(s => s.trim()).filter(Boolean),
    website: form.website,
    industry: form.industry,
    description: form.description,
    tags: form.tagsStr.split(',').map(s => s.trim()).filter(Boolean),
  }
  try {
    if (editingComp.value) {
      await competitorApi.update(editingComp.value.id, data)
      showToast('竞品已更新')
    } else {
      await competitorApi.create(data)
      showToast('竞品已创建')
    }
    showAddModal.value = false
    editingComp.value = null
    Object.assign(form, { name: '', aliasesStr: '', website: '', industry: '', description: '', tagsStr: '' })
    await loadCompetitors()
  } catch (e) {
    showToast(e.response?.data?.detail || '操作失败', 'error')
  }
}

async function deleteCompetitor(id) {
  if (!confirm('确定删除此竞品？')) return
  try {
    await competitorApi.delete(id)
    showToast('竞品已删除')
    if (selectedId.value === id) {
      selectedId.value = null
      detail.value = null
      facts.value = []
      timeline.value = []
    }
    await loadCompetitors()
  } catch {
    showToast('删除失败', 'error')
  }
}

async function addProduct() {
  if (!selectedId.value) return
  try {
    await competitorApi.addProduct(selectedId.value, { ...productForm })
    showProductModal.value = false
    Object.assign(productForm, { name: '', category: '', pricing_info: '', description: '' })
    showToast('产品已添加')
    await selectCompetitor(selectedId.value)
  } catch {
    showToast('添加失败', 'error')
  }
}

async function deleteProduct(productId) {
  if (!confirm('确定删除此产品？')) return
  try {
    await competitorApi.deleteProduct(productId)
    showToast('产品已删除')
    await selectCompetitor(selectedId.value)
  } catch {
    showToast('删除失败', 'error')
  }
}

async function autoLink() {
  linking.value = true
  try {
    const res = await competitorApi.autoLink()
    showToast(`关联完成：${res.data.linked} 条新关联`)
    if (selectedId.value) await selectCompetitor(selectedId.value)
  } catch {
    showToast('自动关联失败', 'error')
  } finally {
    linking.value = false
  }
}

const aggregateItems = computed(() => {
  const byDimension = aggregates.value.by_dimension || aggregates.value.dimensions || {}
  const byType = aggregates.value.by_fact_type || aggregates.value.by_type || {}
  const byStatus = aggregates.value.by_status || {}
  return [
    { key: 'facts', label: 'facts', value: facts.value.length },
    { key: 'dimensions', label: '维度覆盖', value: Object.keys(byDimension).length },
    { key: 'types', label: '类型覆盖', value: Object.keys(byType).length },
    { key: 'active', label: 'active', value: byStatus.active || facts.value.filter(f => f.status === 'active').length },
  ]
})

function buildAggregates(items) {
  const result = { by_dimension: {}, by_fact_type: {}, by_status: {} }
  for (const fact of items || []) {
    result.by_dimension[fact.dimension || 'general'] = (result.by_dimension[fact.dimension || 'general'] || 0) + 1
    result.by_fact_type[fact.fact_type || 'general'] = (result.by_fact_type[fact.fact_type || 'general'] || 0) + 1
    result.by_status[fact.status || 'unknown'] = (result.by_status[fact.status || 'unknown'] || 0) + 1
  }
  return result
}

function goIntel(query) {
  const clean = Object.fromEntries(Object.entries(query).filter(([, value]) => value !== undefined && value !== null && value !== ''))
  router.push({ path: '/intel', query: clean })
}

onMounted(loadCompetitors)
</script>

<style scoped>
.page-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--space-lg);
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-lg);
}
.page-header h1 {
  font-size: 1.5rem;
  font-weight: 700;
}
.header-actions {
  display: flex;
  gap: var(--space-sm);
}

/* Card Grid */
.competitors-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}
.competitor-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-md);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.competitor-card:hover {
  border-color: var(--accent-primary);
  box-shadow: 0 4px 20px rgba(99, 102, 241, 0.1);
}
.competitor-card.selected {
  border-color: var(--accent-primary);
  background: var(--accent-glow);
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-xs);
}
.card-header h3 {
  font-size: 1.1rem;
  font-weight: 600;
}
.card-industry {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin-bottom: var(--space-xs);
}
.card-desc {
  font-size: 0.9rem;
  color: var(--text-secondary);
  margin-bottom: var(--space-sm);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: var(--space-sm);
}
.tag {
  font-size: 0.75rem;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--bg-glass);
  color: var(--text-secondary);
}
.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.8rem;
  color: var(--text-muted);
}
.card-actions {
  display: flex;
  gap: 4px;
}

/* Detail Panel */
.detail-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-lg);
}
.detail-header {
  margin-bottom: var(--space-md);
}
.detail-header h2 {
  font-size: 1.3rem;
  font-weight: 700;
}
.website-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.85rem;
  color: var(--accent-primary);
  text-decoration: none;
}
.detail-stats {
  display: flex;
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}
.stat-card {
  background: var(--bg-glass);
  padding: var(--space-md);
  border-radius: var(--radius-sm);
  text-align: center;
  flex: 1;
}
.stat-number {
  display: block;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--accent-primary);
}
.stat-label {
  font-size: 0.85rem;
  color: var(--text-muted);
}
.section {
  margin-top: var(--space-lg);
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-sm);
}
.section-actions {
  display: flex;
  gap: var(--space-xs);
  flex-wrap: wrap;
}
.section-header h3 {
  font-size: 1.1rem;
  font-weight: 600;
}
.products-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}
.facts-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}
.fact-item {
  background: var(--bg-glass);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-sm);
}
.fact-item.clickable {
  cursor: pointer;
}
.fact-item.clickable:hover {
  outline: 1px solid var(--accent-primary);
}
.aggregate-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-sm);
  margin-bottom: var(--space-md);
}
.aggregate-item {
  padding: var(--space-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
}
.aggregate-item span,
.aggregate-item strong {
  display: block;
}
.aggregate-item span {
  color: var(--text-muted);
  font-size: 0.75rem;
}
.fact-item strong {
  display: block;
  margin-bottom: 4px;
  line-height: 1.45;
}
.fact-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
  color: var(--text-muted);
  font-size: 0.78rem;
}
.timeline-date {
  display: block;
  color: var(--accent-primary);
  font-size: 0.8rem;
  margin-bottom: 4px;
}
.product-item {
  background: var(--bg-glass);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-sm);
  display: flex;
  flex-direction: column;
  gap: 4px;
  position: relative;
}
.product-info {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}
.product-category {
  font-size: 0.75rem;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--accent-glow);
  color: var(--accent-primary);
}
.pricing {
  font-size: 0.85rem;
  color: var(--warning);
}
.product-item .btn-icon {
  position: absolute;
  top: var(--space-sm);
  right: var(--space-sm);
  opacity: 0;
  transition: opacity var(--transition-fast);
}
.product-item:hover .btn-icon {
  opacity: 1;
}
.empty-hint {
  color: var(--text-muted);
  font-size: 0.9rem;
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-lg);
  width: 480px;
  max-width: 90vw;
}
.modal h3 {
  margin-bottom: var(--space-md);
  font-size: 1.1rem;
}
.form-group {
  margin-bottom: var(--space-sm);
}
.form-group label {
  display: block;
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-bottom: 4px;
}
.form-group input,
.form-group textarea {
  width: 100%;
  padding: var(--space-sm);
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 0.9rem;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
  margin-top: var(--space-md);
}

/* Toast */
.toast {
  position: fixed;
  bottom: var(--space-lg);
  right: var(--space-lg);
  padding: var(--space-sm) var(--space-lg);
  border-radius: var(--radius-sm);
  font-size: 0.9rem;
  z-index: 2000;
  animation: fadeInUp 0.3s ease;
}
.toast.success {
  background: var(--success);
  color: white;
}
.toast.error {
  background: var(--error);
  color: white;
}
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.loading-state, .empty-state {
  grid-column: 1 / -1;
  text-align: center;
  padding: var(--space-xl);
  color: var(--text-muted);
}
</style>
