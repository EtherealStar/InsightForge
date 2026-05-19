<template>
  <span class="status-badge" :class="[`status-${tone}`, `status-kind-${kind}`]">
    {{ displayLabel }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  kind: { type: String, default: 'generic' },
  status: { type: [String, Number, null], default: '' },
  label: { type: String, default: '' },
})

const labels = {
  report: {
    draft: '草稿',
    quality_reviewing: '质检中',
    revision_required: '需修订',
    waiting_review: '待审批',
    approved: '已审批',
    published: '已发布',
    rejected: '已拒绝',
    archived: '已归档',
  },
  review: {
    not_reviewed: '未质检',
    passed: '已通过',
    failed: '未通过',
    needs_human: '需人工复核',
  },
  task: {
    queued: '排队中',
    running: '运行中',
    retrying: '重试中',
    succeeded: '成功',
    failed: '失败',
    cancelled: '已取消',
    waiting_review: '待复核',
    SUCCESS: '成功',
    FAILURE: '失败',
    PENDING: '排队中',
    STARTED: '运行中',
  },
  fact: {
    draft: '草稿',
    active: '有效',
    rejected: '已拒绝',
    archived: '已归档',
  },
}

const toneMap = {
  draft: 'neutral',
  not_reviewed: 'neutral',
  archived: 'neutral',
  queued: 'neutral',
  PENDING: 'neutral',
  active: 'success',
  passed: 'success',
  approved: 'success',
  published: 'success',
  succeeded: 'success',
  SUCCESS: 'success',
  waiting_review: 'info',
  quality_reviewing: 'info',
  running: 'info',
  STARTED: 'info',
  needs_human: 'warning',
  revision_required: 'warning',
  retrying: 'warning',
  failed: 'danger',
  FAILURE: 'danger',
  rejected: 'danger',
  cancelled: 'danger',
}

const normalized = computed(() => String(props.status || '').trim())
const displayLabel = computed(() => {
  if (props.label) return props.label
  return labels[props.kind]?.[normalized.value] || normalized.value || '未知'
})
const tone = computed(() => toneMap[normalized.value] || 'neutral')
</script>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  min-height: 22px;
  padding: 2px 8px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1.3;
  white-space: nowrap;
}
.status-neutral {
  background: var(--bg-input);
  color: var(--text-secondary);
}
.status-success {
  background: rgba(16, 185, 129, 0.12);
  border-color: rgba(16, 185, 129, 0.35);
  color: var(--success);
}
.status-info {
  background: rgba(59, 130, 246, 0.12);
  border-color: rgba(59, 130, 246, 0.35);
  color: var(--info);
}
.status-warning {
  background: rgba(245, 158, 11, 0.12);
  border-color: rgba(245, 158, 11, 0.35);
  color: var(--warning);
}
.status-danger {
  background: rgba(239, 68, 68, 0.12);
  border-color: rgba(239, 68, 68, 0.35);
  color: var(--error);
}
</style>
