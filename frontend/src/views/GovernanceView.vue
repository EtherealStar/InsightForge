<template>
  <main class="page-container governance-view">
    <header class="page-header">
      <h1><SvgIcon name="settings" :size="24" /> 来源治理</h1>
      <div class="header-actions">
        <select v-model="tierFilter" @change="loadSources">
          <option value="">全部等级</option>
          <option v-for="tier in tiers" :key="tier" :value="tier">{{ tier }}</option>
        </select>
        <button class="btn btn-secondary" :disabled="loading" @click="loadSources">
          <SvgIcon name="refresh" :size="16" /> 刷新
        </button>
      </div>
    </header>

    <div class="summary-band">
      <div><strong>{{ sources.length }}</strong><span>当前来源</span></div>
      <div><strong>{{ pendingCount }}</strong><span>待审核</span></div>
      <div><strong>{{ admittedCount }}</strong><span>已准入</span></div>
      <div><strong>{{ quarantinedCount }}</strong><span>已隔离</span></div>
    </div>

    <div v-if="loading" class="loading-state">加载中...</div>
    <div v-else-if="!sources.length" class="empty-state">当前筛选下没有来源档案</div>
    <div v-else class="table-wrap">
      <table>
        <thead><tr><th>域名</th><th>等级</th><th>类型</th><th>子域继承</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="source in sources" :key="source.id">
            <td class="domain">{{ source.domain }}</td>
            <td><StatusBadge kind="fact" :status="source.tier" :label="source.tier" /></td>
            <td>{{ source.source_kind }}</td>
            <td>{{ source.inherit_to_subdomains ? '是' : '否' }}</td>
            <td>{{ admissionLabel(source.tier) }}</td>
            <td>
              <button class="btn btn-sm" @click="showRevisions(source)">历史</button>
              <button v-if="canAdmin" class="btn btn-sm btn-primary" @click="edit(source)">评级</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="editing" class="modal-overlay" @click.self="editing = null">
      <form class="modal" @submit.prevent="save">
        <h3>评级 {{ editing.domain }}</h3>
        <label>来源等级<select v-model="form.tier"><option v-for="tier in tiers" :key="tier">{{ tier }}</option></select></label>
        <label>来源类型<select v-model="form.source_kind"><option v-for="kind in kinds" :key="kind">{{ kind }}</option></select></label>
        <label class="check"><input v-model="form.inherit_to_subdomains" type="checkbox" /> 子域继承此档案</label>
        <label>变更理由<textarea v-model.trim="form.reason" rows="3" required /></label>
        <div class="modal-actions"><button type="button" class="btn" @click="editing = null">取消</button><button class="btn btn-primary" :disabled="!form.reason">保存</button></div>
      </form>
    </div>

    <aside v-if="revisionSource" class="drawer">
      <header><h3>{{ revisionSource.domain }} 修订历史</h3><button class="btn-icon" title="关闭" @click="revisionSource = null">×</button></header>
      <div v-for="item in revisions" :key="item.id" class="revision-item">
        <strong>{{ item.tier }} · {{ item.source_kind }}</strong><span>{{ item.reason }}</span><small>{{ item.actor }} · {{ item.created_at || '未知时间' }}</small>
      </div>
    </aside>
    <div v-if="message" class="toast" :class="message.type">{{ message.text }}</div>
  </main>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { governanceApi } from '../api'
import { hasRole } from '../auth'
import StatusBadge from '../components/StatusBadge.vue'
import SvgIcon from '../components/icons/SvgIcon.vue'

const tiers = ['A', 'B', 'C', 'D', 'unknown']
const kinds = ['official', 'news', 'community', 'aggregator', 'research', 'other']
const sources = ref([]), revisions = ref([]), editing = ref(null), revisionSource = ref(null)
const loading = ref(false), tierFilter = ref(''), message = ref(null)
const canAdmin = computed(() => hasRole('admin'))
const form = reactive({ tier: 'unknown', source_kind: 'other', inherit_to_subdomains: false, reason: '' })
const pendingCount = computed(() => sources.value.filter((item) => item.tier === 'unknown').length)
const admittedCount = computed(() => sources.value.filter((item) => ['A', 'B', 'C'].includes(item.tier)).length)
const quarantinedCount = computed(() => sources.value.filter((item) => item.tier === 'D').length)

function admissionLabel(tier) { return ['A', 'B', 'C'].includes(tier) ? '准入' : tier === 'D' ? '隔离' : '待审核' }
function notify(text, type = 'success') { message.value = { text, type }; setTimeout(() => { message.value = null }, 3000) }
async function loadSources() { loading.value = true; try { sources.value = (await governanceApi.listSources(tierFilter.value)).data.sources || [] } catch { notify('加载来源档案失败', 'error') } finally { loading.value = false } }
function edit(source) { editing.value = source; Object.assign(form, { tier: source.tier, source_kind: source.source_kind, inherit_to_subdomains: source.inherit_to_subdomains, reason: '' }) }
async function save() { try { await governanceApi.saveSource(editing.value.domain, { domain: editing.value.domain, ...form }); editing.value = null; notify('来源评级已保存'); await loadSources() } catch (error) { notify(error.response?.data?.detail || '保存失败', 'error') } }
async function showRevisions(source) { revisionSource.value = source; revisions.value = (await governanceApi.listRevisions(source.id)).data.revisions || [] }
onMounted(loadSources)
</script>

<style scoped>
.governance-view { position: relative; }
.header-actions, .summary-band, td:last-child { display: flex; align-items: center; gap: 8px; }
.summary-band { border-block: 1px solid var(--border-color); margin-bottom: 16px; }
.summary-band > div { padding: 14px 24px 14px 0; display: grid; gap: 2px; min-width: 120px; }
.summary-band strong { font-size: 22px; }.summary-band span, small { color: var(--text-muted); }
table { width: 100%; border-collapse: collapse; } th, td { padding: 12px; border-bottom: 1px solid var(--border-color); text-align: left; } th { color: var(--text-muted); font-size: 12px; }.domain { font-weight: 600; }
.modal label { display: grid; gap: 6px; margin: 12px 0; }.modal .check { display: flex; }.drawer { position: fixed; top: 64px; right: 0; bottom: 0; width: min(420px, 100vw); padding: 20px; background: var(--bg-primary); border-left: 1px solid var(--border-color); z-index: 180; overflow: auto; }.drawer header { display: flex; justify-content: space-between; }.revision-item { display: grid; gap: 5px; padding: 12px 0; border-bottom: 1px solid var(--border-color); }
@media (max-width: 760px) { .summary-band { overflow-x: auto; }.table-wrap { overflow-x: auto; } table { min-width: 720px; } }
</style>
