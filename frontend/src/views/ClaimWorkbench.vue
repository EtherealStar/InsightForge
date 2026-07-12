<template>
  <div class="v2-workbench">
    <header class="page-header">
      <div>
        <h1><SvgIcon name="intel" :size="24" /> 三层结构化情报工作台</h1>
        <p class="subtitle">
          事实、原文锚点与分析结论。Lifecycle / Verification / Maturity 都是离散状态，不显示综合分数。
        </p>
      </div>
      <div class="actions">
        <button class="btn btn-primary" @click="showCreateFact = true">新建 Draft Fact</button>
      </div>
    </header>

    <nav class="tabs">
      <button :class="{ active: activeTab === 'facts' }" @click="activeTab = 'facts'">
        Facts ({{ factTotal }})
      </button>
      <button :class="{ active: activeTab === 'claims' }" @click="activeTab = 'claims'">
        Claims ({{ claimTotal }})
      </button>
    </nav>

    <section v-if="activeTab === 'facts'" class="panel">
      <div class="filters">
        <input v-model="factFilters.keyword" class="input" placeholder="按 fact_text 过滤" @keyup.enter="loadFacts" />
        <select v-model="factFilters.lifecycle_status" class="input" @change="loadFacts">
          <option value="">全部 Lifecycle</option>
          <option value="draft">draft</option>
          <option value="active">active</option>
          <option value="superseded">superseded</option>
          <option value="retracted">retracted</option>
          <option value="rejected">rejected</option>
        </select>
        <select v-model="factFilters.verification_status" class="input" @change="loadFacts">
          <option value="">全部 Verification</option>
          <option value="single_source">single_source</option>
          <option value="self_reported">self_reported</option>
          <option value="corroborated">corroborated</option>
          <option value="disputed">disputed</option>
        </select>
        <select v-model="factFilters.fact_type" class="input" @change="loadFacts">
          <option value="">全部类型</option>
          <option v-for="t in factTypes" :key="t" :value="t">{{ t }}</option>
        </select>
        <button class="btn" @click="loadFacts">查询</button>
      </div>

      <LoadingState v-if="loadingFacts" message="加载 facts..." />
      <EmptyState v-else-if="!facts.length" icon="intel" message="暂无事实" />
      <table v-else class="data-table">
        <thead>
          <tr>
            <th>类型</th>
            <th>事实</th>
            <th>Lifecycle</th>
            <th>Verification</th>
            <th>状态理由</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in facts" :key="row.id">
            <td><code>{{ row.fact_type }}</code></td>
            <td>{{ row.fact_text }}</td>
            <td><StatusBadge :kind="'fact'" :status="row.lifecycle_status" /></td>
            <td><StatusBadge :kind="'fact'" :status="row.verification_status" /></td>
            <td class="reason">{{ row.status_reason || '—' }}</td>
            <td class="actions">
              <button v-if="row.lifecycle_status === 'draft'" class="btn btn-primary btn-sm" @click="activateFact(row.id)">
                激活
              </button>
              <button v-if="row.lifecycle_status === 'active'" class="btn btn-danger btn-sm" @click="retractFact(row.id)">
                撤回
              </button>
              <button class="btn btn-sm" @click="viewFact(row)">详情</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="activeTab === 'claims'" class="panel">
      <div class="filters">
        <select v-model="claimFilters.maturity" class="input" @change="loadClaims">
          <option value="">全部 Maturity</option>
          <option value="draft">draft</option>
          <option value="hypothesis">hypothesis</option>
          <option value="supported">supported</option>
          <option value="needs_review">needs_review</option>
          <option value="disputed">disputed</option>
          <option value="superseded">superseded</option>
        </select>
        <button class="btn" @click="loadClaims">查询</button>
      </div>

      <LoadingState v-if="loadingClaims" message="加载 claims..." />
      <EmptyState v-else-if="!claims.length" icon="intel" message="暂无结论" />
      <table v-else class="data-table">
        <thead>
          <tr>
            <th>结论</th>
            <th>标签</th>
            <th>Maturity</th>
            <th>状态理由</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in claims" :key="row.id">
            <td>{{ row.claim_text }}</td>
            <td>
              <span v-for="tag in row.tags" :key="tag" class="tag">{{ tag }}</span>
            </td>
            <td><StatusBadge :kind="'claim'" :status="row.maturity" /></td>
            <td class="reason">{{ row.status_reason || '—' }}</td>
            <td class="actions">
              <button
                v-if="row.maturity === 'hypothesis' || row.maturity === 'draft'"
                class="btn btn-primary btn-sm"
                @click="approveClaim(row.id)"
              >
                Approve
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <div v-if="showCreateFact" class="modal-backdrop" @click.self="showCreateFact = false">
      <div class="modal">
        <h3>新建 Draft Fact</h3>
        <label>Fact Type
          <select v-model="newFact.fact_type" class="input">
            <option v-for="t in factTypes" :key="t" :value="t">{{ t }}</option>
          </select>
        </label>
        <label>Fact Text
          <textarea v-model="newFact.fact_text" class="input" rows="3"></textarea>
        </label>
        <label>Time Precision
          <select v-model="newFact.time_precision" class="input">
            <option value="">未知 / 未指定</option>
            <option value="day">day</option>
            <option value="month">month</option>
            <option value="quarter">quarter</option>
            <option value="unknown">unknown</option>
          </select>
        </label>
        <label>Candidate Key
          <input v-model="newFact.candidate_key" class="input" placeholder="可选；用于候选召回" />
        </label>
        <div class="modal-actions">
          <button class="btn" @click="showCreateFact = false">取消</button>
          <button class="btn btn-primary" @click="createFact">保存</button>
        </div>
      </div>
    </div>

    <div v-if="showFactDetail" class="modal-backdrop" @click.self="showFactDetail = false">
      <div class="modal wide">
        <h3>Fact {{ currentFact?.id }}</h3>
        <p><strong>Fact Text:</strong> {{ currentFact?.fact_text }}</p>
        <p><strong>Lifecycle:</strong> {{ currentFact?.lifecycle_status }}</p>
        <p><strong>Verification:</strong> {{ currentFact?.verification_status }}</p>
        <p><strong>Status Reason:</strong> {{ currentFact?.status_reason || '—' }}</p>
        <pre v-if="currentFact?.normalized_data">{{ currentFact.normalized_data }}</pre>
        <div class="modal-actions">
          <button class="btn" @click="showFactDetail = false">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { intelligenceV2Api } from '../api'
