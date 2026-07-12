<template>
  <div class="mobile-overlay" v-if="mobileOpen" @click="$emit('closeMobile')" />
  <aside class="sidebar" :class="{ collapsed: isCollapsed, 'mobile-open': mobileOpen }">
    <div class="sidebar-header">
      <div class="logo">
        <span class="logo-icon"><SvgIcon name="dashboard" :size="24" /></span>
        <transition name="fade">
          <span v-if="!isCollapsed" class="logo-text">InsightForge</span>
        </transition>
      </div>
      <button class="btn-icon collapse-btn" @click="isCollapsed = !isCollapsed" title="收起/展开">
        <SvgIcon :name="isCollapsed ? 'chevronRight' : 'chevronLeft'" :size="18" />
      </button>
    </div>

    <nav class="sidebar-nav">
      <router-link
        v-for="item in visibleNavItems"
        :key="item.path"
        :to="item.path"
        class="nav-item"
        :class="{ active: $route.path === item.path }"
        @click="$emit('closeMobile')"
      >
        <span class="nav-icon"><SvgIcon :name="item.icon" :size="20" /></span>
        <transition name="fade">
          <span v-if="!isCollapsed" class="nav-label">{{ item.label }}</span>
        </transition>
      </router-link>
    </nav>

    <div class="sidebar-footer" v-if="!isCollapsed">
      <div class="version-info">
        <span>InsightForge v2.0</span>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref } from 'vue'
import { hasRole } from '../auth'
import SvgIcon from './icons/SvgIcon.vue'

defineProps({
  mobileOpen: { type: Boolean, default: false },
})
defineEmits(['closeMobile'])

const isCollapsed = ref(false)

const navItems = [
  { path: '/dashboard', icon: 'dashboard', label: '工作台', role: 'viewer' },
  { path: '/competitors', icon: 'competitor', label: '竞品管理', role: 'viewer' },
  { path: '/intel', icon: 'intel', label: '结构化情报', role: 'viewer' },
  { path: '/governance', icon: 'settings', label: '来源治理', role: 'viewer' },
  { path: '/reports', icon: 'report', label: '分析报告', role: 'viewer' },
  { path: '/tasks', icon: 'task', label: '任务追踪', role: 'viewer' },
  { path: '/query', icon: 'search', label: '智能分析', role: 'analyst' },
  { path: '/memory', icon: 'memory', label: '记忆管理', role: 'viewer' },
  { path: '/webhook', icon: 'webhook', label: '消息推送', role: 'viewer' },
  { path: '/settings', icon: 'settings', label: '功能设置', role: 'viewer' },
  { path: '/config', icon: 'config', label: 'API 配置', role: 'admin' },
]

const visibleNavItems = computed(() => navItems.filter((item) => hasRole(item.role)))
</script>

<style scoped>
.sidebar {
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  width: var(--sidebar-width);
  background: var(--bg-glass);
  backdrop-filter: blur(20px);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  z-index: 100;
  transition: width var(--transition-base);
  overflow: hidden;
}
.sidebar.collapsed {
  width: 64px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-lg) var(--space-md);
  border-bottom: 1px solid var(--border-color);
  min-height: 64px;
}

.logo {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}
.logo-icon {
  display: inline-flex;
  color: var(--accent-primary);
}
.logo-text {
  font-size: 1.25rem;
  font-weight: 700;
  background: var(--accent-gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.collapse-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 1.25rem;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
}
.collapse-btn:hover {
  color: var(--text-primary);
  background: var(--bg-card);
}

.sidebar-nav {
  flex: 1;
  padding: var(--space-md) var(--space-sm);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  text-decoration: none;
  transition: all var(--transition-fast);
  position: relative;
  white-space: nowrap;
}
.nav-item:hover {
  background: var(--bg-card);
  color: var(--text-primary);
}
.nav-item.active {
  background: var(--accent-glow);
  color: var(--accent-primary);
}
.nav-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 60%;
  background: var(--accent-primary);
  border-radius: 0 2px 2px 0;
}

.nav-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 24px;
}
.nav-label {
  font-size: 0.875rem;
  font-weight: 500;
}

.sidebar-footer {
  padding: var(--space-md);
  border-top: 1px solid var(--border-color);
}

.stats-mini {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  margin-bottom: var(--space-md);
}
.stat-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.8125rem;
}
.stat-label {
  color: var(--text-muted);
}
.stat-value {
  color: var(--text-secondary);
  font-weight: 600;
}
.stat-value.accent {
  color: var(--accent-primary);
}

.version-info {
  font-size: 0.75rem;
  color: var(--text-muted);
  text-align: center;
}

/* fade transition */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

@media (max-width: 768px) {
  .sidebar {
    z-index: 250;
    top: 56px;
    bottom: 0;
    transform: translateX(-110%);
    transition: transform 0.2s ease;
  }
  .sidebar.mobile-open {
    transform: translateX(0);
  }
  .mobile-overlay {
    position: fixed;
    left: 0;
    right: 0;
    top: 56px;
    bottom: 0;
    background: rgba(0, 0, 0, 0.35);
    z-index: 240;
  }
}
</style>
