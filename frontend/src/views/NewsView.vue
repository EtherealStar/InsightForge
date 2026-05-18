<template>
  <div class="news-view">
    <div class="page-header">
      <div>
        <h1> 新闻展示</h1>
        <p class="subtitle">浏览已抓取的新闻，支持按来源和语言筛选</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="toggleSelectionMode" style="margin-right: 8px;">
          {{ selectionMode ? '取消多选' : '多选管理' }}
        </button>
        <button class="btn btn-primary" @click="runPipeline" :disabled="pipelineLoading || selectionMode">
          <span v-if="pipelineLoading" class="spinner"></span>
          {{ pipelineLoading ? '抓取中...' : ' 立即抓取' }}
        </button>
      </div>
    </div>

    <!-- 批量操作栏 -->
    <div v-if="selectionMode" class="batch-action-bar card">
      <div class="batch-info">
        已选中 <strong>{{ selectedIds.length }}</strong> 篇文章
      </div>
      <div class="batch-buttons">
        <button class="btn btn-sm btn-accent" :disabled="!selectedIds.length || summarizing" @click="batchResummarize">
          <span v-if="summarizing" class="spinner"></span>
          {{ summarizing ? 'AI 处理中...' : ' AI 重新摘要' }}
        </button>
        <button class="btn btn-sm btn-danger" :disabled="!selectedIds.length" @click="batchDelete" style="margin-left: 8px;">
           删除所选
        </button>
        <button class="btn btn-sm" @click="selectedIds = []" style="margin-left: 8px;" v-if="selectedIds.length">
          清空
        </button>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar card">
      <div class="filter-group">
        <label class="form-label"> 搜索</label>
        <input
          v-model="keyword"
          class="input"
          placeholder="输入关键词搜索..."
          @keyup.enter="search"
        />
      </div>
      <div class="filter-group">
        <label class="form-label">来源</label>
        <div class="tag-list">
          <span
            class="tag"
            :class="{ active: !selectedSource }"
            @click="selectedSource = ''"
          >全部</span>
          <span
            v-for="src in sources"
            :key="src"
            class="tag"
            :class="{ active: selectedSource === src }"
            @click="selectedSource = src"
          >{{ src }}</span>
        </div>
      </div>
      <div class="filter-group">
        <label class="form-label">语言</label>
        <div class="tag-list">
          <span
            class="tag"
            :class="{ active: !selectedLang }"
            @click="selectedLang = ''"
          >全部</span>
          <span
            class="tag"
            :class="{ active: selectedLang === 'zh' }"
            @click="selectedLang = 'zh'"
          >中文</span>
          <span
            class="tag"
            :class="{ active: selectedLang === 'en' }"
            @click="selectedLang = 'en'"
          >英文</span>
        </div>
      </div>
    </div>

    <!-- 统计 -->
    <div class="results-info" v-if="total > 0">
      共 <strong>{{ total }}</strong> 篇新闻
      <span v-if="selectedSource || selectedLang || keyword">（已筛选）</span>
    </div>

    <!-- 新闻列表 -->
    <div v-if="loading" class="news-grid">
      <div v-for="i in 6" :key="i" class="skeleton-card">
        <div class="skeleton" style="height:14px;width:80px;margin-bottom:12px"></div>
        <div class="skeleton" style="height:20px;width:90%;margin-bottom:8px"></div>
        <div class="skeleton" style="height:14px;width:70%"></div>
      </div>
    </div>

    <div v-else-if="articles.length" class="news-grid">
      <NewsCard
        v-for="article in articles"
        :key="article.id"
        :article="article"
        :selectable="selectionMode"
        :selected="selectedIds.includes(article.id)"
        @click="handleCardClick"
        @toggleSelect="toggleSelect(article)"
      />
    </div>

    <div v-else class="empty-state">
      <span class="emoji"></span>
      <p>暂无新闻数据</p>
      <p>点击「立即抓取」按钮获取最新新闻</p>
    </div>

    <!-- 分页 -->
    <div class="pagination" v-if="totalPages > 1">
      <button
        class="btn btn-sm"
        :disabled="page <= 1"
        @click="page--; fetchArticles()"
      >‹ 上一页</button>
      <span class="page-info">第 {{ page }} / {{ totalPages }} 页</span>
      <button
        class="btn btn-sm"
        :disabled="page >= totalPages"
        @click="page++; fetchArticles()"
      >下一页 ›</button>
    </div>

    <!-- 详情弹窗 -->
    <NewsDetail
      v-if="selectedArticle"
      :article="selectedArticle"
      @close="selectedArticle = null"
    />

    <!-- Toast -->
    <div v-if="toast.show" :class="['toast', 'toast-' + toast.type]">
      {{ toast.message }}
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { newsApi, waitForTask } from '../api'
import NewsCard from '../components/NewsCard.vue'
import NewsDetail from '../components/NewsDetail.vue'

const articles = ref([])
const sources = ref([])
const loading = ref(true)
const pipelineLoading = ref(false)
const page = ref(1)
const total = ref(0)
const totalPages = ref(1)
const keyword = ref('')
const selectedSource = ref('')
const selectedLang = ref('')
const selectedArticle = ref(null)

