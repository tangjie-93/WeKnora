import type {
  KnowledgeBase,
  KnowledgeItem,
  LoginResponse,
  SearchHit,
  Session,
  SessionPage,
  ChatMessage,
  WikiIndex,
  WikiGraph,
  WikiPage,
  WikiStats,
  WikiSearchResponse,
} from './types/api'

const BASE = import.meta.env.VITE_WEKNORA_URL || 'http://10.10.14.40:8080/api/v1'
let token = sessionStorage.getItem('weknora_token') || ''
let tenantId = sessionStorage.getItem('weknora_tenant') || ''
export function setAuth(nextToken: string, nextTenant: number | string) { token = nextToken; tenantId = String(nextTenant); sessionStorage.setItem('weknora_token', token); sessionStorage.setItem('weknora_tenant', tenantId) }
export function clearAuth() { token = ''; tenantId = ''; sessionStorage.clear() }
function authHeaders() { const headers: Record<string, string> = {}; if (token) headers.Authorization = `Bearer ${token}`; if (tenantId) headers['X-Tenant-ID'] = tenantId; return headers }

// encodeSlugPath escapes each segment of a hierarchical wiki slug while
// keeping the "/" separators, matching the Go router's wildcard param.
function encodeSlugPath(slug: string) { return slug.split('/').map(encodeURIComponent).join('/') }

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (tenantId) headers.set('X-Tenant-ID', tenantId)
  const response = await fetch(`${BASE}${path}`, { ...init, headers })
  if (response.status === 401 && !path.startsWith('/auth/login')) {
    clearAuth()
    window.dispatchEvent(new Event('weknora:unauthorized'))
    throw new Error('登录已失效，请重新连接知识库')
  }
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body?.error?.message || body?.message || `请求失败（${response.status}）`)
  return body as T
}

// The Go backend returns some collections wrapped in { data }, others bare.
// unwrap keeps callers independent of that inconsistency.
function unwrap<T>(body: unknown): T {
  if (body && typeof body === 'object' && 'data' in (body as Record<string, unknown>) && (body as Record<string, unknown>).data != null) {
    return (body as { data: T }).data
  }
  return body as T
}

