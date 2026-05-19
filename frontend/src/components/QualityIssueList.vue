<template>
  <section class="quality-issues">
    <header class="panel-header">
      <div>
        <h3>{{ title }}</h3>
        <span>{{ issues.length }} 个问题</span>
      </div>
      <SvgIcon name="warning" :size="20" />
    </header>
    <EmptyState
      v-if="!issues.length"
      icon="quality"
      title="暂无质量问题"
      message="最近一次质量门禁未返回 blocker、major 或 minor 问题。"
    />
    <ul v-else>
      <li
        v-for="(issue, index) in issues"
        :key="issue.id || index"
        :class="`issue-${issue.severity || 'minor'}`"
        @click="$emit('select', issue)"
      >
        <div class="issue-topline">
          <strong>{{ issue.category || issue.severity || 'issue' }}</strong>
          <span>{{ issue.severity || 'minor' }}</span>
        </div>
        <p>{{ issue.message || issue.description || '未提供问题描述' }}</p>
        <small v-if="issue.section_key || issue.claim_id || issue.evidence_ref_id">
          {{ issue.section_key || issue.claim_id || issue.evidence_ref_id }}
        </small>
      </li>
    </ul>
  </section>
</template>

<script setup>
import SvgIcon from './icons/SvgIcon.vue'
import EmptyState from './EmptyState.vue'

defineProps({
  title: { type: String, default: '质量问题' },
  issues: { type: Array, default: () => [] },
})
defineEmits(['select'])
</script>

<style scoped>
.panel-header {
  display: flex;
  justify-content: space-between;
  gap: var(--space-md);
  margin-bottom: var(--space-sm);
}
.panel-header span {
  display: block;
  margin-top: 2px;
  color: var(--text-muted);
  font-size: 0.75rem;
}
.quality-issues ul {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  margin: 0;
  padding: 0;
  list-style: none;
}
.quality-issues li {
  padding: var(--space-sm);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  cursor: pointer;
}
.quality-issues li:hover { border-color: var(--border-hover); }
.quality-issues li.issue-blocker {
  border-color: rgba(239, 68, 68, 0.5);
}
.issue-topline {
  display: flex;
  justify-content: space-between;
  gap: var(--space-sm);
  margin-bottom: 4px;
}
.issue-topline span,
.quality-issues small {
  color: var(--text-muted);
  font-size: 0.75rem;
}
.quality-issues p {
  color: var(--text-secondary);
  line-height: 1.45;
}
</style>
