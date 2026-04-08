import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/news',
  },
  {
    path: '/news',
    name: 'News',
    component: () => import('../views/NewsView.vue'),
    meta: { title: '新闻展示', icon: '📰' },
  },
  {
    path: '/briefs',
    name: 'Briefs',
    component: () => import('../views/BriefView.vue'),
    meta: { title: '新闻简报', icon: '📋' },
  },
  {
    path: '/query',
    name: 'Query',
    component: () => import('../views/QueryView.vue'),
    meta: { title: '智能问答', icon: '💬' },
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/SettingsView.vue'),
    meta: { title: '功能设置', icon: '⚙️' },
  },
  {
    path: '/config',
    name: 'Config',
    component: () => import('../views/ConfigView.vue'),
    meta: { title: 'API 配置', icon: '🔧' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = `${to.meta.title || 'Logos'} — Logos AI 新闻助手`
})

export default router
