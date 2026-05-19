<template>
  <slot v-if="allowed" />
  <slot v-else-if="mode === 'disabled'" name="disabled" />
</template>

<script setup>
import { computed } from 'vue'
import { hasRole } from '../auth'

const props = defineProps({
  minRole: { type: String, default: 'viewer' },
  mode: { type: String, default: 'hide' },
})

const allowed = computed(() => hasRole(props.minRole))
</script>
