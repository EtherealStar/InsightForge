<template>
  <div class="brief-view">
    <div class="page-header">
      <div>
        <h1>📋 新闻简报</h1>
        <p class="subtitle">AI 生成的每日新闻简报</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="toggleSelectionMode" style="margin-right: 8px;">
          {{ selectionMode ? '退出管理' : '📁 简报管理' }}
        </button>
        <button class="btn btn-primary" @click="generateBrief" :disabled="generating || selectionMode">
          <span v-if="generating" class="spinner"></span>
          {{ generating ? '生成中...' : '✨ 立即生成' }}
        </button>
      </div>
    </div>

    <!-- 批量操作栏 -->
    <Transition name="slide-bar">
      <div v-if="selectionMode" class="batch-action-bar card">
        <div class="batch-info">
          已选中 <strong>{{ selectedFilenames.length }}</strong> / {{ briefs.length }} 份简报
        </div>
        <div class="batch-buttons">
          <button class="btn btn-sm" @click="selectAll" v-if="selectedFilenames.length < briefs.length">
            ☑ 全选
          </button>
          <button class="btn btn-sm" @click="selectedFilenames = []" v-if="selectedFilenames.length">
            清空
          </button>
          <button class="btn btn-sm btn-export" :disabled="!selectedFilenames.length" @click="batchExport">
            📥 导出所选
          </button>
          <button class="btn btn-sm btn-danger" :disabled="!selectedFilenames.length" @click="batchDelete">
            🗑 删除所选
          </button>
        </div>
      </div>
    </Transition>

    <!-- 简报列表 -->
    <div class="brief-layout">
      <div class="brief-list card">
        <h3>📂 历史简报</h3>
        <div v-if="loadingList" class="brief-loading">
          <div v-for="i in 5" :key="i" class="skeleton" style="height:40px;margin-bottom:8px"></div>
        </div>
        <div v-else-if="briefs.length" class="brief-items">
          <div
            v-for="brief in briefs"
            :key="brief.filename"
            class="brief-item"
            :class="{
              active: !selectionMode && selectedBrief?.filename === brief.filename,
              selected: selectionMode && selectedFilenames.includes(brief.filename),
            }"
            @click="handleItemClick(brief)"
          >
            <!-- 多选模式下显示 checkbox -->
            <div class="brief-item-left">
              <span v-if="selectionMode" class="checkbox" :class="{ checked: selectedFilenames.includes(brief.filename) }">
                <span class="check-icon">✓</span>
              </span>
              <span class="brief-date">📄 {{ brief.date }}</span>
            </div>
            <span class="brief-meta">{{ formatFileSize(brief.size_bytes) }}</span>
          </div>
        </div>
        <div v-else class="empty-state" style="padding: var(--space-lg) 0">
          <span class="emoji">📭</span>
          <p>暂无简报</p>
        </div>
      </div>

      <!-- 简报内容 -->
      <div class="brief-content card">
        <div v-if="loadingContent" class="brief-loading">
          <div class="skeleton" style="height:24px;width:60%;margin-bottom:16px"></div>
          <div v-for="i in 8" :key="i" class="skeleton" style="height:14px;margin-bottom:8px" :style="{ width: (60 + Math.random() * 40) + '%' }"></div>
        </div>
        <div v-else-if="selectedContent">
          <div class="brief-content-header">
            <h2>{{ selectedBrief?.date }} 简报</h2>
            <span class="brief-gen-time">生成时间: {{ formatTime(selectedBrief?.generated_at) }}</span>
          </div>
          <hr class="divider" />
          <div class="markdown-body" v-html="renderedContent"></div>
        </div>
        <div v-else class="empty-state">
          <span class="emoji">👈</span>
          <p>选择一份简报查看</p>
          <p>或点击「立即生成」创建新简报</p>
        </div>
      </div>
    </div>

    <!-- Toast -->
    <div v-if="toast.show" :class="['toast', 'toast-' + toast.type]">
      {{ toast.message }}
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { briefApi } from '../api'
import { marked } from 'marked'

const briefs = ref([])
const selectedBrief = ref(null)
const selectedContent = ref('')
const loadingList = ref(true)
const loadingContent = ref(false)
const generating = ref(false)
const toast = ref({ show: false, message: '', type: 'info' })

// 管理模式
const selectionMode = ref(false)
const selectedFilenames = ref([])

function showToast(message, type = 'info') {
  toast.value = { show: true, message, type }
  setTimeout(() => { toast.value.show = false }, 3000)
}

const renderedContent = computed(() => {
  if (!selectedContent.value) return ''
  try {
    return marked(selectedContent.value)
  } catch {
    return `<p>${selectedContent.value}</p>`
  }
})

async function fetchBriefs() {
  loadingList.value = true
  try {
    const res = await briefApi.list()
    briefs.value = res.data.briefs || []
    // 自动加载最新
    if (briefs.value.length && !selectedBrief.value) {
      loadBrief(briefs.value[0])
    }
  } catch (e) {
    showToast('获取简报列表失败', 'error')
  } finally {
    loadingList.value = false
  }
}

async function loadBrief(brief) {
  selectedBrief.value = brief
  loadingContent.value = true
  try {
    const res = await briefApi.get(brief.filename)
    selectedContent.value = res.data.content
  } catch (e) {
    showToast('加载简报失败', 'error')
    selectedContent.value = ''
  } finally {
    loadingContent.value = false
  }
}