import SvgIcon from '../components/icons/SvgIcon.vue'
import StatusBadge from '../components/StatusBadge.vue'
import LoadingState from '../components/LoadingState.vue'
import EmptyState from '../components/EmptyState.vue'

const factTypes = [
  'product', 'commercial', 'corporate', 'ecosystem',
  'customer_market', 'risk', 'general',
]

const activeTab = ref('facts')

const facts = ref<any[]>([])
const factTotal = ref(0)
const loadingFacts = ref(false)
const factFilters = reactive<any>({
  keyword: '',
  lifecycle_status: '',
  verification_status: '',
  fact_type: '',
})

const claims = ref<any[]>([])
const claimTotal = ref(0)
const loadingClaims = ref(false)
const claimFilters = reactive<any>({ maturity: '' })

const showCreateFact = ref(false)
const showFactDetail = ref(false)
const currentFact = ref<any>(null)
const newFact = reactive({
  fact_type: 'general',
  fact_text: '',
  time_precision: '',
  candidate_key: '',
})

async function loadFacts() {
  loadingFacts.value = true
  try {
    const params: any = { limit: 50 }
    Object.entries(factFilters).forEach(([k, v]) => {
      if (v) params[k] = v
    })
    const resp = await intelligenceV2Api.listFacts(params)
    facts.value = resp.data.items
    factTotal.value = resp.data.items.length
  } finally {
    loadingFacts.value = false
  }
}

async function loadClaims() {
  loadingClaims.value = true
  try {
    const params: any = { limit: 50 }
    if (claimFilters.maturity) params.maturity = claimFilters.maturity
    const resp = await intelligenceV2Api.listClaims(params)
    claims.value = resp.data.items
    claimTotal.value = resp.data.items.length
  } finally {
    loadingClaims.value = false
  }
}

async function createFact() {
  if (!newFact.fact_text.trim()) {
    alert('fact_text 不能为空')
    return
  }
  await intelligenceV2Api.createFact({ ...newFact })
  showCreateFact.value = false
  newFact.fact_text = ''
  await loadFacts()
}

async function activateFact(id: string) {
  const resp = await intelligenceV2Api.activateFact(id)
  if (resp.data.is_active) {
    alert('已激活')
  } else {
    alert(`未激活：${resp.data.status_reason}`)
  }
  await loadFacts()
}

async function retractFact(id: string) {
  const reason = prompt('请填写撤回理由')
  if (!reason) return
  await intelligenceV2Api.retractFact(id, reason)
  alert('已撤回')
  await loadFacts()
}

async function viewFact(row: any) {
  const resp = await intelligenceV2Api.getFact(row.id)
  currentFact.value = resp.data
  showFactDetail.value = true
}

async function approveClaim(id: string) {
  const approvedBy = prompt('批准人 (analyst/admin)')
  if (!approvedBy || approvedBy === 'agent' || approvedBy === 'system') {
    alert('批准人不能是 agent 或 system')
    return
  }
  await intelligenceV2Api.approveClaim(id, approvedBy)
  alert('已批准')
  await loadClaims()
}

onMounted(async () => {
  await loadFacts()
  await loadClaims()
})
</script>

<style scoped>
.v2-workbench { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.page-header h1 { margin: 0; }
.subtitle { color: #6b7280; font-size: 13px; margin: 4px 0 0; }
.tabs { display: flex; gap: 4px; border-bottom: 1px solid #e5e7eb; margin-bottom: 16px; }
.tabs button { padding: 8px 16px; background: transparent; border: none; cursor: pointer; }
.tabs button.active { border-bottom: 2px solid #2563eb; color: #2563eb; font-weight: 600; }
.filters { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 12px; }
.input { padding: 6px 10px; border: 1px solid #d1d5db; border-radius: 6px; background: white; }
.btn { padding: 6px 12px; border: 1px solid #d1d5db; background: white; border-radius: 6px; cursor: pointer; }
.btn-primary { background: #2563eb; color: white; border-color: #2563eb; }
.btn-danger { background: #dc2626; color: white; border-color: #dc2626; }
.btn-sm { padding: 4px 8px; font-size: 12px; }
.data-table { width: 100%; border-collapse: collapse; }
.data-table th, .data-table td { padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: left; font-size: 13px; }
.data-table th { background: #f9fafb; font-weight: 600; }
.reason { color: #b45309; font-size: 12px; }
.tag { display: inline-block; margin-right: 4px; padding: 2px 6px; background: #eef2ff; color: #4338ca; border-radius: 4px; font-size: 11px; }
.actions { display: flex; gap: 6px; }
.modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal { background: white; padding: 24px; border-radius: 8px; min-width: 480px; max-width: 600px; }
.modal.wide { max-width: 720px; }
.modal h3 { margin-top: 0; }
.modal label { display: block; margin-bottom: 12px; font-size: 13px; }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
pre { background: #f3f4f6; padding: 8px; border-radius: 4px; overflow-x: auto; }
</style>