import { computed, ref } from 'vue';
import { useQuery } from '@tanstack/vue-query';
import type { QueryFunctionContext } from '@tanstack/vue-query';
import { ApiError, configureSessionAccess, errorMessage } from '../api/client';
import { fetchCurrentAccount, loginAccount, logoutAccount, refreshSession } from '../api/auth';
import { useSessionStore } from '../stores/session';
import type { CurrentAccount, CurrentAccountView, LoginInput, RegistrationNotice, SessionActions, SessionRuntimeOptions } from '../types/auth';

let runtime: SessionRuntimeOptions | undefined;
const logoutError = ref('');
const isLoggingOut = ref(false);
export const registrationNotice = ref<RegistrationNotice | null>(null);

/** 获取显式装配的运行依赖。@returns query/router实例；装配遗漏时直接报错。 */
function getRuntime(): SessionRuntimeOptions {
    if (!runtime) throw new Error('会话运行时尚未装配。');
    return runtime;
}
/** 仅取消并移除auth查询，不影响独立health缓存。 */
function clearAuthQueries(): void {
    const { queryClient } = getRuntime();
    void queryClient.cancelQueries({ queryKey: ['auth'] }).catch(() => undefined);
    queryClient.removeQueries({ queryKey: ['auth'] });
}
/** 装配请求会话原语及鉴权失效处理。@param options 已创建的query/router。 */
export function configureSessionRuntime(options: SessionRuntimeOptions): void {
    runtime = options;
    const store = useSessionStore();
    configureSessionAccess({
        snapshot: store.snapshot,
        install: store.installTokens,
        refresh: refreshSession,
        expire: (expectedEpoch) => {
            if (store.epoch !== expectedEpoch) return;
            store.invalidateSession();
            clearAuthQueries();
            void options.router.replace('/login');
        },
    });
}
/** 生成epoch隔离的唯一身份查询配置。@param epoch 会话代际。@returns 查询选项；取消或代际变更拒绝回填。 */
function accountOptions(epoch: number) {
    return {
        queryKey: ['auth', 'me', epoch],
        queryFn: async ({ signal }: QueryFunctionContext): Promise<CurrentAccount> => {
            const account = await fetchCurrentAccount(signal);
            const store = useSessionStore();
            if (store.epoch !== epoch || !store.accessToken || store.pendingLogout) throw new ApiError('会话已变更。', 0, 0, 'cancelled');
            store.status = 'authenticated';
            return account;
        },
        retry: false as const,
        staleTime: Infinity,
        gcTime: 0,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
    };
}
/** 恢复或登录后显式校验me；失败保留安全错误页，401由client清理。@returns me成功为true，失败或无凭据为false。 */
export async function bootstrapSession(): Promise<boolean> {
    const store = useSessionStore();
    if (!store.accessToken || store.pendingLogout) return false;
    try {
        await getRuntime().queryClient.fetchQuery(accountOptions(store.epoch));
        return store.status === 'authenticated';
    } catch { return false; }
}
/** 为布局/账户页共享唯一me查询，不把身份复制到store。@returns 查询状态及仅成功且当前代际有效时的账户。 */
export function useCurrentAccount(): CurrentAccountView {
    const store = useSessionStore();
    const query = useQuery(computed(() => ({ ...accountOptions(store.epoch),
        enabled: !!store.accessToken && !store.pendingLogout })));
    const account = computed(() => store.accessToken && !store.pendingLogout && !query.isError.value && !query.isFetching.value
        ? query.data.value : undefined);
    return { query, account };
}
/** 登录先切代并清缓存，安装令牌后进入中性账户视图；该页唯一me查询成功才显示身份，失败可复用会话重试或真实退出。@param input 登录字段。@param signal 页面取消信号。@returns 登录成功进入账户加载页；凭据失败抛安全错误，代际变化不导航。 */
async function signIn(input: LoginInput, signal?: AbortSignal): Promise<void> {
    const store = useSessionStore();
    if (store.pendingLogout || isLoggingOut.value) throw new ApiError('请先重试并确认服务端退出，再登录其他账户。');
    if (store.accessToken) {
        await getRuntime().router.replace('/account');
        return;
    }
    store.invalidateSession();
    clearAuthQueries();
    const epoch = store.epoch;
    const tokens = await loginAccount(input, signal);
    if (signal?.aborted || store.epoch !== epoch) throw new ApiError('登录已取消。', 0, 0, 'cancelled');
    try {
        if (!store.installTokens(tokens, epoch)) throw new ApiError('会话已变更。', 0, 0, 'cancelled');
    } catch (error) {
        store.pendingLogout = tokens.refreshToken;
        store.beginLogout();
        clearAuthQueries();
        throw error;
    }
    registrationNotice.value = null;
    if (store.epoch === epoch && !signal?.aborted) await getRuntime().router.replace('/account');
}
/** 重试待撤销记录；仅服务端成功且本地清理成功才解锁登录，失败明确未确认。@returns 更新退出反馈，不抛给事件处理器。 */
async function retryPendingLogout(): Promise<void> {
    const store = useSessionStore();
    if (!store.pendingLogout || isLoggingOut.value) return;
    isLoggingOut.value = true;
    logoutError.value = '';
    try {
        await logoutAccount(store.pendingLogout);
        store.completeLogout();
        await getRuntime().router.replace('/login');
    } catch (error) {
        logoutError.value = `本地已清除，服务端撤销未确认。${errorMessage(error)} 请重试退出；确认前不能登录新账户。`;
    } finally { isLoggingOut.value = false; }
}
/** 退出立即屏蔽身份并切代，持久pending后调用真实撤销；网络失败不假报成功。@returns 回登录页并显示确认或重试状态。 */
async function signOut(): Promise<void> {
    const store = useSessionStore();
    if (isLoggingOut.value) return;
    store.beginLogout();
    clearAuthQueries();
    registrationNotice.value = null;
    await getRuntime().router.replace('/login');
    await retryPendingLogout();
}
/** 提供页面会话动作和非身份反馈；异步请求由epoch与页面signal保护。@returns 登录退出动作与反馈。 */
export function useSession(): SessionActions {
    return { signIn, signOut, retryPendingLogout, logoutError, isLoggingOut, registrationNotice };
}
