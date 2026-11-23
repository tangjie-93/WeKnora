import { ApiError, isRecord, requestJson } from './client';
import type { AuthMembership, AuthTenant, AuthUserInfo, CurrentAccount, LoginInput, RegisterInput, TokenPair } from '../types/auth';

/** 拒绝成功封装不匹配的响应，不将未验证数据当作身份。@param value 响应。@returns 成功对象。 */
function success(value: unknown): Record<string, unknown> {
    if (!isRecord(value) || value.success !== true) throw new ApiError('服务响应格式不正确，请重试。', 0, 0, 'contract');
    return value;
}
/** 检查公开用户字段。@param value 未可信值。@returns 是否公开用户信息。 */
function isUser(value: unknown): value is AuthUserInfo {
    return isRecord(value) && ['id', 'username', 'email'].every(key => typeof value[key] === 'string')
        && ['avatar', 'created_at', 'updated_at'].every(key => value[key] === null || typeof value[key] === 'string')
        && typeof value.tenant_id === 'number' && typeof value.is_active === 'boolean'
        && typeof value.can_access_all_tenants === 'boolean' && typeof value.is_system_admin === 'boolean' && isRecord(value.preferences);
}
/** 检查安全空间投影。@param value 未可信值。@returns 是否空间。 */
function isTenant(value: unknown): value is AuthTenant {
    return isRecord(value) && typeof value.id === 'number' && value.id > 0
        && ['name', 'status', 'business'].every(key => typeof value[key] === 'string')
        && ['description', 'created_at', 'updated_at'].every(key => value[key] === null || typeof value[key] === 'string')
        && Array.isArray(value.retriever_engines) && typeof value.storage_quota === 'number'
        && typeof value.storage_used === 'number' && value.deleted_at === null;
}
/** 检查真实成员投影，不按用户tenant_id推导角色。@param value 未可信值。@returns 是否成员数组。 */
function isMemberships(value: unknown): value is AuthMembership[] {
    return Array.isArray(value) && value.every(item => isRecord(item) && typeof item.tenant_id === 'number'
        && typeof item.tenant_name === 'string' && typeof item.role === 'string');
}
/** 提取有界令牌字段。@param value 未可信值。@returns 令牌。 */
function token(value: unknown): string {
    if (typeof value !== 'string' || !value || new TextEncoder().encode(value).length > 4096) {
        throw new ApiError('服务返回的会话格式不正确。', 0, 0, 'contract');
    }
    return value;
}
/** 注册仅创建账户；不安装登录状态。@param input 注册字段。@param signal 页面取消信号。@returns 成功完成，失败抛安全错误。 */
export async function registerAccount(input: RegisterInput, signal?: AbortSignal): Promise<void> {
    const data = success(await requestJson('/api/v1/auth/register', { method: 'POST', body: input, signal }));
    if (!isUser(data.user) || !('deleted_at' in data.user) || data.user.deleted_at !== null || typeof data.message !== 'string') throw new ApiError('注册响应格式不正确。', 0, 0, 'contract');
}
/** 登录只提取令牌，身份仍由后续me读取。@param input 凭据。@param signal 取消信号。@returns 完整令牌对，失败不改变store。 */
export async function loginAccount(input: LoginInput, signal?: AbortSignal): Promise<TokenPair> {
    const data = success(await requestJson('/api/v1/auth/login', { method: 'POST', body: input, signal }));
    if (!isUser(data.user) || !isTenant(data.active_tenant) || !isMemberships(data.memberships)) throw new ApiError('登录响应格式不正确。', 0, 0, 'contract');
    return { accessToken: token(data.token), refreshToken: token(data.refresh_token) };
}
/** 读取唯一账户真源；请求取消/失败不返回旧身份。@param signal 查询取消信号。@returns 当前账户与空间。 */
export async function fetchCurrentAccount(signal?: AbortSignal): Promise<CurrentAccount> {
    const response = success(await requestJson('/api/v1/auth/me', { authenticated: true, signal }));
    const data = response.data;
    if (!isRecord(data) || !isUser(data.user) || !isTenant(data.tenant) || !isMemberships(data.memberships)
        || !isRecord(data.preference_defaults) || typeof data.preference_defaults.browser_search_instructions !== 'string'
        || data.tenant_required !== false || !isRecord(data.capabilities)
        || data.capabilities.can_create_tenant !== false || data.capabilities.auto_accept_invitation !== false) {
        throw new ApiError('账户响应格式不正确，请重试。', 0, 0, 'contract');
    }
    return data as unknown as CurrentAccount;
}
/** 按原合同refreshToken提交，不递归触发刷新拦截。@param refreshToken 刷新凭据。@param signal 会话取消信号。@returns 轮换令牌对，失败抛错。 */
export async function refreshSession(refreshToken: string, signal: AbortSignal): Promise<TokenPair> {
    const data = success(await requestJson('/api/v1/auth/refresh', { method: 'POST', body: { refreshToken }, signal }));
    return { accessToken: token(data.access_token), refreshToken: token(data.refresh_token) };
}
/** 使用快照refresh凭据确认服务端全会话撤销；不自动刷新或重试。@param bearer 退出专用凭据。@returns 服务器确认成功，失败由调用方保留pending。 */
export async function logoutAccount(bearer: string): Promise<void> {
    const data = success(await requestJson('/api/v1/auth/logout', { method: 'POST', bearer }));
    if (typeof data.message !== 'string') throw new ApiError('退出响应格式不正确。', 0, 0, 'contract');
}
