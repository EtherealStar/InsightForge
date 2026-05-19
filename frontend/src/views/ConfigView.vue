<template>
  <div class="config-view">
    <div class="page-header">
      <div>
        <h1><SvgIcon name="config" :size="24" /> API 配置</h1>
        <p class="subtitle">管理模型、搜索、结构化抽取、质量门禁和安全策略</p>
      </div>
      <button v-if="isAdmin" class="btn btn-primary" @click="saveConfig" :disabled="saving">
        <SvgIcon name="approve" :size="16" />
        {{ saving ? '保存中...' : '保存配置' }}
      </button>
    </div>

    <div class="config-grid" v-if="config">
      <!-- LLM 配置 -->
      <section class="card config-section">
        <h2>LLM 模型配置</h2>
        <p class="section-desc">选择 AI 模型提供商并配置连接参数</p>

        <!-- Provider 选择 -->
        <div class="provider-selector">
          <div
            v-for="provider in providers"
            :key="provider.id"
            class="provider-card"
            :class="{ active: config.llm_provider === provider.id }"
            @click="config.llm_provider = provider.id"
          >
            <div class="provider-name">{{ provider.name }}</div>
            <div class="provider-desc">{{ provider.description }}</div>
          </div>
        </div>

        <!-- 动态字段 -->
        <div class="config-fields">
          <div v-if="activeProvider?.fields.includes('llm_api_key')" class="form-group">
            <label class="form-label">API Key</label>
            <input v-model="config.llm_api_key" class="input" type="password" placeholder="输入 API Key" />
          </div>
          <div v-if="activeProvider?.fields.includes('llm_base_url')" class="form-group">
            <label class="form-label">Base URL</label>
            <input v-model="config.llm_base_url" class="input" placeholder="https://your-endpoint.com/v1" />
          </div>
          <div v-if="activeProvider?.fields.includes('openai_api_key')" class="form-group">
            <label class="form-label">OpenAI API Key</label>
            <input v-model="config.openai_api_key" class="input" type="password" placeholder="sk-..." />
          </div>
          <div v-if="activeProvider?.fields.includes('google_api_key')" class="form-group">
            <label class="form-label">Google API Key</label>
            <input v-model="config.google_api_key" class="input" type="password" />
          </div>
          <div v-if="activeProvider?.fields.includes('anthropic_api_key')" class="form-group">
            <label class="form-label">Anthropic API Key</label>
            <input v-model="config.anthropic_api_key" class="input" type="password" />
          </div>
          <div v-if="activeProvider?.fields.includes('llm_model')" class="form-group" style="grid-column: 1 / -1;">
            <label class="form-label">模型名称</label>
            <div class="model-input-group">
              <input v-if="!fetchedModels.length" v-model="config.llm_model" class="input" placeholder="模型名称，如 gpt-4o-mini" style="flex: 1" />
              <select v-else v-model="config.llm_model" class="input" style="flex: 1">
                <option v-for="m in fetchedModels" :key="m" :value="m">{{ m }}</option>
              </select>
              <button class="btn btn-secondary" @click="fetchModelList" :disabled="fetchingModels" type="button" title="向服务器发送以获取可用模型列表">
                {{ fetchingModels ? '获取中...' : '获取模型列表' }}
              </button>
            </div>
            <div v-if="fetchedModels.length" class="manual-input-tip" @click="fetchedModels = []">
              不想选择？点击手动输入
            </div>
          </div>
        </div>
      </section>

      <!-- Embedding 配置 -->
      <section class="card config-section">
        <h2>Embedding 配置</h2>
        <p class="section-desc">配置向量化模型（OpenAI 兼容格式）</p>

        <div class="config-fields">
          <div class="form-group">
            <label class="form-label">Embedding API Key</label>
            <input v-model="config.embedding_api_key" class="input" type="password" placeholder="输入 API Key" />
          </div>
          <div class="form-group">
            <label class="form-label">Embedding Base URL</label>
            <input v-model="config.embedding_base_url" class="input" placeholder="https://your-embedding-endpoint.com/v1" />
          </div>
          <div class="form-group">
            <label class="form-label">Embedding 模型名称</label>
            <input v-model="config.embedding_model" class="input" placeholder="text-embedding-3-small" />
          </div>
          <div class="form-group">
            <label class="form-label">向量维度</label>
            <input v-model.number="config.embedding_vector_size" type="number" class="input" min="1" />
            <span class="field-hint">会作为 Embedding 请求的 dimensions 发送；需与当前 Qdrant collection 向量维度一致</span>
          </div>
        </div>
      </section>

      <!-- Rerank 重排序配置 -->
      <section class="card config-section">
        <h2>Rerank 重排序配置</h2>
        <p class="section-desc">配置 Rerank 大模型对检索结果精排，提升知识库查询准确性。支持 Jina、SiliconFlow、Cohere 等 Rerank API</p>

        <div class="config-fields">
          <div class="form-group" style="grid-column: 1 / -1;">
            <label class="form-label">启用状态</label>
            <div class="summary-toggle">
              <label class="toggle-label">
                <input type="checkbox" v-model="config.rerank_enabled" />
                <span>启用 Rerank 重排序</span>
              </label>
              <span class="toggle-hint" v-if="config.rerank_enabled">检索结果将经过 Rerank 模型精排</span>
              <span class="toggle-hint" v-else>仅使用向量相似度排序</span>
            </div>
          </div>
        </div>

        <div class="config-fields" v-if="config.rerank_enabled">
          <div class="form-group">
            <label class="form-label">Rerank API Key</label>
            <input v-model="config.rerank_api_key" class="input" type="password" placeholder="输入 Rerank API Key" />
          </div>
          <div class="form-group">
            <label class="form-label">Rerank Base URL</label>
            <input v-model="config.rerank_base_url" class="input" placeholder="https://api.jina.ai/v1" />
          </div>
          <div class="form-group">
            <label class="form-label">Rerank 模型名称</label>
            <input v-model="config.rerank_model" class="input" placeholder="jina-reranker-v2-base-multilingual" />
          </div>
          <div class="form-group">
            <label class="form-label">候选召回倍数</label>
            <input v-model.number="config.rerank_top_k_multiplier" type="number" class="input" min="1" max="10" />
            <span class="field-hint">Rerank 前的候选数量 = 最终数量 × 此倍数（建议 2-5）</span>
          </div>
        </div>

        <div class="search-engine-status" style="margin-top: var(--space-md);">
          <div class="status-item">
            <span class="status-dot" :class="{ active: config.rerank_enabled && config.rerank_api_key && config.rerank_api_key.length > 0 }"></span>
            <span>Rerank（{{ config.rerank_enabled && config.rerank_api_key && config.rerank_api_key.length > 0 ? '已启用' : '未启用' }}）</span>
          </div>
        </div>
      </section>

      <!-- 搜索引擎配置 (包含 NewsAPI) -->
      <section class="card config-section">
        <h2>搜索引擎配置</h2>
        <p class="section-desc">配置 Web 搜索引擎 API。DuckDuckGo 免费无需配置，Tavily 需要 API Key（可在 <a href="https://tavily.com" target="_blank">tavily.com</a> 获取），NewsAPI 需要 API Key（可在 <a href="https://newsapi.org" target="_blank">newsapi.org</a> 获取）</p>

        <div class="config-fields">
          <div class="form-group">
            <label class="form-label">Tavily API Key</label>
            <input v-model="config.tavily_api_key" class="input" type="password" placeholder="tvly-... (可选，不配置则仅使用 DuckDuckGo)" />
          </div>
          <div class="form-group">
            <label class="form-label">NewsAPI Key</label>
            <input v-model="config.news_api_key" class="input" type="password" placeholder="可选，配置后搜索时自动包含 NewsAPI 结果" />
          </div>
        </div>

        <div class="search-engine-status">
          <div class="status-item">
            <span class="status-dot active"></span>
            <span>DuckDuckGo（免费，始终可用）</span>
          </div>
          <div class="status-item">
            <span class="status-dot" :class="{ active: config.tavily_api_key && config.tavily_api_key.length > 0 }"></span>
            <span>Tavily（{{ config.tavily_api_key && config.tavily_api_key.length > 0 ? '已配置' : '未配置' }}）</span>
          </div>
          <div class="status-item">
            <span class="status-dot" :class="{ active: config.news_api_key && config.news_api_key.length > 0 }"></span>
            <span>NewsAPI（{{ config.news_api_key && config.news_api_key.length > 0 ? '已配置' : '未配置' }}）</span>
          </div>
        </div>
      </section>

      <!-- 结构化抽取配置 -->
      <section class="card config-section">
        <h2>结构化抽取配置</h2>
        <p class="section-desc">配置 facts/events 抽取所使用的模型。该配置独立于主 LLM，不再使用旧摘要链路。</p>

        <div class="config-fields">
          <div class="form-group" style="grid-column: 1 / -1;">
            <label class="form-label">Provider</label>
            <select v-model="config.structured_extraction_provider" class="input">
              <option value="openai_compatible">OpenAI 兼容 API</option>
              <option value="openai">OpenAI GPT</option>
              <option value="gemini">Google Gemini</option>
              <option value="anthropic">Anthropic Claude</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">API Key</label>
            <input v-model="config.structured_extraction_api_key" class="input" type="password" placeholder="结构化抽取 API Key" />
          </div>
          <div class="form-group">
            <label class="form-label">Base URL</label>
            <input v-model="config.structured_extraction_base_url" class="input" placeholder="https://your-endpoint.com/v1" />
          </div>
          <div class="form-group">
            <label class="form-label">模型名称</label>
            <input v-model="config.structured_extraction_model" class="input" placeholder="结构化抽取模型" />
          </div>
          <div class="form-group">
            <label class="form-label">Temperature</label>
            <input v-model.number="config.structured_extraction_temperature" type="number" class="input" min="0" max="2" step="0.1" />
          </div>
          <div class="form-group">
            <label class="form-label">最大 tokens</label>
            <input v-model.number="config.structured_extraction_max_tokens" type="number" class="input" min="256" max="16000" />
            <span class="field-hint">用于单次结构化 JSON 抽取响应的上限</span>
          </div>
        </div>
      </section>

      <!-- Judge 配置 -->
      <section class="card config-section">
        <h2>报告质量 Judge</h2>
        <p class="section-desc">独立于主 LLM 的报告质量审查模型。</p>
        <div class="config-fields">
          <div class="form-group">
            <label class="form-label">Provider</label>
            <select v-model="config.judge_provider" class="input">
              <option value="openai_compatible">OpenAI 兼容 API</option>
              <option value="openai">OpenAI GPT</option>
              <option value="gemini">Google Gemini</option>
              <option value="anthropic">Anthropic Claude</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">API Key</label>
            <input v-model="config.judge_api_key" class="input" type="password" placeholder="Judge API Key" />
          </div>
          <div class="form-group">
            <label class="form-label">Base URL</label>
            <input v-model="config.judge_base_url" class="input" placeholder="https://your-endpoint.com/v1" />
          </div>
          <div class="form-group">
            <label class="form-label">模型名称</label>
            <input v-model="config.judge_model" class="input" placeholder="质量审查模型" />
          </div>
          <div class="form-group">
            <label class="form-label">Temperature</label>
            <input v-model.number="config.judge_temperature" type="number" class="input" min="0" max="2" step="0.1" />
          </div>
          <div class="form-group">
            <label class="form-label">最大 tokens</label>
            <input v-model.number="config.judge_max_tokens" type="number" class="input" min="256" max="16000" />
          </div>
        </div>
      </section>

      <!-- 安全和质量策略 -->
      <section class="card config-section">
        <h2>应用安全与质量策略</h2>
        <p v-if="isProduction" class="section-desc">生产环境危险配置只读，需要通过部署环境变量修改。</p>
        <div class="config-fields">
          <div class="form-group">
            <label class="form-label">APP_ENV</label>
            <input v-model="config.app_env" class="input" :disabled="isProduction" />
          </div>
          <div class="form-group">
            <label class="form-label">启用应用认证</label>
            <label class="toggle-label">
              <input type="checkbox" v-model="config.auth_enabled" :disabled="isProduction" />
              <span>{{ config.auth_enabled ? '已启用' : '未启用' }}</span>
            </label>
          </div>
          <div class="form-group">
            <label class="form-label">质量最低分</label>
            <input v-model.number="config.report_quality_min_score" type="number" class="input" min="0" max="1" step="0.05" />
          </div>
          <div class="form-group">
            <label class="form-label">允许自动发布</label>
            <label class="toggle-label">
              <input type="checkbox" v-model="config.report_quality_auto_publish" />
              <span>{{ config.report_quality_auto_publish ? '允许' : '禁止' }}</span>
            </label>
          </div>
        </div>
      </section>

      <!-- 其他设置 -->
      <section class="card config-section">
        <h2>其他设置</h2>
        <div class="config-fields">
          <div class="form-group">
            <label class="form-label">日志级别</label>
            <select v-model="config.log_level" class="input">
              <option value="DEBUG">DEBUG</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">情报保留天数</label>
            <input v-model.number="config.article_retention_days" type="number" class="input" min="7" max="365" />
          </div>
        </div>
      </section>

      <section v-if="reloadResult" class="card config-section">
        <h2>Reload 结果</h2>
        <pre class="reload-box">{{ JSON.stringify(reloadResult, null, 2) }}</pre>
      </section>

      <section v-if="isAdmin" class="card config-section">
        <div class="audit-header">
          <h2>配置审计</h2>
          <button class="btn btn-sm" @click="fetchAudit">刷新</button>
        </div>
        <div v-if="!auditLogs.length" class="section-desc">暂无审计记录</div>
        <div v-for="log in auditLogs" :key="log.id" class="audit-item">
          <strong>{{ log.action }} · {{ log.actor }}</strong>
          <small>{{ new Date(log.created_at).toLocaleString('zh-CN') }}</small>
          <span>{{ (log.changed_keys || []).join(', ') || '无配置变化' }}</span>
        </div>
      </section>
    </div>

    <!-- Loading -->
    <div v-else class="config-loading">
      <div v-for="i in 3" :key="i" class="card">
        <div class="skeleton" style="height:20px;width:30%;margin-bottom:16px"></div>
        <div class="skeleton" style="height:14px;width:50%;margin-bottom:24px"></div>
        <div class="skeleton" style="height:38px;margin-bottom:12px"></div>
        <div class="skeleton" style="height:38px;margin-bottom:12px"></div>
      </div>
    </div>

    <!-- Toast -->
    <div v-if="toast.show" :class="['toast', 'toast-' + toast.type]">
      {{ toast.message }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { configApi } from '../api'
import { hasRole } from '../auth'
import SvgIcon from '../components/icons/SvgIcon.vue'

const config = ref(null)
const providers = ref([])
const saving = ref(false)
const toast = ref({ show: false, message: '', type: 'info' })
const auditLogs = ref([])
const reloadResult = ref(null)
const isAdmin = computed(() => hasRole('admin'))
const isProduction = computed(() => config.value?.app_env === 'production')

function showToast(message, type = 'info') {
  toast.value = { show: true, message, type }
  setTimeout(() => { toast.value.show = false }, 3000)
}

const activeProvider = computed(() => {
  if (!config.value || !providers.value.length) return null
  return providers.value.find(p => p.id === config.value.llm_provider)
})

const fetchingModels = ref(false)
const fetchedModels = ref([])

watch(() => config.value?.llm_provider, () => {
  fetchedModels.value = []
})

async function fetchModelList() {
  if (!activeProvider.value) return
  fetchingModels.value = true
  
  let apiKey = ''
  let baseUrl = ''
  
  if (activeProvider.value.id === 'openai_compatible') {
    apiKey = config.value.llm_api_key
    baseUrl = config.value.llm_base_url
  } else if (activeProvider.value.id === 'openai') {
    apiKey = config.value.openai_api_key
  } else if (activeProvider.value.id === 'gemini') {
    apiKey = config.value.google_api_key
  } else if (activeProvider.value.id === 'anthropic') {
    apiKey = config.value.anthropic_api_key
  }

  try {
    const res = await configApi.fetchModels({
      provider: activeProvider.value.id,
      api_key: apiKey,
      base_url: baseUrl
    })
    fetchedModels.value = res.data.models
    if (fetchedModels.value.length > 0 && !fetchedModels.value.includes(config.value.llm_model)) {
      config.value.llm_model = fetchedModels.value[0]
    }
    showToast('获取模型列表成功', 'success')
  } catch(e) {
    showToast(e.response?.data?.detail || '获取失败', 'error')
  } finally {
    fetchingModels.value = false
  }
}

async function fetchConfig() {
  try {
    const [configRes, providerRes] = await Promise.all([
      configApi.get(),
      configApi.getProviders(),
    ])
    config.value = configRes.data
    providers.value = providerRes.data.providers
    if (isAdmin.value) {
      await fetchAudit()
    }
  } catch (e) {
    showToast('获取配置失败: ' + e.message, 'error')
  }
}

async function fetchAudit() {
  try {
    const res = await configApi.audit({ limit: 20 })
    auditLogs.value = res.data.items || []
  } catch (e) {
    showToast('获取配置审计失败: ' + (e.response?.data?.detail || e.message), 'error')
  }
}

async function saveConfig() {
  saving.value = true
  try {
    const res = await configApi.update(config.value)
    reloadResult.value = res.data.reload || null
    await fetchAudit()
    showToast('配置已保存并立即生效。', 'success')
  } catch (e) {
    showToast('保存失败: ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    saving.value = false
  }
}

onMounted(fetchConfig)
</script>

<style scoped>
.config-grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.config-section h2 {
  margin-bottom: var(--space-xs);
}
.section-desc {
  color: var(--text-muted);
  font-size: 0.875rem;
  margin-bottom: var(--space-lg);
}

.provider-selector {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}

.provider-card {
  padding: var(--space-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  background: var(--bg-input);
}
.provider-card:hover {
  border-color: var(--border-hover);
}
.provider-card.active {
  border-color: var(--accent-primary);
  background: var(--accent-glow);
  box-shadow: var(--shadow-glow);
}
.provider-name {
  font-weight: 600;
  font-size: 0.9375rem;
  margin-bottom: var(--space-xs);
}
.provider-desc {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.config-fields {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-md);
}

.config-loading {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}
.reload-box {
  padding: var(--space-md);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-secondary);
  overflow: auto;
}
.audit-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-md);
}
.audit-item {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: var(--space-xs) var(--space-md);
  padding: var(--space-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  margin-bottom: var(--space-xs);
}
.audit-item span {
  grid-column: 1 / -1;
  color: var(--text-muted);
}

.model-input-group {
  display: flex;
  gap: var(--space-sm);
  align-items: center;
}

.manual-input-tip {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 6px;
  cursor: pointer;
  display: inline-block;
}
.manual-input-tip:hover {
  text-decoration: underline;
  color: var(--accent-primary);
}

.search-engine-status {
  display: flex;
  gap: var(--space-lg);
  margin-top: var(--space-md);
  padding: var(--space-md);
  background: var(--bg-input);
  border-radius: var(--radius-sm);
}
.status-item {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  font-size: 0.875rem;
  color: var(--text-muted);
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
  opacity: 0.4;
  transition: all var(--transition-fast);
}
.status-dot.active {
  background: #10b981;
  opacity: 1;
  box-shadow: 0 0 6px rgba(16, 185, 129, 0.4);
}

.summary-toggle {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}
.toggle-label {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  cursor: pointer;
  font-size: 0.9375rem;
  color: var(--text-primary);
}
.toggle-label input[type="checkbox"] {
  width: 18px;
  height: 18px;
  accent-color: var(--accent-primary);
  cursor: pointer;
}
.toggle-hint {
  font-size: 0.75rem;
  color: var(--text-muted);
  font-style: italic;
}
.field-hint {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 2px;
}
</style>
