import { ApiError, isRecord, requestJson } from './client';
import type { CreateKnowledgeBaseInput, KnowledgeBaseCreator, KnowledgeBaseView } from '../types/knowledge-bases';

/** 检查非负安全整数，避免错误计数或非有限数字进入界面。@param value 未可信字段。@returns 是否有效计数。 */
function isCount(value: unknown): value is number {
    return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}
/** 检查带时区的 RFC3339 时间。@param value 未可信字段。@returns 是否有效时间。 */
function isTimestamp(value: unknown): value is string {
    return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)
        && Number.isFinite(Date.parse(value));
}
/** 校验一组配置字段类型，不使用未检查的对象断言。@param value 配置对象。@param keys 字段集合。@param kind 预期类型。@returns 字段是否全部有效。 */
function hasFields(value: unknown, keys: string[], kind: 'string' | 'boolean'): boolean {
    return isRecord(value) && keys.every(key => typeof value[key] === kind);
}
/** 校验冻结响应中的配置结构，损坏配置不能被转换成空模型或默认值。@param value 响应对象。@returns 是否符合本轮配置合同。 */
function hasConfigurations(value: Record<string, unknown>): boolean {
    const chunking = value.chunking_config;
    return isRecord(chunking) && isCount(chunking.chunk_size) && isCount(chunking.chunk_overlap)
        && (chunking.separators === null || (Array.isArray(chunking.separators) && chunking.separators.every(item => typeof item === 'string')))
        && hasFields(value.image_processing_config, ['model_id'], 'string')
        && hasFields(value.vlm_config, ['model_id', 'model_name', 'base_url', 'api_key', 'interface_type'], 'string')
        && hasFields(value.vlm_config, ['enabled'], 'boolean')
        && hasFields(value.asr_config, ['model_id', 'language'], 'string') && hasFields(value.asr_config, ['enabled'], 'boolean')
        && (value.storage_provider_config === null || hasFields(value.storage_provider_config, ['provider'], 'string'))
        && hasFields(value.storage_config, ['secret_id', 'secret_key', 'region', 'bucket_name', 'app_id', 'path_prefix', 'provider'], 'string')
        && hasFields(value.indexing_strategy, ['vector_enabled', 'keyword_enabled', 'wiki_enabled', 'graph_enabled'], 'boolean')
        && hasFields(value.capabilities, ['vector', 'keyword', 'wiki', 'graph', 'faq'], 'boolean')
        && ['extract_config', 'faq_config', 'question_generation_config', 'auto_tag_config', 'wiki_config', 'profile_config'].every(key => value[key] === null);
}
/** 验证知识库关键字段及全部公开配置；不接受缺失数组、标识、计数或时间。@param value 未可信 JSON。@returns 是否为冻结的知识库投影。 */
function isKnowledgeBase(value: unknown): value is KnowledgeBaseView {
    return isRecord(value) && typeof value.id === 'string' && /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i.test(value.id)
        && typeof value.name === 'string' && value.name.length > 0 && typeof value.description === 'string'
        && value.type === 'document' && isCount(value.tenant_id) && value.tenant_id > 0 && typeof value.creator_id === 'string'
        && value.is_temporary === false && value.deleted_at === null && isTimestamp(value.created_at) && isTimestamp(value.updated_at)
        && value.embedding_model_id === '' && value.summary_model_id === '' && hasConfigurations(value)
        && ['knowledge_count', 'chunk_count', 'processing_count', 'share_count'].every(key => isCount(value[key]))
        && typeof value.is_processing === 'boolean' && typeof value.is_pinned === 'boolean'
        && (value.pinned_at === null || isTimestamp(value.pinned_at))
        && ['vector_store_id', 'storage_backend_id'].every(key => !(key in value) || (typeof value[key] === 'string' && value[key].length > 0))
        && (!('creator_name' in value) || typeof value.creator_name === 'string')
        && value.vector_store_source === 'unavailable' && value.vector_store_status === 'unavailable';
}
/** 产生业务专属合同错误，不使用认证页面文案。@returns 安全错误；创建时由调用方按结果未确认处理。 */
function contractFailure(): ApiError {
    return new ApiError('知识库服务响应格式不正确，请刷新列表核对后再操作。', 0, 0, 'contract');
}
/** 将请求错误映射为知识库上下文；不展示原始响应或认证字段提示。@param error 捕获错误。@param writing 是否非幂等创建。@returns 安全业务错误。 */
function knowledgeBaseFailure(error: unknown, writing: boolean): ApiError {
    if (!(error instanceof ApiError)) return new ApiError('知识库请求结果未确认，请先刷新列表核对。', 0, 0, 'network');
    let message = '知识库请求未成功，请检查输入后重试。';
    if (error.kind === 'contract') message = '知识库服务响应格式不正确，请刷新列表核对后再操作。';
    else if (error.kind === 'cancelled') message = '知识库请求已取消；取消接收不保证撤销服务端创建。';
    else if (error.kind === 'network' || error.kind === 'timeout') message = writing
        ? '创建结果未确认，请先刷新列表核对，不要直接重复提交。' : '无法读取知识库，请检查网络后重试列表。';
    else if (error.status === 401) message = writing
        ? '会话需要确认，请先刷新列表确认会话，再重新提交。' : '会话已失效，请重新登录后读取知识库。';
    else if (error.status === 403) message = '当前空间不可用或没有知识库操作权限，请刷新账户或退出后联系维护者。';
    else if (error.status === 400 && error.code === 1010) message = '知识库请求的认证信息不符合要求，请退出后重新登录。';
    else if (error.status === 400) message = '知识库提交内容、存储配置或容量不符合要求；请检查名称、描述及本空间 100 条容量限制。';
    else if (error.status === 503) message = '知识库暂不可用：请检查业务存储、100 条容量或已有配置是否超出当前支持范围。';
    else if (error.status >= 500) message = '知识库存储或服务处理失败，请稍后刷新列表核对；不要直接重复创建。';
    return new ApiError(message, error.status, error.code, error.kind);
}
/** 读取当前空间真实列表；失败抛业务错误，绝不把畸形或失败响应当作空数组。@param creator 创建者筛选。@param signal 取消信号。@returns 已校验列表；取消时释放底层请求资源。 */
export async function fetchKnowledgeBases(creator: KnowledgeBaseCreator, signal?: AbortSignal): Promise<KnowledgeBaseView[]> {
    try {
        const value = await requestJson(`/api/v1/knowledge-bases?creator=${encodeURIComponent(creator)}`, { authenticated: true, signal });
        if (!isRecord(value) || value.success !== true || !Array.isArray(value.data) || value.data.length > 100 || !value.data.every(isKnowledgeBase)) throw contractFailure();
        return value.data;
    } catch (error) { throw knowledgeBaseFailure(error, false); }
}
/** 仅发送一次非幂等创建；不自动刷新重发 POST。@param input 白名单输入。@param signal 取消接收信号，不代表服务端回滚。@returns 已确认的服务端投影；失败抛安全错误并由 Hook 决定核对恢复。 */
export async function createKnowledgeBase(input: CreateKnowledgeBaseInput, signal?: AbortSignal): Promise<KnowledgeBaseView> {
    try {
        const value = await requestJson('/api/v1/knowledge-bases', { method: 'POST', body: input, authenticated: true, signal });
        if (!isRecord(value) || value.success !== true || !isKnowledgeBase(value.data)) throw contractFailure();
        return value.data;
    } catch (error) { throw knowledgeBaseFailure(error, true); }
}
