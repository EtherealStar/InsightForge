<template>
  <teleport to="body">
    <div class="modal-overlay" @click.self="$emit('close')">
      <div class="modal-content news-detail">
        <div class="detail-header">
          <div class="detail-meta">
            <span class="tag source-tag">{{ article.source }}</span>
            <span class="tag">{{ languageLabel }}</span>
            <span class="detail-time">{{ formattedDate }}</span>
          </div>
          <button class="btn btn-icon" @click="$emit('close')" title="关闭">✕</button>
        </div>

        <h1 class="detail-title">{{ article.title }}</h1>

        <div class="detail-actions">
          <a :href="article.url" target="_blank" rel="noopener" class="btn btn-sm">
            🔗 查看原文
          </a>
        </div>

        <hr class="divider" />

        <div class="detail-body" v-if="article.html_content || article.content">
          <iframe 
            :srcdoc="article.html_content || article.content" 
            sandbox="allow-same-origin allow-scripts"
            style="width: 100%; height: 60vh; border: none; background: #fff;"
          ></iframe>
        </div>
        <div class="detail-body" v-else-if="article.summary">
          <div class="markdown-body" v-html="renderedContent"></div>
        </div>
        <div class="detail-body" v-else>
          <p class="text-muted">暂无全文内容</p>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { computed } from 'vue'
import { marked } from 'marked'

const props = defineProps({
  article: { type: Object, required: true },
})
defineEmits(['close'])

const languageLabel = computed(() => {
  const map = { zh: '中文', en: '英文', unknown: '未知' }
  return map[props.article.language] || props.article.language
})

const formattedDate = computed(() => {
  const d = props.article.published_at || props.article.created_at
  if (!d) return ''
  return new Date(d).toLocaleString('zh-CN')
})

const fullContent = computed(() => {
  return props.article.summary || ''
})

const renderedContent = computed(() => {
  // 尝试用 markdown 渲染，纯文本也能正常显示
  try {
    return marked(fullContent.value)
  } catch {
    return `<p>${fullContent.value}</p>`
  }
})
</script>

<style scoped>
.news-detail {
  max-width: 900px;
  width: 95%;
}

.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-md);
}

.detail-meta {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  flex-wrap: wrap;
}
.source-tag {
  background: var(--accent-glow);
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}
.detail-time {
  font-size: 0.8125rem;
  color: var(--text-muted);
}

.detail-title {
  font-size: 1.5rem;
  line-height: 1.4;
  margin: var(--space-lg) 0 var(--space-md);
}

.detail-actions {
  margin-bottom: var(--space-sm);
}

.detail-body {
  max-height: 60vh;
  overflow-y: auto;
  padding-right: var(--space-sm);
}

.text-muted {
  color: var(--text-muted);
  font-style: italic;
}
</style>
