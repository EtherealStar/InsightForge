<template>
  <aside class="sidebar" :class="{ collapsed: isCollapsed }">
    <div class="sidebar-header">
      <div class="logo">
        <span class="logo-icon">📰</span>
        <transition name="fade">
          <span v-if="!isCollapsed" class="logo-text">Logos</span>
        </transition>
      </div>
      <button class="btn-icon collapse-btn" @click="isCollapsed = !isCollapsed" title="收起/展开">
        {{ isCollapsed ? '›' : '‹' }}
      </button>
    </div>

    <nav class="sidebar-nav">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="nav-item"
        :class="{ active: $route.path === item.path }"
      >
        <span class="nav-icon">{{ item.icon }}</span>
        <transition name="fade">
          <span v-if="!isCollapsed" class="nav-label">{{ item.label }}</span>
        </transition>
      </router-link>
    </nav>

    <div class="sidebar-footer" v-if="!isCollapsed">
      <div class="stats-mini" v-if="stats">
        <div class="stat-row">
          <span class="stat-label">文章总数</span>
          <span class="stat-value">{{ stats.total }}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">今日新增</span>
          <span class="stat-value accent">{{ stats.today_new }}</span>
        </div>
      </div>
      <div class="version-info">
        <span>Logos v1.0</span>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { newsApi } from '../api'

const isCollapsed = ref(false)
const stats = ref(null)

const navItems = [
  { path: '/news', icon: '📰', label: '新闻展示' },
  { path: '/briefs', icon: '📋', label: '新闻简报' },
  { path: '/query', icon: '💬', label: '智能问答' },
  { path: '/settings', icon: '⚙️', label: '功能设置' },
  { path: '/config', icon: '🔧', label: 'API 配置' },
]

onMounted(async () => {
  try {
    const res = await newsApi.getStats()
    stats.value = res.data
  } catch {
    // 静默处理
  }
})
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
  font-size: 1.5rem;
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
  font-size: 1.125rem;
  flex-shrink: 0;
  width: 24px;
  text-align: center;
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
    display: none;
  }
}
</style>
