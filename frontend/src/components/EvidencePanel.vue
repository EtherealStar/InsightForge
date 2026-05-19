<template>
  <section class="evidence-panel">
    <header class="panel-header">
      <div>
        <h3>{{ title }}</h3>
        <span>{{ items.length }} 条证据</span>
      </div>
      <SvgIcon name="evidence" :size="20" />
    </header>

    <EmptyState
      v-if="!items.length"
      icon="evidence"
      title="暂无证据"
      message="当前对象尚未返回 evidence refs。"
    />
    <div v-else class="evidence-list">
      <a
        v-for="item in items"
        :key="item.id || item.evidence_ref_id || item.citation_label || item.url"
        class="evidence-item"
        :class="{ active: activeKey && itemKey(item) === activeKey }"
        :href="item.url || undefined"
        target="_blank"
        rel="noreferrer"
        @click="$emit('select', item)"
      >
        <strong>{{ item.citation_label || item.evidence_ref_id || item.fact_id || 'Evidence' }}</strong>
        <span>{{ item.title || item.url || item.source_document_id || '未命名来源' }}</span>
        <small v-if="item.snippet">{{ item.snippet }}</small>
      </a>
    </div>
  </section>
</template>

<script setup>
import SvgIcon from './icons/SvgIcon.vue'
import EmptyState from './EmptyState.vue'

defineProps({
  title: { type: String, default: 'Evidence' },
  items: { type: Array, default: () => [] },
  activeKey: { type: String, default: '' },
})
defineEmits(['select'])

function itemKey(item) {
  return String(item.id || item.evidence_ref_id || item.citation_label || item.url || '')
}
</script>

<style scoped>
.evidence-panel {
  min-width: 0;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  margin-bottom: var(--space-sm);
}
.panel-header h3 {
  margin: 0;
}
.panel-header span {
  display: block;
  margin-top: 2px;
  color: var(--text-muted);
  font-size: 0.75rem;
}
.evidence-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}
.evidence-item {
  display: block;
  padding: var(--space-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  text-decoration: none;
}
.evidence-item:hover {
  border-color: var(--border-hover);
}
.evidence-item.active {
  border-color: var(--accent-primary);
  background: var(--accent-glow);
}
.evidence-item span,
.evidence-item small {
  display: block;
  margin-top: 4px;
  color: var(--text-muted);
  word-break: break-word;
}
.evidence-item small {
  line-height: 1.45;
}
</style>
