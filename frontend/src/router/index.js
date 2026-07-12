import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/dashboard',
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: { title: '工作台', icon: 'dashboard' },
  },
  {
    path: '/competitors',
    name: 'Competitors',
    component: () => import('../views/CompetitorView.vue'),
    meta: { title: '竞品管理', icon: 'competitor' },
  },
  {
    path: '/intel',
    name: 'Intel',
    component: () => import('../views/IntelView.vue'),
    meta: { title: '结构化情报', icon: 'intel' },
  },
  {
    path: '/governance',
    name: 'Governance',
    component: () => import('../views/GovernanceView.vue'),
    meta: { title: '来源治理', icon: 'settings' },
  },
  {
    path: '/reports',
    name: 'Reports',
    component: () => import('../views/ReportView.vue'),
    meta: { title: '分析报告', icon: 'report' },
  },
  {
    path: '/tasks',
    name: 'Tasks',
    component: () => import('../views/TaskView.vue'),
    meta: { title: '任务追踪', icon: 'task' },
  },
  {
    path: '/query',
    name: 'Query',
    component: () => import('../views/QueryView.vue'),
    meta: { title: '智能分析', icon: 'search' },
  },
  {
    path: '/memory',
    name: 'Memory',
    component: () => import('../views/MemoryView.vue'),
    meta: { title: '记忆管理', icon: 'memory' },
  },
  {
    path: '/webhook',
    name: 'Webhook',
    component: () => import('../views/WebhookView.vue'),
    meta: { title: '消息推送', icon: 'webhook' },
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/SettingsView.vue'),
    meta: { title: '功能设置', icon: 'settings' },
  },
  {
    path: '/config',
    name: 'Config',
    component: () => import('../views/ConfigView.vue'),
    meta: { title: 'API 配置', icon: 'config' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = `${to.meta.title || 'InsightForge'} — InsightForge AI 竞品分析`
})

export default router
