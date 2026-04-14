<template>
  <div class="newsapi-view">
    <div class="page-header">
      <div>
        <h1>🌍 在线新闻检索</h1>
        <p class="subtitle">通过 NewsAPI 实时检索全网新闻或头条</p>
      </div>
    </div>

    <!-- 模式切换 -->
    <div class="mode-tabs">
      <button class="tab-btn" :class="{ active: mode === 'everything' }" @click="mode = 'everything'">
        全网搜索 (Everything)
      </button>
      <button class="tab-btn" :class="{ active: mode === 'top-headlines' }" @click="mode = 'top-headlines'">
        最新头条 (Top Headlines)
      </button>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar card">
      <div class="filter-group">
        <label class="form-label">🔍 关键词</label>
        <input
          v-model="keyword"
          class="input"
          placeholder="搜索关键词..."
          @keyup.enter="search"
        />
      </div>

      <template v-if="mode === 'everything'">
        <div class="filter-group">
          <label class="form-label">语言</label>
          <select v-model="language" class="input">
            <option value="">所有语言</option>
            <option value="zh">中文 (zh)</option>
            <option value="en">英文 (en)</option>
          </select>
        </div>
        <div class="filter-group">
          <label class="form-label">排序类型</label>
          <select v-model="sortBy" class="input">
            <option value="publishedAt">发布时间 (早 -> 晚)</option>
            <option value="relevancy">相关性度 (高 -> 低)</option>
            <option value="popularity">流行程度 (高 -> 低)</option>
          </select>
        </div>
      </template>

      <template v-if="mode === 'top-headlines'">
        <div class="filter-group">
          <label class="form-label">分类 (选其一)</label>
          <select v-model="category" class="input">
            <option value="">全部分类</option>
            <option value="business">商业 (Business)</option>
            <option value="technology">科技 (Technology)</option>
            <option value="general">综合 (General)</option>
            <option value="health">健康 (Health)</option>
            <option value="science">科学 (Science)</option>
            <option value="sports">体育 (Sports)</option>
            <option value="entertainment">娱乐 (Entertainment)</option>
          </select>
        </div>
        <div class="filter-group">
          <label class="form-label">区域范围</label>
          <select v-model="country" class="input">
            <option value="us">美国 (US)</option>
            <option value="cn">中国 (CN)</option>
            <option value="gb">英国 (GB)</option>
            <option value="jp">日本 (JP)</option>
          </select>
        </div>
      </template>

      <div class="filter-group" style="justify-content: flex-end;">
        <button class="btn btn-primary" @click="search" :disabled="loading">
          {{ loading ? '搜索中...' : '开始搜索' }}
        </button>
      </div>
    </div>

    <!-- 结果区域 -->
    <div v-if="loading" class="news-grid">
      <div v-for="i in 6" :key="i" class="skeleton-card">
        <div class="skeleton" style="height:14px;width:80px;margin-bottom:12px"></div>
        <div class="skeleton" style="height:20px;width:90%;margin-bottom:8px"></div>
        <div class="skeleton" style="height:14px;width:70%"></div>
      </div>
    </div>

    <div v-else-if="articles.length" class="news-grid">
      <div v-for="(article, idx) in articles" :key="idx" class="api-card">
        <div v-if="article.urlToImage" class="api-card-img" :style="{ backgroundImage: 'url(' + article.urlToImage + ')' }"></div>
        <div class="api-card-content">
          <div class="meta">
            <span class="source">{{ article.source?.name || 'Unknown' }}</span>
            <span class="time">{{ formatDate(article.publishedAt) }}</span>
          </div>
          <h3 class="title">
            <a :href="article.url" target="_blank" rel="noopener">{{ article.title }}</a>
          </h3>
          <p class="desc">{{ article.description }}</p>
          <div class="card-actions">
            <!-- Save Button -->
            <button class="btn btn-sm btn-secondary" @click="saveArticle(article)" :disabled="savingMap[article.url]">
              {{ savingMap[article.url] ? '保存中...' : '💾 收藏到数据库' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="empty-state">
      <span class="emoji">🌍</span>
      <p>没有找到相关在线新闻</p>
      <p>调整关键词重试，或者检查在"设置"中是否配置了 NewsAPI 密钥。</p>
    </div>

    <!-- Toast -->
    <div v-if="toast.show" :class="['toast', 'toast-' + toast.type]">
      {{ toast.message }}
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { extNewsApi } from '../api'

const mode = ref('everything')
const keyword = ref('AI')

const language = ref('zh')
const sortBy = ref('publishedAt')

const category = ref('')
const country = ref('us')

const articles = ref([])
const loading = ref(false)
const savingMap = ref({}) // track saving status per article URL

const toast = ref({ show: false, message: '', type: 'info' })
function showToast(message, type = 'info') {
  toast.value = { show: true, message, type }
  setTimeout(() => { toast.value.show = false }, 3000)
}

function formatDate(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  return d.toLocaleString()
}

async function search() {
  loading.value = true
  articles.value = []
  try {
    let res
    if (mode.value === 'everything') {
      res = await extNewsApi.searchEverything({
        q: keyword.value || 'AI',
        language: language.value || undefined,
        sort_by: sortBy.value || undefined,
        page: 1,
        page_size: 20
      })
    } else {
      res = await extNewsApi.searchTopHeadlines({
        q: keyword.value || undefined,
        category: category.value || undefined,
        country: country.value || undefined,
        page: 1,
        page_size: 20
      })
    }
    articles.value = res.data.articles || []
    if (articles.value.length === 0) {
      showToast('没有搜索到相关新闻', 'info')
    }
  } catch (e) {
    showToast('搜索失败: ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    loading.value = false
  }
}

async function saveArticle(article) {
  if (!article.url) return showToast('文章URL无效，无法保存', 'error')
  
  savingMap.value[article.url] = true
  try {
    const data = {
      title: article.title || '无标题',
      url: article.url,
      content: article.content || article.description || article.title,
      source_name: article.source?.name || 'NewsAPI',
      language: language.value || 'en', // 默认或者依赖当前 language
      published_at: article.publishedAt
    }
    const res = await extNewsApi.saveArticle(data)
    showToast(res.data.message || '收藏成功', 'success')
  } catch(e) {
    showToast('收藏失败: ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    savingMap.value[article.url] = false
  }
}
</script>

<style scoped>
.mode-tabs {
  display: flex;
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}

.tab-btn {
  padding: var(--space-sm) var(--space-lg);
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  color: var(--text-muted);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.tab-btn.active {
  background: var(--accent-glow);
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}

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

.news-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--space-lg);
}

.api-card {
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  overflow: hidden;
  transition: transform var(--transition-fast), box-shadow var(--transition-fast);
}

.api-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
  border-color: var(--border-hover);
}

.api-card-img {
  width: 100%;
  height: 160px;
  background-size: cover;
  background-position: center;
  border-bottom: 1px solid var(--border-color);
}

.api-card-content {
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  flex: 1;
}

.meta {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-bottom: var(--space-xs);
}

.source {
  font-weight: 600;
  color: var(--accent-primary);
}

.title {
  font-size: 1.125rem;
  margin-bottom: var(--space-xs);
  line-height: 1.4;
}

.title a {
  color: var(--text-primary);
  text-decoration: none;
}

.title a:hover {
  text-decoration: underline;
}

.desc {
  font-size: 0.875rem;
  color: var(--text-secondary);
  line-height: 1.6;
  flex: 1;
}

.card-actions {
  margin-top: var(--space-md);
  display: flex;
  justify-content: flex-end;
}
</style>
