<template>
  <div class="settings-view">
    <div class="page-header">
      <div>
        <h1>⚙️ 功能设置</h1>
        <p class="subtitle">管理 RSS 来源、调度参数和数据</p>
      </div>
    </div>

    <div class="settings-grid">
      <!-- RSS 来源管理 -->
      <section class="card settings-section">
        <h2>📡 RSS 来源管理</h2>
        <p class="section-desc">配置新闻抓取的 RSS 来源</p>

        <div class="feed-form">
          <input v-model="newFeed.name" class="input" placeholder="来源名称" />
          <input v-model="newFeed.url" class="input" placeholder="RSS URL" />
          <button class="btn btn-primary btn-sm" @click="addFeed" :disabled="!newFeed.name || !newFeed.url">
            + 添加
          </button>
        </div>

        <div class="table-wrapper" v-if="feeds.length">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>URL</th>
                <th style="width:60px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="feed in feeds" :key="feed.id">
                <td>
                  <strong>{{ feed.name }}</strong>
                </td>
                <td>
                  <a :href="feed.url" target="_blank" rel="noopener" class="feed-url">
                    {{ feed.url }}
                  </a>
                </td>
                <td>
                  <button class="btn btn-danger btn-sm" @click="deleteFeed(feed)" title="删除">
                    🗑️
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty-state" style="padding:var(--space-lg) 0">
          <p>暂无 RSS 来源</p>
        </div>
      </section>

      <!-- 网页爬取源管理 -->
      <section class="card settings-section">
        <h2>🕷️ 网页爬取源管理</h2>
        <p class="section-desc">添加新闻网站地址，系统将通过爬虫自动抓取该站点的新闻</p>

        <div class="site-form">
          <input v-model="newSite.name" class="input" placeholder="站点名称" />
          <input v-model="newSite.url" class="input" placeholder="网站 URL（如 https://news.example.com）" />
          <input v-model.number="newSite.max_pages" class="input input-sm" type="number" min="1" max="100"
            placeholder="最大页数" title="单次最大爬取页数" />
          <button class="btn btn-primary btn-sm" @click="addSite" :disabled="!newSite.name || !newSite.url">
            + 添加
          </button>
        </div>

        <details class="advanced-options" v-if="newSite.url">
          <summary>高级选项</summary>
          <div class="form-group" style="margin-top: var(--space-sm)">
            <label class="form-label">链接选择器（CSS selector，可选）</label>
            <input v-model="newSite.link_selector" class="input"
              placeholder="例: a.article-link（留空则自动发现所有链接）" />
          </div>
        </details>

        <div class="table-wrapper" v-if="sites.length">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>URL</th>
                <th style="width:80px">最大页数</th>
                <th style="width:60px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="site in sites" :key="site.id">
                <td>
                  <strong>{{ site.name }}</strong>
                </td>
                <td>
                  <a :href="site.url" target="_blank" rel="noopener" class="feed-url">
                    {{ site.url }}
                  </a>
                  <span v-if="site.link_selector" class="selector-tag" :title="site.link_selector">
                    {{ site.link_selector }}
                  </span>
                </td>
                <td style="text-align:center">{{ site.max_pages }}</td>
                <td>
                  <button class="btn btn-danger btn-sm" @click="deleteSite(site)" title="删除">
                    🗑️
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty-state" style="padding:var(--space-lg) 0">
          <p>暂无爬取源 — 添加网站地址后，Pipeline 执行时会自动爬取</p>
        </div>
      </section>

      <!-- 调度设置 -->
      <section class="card settings-section">
        <h2>⏰ 调度设置</h2>
        <p class="section-desc">配置自动抓取和日报生成的时间</p>

        <div class="schedule-form" v-if="schedule">
          <div class="form-group">
            <label class="form-label">抓取间隔（小时）</label>
            <input v-model.number="schedule.fetch_interval_hours" type="number" class="input" min="1" max="24" />
          </div>
          <div class="form-group">
            <label class="form-label">日报生成时间（24h）</label>
            <input v-model.number="schedule.daily_brief_hour" type="number" class="input" min="0" max="23" />
          </div>
          <div class="form-group">
            <label class="form-label">每次最大抓取数</label>
            <input v-model.number="schedule.max_articles_per_fetch" type="number" class="input" min="5" max="100" />
          </div>
          <div class="form-group">
            <label class="form-label">文章保留天数</label>
            <input v-model.number="schedule.article_retention_days" type="number" class="input" min="7" max="365" />
          </div>
          <button class="btn btn-primary" @click="saveSchedule">
            💾 保存调度设置
          </button>
        </div>
      </section>

      <!-- 数据管理 -->
      <section class="card settings-section">
        <h2>🗃️ 数据管理</h2>
        <p class="section-desc">数据库统计和维护操作</p>

        <div class="stats-grid" v-if="stats">
          <div class="stat-card">
            <span class="stat-number">{{ stats.total }}</span>
            <span class="stat-desc">文章总数</span>
          </div>
          <div class="stat-card">
            <span class="stat-number">{{ stats.embedded }}</span>
            <span class="stat-desc">已向量化</span>
          </div>
          <div class="stat-card">
            <span class="stat-number accent">{{ stats.today_new }}</span>
            <span class="stat-desc">今日新增</span>
          </div>
          <div class="stat-card">
            <span class="stat-number">{{ stats.sources?.length || 0 }}</span>
            <span class="stat-desc">来源数</span>
          </div>
        </div>

        <div class="data-actions">
          <button class="btn" @click="runPipeline" :disabled="pipelineRunning">
            {{ pipelineRunning ? '执行中...' : '🔄 手动执行 Pipeline' }}
          </button>
        </div>
      </section>
    </div>

    <!-- Toast -->
    <div v-if="toast.show" :class="['toast', 'toast-' + toast.type]">
      {{ toast.message }}
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { settingsApi, newsApi } from '../api'