const selectionMode = ref(false)
const selectedIds = ref([])
const summarizing = ref(false)

const toast = ref({ show: false, message: '', type: 'info' })

function showToast(message, type = 'info') {
  toast.value = { show: true, message, type }
  setTimeout(() => { toast.value.show = false }, 3000)
}

async function fetchArticles() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: 18,
    }
    if (selectedSource.value) params.source = selectedSource.value
    if (selectedLang.value) params.language = selectedLang.value
    if (keyword.value) params.keyword = keyword.value

    const res = await newsApi.getArticles(params)
    articles.value = res.data.articles
    total.value = res.data.total
    totalPages.value = res.data.total_pages
  } catch (e) {
    showToast('获取新闻失败: ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    loading.value = false
  }
}

async function fetchSources() {
  try {
    const res = await newsApi.getSources()
    sources.value = res.data.sources || []
  } catch {
    // 静默处理
  }
}

function search() {
  page.value = 1
  selectionMode.value = false
  selectedIds.value = []
  fetchArticles()
}

function handleCardClick(article) {
  if (selectionMode.value) {
    toggleSelect(article)
  } else {
    openDetail(article)
  }
}

function toggleSelectionMode() {
  selectionMode.value = !selectionMode.value
  selectedIds.value = []
}

function toggleSelect(article) {
  const index = selectedIds.value.indexOf(article.id)
  if (index > -1) {
    selectedIds.value.splice(index, 1)
  } else {
    selectedIds.value.push(article.id)
  }
}

async function batchDelete() {
  if (!selectedIds.value.length) return
  if (!confirm(`确定要彻底删除已选中的 ${selectedIds.value.length} 篇新闻及其相关的分析向量数据吗？此操作不可恢复。`)) return
  
  loading.value = true
  try {
    const res = await newsApi.deleteArticles(selectedIds.value)
    showToast(`删除成功！清理了 ${res.data.deleted} 篇新闻数据`, 'success')
    selectionMode.value = false
    selectedIds.value = []
    
    // 如果全删光了，往回退一页
    if (articles.value.length === selectedIds.value.length && page.value > 1) {
      page.value--
    }
    fetchArticles()
  } catch(e) {
    showToast('删除失败: ' + (e.response?.data?.detail || e.message), 'error')
    loading.value = false
  }
}

async function openDetail(article) {
  // 获取完整内容
  try {
    const res = await newsApi.getArticle(article.id)
    selectedArticle.value = res.data
  } catch {
    selectedArticle.value = article
  }
}

async function batchResummarize() {
  if (!selectedIds.value.length) return
  summarizing.value = true
  showToast(`正在对 ${selectedIds.value.length} 篇文章执行 AI 摘要...`, 'info')
  try {
    const res = await newsApi.resummarize(selectedIds.value)
    const r = res.data.result
    showToast(`AI 摘要完成！成功 ${r.success} 篇，失败 ${r.failed} 篇`, r.failed > 0 ? 'warning' : 'success')
    selectionMode.value = false
    selectedIds.value = []
    fetchArticles()
  } catch (e) {
    showToast('AI 摘要失败: ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    summarizing.value = false
  }
}

async function runPipeline() {
  pipelineLoading.value = true
  showToast('正在启动新闻抓取任务...', 'info')
  try {
    const res = await newsApi.runPipeline()
    const taskId = res.data.task_id
    if (!taskId) {
      throw new Error(res.data.message || '未返回任务 ID')
    }

    showToast('新闻抓取任务已开始，正在等待结果...', 'info')
    const r = await waitForTask(taskId)
    if (r === 'Skipped') {
      showToast('抓取任务已跳过：尚未达到自动抓取间隔', 'info')
      return
    }
    if (!r || typeof r !== 'object') {
      throw new Error('任务完成但未返回有效结果')
    }

    if (r.errors && r.errors.length > 0) {
      showToast(`抓取完成(带错误)！新增 ${r.new} 篇。错误: ${r.errors[0]}`, 'warning')
    } else {
      showToast(`抓取完成！新增 ${r.new} 篇，向量化 ${r.embedded} 篇`, 'success')
    }
    fetchArticles()
    fetchSources()
  } catch (e) {
    showToast('抓取失败: ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    pipelineLoading.value = false
  }
}

// 筛选变化时重新加载
watch([selectedSource, selectedLang], () => {
  page.value = 1
  selectionMode.value = false
  selectedIds.value = []
  fetchArticles()
})

onMounted(() => {
  fetchArticles()
  fetchSources()
})
</script>

<style scoped>
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-lg);
  margin-bottom: var(--space-lg);
  padding: var(--space-lg);
}
.filter-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}
.filter-group:first-child {
  min-width: 240px;
}
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
}

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

.results-info {
  font-size: 0.875rem;
  color: var(--text-muted);
  margin-bottom: var(--space-md);
}

.news-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: var(--space-md);
  margin-bottom: var(--space-xl);
}

.skeleton-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-lg);
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-md);
  padding: var(--space-lg) 0;
}
.page-info {
  font-size: 0.875rem;
  color: var(--text-muted);
}
</style>
