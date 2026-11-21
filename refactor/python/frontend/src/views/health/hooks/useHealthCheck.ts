import { computed, onScopeDispose, ref } from 'vue';
import { useQuery, useQueryClient } from '@tanstack/vue-query';
import type { HealthResult, HealthCheckError } from '../../../api/health';
import { fetchHealth } from '../../../api/health';

const HEALTH_QUERY_KEY = ['health', 'python'] as const;

/**
 * 提供手动检测状态；结果、错误和终态时间均派生自 vue-query，不复制到 Pinia。
 * @returns 状态、当次成功结果或错误、浏览器终态时间和检测方法；作用域释放时取消并回收查询。
 */
export function useHealthCheck() {
    const queryClient = useQueryClient();
    const hasAttempted = ref(false);
    let isDisposed = false;
    let isChecking = false;
    const query = useQuery<HealthResult, HealthCheckError>({
        queryKey: HEALTH_QUERY_KEY,
        queryFn: ({ signal }) => fetchHealth(signal),
        enabled: false,
        retry: false,
        refetchOnMount: false,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
        networkMode: 'always',
        gcTime: 0,
    });
    const state = computed(() => {
        if (isDisposed) return 'idle';
        if (query.isFetching.value) return 'checking';
        if (!hasAttempted.value) return 'idle';
        if (query.isError.value) return 'failure';
        if (query.isSuccess.value) return 'success';
        return 'idle';
    });
    const result = computed(() => state.value === 'success' ? query.data.value : undefined);
    const error = computed(() => state.value === 'failure' ? query.error.value ?? undefined : undefined);
    const checkedAt = computed(() => {
        if (state.value === 'success') return query.dataUpdatedAt.value;
        if (state.value === 'failure') return query.errorUpdatedAt.value;
        return undefined;
    });

    /**
     * 主动发起一次检测，同步保护重复调用；成功或失败均由 query 更新，不抛出展示用错误。
     * @returns 本次检测结束后完成；无自动重试，取消不生成新成功结果，始终释放并发锁。
     */
    async function check(): Promise<void> {
        if (isDisposed || isChecking || query.isFetching.value) return;
        isChecking = true;
        hasAttempted.value = true;
        try {
            await query.refetch({ cancelRefetch: false });
        } finally {
            isChecking = false;
        }
    }

    /** 卸载时取消本页在途请求，vue-query 会中止传给 fetchHealth 的信号。 */
    function dispose(): void {
        isDisposed = true;
        void queryClient.cancelQueries({ queryKey: HEALTH_QUERY_KEY, exact: true });
    }
    onScopeDispose(dispose);

    return { state, result, error, checkedAt, check };
}
