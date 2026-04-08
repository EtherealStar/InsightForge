<template>
  <div class="app-layout">
    <NavSidebar />
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
</script>

<style scoped>
.app-layout {
  display: flex;
  min-height: 100vh;
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
  .main-content {
    margin-left: 0;
    padding: var(--space-md);
    padding-top: 60px;
  }
}
</style>
