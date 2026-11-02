import { createRouter, createWebHistory } from 'vue-router'
import { isLoggedIn } from './auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/knowledge' },
    {
      path: '/login',
      name: 'login',
      component: () => import('./pages/LoginPage.vue'),
      meta: { public: true },
    },
    {
      path: '/knowledge',
      name: 'knowledge',
      component: () => import('./pages/KnowledgePage.vue'),
    },
    {
      path: '/faq',
      name: 'faq',
      component: () => import('./pages/FaqPage.vue'),
    },
    {
      path: '/wiki',
      name: 'wiki',
      component: () => import('./pages/WikiPage.vue'),
    },
    {
      path: '/retrieval',
      name: 'retrieval',
      component: () => import('./pages/RetrievalPage.vue'),
    },
    {
      path: '/agents',
      name: 'agents',
      component: () => import('./pages/AgentsPage.vue'),
    },
    {
      path: '/agent-chat',
      name: 'agent-chat',
      component: () => import('./pages/AgentChatPage.vue'),
    },
    {
      path: '/chat',
      name: 'chat',
      component: () => import('./pages/ChatPage.vue'),
    },
    {
      path: '/models',
      name: 'models',
      component: () => import('./pages/ModelsPage.vue'),
    },
  ],
})

router.beforeEach((to) => {
  if (to.meta.public) {
    return isLoggedIn() ? { name: 'knowledge' } : true
  }
  return isLoggedIn() ? true : { name: 'login' }
})

export default router
