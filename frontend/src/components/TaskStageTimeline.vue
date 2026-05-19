<template>
  <section class="task-stage-timeline">
    <div v-if="!stages.length" class="timeline-empty">{{ emptyText }}</div>
    <ol v-else>
      <li v-for="stage in stages" :key="stage.id || stage.stage_name || stage.name">
        <span class="timeline-marker" :class="statusTone(stage.status)" />
        <div>
          <div class="stage-topline">
            <strong>{{ stage.stage_name || stage.name || 'stage' }}</strong>
            <StatusBadge kind="task" :status="stage.status" />
          </div>
          <p v-if="stage.error">{{ stage.error }}</p>
          <small>{{ formatDuration(stage) }}</small>
        </div>
      </li>
    </ol>
  </section>
</template>

<script setup>
import StatusBadge from './StatusBadge.vue'

defineProps({
  stages: { type: Array, default: () => [] },
  emptyText: { type: String, default: '暂无阶段信息' },
})

function statusTone(status) {
  if (['succeeded', 'SUCCESS'].includes(status)) return 'success'
  if (['failed', 'FAILURE', 'cancelled'].includes(status)) return 'danger'
  if (['running', 'STARTED'].includes(status)) return 'info'
  return 'neutral'
}

function formatDuration(stage) {
  if (stage.duration_ms !== undefined && stage.duration_ms !== null) return `${stage.duration_ms} ms`
  if (stage.started_at && stage.completed_at) {
    const delta = new Date(stage.completed_at).getTime() - new Date(stage.started_at).getTime()
    if (Number.isFinite(delta) && delta >= 0) return `${Math.round(delta / 1000)} s`
  }
  return stage.created_at || stage.started_at || ''
}
</script>

<style scoped>
.task-stage-timeline ol {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin: 0;
  padding: 0;
  list-style: none;
}
.task-stage-timeline li {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  gap: var(--space-sm);
}
.timeline-marker {
  width: 10px;
  height: 10px;
  margin-top: 6px;
  border-radius: 999px;
  background: var(--text-muted);
}
.timeline-marker.success { background: var(--success); }
.timeline-marker.info { background: var(--info); }
.timeline-marker.danger { background: var(--error); }
.stage-topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
}
.stage-topline strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-stage-timeline p {
  margin-top: 4px;
  color: var(--error);
  font-size: 0.8125rem;
}
.task-stage-timeline small,
.timeline-empty {
  color: var(--text-muted);
  font-size: 0.8125rem;
}
</style>
