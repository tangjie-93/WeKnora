import { reactive } from 'vue'

export interface Membership {
  tenant_id: number
  tenant_name?: string
  role?: number
}

export interface AuthState {
  token: string
  refreshToken: string
  tenantId: number
  tenantName: string
  userName: string
  email: string
}

const STORAGE_KEY = 'weknora.auth'

const defaults: AuthState = {
  token: '',
  refreshToken: '',
  tenantId: 0,
  tenantName: '',
  userName: '',
  email: '',
}

function load(): AuthState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? { ...defaults, ...(JSON.parse(raw) as Partial<AuthState>) } : { ...defaults }
  } catch {
    return { ...defaults }
  }
}

export const auth = reactive<AuthState>(load())

export function saveAuth(patch: Partial<AuthState>): void {
  Object.assign(auth, patch)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(auth))
}

export function clearAuth(): void {
  Object.assign(auth, defaults)
  localStorage.removeItem(STORAGE_KEY)
}

export function isLoggedIn(): boolean {
  return Boolean(auth.token)
}
