<template>
  <div class="query-view">
    <div class="page-header">
      <div>
        <h1><SvgIcon name="search" :size="24" /> 智能分析</h1>
        <p class="subtitle">自动识别意图 — 快速查询 · 竞品深度研究</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-sm" @click="showReports = !showReports">
          {{ showReports ? '返回对话' : '研究报告' }}
        </button>
      </div>
    </div>

    <!-- 研究报告列表 -->
    <div v-if="showReports" class="reports-panel card">
      <div class="reports-header">
        <div>
          <h2>研究报告文件</h2>
          <p>深度研究保存为文件报告；受质量门禁治理的分析报告请在 Reports 页面查看。</p>
        </div>
        <button v-if="reports.length" class="btn btn-sm btn-danger" @click="batchDeleteReports"
          :disabled="!selectedReports.length">
          删除选中 ({{ selectedReports.length }})
        </button>
      </div>
      <div v-if="reports.length" class="reports-list">
        <div v-for="r in reports" :key="r.filename" class="report-item"
          :class="{ selected: selectedReports.includes(r.filename) }">
          <input type="checkbox" :value="r.filename" v-model="selectedReports" />
          <div class="report-info" @click="viewReport(r.filename)">
            <span class="report-name">{{ r.filename }}</span>
            <span class="report-meta">{{ new Date(r.generated_at).toLocaleString() }} · {{ (r.size_bytes / 1024).toFixed(1) }}KB</span>
          </div>
          <button class="btn btn-sm" @click="pushReport(r.filename)" title="推送">
            <SvgIcon name="publish" :size="16" />
          </button>
        </div>
      </div>
      <div v-else class="empty-state"><p>暂无研究报告</p></div>

      <!-- 报告详情 -->
      <div v-if="viewingReport" class="report-detail card">
        <div class="report-detail-header">
          <h3>{{ viewingReport.filename }}</h3>
          <button class="btn btn-sm" @click="viewingReport = null">关闭</button>
        </div>
        <div class="markdown-body" v-html="renderMarkdown(viewingReport.content)"></div>
      </div>
    </div>

    <!-- 对话区域 -->
    <div v-else class="chat-shell card">
      <aside class="session-sidebar">
        <button class="btn btn-primary new-chat-btn" @click="newConversation" :disabled="streaming">
          新对话
        </button>
        <div class="session-title">最近会话</div>
        <div v-if="sessionsLoading" class="session-empty">加载中...</div>
        <div v-else-if="!sessions.length" class="session-empty">暂无普通问答会话</div>
        <template v-else>
          <button
            v-for="session in sessions"
            :key="session.session_id"
            class="session-item"
            :class="{ active: currentSessionId === session.session_id }"
            @click="openSession(session.session_id)"
            :disabled="streaming"
          >
            <span class="session-topic">{{ session.topic || '未命名会话' }}</span>
            <span class="session-preview">{{ session.last_message_preview || '暂无消息' }}</span>
            <span class="session-meta">{{ formatTime(session.updated_at) }} · {{ session.message_count || 0 }} 条</span>
          </button>
        </template>
      </aside>

      <div class="chat-container">
        <div class="chat-messages" ref="messagesRef">
        <div v-if="!messages.length" class="chat-welcome">
          <div class="welcome-icon"><SvgIcon name="dashboard" :size="48" /></div>
          <h2>你好，我是 InsightForge 竞品分析助手</h2>
          <p>我能自动识别你的需求：快速查询或深度竞品研究</p>
          <div class="mode-hints">
            <div class="mode-hint">
              <span class="mode-badge quick">快速查询</span>
              <span>查询竞品信息、情报统计、对比分析</span>
            </div>
            <div class="mode-hint">
              <span class="mode-badge deep">深度研究</span>
              <span>说「深度研究/分析/调查/写报告」触发</span>
            </div>
          </div>
          <div class="suggestion-chips">
            <button v-for="q in suggestions" :key="q" class="btn btn-sm" @click="askQuestion(q)">{{ q }}</button>
          </div>
        </div>

        <div v-for="(msg, i) in messages" :key="i" :class="['chat-message', msg.role]">
          <div class="message-avatar">
            <SvgIcon :name="msg.role === 'user' ? 'user' : 'search'" :size="18" />
          </div>
          <div class="message-content">
            <div v-if="msg.reasoning && msg.reasoning.length" class="reasoning-block">
              <div class="reasoning-header" @click="msg.reasoningOpen = !msg.reasoningOpen">
                <span class="reasoning-toggle">{{ msg.reasoningOpen ? '▼' : '▶' }}</span>
                <span class="reasoning-icon"></span>
                <span>推理过程（{{ msg.reasoning.length }} 步）</span>
              </div>
              <div v-if="msg.reasoningOpen" class="reasoning-steps">
                <div v-for="(step, j) in msg.reasoning" :key="j" :class="['reasoning-step', step.event_type]">
                  <div class="step-icon"><SvgIcon :name="stepIcon(step.event_type)" :size="16" /></div>
                  <div class="step-content">
                    <div class="step-label">{{ stepLabel(step.event_type) }}</div>
                    <div class="step-text" v-if="isToolEvent(step.event_type)">
                      <code>{{ step.tool_name }}({{ formatToolInput(step.tool_input) }})</code>
                    </div>
                    <div class="step-text" v-else>{{ step.content }}</div>
                  </div>
                </div>
              </div>
            </div>
            <div v-if="msg.role === 'assistant'" class="markdown-body" v-html="renderMarkdown(msg.content)"></div>
            <div v-else>{{ msg.content }}</div>
            <router-link v-if="msg.reportId" class="report-link" :to="`/reports?report_id=${msg.reportId}`">
              <SvgIcon name="report" :size="16" />
              查看受质量门禁治理的分析报告
            </router-link>
          </div>
        </div>

        <div v-if="pendingPlan" class="plan-review">
          <div class="plan-review-header">
            <div>
              <h3>研究计划审阅</h3>
              <p>{{ pendingPlan.topic }}</p>
            </div>
            <button class="btn btn-primary" @click="confirmAndExecutePlan" :disabled="streaming">
              {{ streaming ? '执行中...' : '确认并执行' }}
            </button>
          </div>
          <textarea v-model="planEditingText" class="input plan-editor" :disabled="streaming"></textarea>
          <div class="todo-editor">
            <div v-for="(todo, idx) in editableTodos" :key="todo.id || idx" class="todo-row">
              <span class="todo-status" :class="todo.status">{{ todoStatusLabel(todo.status) }}</span>
              <input v-model="todo.title" class="input" :disabled="streaming" />
              <button class="btn btn-sm" @click="removeTodo(idx)" :disabled="streaming || editableTodos.length <= 1">删除</button>
            </div>
            <button class="btn btn-sm" @click="addTodo" :disabled="streaming">添加 Todo</button>
          </div>
        </div>

        <!-- 流式加载中 -->
        <div v-if="streaming" class="chat-message assistant">
          <div class="message-avatar"><SvgIcon name="search" :size="18" /></div>
          <div class="message-content">
            <div v-if="streamReasoning.length" class="reasoning-block live">
              <div class="reasoning-header">
                <span class="reasoning-icon pulse"></span>
                <span>{{ isDeepResearch ? '深度研究中...' : '正在推理...' }}</span>
              </div>
              <div class="reasoning-steps">
                <div v-for="(step, j) in streamReasoning" :key="j" :class="['reasoning-step', step.event_type]">
                  <div class="step-icon"><SvgIcon :name="stepIcon(step.event_type)" :size="16" /></div>
                  <div class="step-content">
                    <div class="step-label">{{ stepLabel(step.event_type) }}</div>
                    <div class="step-text" v-if="isToolEvent(step.event_type)">
                      <code>{{ step.tool_name }}({{ formatToolInput(step.tool_input) }})</code>
                    </div>
                    <div class="step-text" v-else>{{ step.content }}</div>
                  </div>
                </div>
              </div>
            </div>
            <div v-if="streamRawOutput && !streamAnswer" class="live-output">
              <div class="live-output-label">当前 AI 输出</div>
              <pre>{{ streamRawOutput }}</pre>
            </div>
            <div v-if="streamAnswer" class="markdown-body" v-html="renderMarkdown(streamAnswer)"></div>
            <span v-if="!streamAnswer" class="typing-cursor">▊</span>
          </div>
        </div>
        </div>

        <!-- 输入区 -->
        <div class="chat-input-area">
          <input v-model="input" class="input chat-input"
            :placeholder="inputPlaceholder"
            @keyup.enter="askQuestion(input)" :disabled="streaming" />
          <button class="btn btn-primary" @click="askQuestion(input)" :disabled="!input.trim() || streaming">
            {{ streaming ? (isDeepResearch ? '研究中...' : '推理中...') : '发送' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, computed, onMounted } from 'vue'
import { queryApi, researchApi } from '../api'
import { marked } from 'marked'
import SvgIcon from '../components/icons/SvgIcon.vue'

const messages = ref([])
const input = ref('')
const streaming = ref(false)
const streamAnswer = ref('')
const streamRawOutput = ref('')
const streamReasoning = ref([])
const messagesRef = ref(null)
const showReports = ref(false)
const reports = ref([])
const selectedReports = ref([])
const viewingReport = ref(null)
const pendingPlan = ref(null)
const planEditingText = ref('')
const editableTodos = ref([])
const sessions = ref([])
const sessionsLoading = ref(false)
const currentSessionId = ref(null)

const DEEP_RESEARCH_KEYWORDS = ['深度研究', '深入分析', '深度分析', '写报告', '写一份报告', '详细调查', '研究报告', '深入研究', '全面分析', '深入调查']

const isDeepResearch = computed(() => {
  const q = input.value.trim()
  return DEEP_RESEARCH_KEYWORDS.some(k => q.includes(k))
})

const inputPlaceholder = computed(() => {
  if (isDeepResearch.value) return '将进入深度竞品研究模式...'
  return '输入问题（快速查询）或包含「深度研究」触发竞品分析模式'
})

const suggestions = [
  'Cursor 和 Windsurf 有什么区别？',
  '最近 AI 编程工具有什么新动态？',
  '当前监控了哪些竞品？',
  '深度研究：Cursor vs TRAE 竞品对比分析',
]

function renderMarkdown(text) {
  if (!text) return ''
  try { return marked(text) } catch { return `<p>${text}</p>` }
}

function stepIcon(type) {
  return {
    thought: 'search',
    action: 'task',
    action_start: 'task',
    observation: 'evidence',
    action_result: 'evidence',
    error: 'warning',
  }[type] || 'task'
}

function stepLabel(type) {
  return {
    thought: '思考',
    action: '调用工具',
    action_start: '调用工具',
    observation: '工具结果',
    action_result: '工具结果',
    error: '错误',
  }[type] || type
}

function isToolEvent(type) {
  return type === 'action' || type === 'action_start'
}

function todoStatusLabel(status) {
  return {
    pending: '待执行',
    in_progress: '执行中',
    completed: '完成',
  }[status] || status || '待执行'
}

function formatPlan(plan) {
  if (!plan) return ''
  if (typeof plan === 'string') return plan
  try { return JSON.stringify(plan, null, 2) } catch { return String(plan) }
}

function parsePlanText(text) {
  try { return JSON.parse(text) } catch { return { raw: text } }
}

function normalizeTodos(todos) {
  return (todos || []).map((todo, idx) => ({
    id: todo.id || `todo-${idx + 1}`,
    title: todo.title || '',
    status: todo.status || 'pending',
  }))
}

function addTodo() {
  editableTodos.value.push({
    id: `todo-${Date.now()}`,
    title: '',
    status: 'pending',
  })
}

function removeTodo(index) {
  editableTodos.value.splice(index, 1)
}

function formatToolInput(inp) {
  if (!inp) return ''
  try { return Object.entries(inp).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ') } catch { return String(inp) }
}

function scrollToBottom() {
  nextTick(() => { if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight })
}

function formatTime(value) {
  if (!value) return '未知时间'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return '未知时间'
  }
}

function normalizeSessionMessages(items) {
  return (items || [])
    .filter(item => item?.role === 'user' || item?.role === 'assistant')
    .map(item => ({
      role: item.role,
      content: item.content || '',
      reportId: extractReportId(item.content || ''),
      reasoning: null,
      reasoningOpen: false,
    }))
}

function extractReportId(text) {
  if (!text) return null
  const match = String(text).match(/report[_\s-]?id["'`:\s=]+(\d+)/i)
  return match ? Number(match[1]) : null
}

async function fetchSessions() {
  sessionsLoading.value = true
  try {
    const res = await queryApi.listSessions({ limit: 30, offset: 0 })
    sessions.value = res.data.items || []
  } catch {
    sessions.value = []
  } finally {
    sessionsLoading.value = false
  }
}

function newConversation() {
  currentSessionId.value = null
  messages.value = []
  pendingPlan.value = null
  planEditingText.value = ''
  editableTodos.value = []
  input.value = ''
  scrollToBottom()
}

async function openSession(sessionId) {
  if (!sessionId || streaming.value) return
  try {
    const res = await queryApi.getSession(sessionId)
    currentSessionId.value = res.data.session_id || res.data.id
    messages.value = normalizeSessionMessages(res.data.messages)
    pendingPlan.value = null
    scrollToBottom()
  } catch { /* silent */ }
}

async function askQuestion(question) {
  if (!question?.trim()) return
  const q = question.trim()
  input.value = ''

  messages.value.push({ role: 'user', content: q })
  scrollToBottom()

  streaming.value = true
  streamAnswer.value = ''
  streamRawOutput.value = ''
  streamReasoning.value = []
  const reasoning = []

  // 判断是否深度研究
  const useDeepResearch = DEEP_RESEARCH_KEYWORDS.some(k => q.includes(k))

  try {
    if (useDeepResearch) {
      const res = await researchApi.createPlan(q)
      pendingPlan.value = res.data
      planEditingText.value = formatPlan(res.data.plan)
      editableTodos.value = normalizeTodos(res.data.todos)
      messages.value.push({
        role: 'assistant',
        content: '已生成研究计划，请审阅并调整 todo list 后确认执行。',
        reasoning: null,
        reasoningOpen: false,
      })
      return
    }

    const response = await queryApi.askStream(q, 10, currentSessionId.value)

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6)
          if (data === '[DONE]') break
          try {
            const event = JSON.parse(data)
            if (!currentSessionId.value && event.run_id) {
              currentSessionId.value = event.run_id
            }
            if (event.event_type === 'llm_delta') {
              streamRawOutput.value += event.content || ''
            } else if (event.event_type === 'answer_delta') {
              streamAnswer.value += event.content || ''
            } else if (event.event_type === 'answer') {
              streamAnswer.value = event.content
              streamRawOutput.value = ''
            } else if (event.event_type === 'error') {
              streamAnswer.value += '\n\n' + event.content
            } else {
              reasoning.push(event)
              streamReasoning.value = [...reasoning]
            }
            scrollToBottom()
          } catch { /* ignore */ }
        }
      }
    }

    messages.value.push({
      role: 'assistant',
      content: streamAnswer.value,
      reportId: extractReportId(streamAnswer.value),
      reasoning: reasoning.length > 0 ? [...reasoning] : null,
      reasoningOpen: false,
    })
    fetchSessions()

  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: `请求失败: ${e.message}\n\n请检查后端服务是否正常运行。`,
      reasoning: null, reasoningOpen: false,
    })
  } finally {
    streaming.value = false
    streamAnswer.value = ''
    streamRawOutput.value = ''
    streamReasoning.value = []
    scrollToBottom()
  }
}

