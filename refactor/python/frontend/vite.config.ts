import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';

/**
 * 读取前端端口及仅供开发服务器使用的代理目标，不向浏览器暴露后端地址。
 * @param 配置环境 当前 Vite 模式。
 * @returns 仅代理健康检查的本机开发配置；端口被占用时直接报错。
 */
export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, process.cwd(), '');
    const port = Number(env.FRONTEND_PORT || 5400);
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
        throw new Error('FRONTEND_PORT 必须是 1–65535 之间的整数。');
    }

    return {
        plugins: [vue(), tailwindcss()],
        server: {
            host: '127.0.0.1',
            port,
            strictPort: true,
            proxy: {
                '^/health$': {
                    target: env.BACKEND_PROXY_TARGET || 'http://127.0.0.1:8080',
                    changeOrigin: true,
                },
            },
        },
    };
});
