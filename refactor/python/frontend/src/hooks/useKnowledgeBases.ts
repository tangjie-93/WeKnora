import { computed, onScopeDispose, ref, toRaw, watch } from 'vue';
import { useQuery, useQueryClient } from '@tanstack/vue-query';
import type { QueryFunctionContext } from '@tanstack/vue-query';
import { ApiError } from '../api/client';
import { createKnowledgeBase, fetchKnowledgeBases } from '../api/knowledge-bases';
import { useSessionStore } from '../stores/session';
import { useCurrentAccount } from './useSession';
import type { CreateKnowledgeBaseInput, KnowledgeBaseCreator, KnowledgeBaseOwnership, KnowledgeBaseQueryKey, KnowledgeBaseView, UseKnowledgeBasesReturn } from '../types/knowledge-bases';

/** 提供真实身份归属的知识库查询与单次创建；失败保持可恢复状态，切代、筛选及卸载同步废弃旧回调并取消接收。@returns 冻结的数据状态和操作接口。 */
export function useKnowledgeBases(): UseKnowledgeBasesReturn {
    const store = useSessionStore();
    const queryClient = useQueryClient();
    const { account, query: accountQuery } = useCurrentAccount();
    const creator = ref<KnowledgeBaseCreator>('all');
    const isSubmitting = ref(false);
    const submitError = ref('');
    let disposed = false;
    let contextGeneration = 0;
    let listGeneration = 0;
    let submissionGeneration = 0;
    let submissionController: AbortController | undefined;
    let activeSubmissionOwner = '';
    let needsVerification = false;
    let verificationOwner = '';
    const ownerKey = computed(() => `${store.epoch}:${account.value?.user.id || ''}:${account.value?.tenant.id || 0}`);
    const queryKey = computed<KnowledgeBaseQueryKey>(() => ['knowledge-bases', store.epoch,
        account.value?.user.id || '', account.value?.tenant.id || 0, creator.value]);
    const isEnabled = computed(() => !disposed && !!account.value && !!store.accessToken && !store.pendingLogout
        && account.value.user.is_active && account.value.memberships.some(item => item.tenant_id === account.value?.tenant.id));
    const canCreate = computed(() => isEnabled.value && !!account.value?.memberships.some(item =>
        item.tenant_id === account.value?.tenant.id && ['owner', 'admin', 'contributor'].includes(item.role)));

    /** 捕获仅来自当前有效 me 的归属。@returns 当前归属，身份无效时为 undefined。 */
    function captureOwner(): KnowledgeBaseOwnership | undefined {
        const current = account.value;
        if (disposed || !isEnabled.value || !current) return undefined;
        return { epoch: store.epoch, userID: current.user.id, tenantID: current.tenant.id,
            creator: creator.value, generation: contextGeneration };
    }
    /** 校验归属及页面代际；每个异步分支都必须重新判断。@param owner 原归属。@returns 是否仍可操作当前页面。 */
    function owns(owner: KnowledgeBaseOwnership): boolean {
        const current = captureOwner();
        return !!current && current.epoch === owner.epoch && current.userID === owner.userID
            && current.tenantID === owner.tenantID && current.creator === owner.creator && current.generation === owner.generation;
    }
    /** 产生无敏感上下文的逻辑取消。@returns 仅用于阻止旧结果回填的错误。 */
    function cancelled(): ApiError { return new ApiError('知识库请求归属已变更。', 0, 0, 'cancelled'); }
    /** 执行当前归属列表请求，传输及逻辑取消双重保护。@param context 查询取消信号。@returns 当前空间列表；晚到成功和错误均转为取消，不回填旧数据。 */
    async function loadList({ signal, queryKey: requestedKey }: QueryFunctionContext): Promise<KnowledgeBaseView[]> {
        const owner = captureOwner();
        const generation = listGeneration;
        if (!owner || requestedKey.some((part, index) => part !== queryKey.value[index])) throw cancelled();
        try {
            const result = await fetchKnowledgeBases(owner.creator, signal);
            if (signal.aborted || generation !== listGeneration || !owns(owner)) throw cancelled();
            if (result.some(item => item.tenant_id !== owner.tenantID)) {
                throw new ApiError('知识库响应空间不匹配，请刷新账户后重试。', 0, 0, 'contract');
            }
            return result;
        } catch (error) {
            if (signal.aborted || generation !== listGeneration || !owns(owner)) throw cancelled();
            throw error;
        }
    }
    const listQuery = useQuery(computed(() => ({ queryKey: queryKey.value, queryFn: loadList,
        enabled: isEnabled.value, retry: false, gcTime: 0, staleTime: 0,
        refetchOnWindowFocus: false, refetchOnReconnect: false })));
    const items = computed(() => {
        if (!isEnabled.value || listQuery.isError.value) return [];
        // observer 的跨键更新是异步的，先核对当前键缓存的原始引用，连同租户的旧筛选快照也不展示。
        const observed = listQuery.data.value;
        const cached = queryClient.getQueryData<KnowledgeBaseView[]>(queryKey.value);
        if (!cached || !observed || toRaw(observed) !== toRaw(cached)) return [];
        return cached.filter(item => item.tenant_id === account.value?.tenant.id);
    });

    /** 取消已废弃的精确查询；不影响别的模块或空间。@param key 旧查询键。 */
    function cancelList(key: KnowledgeBaseQueryKey): void {
        void queryClient.cancelQueries({ queryKey: key, exact: true }).catch(() => undefined);
    }
    /** 废弃草稿反馈与旧提交回调；取消不保证回滚，必须先核对全部列表才允许重提。 */
    function clearDraftState(): void {
        if (isSubmitting.value) {
            needsVerification = true;
            verificationOwner = activeSubmissionOwner;
        }
        submissionGeneration += 1;
        submissionController?.abort();
        submissionController = undefined;
        isSubmitting.value = false;
        submitError.value = needsVerification ? '创建结果未确认，请先刷新全部列表核对，不要重复提交。' : '';
    }
    /** 同步使旧页面与查询代际失效，保留同身份的模糊写入保护。@param next 新查询键。@param previous 旧查询键。 */
    function changeContext(next: KnowledgeBaseQueryKey, previous: KnowledgeBaseQueryKey): void {
        contextGeneration += 1;
        listGeneration += 1;
        cancelList(previous);
        clearDraftState();
        const nextOwner = `${next[1]}:${next[2]}:${next[3]}`;
        if (!next[2] && verificationOwner.startsWith(`${next[1]}:`)) {
            // me 重新校验期间隐藏反馈，但不能借此解除同身份待核对的写入保护。
            submitError.value = '';
        } else if (verificationOwner !== nextOwner) {
            needsVerification = false;
            verificationOwner = '';
            submitError.value = '';
        }
    }
    watch(queryKey, changeContext, { flush: 'sync' });

    /** 取消旧列表后提升代际，再读取当前归属；失败不假报空列表。@param owner 原归属。@returns 成功且仍归属当前页面时为 true。 */
    async function refreshOwnedList(owner: KnowledgeBaseOwnership): Promise<boolean> {
        if (!owns(owner)) return false;
        listGeneration += 1;
        await queryClient.cancelQueries({ queryKey: queryKey.value, exact: true });
        if (!owns(owner)) return false;
        const result = await listQuery.refetch();
        return owns(owner) && !result.isError && !!result.data;
    }
    /** 手动核对列表；只有当前身份的全部列表成功读回后才解除模糊创建保护，失败保留错误和输入。@returns 不向事件处理器抛错。 */
    async function retryList(): Promise<void> {
        if (isSubmitting.value) return;
        const owner = captureOwner();
        if (!owner) return;
        try {
            const refreshed = await refreshOwnedList(owner);
            if (!refreshed || !owns(owner)) return;
            if (owner.creator === 'all' && !isSubmitting.value) {
                needsVerification = false;
                verificationOwner = '';
                submitError.value = '';
            }
        } catch {
            if (owns(owner) && needsVerification) submitError.value = '列表核对尚未成功，请重试全部列表，确认前不要重复创建。';
        }
    }
    /** 同步锁定单次创建，捕获归属后只发送一次 POST。成功先取消旧列表再重读；不确定结果要求核对，旧 success/error/finally 不改新草稿。@param input 表单白名单输入。@returns 仅当前归属的确定创建成功为 true；列表失败单独提示，不误报创建失败。 */
    async function submit(input: CreateKnowledgeBaseInput): Promise<boolean> {
        if (isSubmitting.value || disposed) return false;
        if (needsVerification) {
            submitError.value = '创建结果未确认，请先刷新全部列表核对，不要重复提交。';
            return false;
        }
        const owner = captureOwner();
        if (!owner || !canCreate.value) { submitError.value = '请先确认当前账户及空间创建权限。'; return false; }
        isSubmitting.value = true;
        submitError.value = '';
        const generation = ++submissionGeneration;
        const controller = new AbortController();
        submissionController = controller;
        activeSubmissionOwner = ownerKey.value;
        /** 保护本次提交的每个异步分支。@returns 是否仍拥有提交锁与原页面。 */
        const ownsSubmission = (): boolean => generation === submissionGeneration && owns(owner) && !controller.signal.aborted;
        try {
            const created = await createKnowledgeBase(input, controller.signal);
            if (!ownsSubmission()) return false;
            if (created.tenant_id !== owner.tenantID || created.creator_id !== owner.userID) {
                throw new ApiError('创建响应归属不匹配，请先刷新列表核对。', 0, 0, 'contract');
            }
            let refreshed = false;
            try { refreshed = await refreshOwnedList(owner); }
            catch { /* 已确认创建，重查失败不能改写创建结果。 */ }
            if (!ownsSubmission()) return false;
            submitError.value = refreshed ? '' : '知识库已创建，但列表刷新未成功；请重试列表，不要再次提交创建。';
            return true;
        } catch (error) {
            if (!ownsSubmission()) return false;
            needsVerification = !(error instanceof ApiError) || ['network', 'timeout', 'contract', 'cancelled'].includes(error.kind)
                || error.status >= 500 || error.status === 401;
            if (needsVerification) verificationOwner = ownerKey.value;
            submitError.value = error instanceof ApiError && error.status === 401
                ? '会话需要确认，请先刷新全部列表确认会话，再重新提交。'
                : needsVerification ? '创建结果未确认，请先刷新全部列表核对，不要直接重复提交。'
                    : error instanceof ApiError ? error.message : '知识库创建未完成。';
            return false;
        } finally {
            if (ownsSubmission()) {
                isSubmitting.value = false;
                submissionController = undefined;
            }
        }
    }
    onScopeDispose(() => {
        disposed = true;
        contextGeneration += 1;
        listGeneration += 1;
        submissionGeneration += 1;
        submissionController?.abort();
        cancelList(queryKey.value);
    });
    return { account, accountQuery, listQuery, items, canCreate, creator, submit, isSubmitting, submitError, retryList, clearDraftState };
}
