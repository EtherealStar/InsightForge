<template>
  <div class="loading-state-block">
    <span class="spinner" />
    <span>{{ message }}</span>
  </div>
</template>

<script setup>
defineProps({
  message: { type: String, default: '加载中...' },
})
</script>

<style scoped>
.loading-state-block {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  min-height: 120px;
  padding: var(--space-lg);
  color: var(--text-secondary);
}
</style>
