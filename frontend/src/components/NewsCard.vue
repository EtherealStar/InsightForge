<template>
  <div 
    class="news-card" 
    :class="{ 'card-selectable': selectable, 'card-selected': selected }" 
    @click="$emit('click', article)"
  >
    <div v-if="selectable" class="card-selection-layer">
      <input type="checkbox" :checked="selected" @click.stop="$emit('toggleSelect')" />
    </div>
    <div class="card-header">
      <div class="card-meta">
        <span class="tag source-tag">{{ article.source }}</span>
        <span class="tag lang-tag">{{ languageLabel }}</span>
      </div>
      <span class="card-time">{{ timeAgo }}</span>
    </div>
    <h3 class="card-title">{{ article.title }}</h3>
    <p class="card-summary">{{ displaySummary }}</p>
    <div class="card-tags" v-if="article.tags && article.tags.length">
      <span v-for="tag in article.tags" :key="tag" class="card-tag">{{ tag }}</span>
    </div>
    <div class="card-footer">
      <span class="card-status" :class="'badge-' + statusType">{{ statusLabel }}</span>
      <span class="card-link" @click.stop>
        <a :href="article.url" target="_blank" rel="noopener">原文 ↗</a>
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  article: { type: Object, required: true },
  selectable: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
})

defineEmits(['click', 'toggleSelect'])

const languageLabel = computed(() => {
  const map = { zh: '中文', en: '英文', unknown: '未知' }
  return map[props.article.language] || props.article.language
})

const statusType = computed(() => {
  const map = { embedded: 'success', summarized: 'success', stored: 'info', pending_summary: 'warning', raw: 'warning' }
  return map[props.article.status] || 'info'
})

const statusLabel = computed(() => {
  const map = { embedded: '已向量化', summarized: '已摘要', stored: '已存储', pending_summary: '待摘要', raw: '未处理' }
  return map[props.article.status] || props.article.status
})

const displaySummary = computed(() => {
  const text = props.article.summary || props.article.content_preview || props.article.content || ''
  return text.length > 150 ? text.slice(0, 150) + '...' : text
})

const timeAgo = computed(() => {
  const pub = props.article.published_at || props.article.created_at
  if (!pub) return ''
  const diff = Date.now() - new Date(pub).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins} 分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  return `${days} 天前`
})
</script>

<style scoped>
.news-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-lg);
  cursor: pointer;
  transition: all var(--transition-base);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  position: relative;
}
.news-card:hover {
  border-color: var(--border-hover);
  box-shadow: var(--shadow-md), var(--shadow-glow);
  transform: translateY(-2px);
}

.card-selectable {
  transition: border-color 0.2s, box-shadow 0.2s;
}
.card-selected {
  border-color: var(--accent-primary);
  background: var(--accent-glow);
  box-shadow: var(--shadow-glow);
}

.card-selection-layer {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 10;
}
.card-selection-layer input[type="checkbox"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
  accent-color: var(--accent-primary);
}


.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
}
.card-meta {
  display: flex;
  gap: var(--space-xs);
}
.source-tag {
  background: var(--accent-glow);
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}
.card-time {
  font-size: 0.75rem;
  color: var(--text-muted);
  flex-shrink: 0;
}

.card-title {
  font-size: 1rem;
  font-weight: 600;
  line-height: 1.4;
  color: var(--text-primary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-summary {
  font-size: 0.8125rem;
  color: var(--text-secondary);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: var(--space-xs);
}
.card-status {
  font-size: 0.6875rem;
  padding: 2px 8px;
  border-radius: 999px;
}
.card-link a {
  font-size: 0.75rem;
  color: var(--text-muted);
  transition: color var(--transition-fast);
}
.card-link a:hover {
  color: var(--accent-primary);
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.card-tag {
  font-size: 0.6875rem;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--accent-glow);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  white-space: nowrap;
}
</style>
