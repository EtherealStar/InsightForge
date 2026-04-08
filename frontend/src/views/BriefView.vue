<template>
  <div class="brief-view">
    <div class="page-header">
      <div>
        <h1>📋 新闻简报</h1>
        <p class="subtitle">AI 生成的每日新闻简报</p>
      </div>
      <button class="btn btn-primary" @click="generateBrief" :disabled="generating">
        <span v-if="generating" class="spinner"></span>
        {{ generating ? '生成中...' : '✨ 立即生成' }}
      </button>
    </div>

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
            :class="{ active: selectedBrief?.filename === brief.filename }"
            @click="loadBrief(brief)"
          >
            <span class="brief-date">📄 {{ brief.date }}</span>
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
.brief-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
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

.brief-date {
  font-weight: 500;
}
.brief-meta {
  font-size: 0.75rem;
  color: var(--text-muted);
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
}
</style>
