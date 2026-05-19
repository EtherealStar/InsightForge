<template>
  <div v-if="modelValue" class="confirm-overlay" @click.self="emit('update:modelValue', false)">
    <section class="confirm-dialog" role="dialog" aria-modal="true" :aria-labelledby="titleId">
      <h3 :id="titleId">{{ title }}</h3>
      <p>{{ message }}</p>
      <div class="confirm-actions">
        <button class="btn btn-secondary" @click="emit('update:modelValue', false)">
          {{ cancelLabel }}
        </button>
        <button class="btn" :class="danger ? 'btn-danger' : 'btn-primary'" @click="confirm">
          {{ confirmLabel }}
        </button>
      </div>
    </section>
  </div>
</template>

<script setup>
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '确认操作' },
  message: { type: String, default: '确定继续执行此操作？' },
  confirmLabel: { type: String, default: '确认' },
  cancelLabel: { type: String, default: '取消' },
  danger: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'confirm'])
const titleId = `confirm-${Math.random().toString(36).slice(2)}`

function confirm() {
  emit('confirm')
  emit('update:modelValue', false)
}
</script>

<style scoped>
.confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-lg);
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(4px);
}
.confirm-dialog {
  width: min(420px, 100%);
  padding: var(--space-lg);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  box-shadow: var(--shadow-lg);
}
.confirm-dialog h3 {
  margin-bottom: var(--space-sm);
}
.confirm-dialog p {
  color: var(--text-secondary);
}
.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
  margin-top: var(--space-lg);
}
</style>
