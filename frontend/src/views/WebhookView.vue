<template>
  <div class="webhook-view">
    <div class="page-header">
      <div>
        <h1><SvgIcon name="webhook" :size="24" /> 消息推送</h1>
        <p class="subtitle">管理 Webhook 推送渠道，将分析报告和竞品情报推送到各平台</p>
      </div>
      <div v-if="isAdmin" class="header-actions">
        <button class="btn" @click="pushAll" :disabled="pushing">
          <span v-if="pushing" class="spinner"></span>
          <SvgIcon v-else name="publish" :size="16" />
          {{ pushing ? '推送中...' : '推送最新报告' }}
        </button>
        <button class="btn btn-primary" @click="openAddModal">
          <SvgIcon name="plus" :size="16" />
          添加渠道
        </button>
      </div>
    </div>

    <!-- 自动推送开关 -->
    <section class="card auto-push-section">
      <div class="auto-push-row">
        <div class="auto-push-info">
          <h3>自动推送</h3>
          <p class="auto-push-desc">开启后，发布分析报告时将自动推送到所有已启用的渠道</p>
        </div>
        <label v-if="isAdmin" class="toggle-switch">
          <input type="checkbox" v-model="autoPush" @change="toggleAutoPush" />
          <span class="toggle-slider"></span>
        </label>
      </div>
    </section>

    <!-- 渠道列表 -->
    <section class="channels-grid" v-if="channels.length">
      <div
        v-for="ch in channels"
        :key="ch.id"
        class="channel-card card"
        :class="{ disabled: !ch.enabled }"
      >
        <div class="channel-header">
          <div class="channel-identity">
            <span class="platform-icon"><SvgIcon :name="getPlatformIcon(ch.platform)" :size="24" /></span>
            <div>
              <h3 class="channel-name">{{ ch.name }}</h3>
              <span class="platform-badge">{{ getPlatformName(ch.platform) }}</span>
            </div>
          </div>
          <label v-if="isAdmin" class="toggle-switch toggle-sm">
            <input
              type="checkbox"
              :checked="ch.enabled"
              @change="toggleChannel(ch)"
            />
            <span class="toggle-slider"></span>
          </label>
        </div>

        <div class="channel-detail">
          <div class="detail-row" v-if="ch.webhook_url">
            <span class="detail-label">Webhook</span>
            <span class="detail-value mono">{{ maskSecret(ch.webhook_url) }}</span>
          </div>
          <div class="detail-row" v-if="ch.platform === 'telegram'">
            <span class="detail-label">Bot Token</span>
            <span class="detail-value mono">{{ maskSecret(ch.bot_token) }}</span>
          </div>
          <div class="detail-row" v-if="ch.platform === 'telegram'">
            <span class="detail-label">Chat ID</span>
            <span class="detail-value mono">{{ ch.chat_id }}</span>
          </div>
          <div class="detail-row" v-if="ch.platform === 'ntfy'">
            <span class="detail-label">Server</span>
            <span class="detail-value mono">{{ ch.server_url }}</span>
          </div>
          <div class="detail-row" v-if="ch.platform === 'ntfy'">
            <span class="detail-label">Topic</span>
            <span class="detail-value mono">{{ ch.topic }}</span>
          </div>
        </div>

        <div v-if="isAdmin" class="channel-actions">
          <button
            class="btn btn-sm"
            @click="testChannel(ch)"
            :disabled="testingId === ch.id"
            title="发送测试消息"
          >
            <SvgIcon name="refresh" :size="14" />
            {{ testingId === ch.id ? '发送中...' : '测试' }}
          </button>
          <button class="btn btn-sm" @click="openEditModal(ch)" title="编辑">
            <SvgIcon name="edit" :size="14" />
            编辑
          </button>
          <button class="btn btn-sm btn-danger" @click="deleteChannel(ch)" title="删除">
            <SvgIcon name="delete" :size="14" />
            删除
          </button>
        </div>
      </div>
    </section>

    <!-- 空状态 -->
    <div v-else class="card empty-state">
      <p>暂无推送渠道</p>
      <p>点击「添加渠道」配置飞书、钉钉、企业微信、Telegram 或 ntfy</p>
      <button v-if="isAdmin" class="btn btn-primary" @click="openAddModal" style="margin-top: var(--space-md)">
        <SvgIcon name="plus" :size="16" />
        添加第一个渠道
      </button>
    </div>

    <!-- 添加/编辑 Modal -->
    <teleport to="body">
      <div v-if="modalOpen" class="modal-overlay" @click.self="closeModal">
        <div class="modal card">
          <div class="modal-header">
            <h2>{{ editingChannel ? '编辑渠道' : '添加推送渠道' }}</h2>
            <button class="btn-icon" @click="closeModal"></button>
          </div>

          <!-- 平台选择 -->
          <div class="platform-selector" v-if="!editingChannel">
            <button
              v-for="p in platforms"
              :key="p.id"
              class="platform-option"
              :class="{ active: form.platform === p.id }"
              @click="selectPlatform(p.id)"
            >
              <span class="platform-opt-icon"><SvgIcon :name="getPlatformIcon(p.id)" :size="20" /></span>
              <span class="platform-opt-name">{{ p.name }}</span>
            </button>
          </div>

          <!-- 配置帮助 -->
          <div class="platform-help" v-if="currentPlatformHelp">
            <SvgIcon name="evidence" :size="16" />
            <span>{{ currentPlatformHelp }}</span>
          </div>

          <!-- 表单 -->
          <div class="modal-form">
            <div class="form-group">
              <label class="form-label">渠道名称</label>
              <input v-model="form.name" class="input" placeholder="如：飞书工作群" />
            </div>

            <!-- 飞书/钉钉/企业微信 -->
            <div class="form-group" v-if="['feishu','dingtalk','wecom'].includes(form.platform)">
              <label class="form-label">Webhook URL</label>
              <input v-model="form.webhook_url" class="input" placeholder="https://..." />
            </div>

            <!-- Telegram -->
            <template v-if="form.platform === 'telegram'">
              <div class="form-group">
                <label class="form-label">Bot Token</label>
                <input v-model="form.bot_token" class="input" placeholder="123456:ABC-DEF..." />
              </div>
              <div class="form-group">
                <label class="form-label">Chat ID</label>
                <input v-model="form.chat_id" class="input" placeholder="-100123456789" />
              </div>
            </template>

            <!-- ntfy -->
            <template v-if="form.platform === 'ntfy'">
              <div class="form-group">
                <label class="form-label">服务器地址</label>
                <input v-model="form.server_url" class="input" placeholder="https://ntfy.sh" />
              </div>
              <div class="form-group">
                <label class="form-label">Topic</label>
                <input v-model="form.topic" class="input" placeholder="my-intel-report" />
              </div>
            </template>
          </div>

          <div class="modal-footer">
            <button class="btn" @click="closeModal">取消</button>
            <button class="btn btn-primary" @click="submitForm" :disabled="!isFormValid">
              {{ editingChannel ? '保存' : '添加' }}
            </button>
          </div>
        </div>
      </div>
    </teleport>

    <!-- Toast -->
    <div v-if="toast.show" :class="['toast', 'toast-' + toast.type]">
      {{ toast.message }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { webhookApi } from '../api'
import { hasRole } from '../auth'
import SvgIcon from '../components/icons/SvgIcon.vue'

const channels = ref([])
const platforms = ref([])
const autoPush = ref(false)
const pushing = ref(false)
const testingId = ref(null)
const modalOpen = ref(false)
const editingChannel = ref(null)
const toast = ref({ show: false, message: '', type: 'info' })
const isAdmin = computed(() => hasRole('admin'))

const defaultForm = () => ({
  name: '',
  platform: 'feishu',
  webhook_url: '',
  bot_token: '',
  chat_id: '',
  server_url: 'https://ntfy.sh',
  topic: '',
})

const form = ref(defaultForm())

function showToast(message, type = 'info') {
  toast.value = { show: true, message, type }
  setTimeout(() => { toast.value.show = false }, 3500)
}

// ========== 平台信息 ==========
function getPlatformIcon(id) {
  const map = { feishu: 'webhook', dingtalk: 'webhook', wecom: 'webhook', telegram: 'publish', ntfy: 'webhook' }
  return map[id] || 'webhook'
}
function getPlatformName(id) {
  const map = { feishu: '飞书', dingtalk: '钉钉', wecom: '企业微信', telegram: 'Telegram', ntfy: 'ntfy' }
  return map[id] || id
}

function maskSecret(value) {
  if (!value) return ''
  const text = String(value)
  if (text.includes('*')) return text
  if (text.length <= 12) return '********'
  return `${text.slice(0, 6)}...${text.slice(-4)}`
}

const currentPlatformHelp = computed(() => {
  const p = platforms.value.find(x => x.id === form.value.platform)
  return p?.help || ''
})

const isFormValid = computed(() => {
  if (!form.value.name) return false
  const plat = form.value.platform
  if (['feishu', 'dingtalk', 'wecom'].includes(plat)) return !!form.value.webhook_url
  if (plat === 'telegram') return !!form.value.bot_token && !!form.value.chat_id
  if (plat === 'ntfy') return !!form.value.topic
  return false
})

// ========== 数据加载 ==========
async function fetchChannels() {
  try {
    const res = await webhookApi.getChannels()
    channels.value = res.data.channels || []
    autoPush.value = res.data.auto_push || false
  } catch (e) {
    showToast('获取推送渠道失败', 'error')
  }
}

async function fetchPlatforms() {
  try {
    const res = await webhookApi.getPlatforms()
    platforms.value = res.data.platforms || []
  } catch {
    // 使用本地备份
    platforms.value = [
      { id: 'feishu', name: '飞书', icon: 'webhook', help: '' },
      { id: 'dingtalk', name: '钉钉', icon: 'webhook', help: '' },
      { id: 'wecom', name: '企业微信', icon: 'webhook', help: '' },
      { id: 'telegram', name: 'Telegram', icon: 'publish', help: '' },
      { id: 'ntfy', name: 'ntfy', icon: 'webhook', help: '' },
    ]
  }
}

// ========== 操作 ==========
async function toggleAutoPush() {
  try {
    await webhookApi.setAutoPush(autoPush.value)
    showToast(`自动推送已${autoPush.value ? '开启' : '关闭'}`, 'success')
  } catch (e) {
    autoPush.value = !autoPush.value
    showToast('设置失败', 'error')
  }
}

async function toggleChannel(ch) {
  try {
    await webhookApi.updateChannel(ch.id, { enabled: !ch.enabled })
    ch.enabled = !ch.enabled
    showToast(`${ch.name} 已${ch.enabled ? '启用' : '禁用'}`, 'success')
  } catch (e) {
    showToast('操作失败', 'error')
  }
}

async function testChannel(ch) {
  testingId.value = ch.id
  try {
    await webhookApi.testChannel(ch.id)
    showToast(`测试消息已发送到「${ch.name}」`, 'success')
  } catch (e) {
    showToast('测试失败: ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    testingId.value = null
  }
}

async function deleteChannel(ch) {
  if (!confirm(`确定要删除「${ch.name}」吗？`)) return
  try {
    await webhookApi.deleteChannel(ch.id)
    showToast(`已删除: ${ch.name}`, 'success')
    fetchChannels()
  } catch (e) {
    showToast('删除失败', 'error')
  }
}

async function pushAll() {
  pushing.value = true
  try {
    const res = await webhookApi.pushAll()
    showToast(res.data.message, 'success')
  } catch (e) {
    showToast('推送失败: ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    pushing.value = false
  }
}

// ========== Modal ==========
function openAddModal() {
  editingChannel.value = null
  form.value = defaultForm()
  modalOpen.value = true
}

function openEditModal(ch) {
  editingChannel.value = ch
  form.value = {
    name: ch.name,
    platform: ch.platform,
    webhook_url: ch.webhook_url || '',
    bot_token: ch.bot_token || '',
    chat_id: ch.chat_id || '',
    server_url: ch.server_url || 'https://ntfy.sh',
    topic: ch.topic || '',
  }
  modalOpen.value = true
}

function closeModal() {
  modalOpen.value = false
  editingChannel.value = null
}

function selectPlatform(id) {
  form.value.platform = id
}

async function submitForm() {
  try {
    if (editingChannel.value) {
      await webhookApi.updateChannel(editingChannel.value.id, form.value)
      showToast('渠道已更新', 'success')
    } else {
      await webhookApi.addChannel(form.value)
      showToast('渠道添加成功', 'success')
    }
    closeModal()
    fetchChannels()
  } catch (e) {
    showToast(e.response?.data?.detail || '操作失败', 'error')
  }
}

onMounted(() => {
  fetchChannels()
  fetchPlatforms()
})
</script>

<style scoped>
/* ===== 自动推送 Section ===== */
.auto-push-section {
  margin-bottom: var(--space-lg);
}
.auto-push-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-lg);
}
.auto-push-info h3 {
  margin: 0 0 2px 0;
  font-size: 1rem;
}
.auto-push-desc {
  color: var(--text-muted);
  font-size: 0.8125rem;
  margin: 0;
}

/* ===== Toggle Switch ===== */
.toggle-switch {
  position: relative;
  display: inline-block;
  width: 48px;
  height: 26px;
  flex-shrink: 0;
}
.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}
.toggle-slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  border-radius: 26px;
  transition: all var(--transition-base);
}
.toggle-slider::before {
  content: '';
  position: absolute;
  height: 20px;
  width: 20px;
  left: 2px;
  bottom: 2px;
  background: var(--text-muted);
  border-radius: 50%;
  transition: all var(--transition-base);
}
.toggle-switch input:checked + .toggle-slider {
  background: var(--accent-primary);
  border-color: var(--accent-primary);
}
.toggle-switch input:checked + .toggle-slider::before {
  background: #fff;
  transform: translateX(22px);
}
.toggle-sm {
  width: 40px;
  height: 22px;
}
.toggle-sm .toggle-slider::before {
  height: 16px;
  width: 16px;
}
.toggle-sm input:checked + .toggle-slider::before {
  transform: translateX(18px);
}

