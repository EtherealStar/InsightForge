<template>
  <svg
    class="svg-icon"
    :class="[`svg-icon-${name}`]"
    :width="size"
    :height="size"
    :viewBox="icon.viewBox"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
    focusable="false"
  >
    <path
      v-for="(path, index) in icon.paths"
      :key="index"
      :d="path"
      stroke="currentColor"
      stroke-width="1.8"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  </svg>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 20 },
})

const icons = {
  dashboard: ['M3 13h8V3H3v10Z', 'M13 21h8V11h-8v10Z', 'M3 21h8v-6H3v6Z', 'M13 9h8V3h-8v6Z'],
  competitor: ['M4 20V8l8-4 8 4v12', 'M8 20v-6h8v6', 'M8 10h.01', 'M12 10h.01', 'M16 10h.01'],
  intel: ['M4 6h16', 'M4 12h10', 'M4 18h16', 'M17 10l3 2-3 2'],
  report: ['M7 3h7l5 5v13H7V3Z', 'M14 3v5h5', 'M10 13h6', 'M10 17h6'],
  task: ['M9 6h11', 'M9 12h11', 'M9 18h11', 'M4 6l1 1 2-3', 'M4 12l1 1 2-3', 'M4 18l1 1 2-3'],
  search: ['M11 19a8 8 0 1 1 0-16 8 8 0 0 1 0 16Z', 'M21 21l-4.35-4.35'],
  memory: ['M7 4h10a3 3 0 0 1 3 3v10a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3Z', 'M9 8h6', 'M9 12h6', 'M9 16h3'],
  webhook: ['M7 8a4 4 0 1 1 4 4', 'M17 16a4 4 0 1 1-4-4', 'M7 16a4 4 0 1 0 4-4'],
  settings: ['M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z', 'M19.4 15a1.8 1.8 0 0 0 .36 1.98l.04.05a2.2 2.2 0 0 1-3.11 3.11l-.05-.04a1.8 1.8 0 0 0-1.98-.36 1.8 1.8 0 0 0-1.1 1.66V21a2.2 2.2 0 0 1-4.4 0v-.07a1.8 1.8 0 0 0-1.1-1.66 1.8 1.8 0 0 0-1.98.36l-.05.04a2.2 2.2 0 0 1-3.11-3.11l.04-.05A1.8 1.8 0 0 0 4.6 15a1.8 1.8 0 0 0-1.66-1.1H3a2.2 2.2 0 0 1 0-4.4h.07a1.8 1.8 0 0 0 1.66-1.1 1.8 1.8 0 0 0-.36-1.98l-.04-.05a2.2 2.2 0 0 1 3.11-3.11l.05.04A1.8 1.8 0 0 0 9 4.6a1.8 1.8 0 0 0 1.1-1.66V3a2.2 2.2 0 0 1 4.4 0v.07a1.8 1.8 0 0 0 1.1 1.66 1.8 1.8 0 0 0 1.98-.36l.05-.04a2.2 2.2 0 0 1 3.11 3.11l-.04.05A1.8 1.8 0 0 0 19.4 9c0 .74.45 1.41 1.13 1.66H21a2.2 2.2 0 0 1 0 4.4h-.07A1.8 1.8 0 0 0 19.4 15Z'],
  config: ['M4 7h16', 'M7 7v10a3 3 0 0 0 3 3h4a3 3 0 0 0 3-3V7', 'M9 7V5a3 3 0 0 1 6 0v2', 'M10 13h4'],
  approve: ['M20 6 9 17l-5-5'],
  reject: ['M18 6 6 18', 'M6 6l12 12'],
  publish: ['M12 3v12', 'M7 8l5-5 5 5', 'M5 21h14'],
  refresh: ['M21 12a9 9 0 0 1-15.1 6.6', 'M3 12A9 9 0 0 1 18.1 5.4', 'M18 2v4h-4', 'M6 22v-4h4'],
  evidence: ['M5 4h14v16H5V4Z', 'M8 8h8', 'M8 12h8', 'M8 16h5'],
  warning: ['M12 3 2 21h20L12 3Z', 'M12 9v5', 'M12 17h.01'],
  edit: ['M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3Z', 'M14 7l3 3'],
  delete: ['M4 7h16', 'M10 11v6', 'M14 11v6', 'M6 7l1 14h10l1-14', 'M9 7V4h6v3'],
  link: ['M10 13a5 5 0 0 0 7.07 0l2-2a5 5 0 0 0-7.07-7.07l-1.15 1.15', 'M14 11a5 5 0 0 0-7.07 0l-2 2A5 5 0 0 0 12 20.07l1.15-1.15'],
  plus: ['M12 5v14', 'M5 12h14'],
  menu: ['M4 6h16', 'M4 12h16', 'M4 18h16'],
  chevronLeft: ['M15 18l-6-6 6-6'],
  chevronRight: ['M9 18l6-6-6-6'],
  close: ['M18 6 6 18', 'M6 6l12 12'],
  external: ['M14 4h6v6', 'M20 4l-9 9', 'M20 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h5'],
  quality: ['M12 3l7 4v5c0 5-3 8-7 9-4-1-7-4-7-9V7l7-4Z', 'M9 12l2 2 4-4'],
  user: ['M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z', 'M4 21a8 8 0 0 1 16 0'],
}

const icon = computed(() => ({
  viewBox: '0 0 24 24',
  paths: icons[props.name] || icons.warning,
}))
</script>

<style scoped>
.svg-icon {
  display: inline-block;
  flex-shrink: 0;
  vertical-align: middle;
}
</style>
