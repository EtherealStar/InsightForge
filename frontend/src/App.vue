<template>
  <div class="app-layout">
    <header class="mobile-topbar">
      <button class="btn-icon mobile-menu-btn" @click="mobileNavOpen = true" aria-label="打开菜单">
        <SvgIcon name="menu" :size="22" />
      </button>
      <span class="mobile-title">InsightForge</span>
    </header>

    <NavSidebar :mobileOpen="mobileNavOpen" @closeMobile="mobileNavOpen = false" />
    <main class="main-content">
      <section v-if="authReady && !authState.actor" class="auth-panel">
        <h1>InsightForge</h1>
        <p>输入应用 API Key 以继续。</p>
        <div class="auth-form">
          <input
            v-model="apiKeyInput"
            class="input"
            type="password"
            placeholder="if_..."
            @keyup.enter="saveApiKey"
          />
          <button class="btn btn-primary" @click="saveApiKey" :disabled="checkingAuth">
            {{ checkingAuth ? '验证中...' : '登录' }}
          </button>
        </div>
        <p v-if="authError" class="auth-error">{{ authError }}</p>
      </section>
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component v-if="!authReady || authState.actor" :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
import NavSidebar from './components/NavSidebar.vue'
import SvgIcon from './components/icons/SvgIcon.vue'
import { computed, onMounted, ref } from 'vue'
import { authApi } from './api'
import { authState, setActor, setApiKey } from './auth'

const mobileNavOpen = ref(false)
const apiKeyInput = ref(authState.apiKey)
const checkingAuth = ref(false)
const authError = ref('')
const authReady = computed(() => authState.ready)

async function refreshAuth() {
  checkingAuth.value = true
  authError.value = ''
  try {
    const res = await authApi.me()
    setActor(res.data)
  } catch (e) {
    setActor(null)
    authError.value = e.response?.data?.detail || e.message || '认证失败'
  } finally {
    checkingAuth.value = false
  }
}

async function saveApiKey() {
  setApiKey(apiKeyInput.value.trim())
  await refreshAuth()
}

onMounted(refreshAuth)
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

.auth-panel {
  max-width: 420px;
  margin: 10vh auto 0;
  padding: var(--space-xl);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-card);
}
.auth-panel h1 {
  margin-bottom: var(--space-sm);
}
.auth-panel p {
  color: var(--text-secondary);
}
.auth-form {
  display: flex;
  gap: var(--space-sm);
  margin-top: var(--space-md);
}
.auth-form .input {
  flex: 1;
}
.auth-error {
  color: var(--error);
  margin-top: var(--space-sm);
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
