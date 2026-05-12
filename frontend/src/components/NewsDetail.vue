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
          <button class="btn btn-icon" @click="$emit('close')" title="关闭"></button>
        </div>

        <h1 class="detail-title">{{ article.title }}</h1>

        <div class="detail-actions">
          <a :href="article.url" target="_blank" rel="noopener" class="btn btn-sm">
             查看原文
          </a>
        </div>

        <hr class="divider" />

        <div class="detail-body" v-if="article.content">
          <div class="markdown-body" v-html="renderedContent"></div>
        </div>
        <div class="detail-body" v-else-if="article.summary">
          <div class="markdown-body" v-html="renderedSummary"></div>
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

function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function sanitizeHtml(html) {
  const template = document.createElement('template')
  template.innerHTML = html

  const blockedTags = new Set(['script', 'style', 'iframe', 'object', 'embed', 'form'])
  const urlAttributes = new Set(['href', 'src', 'xlink:href'])
  const walker = document.createTreeWalker(template.content, NodeFilter.SHOW_ELEMENT)
  const nodes = []
  while (walker.nextNode()) nodes.push(walker.currentNode)

  for (const node of nodes) {
    const tagName = node.tagName.toLowerCase()
    if (blockedTags.has(tagName)) {
      node.remove()
      continue
    }

    for (const attr of [...node.attributes]) {
      const name = attr.name.toLowerCase()
      const value = attr.value.trim().toLowerCase()
      const unsafeUrl = urlAttributes.has(name) &&
        (value.startsWith('javascript:') || value.startsWith('data:text/html'))
      if (name.startsWith('on') || name === 'style' || name === 'srcdoc' || unsafeUrl) {
        node.removeAttribute(attr.name)
      }
    }
  }

  return template.innerHTML
}

function renderMarkdown(text) {
  try {
    return sanitizeHtml(marked.parse(text || '', { async: false }))
  } catch {
    return `<p>${escapeHtml(text || '')}</p>`
  }
}

const renderedContent = computed(() => {
  return renderMarkdown(props.article.content || '')
})

const renderedSummary = computed(() => {
  return renderMarkdown(props.article.summary || '')
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