const feeds = ref([])
const sites = ref([])
const schedule = ref(null)
const stats = ref(null)
const pipelineRunning = ref(false)
const newFeed = ref({ name: '', url: '' })
const newSite = ref({ name: '', url: '', max_pages: 20, link_selector: '' })
const toast = ref({ show: false, message: '', type: 'info' })

function showToast(message, type = 'info') {
  toast.value = { show: true, message, type }
  setTimeout(() => { toast.value.show = false }, 3000)
}

// ========== RSS 源 ==========
async function fetchFeeds() {
  try {
    const res = await settingsApi.getFeeds()
    feeds.value = res.data.feeds || []
  } catch (e) {
    showToast('获取 RSS 源失败', 'error')
  }
}

async function addFeed() {
  try {
    await settingsApi.addFeed({ name: newFeed.value.name, url: newFeed.value.url })
    showToast('来源添加成功', 'success')
    newFeed.value = { name: '', url: '' }
    fetchFeeds()
  } catch (e) {
    showToast(e.response?.data?.detail || '添加失败', 'error')
  }
}

async function deleteFeed(feed) {
  if (!confirm(`确定要删除「${feed.name}」吗？`)) return
  try {
    await settingsApi.deleteFeed(feed.id)
    showToast('已删除: ' + feed.name, 'success')
    fetchFeeds()
  } catch (e) {
    showToast('删除失败', 'error')
  }
}

// ========== 网页爬取源 ==========
async function fetchSites() {
  try {
    const res = await settingsApi.getSites()
    sites.value = res.data.sites || []
  } catch (e) {
    showToast('获取爬取源失败', 'error')
  }
}

async function addSite() {
  try {
    await settingsApi.addSite({
      name: newSite.value.name,
      url: newSite.value.url,
      max_pages: newSite.value.max_pages || 20,
      link_selector: newSite.value.link_selector || '',
    })
    showToast('爬取源添加成功', 'success')
    newSite.value = { name: '', url: '', max_pages: 20, link_selector: '' }
    fetchSites()
  } catch (e) {
    showToast(e.response?.data?.detail || '添加失败', 'error')
  }
}

async function deleteSite(site) {
  if (!confirm(`确定要删除「${site.name}」吗？`)) return
  try {
    await settingsApi.deleteSite(site.id)
    showToast('已删除: ' + site.name, 'success')
    fetchSites()
  } catch (e) {
    showToast('删除失败', 'error')
  }
}

// ========== 调度 & 数据 ==========
async function fetchSchedule() {
  try {
    const res = await settingsApi.getSchedule()
    schedule.value = res.data
  } catch (e) {
    showToast('获取调度配置失败', 'error')
  }
}

async function saveSchedule() {
  try {
    await settingsApi.updateSchedule(schedule.value)
    showToast('调度配置已保存', 'success')
  } catch (e) {
    showToast('保存失败', 'error')
  }
}

async function fetchStats() {
  try {
    const res = await newsApi.getStats()
    stats.value = res.data
  } catch {
    // 静默处理
  }
}

async function runPipeline() {
  pipelineRunning.value = true
  try {
    const res = await newsApi.runPipeline()
    const r = res.data.result
    showToast(`Pipeline 完成！新增 ${r.new} 篇`, 'success')
    fetchStats()
  } catch (e) {
    showToast('执行失败: ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    pipelineRunning.value = false
  }
}

onMounted(() => {
  fetchFeeds()
  fetchSites()
  fetchSchedule()
  fetchStats()
})
</script>

<style scoped>
.settings-grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.settings-section h2 {
  margin-bottom: var(--space-xs);
}
.section-desc {
  color: var(--text-muted);
  font-size: 0.875rem;
  margin-bottom: var(--space-lg);
}

.feed-form {
  display: flex;
  gap: var(--space-sm);
  margin-bottom: var(--space-lg);
}
.feed-form .input:first-child {
  width: 200px;
  flex-shrink: 0;
}
.feed-form .input:nth-child(2) {
  flex: 1;
}

.feed-url {
  font-size: 0.8125rem;
  color: var(--text-muted);
  word-break: break-all;
}

.site-form {
  display: flex;
  gap: var(--space-sm);
  margin-bottom: var(--space-md);
}
.site-form .input:first-child {
  width: 160px;
  flex-shrink: 0;
}
.site-form .input:nth-child(2) {
  flex: 1;
}
.site-form .input-sm {
  width: 100px;
  flex-shrink: 0;
}

.advanced-options {
  margin-bottom: var(--space-lg);
  font-size: 0.875rem;
  color: var(--text-muted);
}
.advanced-options summary {
  cursor: pointer;
  user-select: none;
}

.selector-tag {
  display: inline-block;
  margin-left: var(--space-xs);
  padding: 1px 6px;
  font-size: 0.7rem;
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-family: monospace;
}

.schedule-form {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--space-md);
}
.schedule-form .btn {
  grid-column: 1 / -1;
  justify-self: start;
  margin-top: var(--space-sm);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}
.stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-md);
  background: var(--bg-input);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
}
.stat-number {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--text-primary);
}
.stat-number.accent {
  color: var(--accent-primary);
}
.stat-desc {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 2px;
}

.data-actions {
  display: flex;
  gap: var(--space-md);
}

@media (max-width: 768px) {
  .feed-form,
  .site-form {
    flex-direction: column;
  }
  .feed-form .input:first-child,
  .site-form .input:first-child {
    width: 100%;
  }
  .site-form .input-sm {
    width: 100%;
  }
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
