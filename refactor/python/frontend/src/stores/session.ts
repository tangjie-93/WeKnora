import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { SessionSnapshot, SessionStatus, TokenPair } from '../types/auth';

const CREDENTIALS_KEY = 'weknora.auth.v1';
const LOGOUT_KEY = 'weknora.auth.v1.pending-logout';

/** 验证本地凭据形状，不把浏览器存储当作身份或权限来源。@param value 待验证值。@returns 是否为有界令牌对。 */
function isTokenPair(value: unknown): value is TokenPair {
    if (!value || typeof value !== 'object') return false;
    return 'accessToken' in value && validToken(value.accessToken)
        && 'refreshToken' in value && validToken(value.refreshToken);
}
/** 校验本地令牌长度。@param value 未可信值。@returns 是否可作为有界凭据提交。 */
function validToken(value: unknown): value is string {
    return typeof value === 'string' && value.length > 0 && new TextEncoder().encode(value).length <= 4096;
}

/** 仅管理凭据与生命周期；用户和空间始终由 me 查询提供。@returns 会话原语与只含令牌的状态。 */
export const useSessionStore = defineStore('session', () => {
    const accessToken = ref('');
    const refreshToken = ref('');
    const status = ref<SessionStatus>('anonymous');
    const epoch = ref(0);
    const pendingLogout = ref('');
    const storageError = ref('');
    let controller = new AbortController();

    /** 切断旧会话异步回写；不宣称 abort 能撤销服务器操作。@returns 新 epoch。 */
    function advanceEpoch(): number {
        controller.abort();
        controller = new AbortController();
        epoch.value += 1;
        return epoch.value;
    }
    /** 恢复本标签令牌；待退出优先，解析失败不恢复身份。 */
    function restoreCredentials(): void {
        try {
            const pending = sessionStorage.getItem(LOGOUT_KEY);
            if (pending && validToken(pending)) {
                pendingLogout.value = pending;
                status.value = 'terminating';
                sessionStorage.removeItem(CREDENTIALS_KEY);
                return;
            }
            const raw = sessionStorage.getItem(CREDENTIALS_KEY);
            if (!raw) return;
            const parsed: unknown = JSON.parse(raw);
            if (!isTokenPair(parsed)) {
                sessionStorage.removeItem(CREDENTIALS_KEY);
                return;
            }
            accessToken.value = parsed.accessToken;
            refreshToken.value = parsed.refreshToken;
            status.value = 'restoring';
        } catch {
            storageError.value = '无法读取本标签会话存储，请检查浏览器隐私设置后重试。';
        }
    }
    /** 安装完整令牌对；持久化失败不进入成功会话。@param tokens 新令牌对。@param expectedEpoch 发起操作的 epoch。@returns 是否仍属于当前会话。 */
    function installTokens(tokens: TokenPair, expectedEpoch: number): boolean {
        if (epoch.value !== expectedEpoch || pendingLogout.value) return false;
        sessionStorage.setItem(CREDENTIALS_KEY, JSON.stringify(tokens));
        accessToken.value = tokens.accessToken;
        refreshToken.value = tokens.refreshToken;
        status.value = 'restoring';
        return true;
    }
    /** 清除凭据并取消旧请求；不清除独立的待退出记录。 */
    function invalidateSession(): void {
        advanceEpoch();
        accessToken.value = '';
        refreshToken.value = '';
        status.value = pendingLogout.value ? 'terminating' : 'anonymous';
        try { sessionStorage.removeItem(CREDENTIALS_KEY); }
        catch { storageError.value = '浏览器会话清理失败，请关闭本标签后再使用。'; }
    }
    /** 先保存幂等退出凭据，再失效身份；失败仍在本标签阻止新登录。 */
    function beginLogout(): void {
        pendingLogout.value = refreshToken.value || accessToken.value || pendingLogout.value;
        try {
            if (pendingLogout.value) sessionStorage.setItem(LOGOUT_KEY, pendingLogout.value);
        } catch {
            storageError.value = '无法持久保存待退出状态；请保持本标签打开并重试服务端退出。';
        }
        invalidateSession();
    }
    /** 服务端确认撤销后才移除 pending；存储失败继续阻止登录，允许幂等重试。 */
    function completeLogout(): void {
        sessionStorage.removeItem(LOGOUT_KEY);
        sessionStorage.removeItem(CREDENTIALS_KEY);
        pendingLogout.value = '';
        status.value = 'anonymous';
        storageError.value = '';
    }
    /** 获取请求快照，不包含用户、空间或角色。@returns 可用会话快照或 null。 */
    function snapshot(): SessionSnapshot | null {
        if (!accessToken.value || pendingLogout.value) return null;
        return { accessToken: accessToken.value, refreshToken: refreshToken.value, epoch: epoch.value, signal: controller.signal };
    }
    return { accessToken, refreshToken, status, epoch, pendingLogout, storageError,
        restoreCredentials, installTokens, invalidateSession, beginLogout, completeLogout, snapshot };
});
