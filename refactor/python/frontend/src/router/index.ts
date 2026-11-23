import { createRouter, createWebHashHistory } from 'vue-router';
import type { Router } from 'vue-router';
import type { Pinia } from 'pinia';
import { useSessionStore } from '../stores/session';
import { bootstrapSession } from '../hooks/useSession';

const router = createRouter({
    history: createWebHashHistory(import.meta.env.BASE_URL),
    routes: [
        { path: '/', name: 'home', component: () => import('../views/login/index.vue') },
        { path: '/login', name: 'login', component: () => import('../views/login/index.vue') },
        { path: '/register', name: 'register', component: () => import('../views/register/index.vue') },
        { path: '/account', component: () => import('../layouts/ProductLayout.vue'), children: [
            { path: '', name: 'account', component: () => import('../views/account/index.vue'), meta: { requiresAuth: true } },
        ] },
        { path: '/workbench', component: () => import('../layouts/WorkbenchLayout.vue'), children: [
            { path: '', redirect: '/workbench/health' },
            { path: 'health', name: 'health', component: () => import('../views/health/index.vue') },
            { path: 'progress', name: 'progress', component: () => import('../views/progress/index.vue') },
        ] },
        { path: '/health', redirect: '/workbench/health' },
        { path: '/progress', redirect: '/workbench/progress' },
        { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('../views/not-found/index.vue') },
    ],
    scrollBehavior: () => ({ top: 0 }),
});

/** 在Pinia/query装配之后安装守卫；公共工作台不依赖me成功。@param target Router实例。@param pinia 已激活Pinia。 */
export function installSessionGuards(target: Router, pinia: Pinia): void {
    target.beforeEach(async to => {
        const session = useSessionStore(pinia);
        if (to.name === 'home') {
            if (session.accessToken && !session.pendingLogout) await bootstrapSession();
            return { path: session.accessToken && !session.pendingLogout ? '/account' : '/login', replace: true };
        }
        if (to.meta.requiresAuth && (!session.accessToken || session.pendingLogout)) return { path: '/login', replace: true };
        if ((to.name === 'login' || to.name === 'register') && session.accessToken && !session.pendingLogout) {
            return { path: '/account', replace: true };
        }
        document.title = `${to.name === 'account' ? '账户与空间' : to.name === 'login' ? '登录' : to.name === 'register' ? '注册' : '工作台'} · WeKnora`;
        return true;
    });
}

export default router;