export const api = {
  login: async (email: string, password: string) => {
    const body = await request<LoginResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
    if (!body.token) throw new Error(body.message || '登录失败')
    setAuth(body.token, body.active_tenant?.id || '')
    return body
  },
  listKbs: async () => unwrap<KnowledgeBase[]>(await request('/knowledge-bases')) || [],
  createKb: async (name: string, description: string) => unwrap<KnowledgeBase>(await request('/knowledge-bases', { method: 'POST', body: JSON.stringify({ name, description }) })),
  upload: async (kbId: string, file: File, progress: (value: number) => void) => new Promise<KnowledgeItem>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const form = new FormData()
    form.append('file', file)
    xhr.open('POST', `${BASE}/knowledge-bases/${kbId}/knowledge/file`)
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    if (tenantId) xhr.setRequestHeader('X-Tenant-ID', tenantId)
    xhr.upload.onprogress = (e) => e.lengthComputable && progress(Math.round((e.loaded / e.total) * 100))
    xhr.onerror = () => reject(new Error('上传失败，请检查后端地址'))
    xhr.onload = () => {
      const body = JSON.parse(xhr.responseText || '{}')
      xhr.status >= 200 && xhr.status < 300 ? resolve(unwrap<KnowledgeItem>(body)) : reject(new Error(body?.error?.message || '上传失败'))
    }
    xhr.send(form)
  }),
  listKnowledge: async (kbId: string) => unwrap<KnowledgeItem[]>(await request(`/knowledge-bases/${kbId}/knowledge?page=1&page_size=100`)) || [],
  deleteKnowledge: async (id: string) => request(`/knowledge/${id}`, { method: 'DELETE' }),
  reparseKnowledge: async (id: string) => request(`/knowledge/${id}/reparse`, { method: 'POST' }),
  previewKnowledge: async (id: string) => {
    const response = await fetch(`${BASE}/knowledge/${id}/preview`, { headers: authHeaders() })
    if (!response.ok) throw new Error(`预览失败（${response.status}）`)
    return response.blob()
  },
  wikiIndex: async (kbId: string) => unwrap<WikiIndex>(await request(`/knowledgebase/${kbId}/wiki/index?limit=100`)),
  wikiGraph: async (kbId: string) => {
    const graph = unwrap<WikiGraph>(await request(`/knowledgebase/${kbId}/wiki/graph?mode=overview&limit=100`))
    return { nodes: graph?.nodes || [], edges: graph?.edges || [], meta: graph?.meta } as WikiGraph
  },
  wikiStats: async (kbId: string) => unwrap<WikiStats>(await request(`/knowledgebase/${kbId}/wiki/stats`)),
  wikiPage: async (kbId: string, slug: string) => unwrap<WikiPage>(await request(`/knowledgebase/${kbId}/wiki/pages/${encodeSlugPath(slug)}`)),
  wikiSearch: async (kbId: string, q: string, limit = 20) => {
    const result = unwrap<WikiSearchResponse>(await request(`/knowledgebase/${kbId}/wiki/search?q=${encodeURIComponent(q)}&limit=${limit}`))
    return result || { pages: [] }
  },
  // Backend DTO uses query_text (types/search.go); `query` returns 400.
  search: async (kbId: string, query: string) => unwrap<SearchHit[]>(await request(`/knowledge-bases/${kbId}/hybrid-search`, { method: 'POST', body: JSON.stringify({ query_text: query, match_count: 8 }) })) || [],
  createSession: async (title = '新对话') => unwrap<Session>(await request('/sessions', { method: 'POST', body: JSON.stringify({ title }) })),
  listSessions: async () => unwrap<Session[]>(await request<SessionPage>('/sessions?page=1&page_size=50')) || [],
  // Sessions are knowledge-base-independent; rename only sends title so the
  // backend keeps the stored description untouched.
  renameSession: async (id: string, title: string) => unwrap<Session>(await request(`/sessions/${id}`, { method: 'PUT', body: JSON.stringify({ title }) })),
  deleteSession: async (id: string) => request(`/sessions/${id}`, { method: 'DELETE' }),
  clearSessionMessages: async (id: string) => request(`/sessions/${id}/messages`, { method: 'DELETE' }),
  batchDeleteSessions: async (ids: string[]) => request('/sessions/batch', { method: 'DELETE', body: JSON.stringify({ ids }) }),
  toggleSessionPin: async (id: string, pinned: boolean) => request(`/sessions/${id}/pin`, { method: pinned ? 'POST' : 'DELETE' }),
  loadMessages: async (sessionId: string) => unwrap<ChatMessage[]>(await request(`/messages/${sessionId}/load`)) || [],
  // knowledge_base_ids is what scopes retrieval; omitting it makes the model
  // answer without any of the workspace content.
  streamChat: async (sessionId: string, kbId: string, query: string, onEvent: (event: Record<string, unknown>) => void) => {
    const response = await fetch(`${BASE}/knowledge-chat/${sessionId}`, {
      method: 'POST',
      headers: { ...authHeaders(), 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ query, knowledge_base_ids: kbId ? [kbId] : [] }),
    })
    if (!response.ok || !response.body) throw new Error(`对话请求失败（${response.status}）`)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() || ''
      for (const block of blocks) {
        const line = block.split('\n').find((item) => item.trim().startsWith('data:'))
        if (!line) continue
        const raw = line.trim().slice(5).trim()
        if (!raw) continue
        try {
          onEvent(JSON.parse(raw) as Record<string, unknown>)
        } catch {
          // Ignore malformed keep-alive frames instead of killing the stream.
        }
      }
    }
  },
}