/* ===== 渠道卡片网格 ===== */
.channels-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: var(--space-lg);
}

.channel-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  transition: all var(--transition-base);
  border: 1px solid var(--border-color);
}
.channel-card.disabled {
  opacity: 0.55;
}
.channel-card:hover {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 1px var(--accent-primary);
}

.channel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.channel-identity {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}
.platform-icon {
  font-size: 1.75rem;
  line-height: 1;
}
.channel-name {
  margin: 0;
  font-size: 1rem;
  color: var(--text-primary);
}
.platform-badge {
  font-size: 0.75rem;
  color: var(--text-muted);
  background: var(--bg-input);
  padding: 1px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
}

.channel-detail {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.detail-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-sm);
  font-size: 0.8125rem;
}
.detail-label {
  color: var(--text-muted);
  flex-shrink: 0;
  min-width: 70px;
}
.detail-value {
  color: var(--text-secondary);
  word-break: break-all;
}
.detail-value.mono {
  font-family: 'Cascadia Code', 'Fira Code', monospace;
  font-size: 0.75rem;
}

.channel-actions {
  display: flex;
  gap: var(--space-sm);
  border-top: 1px solid var(--border-color);
  padding-top: var(--space-md);
}

/* ===== Header Actions ===== */
.header-actions {
  display: flex;
  gap: var(--space-sm);
}

