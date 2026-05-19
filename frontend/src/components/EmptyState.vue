<template>
  <div class="empty-state-block">
    <SvgIcon v-if="icon" :name="icon" :size="32" />
    <h3 v-if="title">{{ title }}</h3>
    <p v-if="message">{{ message }}</p>
    <slot />
  </div>
</template>

<script setup>
import SvgIcon from './icons/SvgIcon.vue'

defineProps({
  icon: { type: String, default: 'evidence' },
  title: { type: String, default: '' },
  message: { type: String, default: '' },
})
</script>

<style scoped>
.empty-state-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  min-height: 140px;
  padding: var(--space-xl);
  color: var(--text-muted);
  text-align: center;
}
.empty-state-block h3 {
  font-size: 1rem;
}
.empty-state-block p {
  max-width: 520px;
  color: var(--text-secondary);
}
</style>
