<template>
  <div class="app-layout">
    <header class="mobile-topbar">
      <button class="btn-icon mobile-menu-btn" @click="mobileNavOpen = true" aria-label="打开菜单">
        
      </button>
      <span class="mobile-title">Logos</span>
    </header>

    <NavSidebar :mobileOpen="mobileNavOpen" @closeMobile="mobileNavOpen = false" />
    <main class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
import NavSidebar from './components/NavSidebar.vue'
import { ref } from 'vue'

const mobileNavOpen = ref(false)
</script>

<style scoped>
.app-layout {
  display: flex;
  min-height: 100vh;
}

.mobile-topbar {
  display: none;
}

.main-content {
  flex: 1;
  margin-left: var(--sidebar-width);
  padding: var(--space-xl) var(--space-2xl);
  min-width: 0;
}

/* 页面切换动画 */
.page-enter-active {
  animation: pageIn 0.3s ease;
}
.page-leave-active {
  animation: pageOut 0.2s ease;
}
@keyframes pageIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes pageOut {
  from { opacity: 1; }
  to { opacity: 0; }
}

@media (max-width: 768px) {
  .mobile-topbar {
    position: fixed;
    left: 0;
    right: 0;
    top: 0;
    height: 56px;
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    padding: 0 var(--space-md);
    background: var(--bg-glass);
    backdrop-filter: blur(20px);
    border-bottom: 1px solid var(--border-color);
    z-index: 200;
  }
  .mobile-menu-btn {
    width: 40px;
    height: 40px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-color);
    background: var(--bg-card);
    color: var(--text-primary);
    cursor: pointer;
  }
  .mobile-title {
    font-weight: 700;
    letter-spacing: 0.2px;
    color: var(--text-primary);
  }
  .main-content {
    margin-left: 0;
    padding: var(--space-md);
    padding-top: 60px;
  }
}
</style>