/* ===== Modal ===== */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease;
}
.modal {
  width: 520px;
  max-width: 95vw;
  max-height: 85vh;
  overflow-y: auto;
  animation: slideUp 0.25s ease;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-lg);
}
.modal-header h2 {
  margin: 0;
}
.modal-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
}

/* ===== Platform Selector ===== */
.platform-selector {
  display: flex;
  gap: var(--space-sm);
  margin-bottom: var(--space-lg);
  flex-wrap: wrap;
}
.platform-option {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-input);
  cursor: pointer;
  transition: all var(--transition-fast);
  min-width: 72px;
  font-size: inherit;
  color: var(--text-secondary);
}
.platform-option:hover {
  border-color: var(--accent-primary);
  background: var(--bg-card-hover);
}
.platform-option.active {
  border-color: var(--accent-primary);
  background: var(--accent-glow);
  color: var(--accent-primary);
}
.platform-opt-icon {
  font-size: 1.5rem;
}
.platform-opt-name {
  font-size: 0.75rem;
  font-weight: 600;
}

/* ===== Platform Help ===== */
.platform-help {
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 0.8125rem;
  color: var(--text-muted);
  margin-bottom: var(--space-lg);
  line-height: 1.5;
}
.help-icon {
  flex-shrink: 0;
}

/* ===== Animations ===== */
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 768px) {
  .channels-grid {
    grid-template-columns: 1fr;
  }
  .header-actions {
    flex-direction: column;
  }
  .platform-selector {
    gap: var(--space-xs);
  }
  .platform-option {
    min-width: 56px;
    padding: var(--space-xs) var(--space-sm);
  }
}
</style>
