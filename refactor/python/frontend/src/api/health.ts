/** 浏览器校验后的诊断信息；后两项不属于后端 JSON。 */
export interface HealthResult {
    status: 'ok';
    httpStatus: 200;
    implementation: 'python-fastapi';
}

/** 固定分类和安全文案，不携带代理原始正文或内部堆栈。 */
export class HealthCheckError extends Error {
    /**
     * 创建可供页面直接展示的健康检查错误。
     * @param kind 网络、超时、HTTP 或协议分类。
     * @param message 固定的安全诊断文案。
     * @param status 可选的实际 HTTP 状态码。
     */
    constructor(
        public readonly kind: 'network' | 'timeout' | 'http' | 'protocol',
        message: string,
        public readonly status?: number,
    ) {
        super(message);
        this.name = 'HealthCheckError';
    }
}

const HEALTH_TIMEOUT_MS = 5000;

/**
 * 请求同源健康接口，仅接受精确的 Python 健康合同。
 * @param signal vue-query 的取消信号；取消原样传播，不误报为超时。
 * @returns 成功返回已校验诊断；失败抛四类安全错误，始终清理定时器和监听器。
 */
export async function fetchHealth(signal?: AbortSignal): Promise<HealthResult> {
    const controller = new AbortController();
    const timeoutError = new HealthCheckError('timeout', '检测超过 5 秒，请检查后端后重试。');
    /** 转发查询取消原因，确保卸载不会留下仍在读取的请求。 */
    function onAbort(): void {
        controller.abort(signal?.reason);
    }
    signal?.addEventListener('abort', onAbort, { once: true });
    if (signal?.aborted) onAbort();
    const timer = setTimeout(() => controller.abort(timeoutError), HEALTH_TIMEOUT_MS);

    try {
        const response = await fetch('/health', { signal: controller.signal, cache: 'no-store' });
        if (response.status !== 200) {
            throw new HealthCheckError('http', `检测收到 HTTP ${response.status}，请检查开发代理和后端。`, response.status);
        }
        const contentType = response.headers.get('Content-Type')?.split(';')[0]?.trim().toLowerCase();
        if (contentType !== 'application/json') {
            throw new HealthCheckError('protocol', '响应不是 JSON，请确认代理指向 Python 后端。');
        }
        const body: unknown = await response.json();
        if (typeof body !== 'object' || body === null || Array.isArray(body)
            || Object.keys(body).length !== 1 || !('status' in body) || body.status !== 'ok') {
            throw new HealthCheckError('protocol', '响应内容不符合健康接口合同。');
        }
        if (response.headers.get('X-WeKnora-Implementation') !== 'python-fastapi') {
            throw new HealthCheckError('protocol', '未识别到 Python 后端标记，请检查代理是否误连原 Go 服务。');
        }
        controller.signal.throwIfAborted();
        return { status: 'ok', httpStatus: 200, implementation: 'python-fastapi' };
    } catch (error: unknown) {
        if (controller.signal.aborted) throw controller.signal.reason;
        if (error instanceof HealthCheckError) throw error;
        if (error instanceof SyntaxError) {
            throw new HealthCheckError('protocol', '响应 JSON 无法解析，请检查代理和后端。');
        }
        throw new HealthCheckError('network', '无法连接后端，请确认服务已启动，并检查网络和开发代理。');
    } finally {
        clearTimeout(timer);
        signal?.removeEventListener('abort', onAbort);
    }
}