async function confirmAndExecutePlan() {
  if (!pendingPlan.value || streaming.value) return

  const sessionId = pendingPlan.value.session_id
  const plan = parsePlanText(planEditingText.value)
  const todos = editableTodos.value
    .filter(todo => todo.title?.trim())
    .map((todo, idx) => ({
      id: todo.id || `todo-${idx + 1}`,
      title: todo.title.trim(),
      status: todo.status || 'pending',
    }))

  streaming.value = true
  streamAnswer.value = ''
  streamRawOutput.value = ''
  streamReasoning.value = []
  const reasoning = []

  try {
    await researchApi.updatePlan(sessionId, { plan, todos })
    editableTodos.value = todos
    const response = await researchApi.executeStream(sessionId)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6)
          if (data === '[DONE]') break
          try {
            const event = JSON.parse(data)
            if (event.event_type === 'llm_delta') {
              streamRawOutput.value += event.content || ''
            } else if (event.event_type === 'answer_delta') {
              streamAnswer.value += event.content || ''
            } else if (event.event_type === 'answer') {
              streamAnswer.value = event.content
              streamRawOutput.value = ''
            } else if (event.event_type === 'todo_update') {
              editableTodos.value = normalizeTodos(event.metadata?.todos || editableTodos.value)
            } else if (event.event_type === 'error') {
              streamAnswer.value += '\n\n' + event.content
            } else {
              reasoning.push(event)
              streamReasoning.value = [...reasoning]
            }
            scrollToBottom()
          } catch { /* ignore */ }
        }
      }
    }

    messages.value.push({
      role: 'assistant',
      content: streamAnswer.value,
      reportId: extractReportId(streamAnswer.value),
      reasoning: reasoning.length > 0 ? [...reasoning] : null,
      reasoningOpen: false,
    })
    pendingPlan.value = null
    fetchReports()
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: `研究执行失败: ${e.message}`,
      reasoning: null,
      reasoningOpen: false,
    })
  } finally {
    streaming.value = false
    streamAnswer.value = ''
    streamRawOutput.value = ''
    streamReasoning.value = []
    scrollToBottom()
  }
}

