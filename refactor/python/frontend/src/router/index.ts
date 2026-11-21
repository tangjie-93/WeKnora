import { createRouter, createWebHashHistory } from 'vue-router';
import HealthPage from '../views/health/index.vue';
import ProgressPage from '../views/progress/index.vue';
import NotFoundPage from '../views/not-found/index.vue';

const router = createRouter({
    history: createWebHashHistory(import.meta.env.BASE_URL),
    routes: [
        { path: '/', redirect: '/health' },
        { path: '/health', name: 'health', component: HealthPage },
        { path: '/progress', name: 'progress', component: ProgressPage },
        { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFoundPage },
    ],
});

export default router;