async function generateBrief() {
  generating.value = true
  showToast('正在生成简报...', 'info')
  try {
    const res = await briefApi.generate()
    showToast(`简报已生成！覆盖 ${res.data.article_count} 篇文章`, 'success')
    // 刷新列表并加载新生成的
    await fetchBriefs()
    if (briefs.value.length) {
      loadBrief(briefs.value[0])
    }
  } catch (e) {
    showToast('生成失败: ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    generating.value = false
  }
}

// ===== 管理模式逻辑 =====

function toggleSelectionMode() {
  selectionMode.value = !selectionMode.value
  selectedFilenames.value = []
}

function handleItemClick(brief) {
  if (selectionMode.value) {
    toggleSelect(brief)
  } else {
    loadBrief(brief)
  }
}

function toggleSelect(brief) {
  const idx = selectedFilenames.value.indexOf(brief.filename)
  if (idx > -1) {
    selectedFilenames.value.splice(idx, 1)
  } else {
    selectedFilenames.value.push(brief.filename)
  }
}

function selectAll() {
  selectedFilenames.value = briefs.value.map(b => b.filename)
}

async function batchDelete() {
  if (!selectedFilenames.value.length) return
  const count = selectedFilenames.value.length
  if (!confirm(`确定要删除已选中的 ${count} 份简报吗？此操作不可恢复。`)) return

  try {
    const res = await briefApi.batchDelete(selectedFilenames.value)
    const deleted = res.data.deleted
    showToast(`成功删除 ${deleted} 份简报`, 'success')

    // 如果当前查看的简报被删除，清空内容区
    if (selectedBrief.value && selectedFilenames.value.includes(selectedBrief.value.filename)) {
      selectedBrief.value = null
      selectedContent.value = ''
    }

    selectedFilenames.value = []
    selectionMode.value = false
    await fetchBriefs()

    // 如果还有简报且当前没有选中的，加载第一个
    if (briefs.value.length && !selectedBrief.value) {
      loadBrief(briefs.value[0])
    }
  } catch (e) {
    showToast('删除失败: ' + (e.response?.data?.detail || e.message), 'error')
  }
}

async function batchExport() {
  if (!selectedFilenames.value.length) return

  try {
    showToast('正在准备导出...', 'info')
    const res = await briefApi.batchExport(selectedFilenames.value)

    // 从 blob 触发浏览器下载
    const blob = new Blob([res.data])
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url

    if (selectedFilenames.value.length === 1) {
      a.download = selectedFilenames.value[0]
    } else {
      a.download = 'briefs_export.zip'
    }

    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)

    showToast(`已导出 ${selectedFilenames.value.length} 份简报`, 'success')
  } catch (e) {
    showToast('导出失败: ' + (e.response?.data?.detail || e.message), 'error')
  }
}

function formatFileSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  return (bytes / 1024).toFixed(1) + ' KB'
}

function formatTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN')
}

onMounted(fetchBriefs)
</script>

<style scoped>
.header-actions {
  display: flex;
  align-items: center;
}

/* 批量操作栏 */
.batch-action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-md) var(--space-lg);
  margin-bottom: var(--space-lg);
  border: 1px solid var(--accent-primary);
  background: var(--accent-glow);
}
.batch-info {
  font-size: 0.9375rem;
  color: var(--text-primary);
}
.batch-buttons {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}
.btn-export {
  border-color: var(--info);
  color: var(--info);
}
.btn-export:hover:not(:disabled) {
  background: rgba(59, 130, 246, 0.15);
}
.btn-export:disabled {
  opacity: 0.5;
}
.btn-danger {
  background: #f43f5e;
  border-color: #f43f5e;
  color: white;
}
.btn-danger:hover:not(:disabled) {
  background: #e11d48;
}
.btn-danger:disabled {
  opacity: 0.5;
}

/* 动画 */
.slide-bar-enter-active,
.slide-bar-leave-active {
  transition: all 0.25s ease;
}
.slide-bar-enter-from,
.slide-bar-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

/* 布局 */
.brief-layout {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: var(--space-lg);
  align-items: start;
}

.brief-list {
  position: sticky;
  top: var(--space-lg);
}
.brief-list h3 {
  margin-bottom: var(--space-md);
}

.brief-items {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.brief-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  font-size: 0.875rem;
}
.brief-item:hover {
  background: var(--bg-card-hover);
}
.brief-item.active {
  background: var(--accent-glow);
  color: var(--accent-primary);
}
.brief-item.selected {
  background: rgba(59, 130, 246, 0.12);
  border-left: 3px solid var(--info);
  padding-left: calc(var(--space-md) - 3px);
}

.brief-item-left {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

/* Checkbox */
.checkbox {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border: 2px solid var(--text-muted);
  border-radius: 4px;
  flex-shrink: 0;
  transition: all var(--transition-fast);
}
.checkbox .check-icon {
  opacity: 0;
  font-size: 0.75rem;
  color: white;
  transition: opacity var(--transition-fast);
}
.checkbox.checked {
  background: var(--info);
  border-color: var(--info);
}
.checkbox.checked .check-icon {
  opacity: 1;
}

.brief-date {
  font-weight: 500;
}
.brief-meta {
  font-size: 0.75rem;
  color: var(--text-muted);
  flex-shrink: 0;
}

.brief-content {
  min-height: 400px;
}

.brief-content-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-md);
}
.brief-gen-time {
  font-size: 0.8125rem;
  color: var(--text-muted);
  flex-shrink: 0;
}

.brief-loading {
  padding: var(--space-md) 0;
}

@media (max-width: 768px) {
  .brief-layout {
    grid-template-columns: 1fr;
  }
  .brief-list {
    position: static;
  }
  .header-actions {
    flex-direction: column;
    gap: var(--space-sm);
  }
}
</style>