async function fetchReports() {
  try {
    const res = await researchApi.list()
    reports.value = res.data.reports || []
  } catch { /* silent */ }
}

async function viewReport(filename) {
  try {
    const res = await researchApi.get(filename)
    viewingReport.value = res.data
  } catch { /* silent */ }
}

async function batchDeleteReports() {
  if (!selectedReports.value.length || !confirm(`确定删除 ${selectedReports.value.length} 份报告？`)) return
  try {
    await researchApi.batchDelete(selectedReports.value)
    selectedReports.value = []
    fetchReports()
  } catch { /* silent */ }
}

async function pushReport(filename) {
  try {
    await researchApi.push(filename)
    alert('推送成功')
  } catch (e) {
    alert('推送失败: ' + (e.response?.data?.detail || e.message))
  }
}

onMounted(() => {
  fetchReports()
  fetchSessions()
})
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.header-actions {
  display: flex;
  gap: var(--space-sm);
}

.chat-shell {
  display: flex;
  height: calc(100vh - 180px);
  min-height: 500px;
  padding: 0;
  overflow: hidden;
}

.session-sidebar {
  width: 280px;
  flex-shrink: 0;
  border-right: 1px solid var(--border-color);
  background: var(--bg-secondary);
  padding: var(--space-md);
  overflow-y: auto;
}
.new-chat-btn {
  width: 100%;
  margin-bottom: var(--space-md);
}
.session-title {
  margin-bottom: var(--space-sm);
  color: var(--text-muted);
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
}
.session-empty {
  color: var(--text-muted);
  font-size: 0.875rem;
  padding: var(--space-md) 0;
}
.session-item {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: var(--space-sm);
  margin-bottom: var(--space-xs);
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  text-align: left;
  cursor: pointer;
}
.session-item:hover {
  background: var(--bg-card);
}
.session-item.active {
  border-color: rgba(245, 158, 11, 0.35);
  background: var(--accent-glow);
}
.session-topic {
  color: var(--text-primary);
  font-size: 0.875rem;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-preview {
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 0.8rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-meta {
  color: var(--text-muted);
  font-size: 0.75rem;
}

.chat-container {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.chat-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  text-align: center;
  gap: var(--space-md);
  color: var(--text-secondary);
}
.welcome-icon {
  display: inline-flex;
  margin-bottom: var(--space-sm);
  color: var(--accent-primary);
}
.chat-welcome h2 { color: var(--text-primary); }

.mode-hints {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin: var(--space-md) 0;
  font-size: 0.875rem;
}
.mode-hint {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}
.mode-badge {
  padding: 2px 10px;
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  font-weight: 600;
  flex-shrink: 0;
}
.mode-badge.quick {
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
  border: 1px solid rgba(16, 185, 129, 0.3);
}
.mode-badge.deep {
  background: rgba(99, 102, 241, 0.15);
  color: #6366f1;
  border: 1px solid rgba(99, 102, 241, 0.3);
}

.suggestion-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  justify-content: center;
  margin-top: var(--space-md);
}

.chat-message {
  display: flex;
  gap: var(--space-md);
  max-width: 85%;
  animation: messageIn 0.3s ease;
}
.chat-message.user { align-self: flex-end; flex-direction: row-reverse; }
.chat-message.assistant { align-self: flex-start; }
@keyframes messageIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

.message-avatar {
  width: 36px; height: 36px;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.25rem; flex-shrink: 0;
  background: var(--bg-card); border-radius: 50%;
}
.message-content {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-md) var(--space-lg);
  font-size: 0.9375rem; line-height: 1.7; min-width: 200px;
}
.chat-message.user .message-content {
  background: var(--accent-glow);
  border-color: rgba(245, 158, 11, 0.2);
}

