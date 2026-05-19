<template>
  <section class="audit-timeline">
    <header v-if="title" class="panel-header">
      <h3>{{ title }}</h3>
      <span>{{ items.length }} 条记录</span>
    </header>
    <EmptyState
      v-if="!items.length"
      icon="task"
      title="暂无审计记录"
      message="当前对象尚未返回 audit trail。"
    />
    <ol v-else>
      <li v-for="item in items" :key="item.id || item.created_at || item.action">
        <strong>{{ item.action || item.event_type || 'audit' }}</strong>
        <span>{{ formatTime(item.created_at || item.timestamp) }}</span>
        <p v-if="item.actor || item.message">{{ item.actor || item.message }}</p>
      </li>
    </ol>
  </section>
</template>

<script setup>
import EmptyState from './EmptyState.vue'

defineProps({
  title: { type: String, default: 'Audit' },
  items: { type: Array, default: () => [] },
})

function formatTime(value) {
  if (!value) return ''
  try {
    return new Date(value).toLocaleString('zh-CN')
  } catch {
    return String(value)
  }
}
</script>

<style scoped>
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  margin-bottom: var(--space-sm);
}
.panel-header span {
  color: var(--text-muted);
  font-size: 0.75rem;
}
.audit-timeline ol {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  margin: 0;
  padding: 0;
  list-style: none;
}
.audit-timeline li {
  padding: var(--space-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
}
.audit-timeline strong,
.audit-timeline span,
.audit-timeline p {
  display: block;
}
.audit-timeline span,
.audit-timeline p {
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 0.8125rem;
}
</style>
