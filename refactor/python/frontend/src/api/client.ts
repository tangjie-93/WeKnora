import type { ApiFailureKind, RefreshFlight, RequestOptions, SessionAccess, SessionSnapshot } from '../types/auth';

let sessionAccess: SessionAccess | undefined;
let refreshFlight: RefreshFlight | undefined;
const REQUEST_TIMEOUT_MS = 15000;

export class ApiError extends Error {
    /** 保存安全错误类别，绝不附带请求体或凭据。@param message 安全提示。@param status HTTP状态。@param code 应用错误码。@param kind 失败类别。 */
    constructor(message: string, public readonly status = 0, public readonly code = 0,
        public readonly kind: ApiFailureKind = 'http') {
        super(message);
        this.name = 'ApiError';
    }
}
/** 显式安装凭据原语，避免路由/store循环依赖。@param access 会话读写适配器。 */
export function configureSessionAccess(access: SessionAccess): void { sessionAccess = access; }

/** 按状态提供受控反馈，不把服务器意外内容或令牌呈现到页面。@param status HTTP状态。@param code 应用码。@returns 用户提示。 */
function httpMessage(status: number, code: number): string {
    if (status === 401) return '邮箱或密码不正确，或会话已失效，请重新登录。';
    if (status === 403) return '当前空间不可用或没有访问权限，请退出后联系维护者。';
    if (status === 400 && code === 1000) return '用户名或邮箱已被使用，请换一个后重试。';
    if (status === 400) return '提交内容不符合要求，请检查字段格式和密码规则。';
    if (status === 429) return '操作过于频繁，请稍后再试。';
    if (status === 503) return '认证服务暂不可用。请确认已显式初始化独立认证数据库与持久密钥，再重试。';
    if (status >= 500) return '服务暂时无法完成请求，请稍后重试。';
    return '请求未成功，请检查输入后重试。';
}
/** 发起有超时与取消清理的JSON请求；失败只抛安全错误。@param path 固定同源路径。@param options 请求配置。@param bearer 凭据快照。@returns 未可信JSON。 */
async function sendJson(path: string, options: RequestOptions, bearer?: string): Promise<unknown> {
    const controller = new AbortController();
    const abort = (): void => controller.abort();
    options.signal?.addEventListener('abort', abort, { once: true });
    if (options.signal?.aborted) controller.abort();
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, REQUEST_TIMEOUT_MS);
    try {
        const headers: Record<string, string> = { Accept: 'application/json' };
        if (options.body !== undefined) headers['Content-Type'] = 'application/json';
        if (bearer) headers.Authorization = `Bearer ${bearer}`;
        const response = await fetch(path, { method: options.method || 'GET', headers,
            body: options.body === undefined ? undefined : JSON.stringify(options.body),
            signal: controller.signal, cache: 'no-store', credentials: 'omit' });
        let data: unknown;
        try { data = await response.json(); }
        catch { throw new ApiError(httpMessage(response.status, 0), response.status, 0, 'contract'); }
        if (!response.ok) {
            const code = isRecord(data) && isRecord(data.error) && typeof data.error.code === 'number' ? data.error.code : 0;
            throw new ApiError(httpMessage(response.status, code), response.status, code);
        }
        return data;
    } catch (error) {
        if (error instanceof ApiError) throw error;
        if (controller.signal.aborted) throw new ApiError(timedOut ? '请求超时，请重试。' : '请求已取消。', 0, 0, timedOut ? 'timeout' : 'cancelled');
        throw new ApiError('无法连接服务，请检查网络后重试。', 0, 0, 'network');
    } finally {
        clearTimeout(timer);
        options.signal?.removeEventListener('abort', abort);
    }
}
/** 同一epoch只轮换一次；旧401沿用已更新token，不消耗新刷新凭据。@param snapshot 原请求快照。@returns 刷新完成；失效时清理当前会话。 */
export async function refreshSingleFlight(snapshot: SessionSnapshot): Promise<void> {
    const access = sessionAccess;
    const current = access?.snapshot();
    if (!access || !current || current.epoch !== snapshot.epoch) throw new ApiError('会话已变更。', 0, 0, 'cancelled');
    if (current.accessToken !== snapshot.accessToken) return;
    if (refreshFlight?.epoch === snapshot.epoch) return refreshFlight.promise;
    const promise = (async (): Promise<void> => {
        try {
            const tokens = await access.refresh(current.refreshToken, current.signal);
            if (!access.install(tokens, current.epoch)) throw new ApiError('会话已变更。', 0, 0, 'cancelled');
        } catch (error) {
            if (access.snapshot()?.epoch === current.epoch) access.expire(current.epoch);
            throw error;
        }
    })();
    const flight = { epoch: snapshot.epoch, promise };
    refreshFlight = flight;
    try { await promise; }
    finally { if (refreshFlight === flight) refreshFlight = undefined; }
}
/** 执行同源请求；仅受保护GET在401时刷新并重试一次，epoch变化后拒绝晚到结果。@param path 固定API路径。@param options 请求配置。@returns 未可信JSON，需业务适配器解包。 */
export async function requestJson(path: string, options: RequestOptions = {}): Promise<unknown> {
    const initial = options.authenticated ? sessionAccess?.snapshot() : undefined;
    if (options.authenticated && !initial) throw new ApiError('请先登录。', 401, 1001);
    const signals = [options.signal, initial?.signal].filter((signal): signal is AbortSignal => !!signal);
    const controller = new AbortController();
    const abort = (): void => controller.abort();
    signals.forEach(signal => { signal.addEventListener('abort', abort, { once: true }); if (signal.aborted) abort(); });
    const config = { ...options, signal: controller.signal };
    try {
        let result: unknown;
        try { result = await sendJson(path, config, initial?.accessToken || options.bearer); }
        catch (error) {
            if (!(error instanceof ApiError) || error.status !== 401 || !initial || (options.method && options.method !== 'GET')) throw error;
            await refreshSingleFlight(initial);
            const current = sessionAccess?.snapshot();
            if (!current || current.epoch !== initial.epoch) throw new ApiError('会话已变更。', 0, 0, 'cancelled');
            try { result = await sendJson(path, config, current.accessToken); }
            catch (retryError) {
                if (retryError instanceof ApiError && retryError.status === 401) sessionAccess?.expire(initial.epoch);
                throw retryError;
            }
        }
        if (initial && sessionAccess?.snapshot()?.epoch !== initial.epoch) throw new ApiError('会话已变更。', 0, 0, 'cancelled');
        return result;
    } finally { signals.forEach(signal => signal.removeEventListener('abort', abort)); }
}
/** 验证对象形状供API解包使用。@param value 未可信值。@returns 是否普通JSON对象。 */
export function isRecord(value: unknown): value is Record<string, unknown> {
    return !!value && typeof value === 'object' && !Array.isArray(value);
}
/** 将未知错误转换为无敏感内容的界面提示。@param error 捕获错误。@returns 安全提示。 */
export function errorMessage(error: unknown): string {
    return error instanceof ApiError ? error.message : '操作未完成，请重试；若持续失败请检查浏览器存储与服务配置。';
}