.plan-review {
  align-self: stretch;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-lg);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-card);
}
.plan-review-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-md);
}
.plan-review-header h3 {
  margin: 0 0 4px;
  font-size: 1rem;
}
.plan-review-header p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.875rem;
}
.plan-editor {
  min-height: 220px;
  resize: vertical;
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 0.85rem;
  line-height: 1.5;
}
.todo-editor {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}
.todo-row {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-sm);
}
.todo-status {
  font-size: 0.75rem;
  color: var(--text-secondary);
}
.todo-status.in_progress { color: #f59e0b; }
.todo-status.completed { color: #10b981; }

/* 推理过程 */
.reasoning-block {
  margin-bottom: var(--space-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.reasoning-block.live {
  border-color: rgba(99, 102, 241, 0.4);
  background: rgba(99, 102, 241, 0.03);
}
.reasoning-header {
  display: flex; align-items: center; gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--bg-secondary);
  cursor: pointer; font-size: 0.85rem; color: var(--text-secondary);
  user-select: none; transition: background 0.2s;
}
.reasoning-header:hover { background: var(--bg-tertiary, var(--bg-secondary)); }
.reasoning-toggle { font-size: 0.7rem; color: var(--text-secondary); }
.reasoning-icon { font-size: 1rem; }
.reasoning-icon.pulse { animation: pulse 1.5s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

.reasoning-steps { padding: var(--space-sm) var(--space-md); display: flex; flex-direction: column; gap: 6px; }
.reasoning-step {
  display: flex; gap: var(--space-sm);
  font-size: 0.825rem; line-height: 1.5; padding: 4px 0;
  animation: stepFade 0.3s ease;
}
@keyframes stepFade { from { opacity: 0; transform: translateX(-8px); } to { opacity: 1; transform: translateX(0); } }
.step-icon { flex-shrink: 0; width: 22px; text-align: center; }
.step-content { flex: 1; min-width: 0; }
.step-label { font-weight: 600; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }
.reasoning-step.thought .step-label { color: #8b5cf6; }
.reasoning-step.action .step-label,
.reasoning-step.action_start .step-label { color: #f59e0b; }
.reasoning-step.observation .step-label,
.reasoning-step.action_result .step-label { color: #10b981; }
.reasoning-step.error .step-label { color: #ef4444; }
.step-text { color: var(--text-secondary); word-break: break-word; }
.step-text code {
  background: rgba(99, 102, 241, 0.1); padding: 2px 6px; border-radius: 3px;
  font-size: 0.8rem; font-family: 'Fira Code', 'Consolas', monospace; color: var(--text-primary);
}
.reasoning-step.observation .step-text,
.reasoning-step.action_result .step-text {
  max-height: 120px; overflow-y: auto; font-size: 0.8rem; white-space: pre-wrap;
  background: var(--bg-secondary); padding: 6px 8px; border-radius: var(--radius-sm); margin-top: 2px;
}

.live-output {
  margin-bottom: var(--space-md);
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
}
.live-output-label {
  margin-bottom: 4px;
  color: var(--text-muted);
  font-size: 0.75rem;
  font-weight: 600;
}
.live-output pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-secondary);
  font-family: inherit;
  font-size: 0.825rem;
  line-height: 1.5;
}

.typing-cursor { display: inline-block; color: var(--accent-primary); animation: blink 1s infinite; }
@keyframes blink { 0%, 50% { opacity: 1; } 51%, 100% { opacity: 0; } }

.chat-input-area {
  display: flex; gap: var(--space-md);
  padding: var(--space-md) var(--space-lg);
  border-top: 1px solid var(--border-color);
  background: var(--bg-secondary);
}
.chat-input { flex: 1; }

/* 研究报告面板 */
.reports-panel { padding: var(--space-lg); }
.reports-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: var(--space-lg);
}
.reports-header p {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: 0.8125rem;
}
.report-link {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  margin-top: var(--space-sm);
  padding: var(--space-xs) var(--space-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
}
.reports-list { display: flex; flex-direction: column; gap: var(--space-sm); }
.report-item {
  display: flex; align-items: center; gap: var(--space-md);
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--border-color); border-radius: var(--radius-sm);
  transition: background 0.2s;
}
.report-item:hover { background: var(--bg-secondary); }
.report-item.selected { border-color: var(--accent-primary); background: var(--accent-glow); }
.report-info { flex: 1; cursor: pointer; display: flex; flex-direction: column; }
.report-name { font-size: 0.875rem; font-weight: 500; word-break: break-all; }
.report-meta { font-size: 0.75rem; color: var(--text-muted); }

.report-detail { margin-top: var(--space-lg); max-height: 60vh; overflow-y: auto; }
.report-detail-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: var(--space-md); border-bottom: 1px solid var(--border-color);
  position: sticky; top: 0; background: var(--bg-card); z-index: 1;
}
.report-detail .markdown-body { padding: var(--space-lg); }

.empty-state { text-align: center; padding: var(--space-xl); color: var(--text-muted); }

@media (max-width: 900px) {
  .chat-shell {
    flex-direction: column;
    height: auto;
    min-height: calc(100vh - 180px);
  }
  .session-sidebar {
    width: auto;
    max-height: 220px;
    border-right: 0;
    border-bottom: 1px solid var(--border-color);
  }
  .chat-container {
    min-height: 520px;
  }
}
</style>
