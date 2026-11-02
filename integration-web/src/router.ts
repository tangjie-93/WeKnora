import { createRouter, createWebHistory } from 'vue-router'
import WorkspaceView from './views/workspace/index.vue'
export const router = createRouter({ history: createWebHistory(), routes: [{ path: '/', redirect: '/workspace' }, { path: '/workspace', component: WorkspaceView }] })
