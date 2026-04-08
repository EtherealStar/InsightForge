<template>
  <div class="config-view">
    <div class="page-header">
      <div>
        <h1>🔧 API 配置</h1>
        <p class="subtitle">编辑 .env 文件，配置 LLM 和 Embedding API</p>
      </div>
      <button class="btn btn-primary" @click="saveConfig" :disabled="saving">
        {{ saving ? '保存中...' : '💾 保存配置' }}
      </button>
    </div>

    <div class="config-grid" v-if="config">
      <!-- LLM 配置 -->
      <section class="card config-section">
        <h2>🤖 LLM 模型配置</h2>
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
                {{ fetchingModels ? '获取中...' : '⚡ 获取模型列表' }}
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
        <h2>🧬 Embedding 配置</h2>
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
        </div>
      </section>

      <!-- 其他设置 -->
      <section class="card config-section">
        <h2>📝 其他设置</h2>
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
            <label class="form-label">文章保留天数</label>
            <input v-model.number="config.article_retention_days" type="number" class="input" min="7" max="365" />
          </div>
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

const config = ref(null)
const providers = ref([])
const saving = ref(false)
const toast = ref({ show: false, message: '', type: 'info' })

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
  } catch (e) {
    showToast('获取配置失败: ' + e.message, 'error')
  }
}

async function saveConfig() {
  saving.value = true
  try {
    await configApi.update(config.value)
    showToast('配置已保存！重启后端以加载新配置。', 'success')
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
</style>
