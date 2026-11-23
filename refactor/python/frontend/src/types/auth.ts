import type { ComputedRef, Ref } from 'vue';
import type { QueryClient, UseQueryReturnType } from '@tanstack/vue-query';
import type { Router } from 'vue-router';

export interface AuthUserInfo {
    id: string;
    username: string;
    email: string;
    avatar: string | null;
    tenant_id: number;
    is_active: boolean;
    can_access_all_tenants: boolean;
    is_system_admin: boolean;
    preferences: Record<string, unknown>;
    created_at: string | null;
    updated_at: string | null;
}
export interface AuthUser extends AuthUserInfo { deleted_at: null }
export interface AuthTenant {
    id: number;
    name: string;
    description: string | null;
    status: string;
    retriever_engines: unknown[];
    business: string;
    storage_quota: number;
    storage_used: number;
    created_at: string | null;
    updated_at: string | null;
    deleted_at: null;
}
export interface AuthMembership { tenant_id: number; tenant_name: string; role: string }
export interface CurrentAccount {
    user: AuthUserInfo;
    tenant: AuthTenant;
    memberships: AuthMembership[];
    preference_defaults: { browser_search_instructions: string };
    tenant_required: false;
    capabilities: { can_create_tenant: false; auto_accept_invitation: false };
}
export interface RegisterInput { username: string; email: string; password: string }
export interface LoginInput { email: string; password: string }
export interface RegisterResponse { success: true; message: string; user: AuthUser }
export interface LoginResponse {
    success: true;
    message: string;
    user: AuthUser;
    active_tenant: AuthTenant;
    memberships: AuthMembership[];
    token: string;
    refresh_token: string;
}
export interface RefreshResponse { success: true; message: string; access_token: string; refresh_token: string }
export interface MessageResponse { success: true; message: string }
export interface CurrentAccountResponse { success: true; data: CurrentAccount }
export interface TokenPair { accessToken: string; refreshToken: string }
export type SessionStatus = 'anonymous' | 'restoring' | 'authenticated' | 'terminating';
export interface SessionSnapshot extends TokenPair { epoch: number; signal: AbortSignal }
export interface SessionAccess {
    snapshot: () => SessionSnapshot | null;
    install: (tokens: TokenPair, epoch: number) => boolean;
    expire: (epoch: number) => void;
    refresh: (refreshToken: string, signal: AbortSignal) => Promise<TokenPair>;
}
export interface RequestOptions {
    method?: 'GET' | 'POST';
    body?: unknown;
    signal?: AbortSignal;
    authenticated?: boolean;
    bearer?: string;
}
export interface RefreshFlight { epoch: number; promise: Promise<void> }
export type ApiFailureKind = 'http' | 'network' | 'timeout' | 'contract' | 'cancelled' | 'storage';
export interface SessionRuntimeOptions { queryClient: QueryClient; router: Router }
export interface RegistrationNotice { email: string; message: string }
export interface SessionActions {
    signIn: (input: LoginInput, signal?: AbortSignal) => Promise<void>;
    signOut: () => Promise<void>;
    retryPendingLogout: () => Promise<void>;
    logoutError: Ref<string>;
    isLoggingOut: Ref<boolean>;
    registrationNotice: Ref<RegistrationNotice | null>;
}
export interface CurrentAccountView {
    query: UseQueryReturnType<CurrentAccount, Error>;
    account: ComputedRef<CurrentAccount | undefined>;
}
