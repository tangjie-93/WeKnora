import { auth, clearAuth, saveAuth } from './auth'

const BASE = '/api/v1'

export interface ApiErrorBody {
  code: number
  message: string
  details?: unknown
}

export class ApiError extends Error {
  code: number
  status: number

  constructor(message: string, code: number, status: number) {
    super(message)
    this.code = code
    this.status = status
  }
}

function buildHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = { ...extra }
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`
  if (auth.tenantId) headers['X-Tenant-ID'] = String(auth.tenantId)
  return headers
}

async function refreshTokens(): Promise<boolean> {
  if (!auth.refreshToken) return false
  const response = await fetch(`${BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: auth.refreshToken }),
  })
  if (!response.ok) {
    clearAuth()
    return false
  }
  const data = (await response.json()) as {
    access_token?: string
    refresh_token?: string
  }
  if (!data.access_token) {
    clearAuth()
    return false
  }
  saveAuth({
    token: data.access_token,
    refreshToken: data.refresh_token || auth.refreshToken,
  })
  return true
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<T> {
  const headers = buildHeaders(
    options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' },
  )
  const response = await fetch(`${BASE}${path}`, { ...options, headers })
  if (response.status === 401 && retry && auth.refreshToken) {
    if (await refreshTokens()) return request<T>(path, options, false)
  }

  const payload = (await response.json().catch(() => null)) as
    | { success?: boolean; error?: ApiErrorBody; data?: unknown }
    | null

  if (!response.ok || payload?.success === false) {
    const message =
      payload?.error?.message || `${response.status} ${response.statusText}`
    throw new ApiError(message, payload?.error?.code ?? response.status, response.status)
  }
  return payload as T
}

// ---------------------------------------------------------------- 类型定义

export interface UserPayload {
  id: string
  username: string
  email: string
  tenant_id: number
}

export interface TenantPayload {
  id: number
  name: string
  description: string
}

export interface Membership {
  tenant_id: number
  tenant_name: string
  role: string
}

export interface LoginResponse {
  success: boolean
  user: UserPayload
  active_tenant: TenantPayload | null
  memberships: Membership[]
  token: string
  refresh_token: string
}

export interface ModelParameters {
  base_url?: string
  api_key?: string
  embedding_parameters?: { dimension?: number }
  [key: string]: unknown
}

export interface ModelItem {
  id: string
  name: string
  display_name: string
  type: string
  source: string
  description: string
  parameters: ModelParameters
  is_default: boolean
  status: string
  created_at: string | null
}

export interface TestResult {
  ok: boolean
  reply?: string
  dimension?: number
  latency_ms?: number
}

export interface ChunkingConfig {
  chunk_size?: number
  chunk_overlap?: number
}

export interface KnowledgeBase {
  id: string
  name: string
  description: string
  type: string
  chunking_config: ChunkingConfig
  embedding_model_id: string
  indexing_strategy?: Record<string, unknown>
  faq_config?: Record<string, unknown>
  created_at: string | null
}

export interface KnowledgeItem {
  id: string
  knowledge_base_id: string
  type: string
  title: string
  parse_status: string
  file_name: string
  file_type: string
  file_size: number
  error_message: string
  folder_path?: string
  tag_ids?: string[]
  created_at: string | null
}

export interface KnowledgeTag {
  id: string
  seq_id: number
  knowledge_base_id: string
  name: string
  color: string
  sort_order: number
  knowledge_count: number
  chunk_count: number
  created_at: string | null
  updated_at: string | null
}

export interface TagPage {
  total: number
  page: number
  page_size: number
  data: KnowledgeTag[]
}

export interface FolderNode {
  path: string
  name: string
  document_count: number
  total_count: number
  children?: FolderNode[]
}

export interface FolderTree {
  root_document_count: number
  total_document_count: number
  folders: FolderNode[]
}

export interface FaqEntry {
  id: number
  chunk_id: string
  knowledge_id: string
  knowledge_base_id: string
  tag_id: number
  tag_name: string
  is_enabled: boolean
  is_recommended: boolean
  standard_question: string
  similar_questions: string[]
  negative_questions: string[]
  answers: string[]
  answer_strategy: string
  index_mode: string
  created_at: string | null
  updated_at: string | null
}

export interface FaqEntryPage {
  total: number
  page: number
  page_size: number
  data: FaqEntry[]
}

export interface FaqSearchHit extends FaqEntry {
  score: number
  match_type: string
  matched_question: string
}

export interface WikiPage {
  id: string
  tenant_id: number
  knowledge_base_id: string
  slug: string
  title: string
  page_type: string
  status: string
  content: string
  summary: string
  parent_slug: string
  folder_id: string
  category_path: string[]
  wiki_path: string
  depth: number
  sort_order: number
  source_refs: string[]
  chunk_refs: string[]
  in_links: string[]
  out_links: string[]
  aliases: string[]
  page_metadata: Record<string, unknown>
  version: number
  last_edit_source: string
  last_editor_id: string
  created_at: string | null
  updated_at: string | null
}

export interface WikiPageList {
  pages: WikiPage[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface WikiRevision {
  id: string
  page_id: string
  slug: string
  version: number
  title: string
  page_type: string
  status: string
  summary: string
  aliases: string[]
  edit_source: string
  editor_id: string
  edited_at: string | null
  content?: string
}

export interface WikiRevisionList {
  revisions: WikiRevision[]
  total: number
  current_version: number
}

export interface WikiFolder {
  id: string
  knowledge_base_id: string
  parent_id: string
  name: string
  path: string
  depth: number
  sort_order: number
  page_count?: number
  has_children?: boolean
  created_at: string | null
  updated_at: string | null
}

export interface WikiFolderList {
  parent_id: string
  folders: WikiFolder[]
}

export interface WikiGraphNode {
  slug: string
  title: string
  page_type: string
  link_count: number
}

export interface WikiGraphEdge {
  source: string
  target: string
}

export interface WikiGraph {
  nodes: WikiGraphNode[]
  edges: WikiGraphEdge[]
  meta: Record<string, unknown>
}

export interface WikiStats {
  total_pages: number
  pages_by_type: Record<string, number>
  total_links: number
  orphan_count: number
  recent_updates: WikiPage[]
}

export interface AgentConfig {
  agent_mode?: string
  agent_type?: string
  system_prompt?: string
  model_id?: string
  temperature?: number
  max_iterations?: number
  allowed_tools?: string[]
  kb_selection_mode?: string
  knowledge_bases?: string[]
  mcp_selection_mode?: string
  mcp_services?: string[]
  web_search_enabled?: boolean
  multi_turn_enabled?: boolean
  embedding_top_k?: number
  rerank_top_k?: number
  [key: string]: unknown
}

export interface AgentItem {
  id: string
  tenant_id: number
  name: string
  description: string
  avatar: string
  is_builtin: boolean
  created_by: string
  runnable_by_viewer: boolean
  config: AgentConfig
  created_at: string | null
  updated_at: string | null
}

export interface AgentToolInfo {
  name: string
  label: string
  description: string
  group: string
  danger?: boolean
  requirement: { any_of: string[]; all_of: string[] }
}

export interface AgentToolCatalog {
  tools: AgentToolInfo[]
  default_tools: string[]
  switch_managed_tools: string[]
}

export interface AgentTypePreset {
  id: string
  i18n: Record<string, { label: string; description: string }>
  config?: Partial<AgentConfig>
  kb_filter?: { any_of?: string[]; all_of?: string[]; none_of?: string[] }
}

export interface PromptPlaceholder {
  name: string
  label: string
  description: string
}

export interface AgentPlaceholders {
  all: PromptPlaceholder[]
  system_prompt: PromptPlaceholder[]
  agent_system_prompt: PromptPlaceholder[]
  context_template: PromptPlaceholder[]
  rewrite_system_prompt: PromptPlaceholder[]
  rewrite_prompt: PromptPlaceholder[]
  fallback_prompt: PromptPlaceholder[]
}

export interface KnowledgeListQuery {
  folderPath?: string
  folderScope?: 'exact' | 'subtree'
  tagId?: string
}

export interface ChunkItem {
  id: string
  knowledge_id: string
  content: string
  chunk_index: number
  is_enabled: boolean
}

export interface SearchHit {
  id: string
  knowledge_id: string
  knowledge_base_id: string
  content: string
  chunk_index: number
  score: number
  vector_score: number
  keyword_score: number
}

export interface Reference {
  id: string
  knowledge_id: string
  knowledge_title: string
  chunk_index: number
  content: string
  score: number
}

export interface SessionItem {
  id: string
  title: string
  description: string
  knowledge_base_id: string
  created_at: string | null
  updated_at: string | null
}

export interface MessageItem {
  id: string
  session_id: string
  role: 'user' | 'assistant' | string
  content: string
  knowledge_references: Reference[]
  is_completed: boolean
  created_at: string | null
}

export interface StreamEvent {
  id?: string
  response_type: string
  data: Record<string, unknown>
  assistant_message_id?: string
  knowledge_references?: Reference[]
}

interface DataResponse<T> {
  success: boolean
  data: T
}

// ---------------------------------------------------------------- 认证

export const api = {
  async login(account: string, password: string): Promise<LoginResponse> {
    // 后端 login_name 支持用户名或邮箱，字段名沿用 email
    const response = await request<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: account, password }),
    })
    saveAuth({
      token: response.token,
      refreshToken: response.refresh_token,
      tenantId: response.active_tenant?.id ?? 0,
      tenantName: response.active_tenant?.name ?? '',
      userName: response.user.username,
      email: response.user.email,
    })
    return response
  },

  async register(username: string, email: string, password: string): Promise<void> {
    await request('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, email, password }),
    })
  },

  async logout(): Promise<void> {
    try {
      await request('/auth/logout', { method: 'POST' })
    } finally {
      clearAuth()
    }
  },

  // ---------------------------------------------------------------- 模型

  async listModels(): Promise<ModelItem[]> {
    const response = await request<DataResponse<ModelItem[]>>('/models')
    return response.data
  },

  async createModel(payload: Record<string, unknown>): Promise<ModelItem> {
    const response = await request<DataResponse<ModelItem>>('/models', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    return response.data
  },

  async deleteModel(id: string): Promise<void> {
    await request(`/models/${id}`, { method: 'DELETE' })
  },

  async testModel(id: string): Promise<TestResult> {
    const response = await request<DataResponse<TestResult>>(`/models/${id}/test`, {
      method: 'POST',
    })
    return response.data
  },

  // ---------------------------------------------------------------- 知识库

  async listKnowledgeBases(): Promise<KnowledgeBase[]> {
    const response = await request<DataResponse<KnowledgeBase[]>>('/knowledge-bases')
    return response.data
  },

  async createKnowledgeBase(
    name: string,
    description: string,
    type: 'document' | 'faq' | 'wiki' = 'document',
  ): Promise<KnowledgeBase> {
    const response = await request<DataResponse<KnowledgeBase>>('/knowledge-bases', {
      method: 'POST',
      body: JSON.stringify({ name, description, type }),
    })
    return response.data
  },

  async listKnowledge(kbId: string, query: KnowledgeListQuery = {}): Promise<KnowledgeItem[]> {
    const params = new URLSearchParams()
    if (query.folderPath) params.set('folder_path', query.folderPath)
    if (query.folderScope) params.set('folder_scope', query.folderScope)
    if (query.tagId) params.set('tag_id', query.tagId)
    const suffix = params.toString() ? `?${params}` : ''
    const response = await request<DataResponse<KnowledgeItem[]>>(
      `/knowledge-bases/${kbId}/knowledge${suffix}`,
    )
    return response.data
  },

  // ---------------------------------------------------------------- 标签

  async listTags(kbId: string, keyword = ''): Promise<TagPage> {
    const params = new URLSearchParams({ page: '1', page_size: '100' })
    if (keyword) params.set('keyword', keyword)
    const response = await request<DataResponse<TagPage>>(
      `/knowledge-bases/${kbId}/tags?${params}`,
    )
    return response.data
  },

  async createTag(kbId: string, name: string, color = ''): Promise<KnowledgeTag> {
    const response = await request<DataResponse<KnowledgeTag>>(`/knowledge-bases/${kbId}/tags`, {
      method: 'POST',
      body: JSON.stringify({ name, color }),
    })
    return response.data
  },

  async updateTag(kbId: string, tagRef: string | number, payload: Record<string, unknown>): Promise<KnowledgeTag> {
    const response = await request<DataResponse<KnowledgeTag>>(
      `/knowledge-bases/${kbId}/tags/${tagRef}`,
      { method: 'PUT', body: JSON.stringify(payload) },
    )
    return response.data
  },

  async deleteTag(kbId: string, tagRef: string | number, force = false): Promise<void> {
    await request(`/knowledge-bases/${kbId}/tags/${tagRef}?force=${force}`, { method: 'DELETE' })
  },

  async setKnowledgeTags(
    kbId: string,
    updates: Record<string, string[]>,
  ): Promise<void> {
    await request('/knowledge/tags', {
      method: 'PUT',
      body: JSON.stringify({ kb_id: kbId, updates }),
    })
  },

  // ---------------------------------------------------------------- 文件夹

  async listFolders(kbId: string): Promise<FolderTree> {
    const response = await request<DataResponse<FolderTree>>(
      `/knowledge-bases/${kbId}/knowledge/folders`,
    )
    return response.data
  },

  async moveKnowledge(kbId: string, knowledgeIds: string[], folderPath: string): Promise<{ moved_count: number; folder_path: string }> {
    const response = await request<DataResponse<{ moved_count: number; folder_path: string }>>(
      '/knowledge/move',
      {
        method: 'POST',
        body: JSON.stringify({ kb_id: kbId, knowledge_ids: knowledgeIds, folder_path: folderPath }),
      },
    )
    return response.data
  },

  async renameFolder(kbId: string, from: string, to: string): Promise<void> {
    await request(`/knowledge-bases/${kbId}/knowledge/folders`, {
      method: 'PUT',
      body: JSON.stringify({ from, to }),
    })
  },

  // ---------------------------------------------------------------- FAQ

  async listFaqEntries(
    kbId: string,
    filters: { keyword?: string; tagId?: number; isEnabled?: boolean; page?: number; pageSize?: number } = {},
  ): Promise<FaqEntryPage> {
    const params = new URLSearchParams({
      page: String(filters.page ?? 1),
      page_size: String(filters.pageSize ?? 20),
    })
    if (filters.keyword) params.set('keyword', filters.keyword)
    if (filters.tagId) params.set('tag_id', String(filters.tagId))
    if (filters.isEnabled !== undefined) params.set('is_enabled', String(filters.isEnabled))
    const response = await request<DataResponse<FaqEntryPage>>(
      `/knowledge-bases/${kbId}/faq/entries?${params}`,
    )
    return response.data
  },

  async createFaqEntry(kbId: string, payload: Record<string, unknown>): Promise<FaqEntry> {
    const response = await request<DataResponse<FaqEntry>>(`/knowledge-bases/${kbId}/faq/entry`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    return response.data
  },

  async updateFaqEntry(kbId: string, entryId: number, payload: Record<string, unknown>): Promise<FaqEntry> {
    const response = await request<DataResponse<FaqEntry>>(
      `/knowledge-bases/${kbId}/faq/entries/${entryId}`,
      { method: 'PUT', body: JSON.stringify(payload) },
    )
    return response.data
  },

  async updateFaqFields(
    kbId: string,
    payload: Record<string, unknown>,
  ): Promise<{ updated: number }> {
    const response = await request<DataResponse<{ updated: number }>>(
      `/knowledge-bases/${kbId}/faq/entries/fields`,
      { method: 'PUT', body: JSON.stringify(payload) },
    )
    return response.data
  },

  async deleteFaqEntries(kbId: string, ids: number[]): Promise<void> {
    await request(`/knowledge-bases/${kbId}/faq/entries`, {
      method: 'DELETE',
      body: JSON.stringify({ ids }),
    })
  },

  async searchFaq(kbId: string, queryText: string, matchCount = 10): Promise<FaqSearchHit[]> {
    const response = await request<DataResponse<FaqSearchHit[]>>(
      `/knowledge-bases/${kbId}/faq/search`,
      { method: 'POST', body: JSON.stringify({ query_text: queryText, match_count: matchCount }) },
    )
    return response.data
  },

  /** 上传文件并报告传输百分比；完成后返回入库结果，网络或接口失败时拒绝。 */
  async uploadKnowledge(
    kbId: string,
    file: File,
    onProgress?: (percent: number) => void,
  ): Promise<KnowledgeItem> {
    const form = new FormData()
    form.append('file', file)
    return new Promise<KnowledgeItem>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', `${BASE}/knowledge-bases/${kbId}/knowledge/file`)
      const headers = buildHeaders()
      Object.entries(headers).forEach(([key, value]) => xhr.setRequestHeader(key, value))
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100))
      }
      xhr.onload = async () => {
        if (xhr.status === 401 && auth.refreshToken) {
          try {
            if (await refreshTokens()) {
              const response = await request<DataResponse<KnowledgeItem>>(
                `/knowledge-bases/${kbId}/knowledge/file`, { method: 'POST', body: form }, false,
              )
              resolve(response.data)
              return
            }
          } catch (err) { reject(err); return }
        }
        let payload
        try { payload = JSON.parse(xhr.responseText) }
        catch { reject(new ApiError(`上传失败（${xhr.status}），请检查服务后重试`, xhr.status, xhr.status)); return }
        if (xhr.status >= 200 && xhr.status < 300 && payload.success !== false) {
          resolve(payload.data)
        } else {
          reject(new ApiError(payload.error?.message || `上传失败（${xhr.status}）`, xhr.status, xhr.status))
        }
      }
      xhr.onerror = () => reject(new ApiError('上传失败，请检查后端是否启动', 0, 0))
      xhr.onabort = () => reject(new ApiError('上传已取消', 0, 0))
      xhr.send(form)
    })
  },

  async createManualKnowledge(
    kbId: string,
    title: string,
    content: string,
  ): Promise<KnowledgeItem> {
    const response = await request<DataResponse<KnowledgeItem>>(
      `/knowledge-bases/${kbId}/knowledge/manual`,
      { method: 'POST', body: JSON.stringify({ title, content }) },
    )
    return response.data
  },

  async deleteKnowledge(id: string): Promise<void> {
    await request(`/knowledge/${id}`, { method: 'DELETE' })
  },

  async listChunks(knowledgeId: string): Promise<ChunkItem[]> {
    const response = await request<DataResponse<ChunkItem[]>>(`/chunks/${knowledgeId}`)
    return response.data
  },

  async hybridSearch(kbId: string, query: string, topK = 5): Promise<SearchHit[]> {
    const response = await request<DataResponse<SearchHit[]>>(
      `/knowledge-bases/${kbId}/hybrid-search`,
      { method: 'POST', body: JSON.stringify({ query, top_k: topK }) },
    )
    return response.data
  },

  // ---------------------------------------------------------------- Wiki

  async listWikiPages(
    kbId: string,
    filters: { pageType?: string; status?: string; query?: string; folderId?: string; page?: number; pageSize?: number } = {},
  ): Promise<WikiPageList> {
    const params = new URLSearchParams({
      page: String(filters.page ?? 1),
      page_size: String(filters.pageSize ?? 200),
    })
    if (filters.pageType) params.set('page_type', filters.pageType)
    if (filters.status) params.set('status', filters.status)
    if (filters.query) params.set('query', filters.query)
    if (filters.folderId !== undefined) params.set('folder_id', filters.folderId)
    const response = await request<DataResponse<WikiPageList>>(
      `/knowledge-bases/${kbId}/wiki/pages?${params}`,
    )
    return response.data
  },

  async getWikiPage(kbId: string, slug: string): Promise<WikiPage> {
    const response = await request<DataResponse<WikiPage>>(
      `/knowledge-bases/${kbId}/wiki/pages/${encodeURIComponent(slug)}`,
    )
    return response.data
  },

  async createWikiPage(kbId: string, payload: Record<string, unknown>): Promise<WikiPage> {
    const response = await request<DataResponse<WikiPage>>(`/knowledge-bases/${kbId}/wiki/pages`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    return response.data
  },

  async updateWikiPage(kbId: string, slug: string, payload: Record<string, unknown>): Promise<WikiPage> {
    const response = await request<DataResponse<WikiPage>>(
      `/knowledge-bases/${kbId}/wiki/pages/${encodeURIComponent(slug)}`,
      { method: 'PUT', body: JSON.stringify(payload) },
    )
    return response.data
  },

  async deleteWikiPage(kbId: string, slug: string): Promise<void> {
    await request(`/knowledge-bases/${kbId}/wiki/pages/${encodeURIComponent(slug)}`, {
      method: 'DELETE',
    })
  },

  async moveWikiPage(kbId: string, slug: string, folderId: string): Promise<WikiPage> {
    const response = await request<DataResponse<WikiPage>>(
      `/knowledge-bases/${kbId}/wiki/move-page`,
      { method: 'PUT', body: JSON.stringify({ slug, folder_id: folderId }) },
    )
    return response.data
  },

  async listWikiRevisions(kbId: string, slug: string, contentVersion = 0): Promise<WikiRevisionList> {
    const params = new URLSearchParams()
    if (contentVersion > 0) params.set('content_version', String(contentVersion))
    const suffix = params.toString() ? `?${params}` : ''
    const response = await request<DataResponse<WikiRevisionList>>(
      `/knowledge-bases/${kbId}/wiki/revisions/${encodeURIComponent(slug)}${suffix}`,
    )
    return response.data
  },

  async revertWikiPage(kbId: string, slug: string, version: number): Promise<WikiPage> {
    const response = await request<DataResponse<WikiPage>>(
      `/knowledge-bases/${kbId}/wiki/revert`,
      { method: 'POST', body: JSON.stringify({ slug, version }) },
    )
    return response.data
  },

  async listWikiFolders(kbId: string, parentId = ''): Promise<WikiFolderList> {
    const params = new URLSearchParams()
    if (parentId) params.set('parent_id', parentId)
    const suffix = params.toString() ? `?${params}` : ''
    const response = await request<DataResponse<WikiFolderList>>(
      `/knowledge-bases/${kbId}/wiki/folders${suffix}`,
    )
    return response.data
  },

  async createWikiFolder(kbId: string, parentId: string, name: string): Promise<WikiFolder> {
    const response = await request<DataResponse<WikiFolder>>(
      `/knowledge-bases/${kbId}/wiki/folders`,
      { method: 'POST', body: JSON.stringify({ parent_id: parentId, name }) },
    )
    return response.data
  },

  async deleteWikiFolder(kbId: string, folderId: string): Promise<void> {
    await request(`/knowledge-bases/${kbId}/wiki/folders/${folderId}`, { method: 'DELETE' })
  },

  async getWikiGraph(
    kbId: string,
    mode: 'overview' | 'ego' = 'overview',
    center = '',
    depth = 1,
  ): Promise<WikiGraph> {
    const params = new URLSearchParams({ mode, depth: String(depth) })
    if (center) params.set('center', center)
    const response = await request<DataResponse<WikiGraph>>(
      `/knowledge-bases/${kbId}/wiki/graph?${params}`,
    )
    return response.data
  },

  async getWikiStats(kbId: string): Promise<WikiStats> {
    const response = await request<DataResponse<WikiStats>>(
      `/knowledge-bases/${kbId}/wiki/stats`,
    )
    return response.data
  },

  // ---------------------------------------------------------------- Agent

  async listAgents(creator = ''): Promise<AgentItem[]> {
    const params = new URLSearchParams()
    if (creator) params.set('creator', creator)
    const suffix = params.toString() ? `?${params}` : ''
    const response = await request<DataResponse<AgentItem[]>>(`/agents${suffix}`)
    return response.data
  },

  async createAgent(payload: Record<string, unknown>): Promise<AgentItem> {
    const response = await request<DataResponse<AgentItem>>('/agents', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    return response.data
  },

  async getAgent(id: string): Promise<AgentItem> {
    const response = await request<DataResponse<AgentItem>>(`/agents/${id}`)
    return response.data
  },

  async updateAgent(id: string, payload: Record<string, unknown>): Promise<AgentItem> {
    const response = await request<DataResponse<AgentItem>>(`/agents/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
    return response.data
  },

  async patchAgent(id: string, payload: Record<string, unknown>): Promise<AgentItem> {
    const response = await request<DataResponse<AgentItem>>(`/agents/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    })
    return response.data
  },

  async deleteAgent(id: string): Promise<void> {
    await request(`/agents/${id}`, { method: 'DELETE' })
  },

  async copyAgent(id: string): Promise<AgentItem> {
    const response = await request<DataResponse<AgentItem>>(`/agents/${id}/copy`, {
      method: 'POST',
    })
    return response.data
  },

  async getAgentTools(): Promise<AgentToolCatalog> {
    const response = await request<DataResponse<AgentToolCatalog>>('/agents/tools')
    return response.data
  },

  async getAgentTypePresets(): Promise<AgentTypePreset[]> {
    const response = await request<DataResponse<AgentTypePreset[]>>('/agents/type-presets')
    return response.data
  },

  async getAgentPlaceholders(): Promise<AgentPlaceholders> {
    const response = await request<DataResponse<AgentPlaceholders>>('/agents/placeholders')
    return response.data
  },

  // ---------------------------------------------------------------- 会话

  async listSessions(): Promise<SessionItem[]> {
    const response = await request<DataResponse<SessionItem[]>>('/sessions')
    return response.data
  },

  async createSession(title: string, knowledgeBaseId: string): Promise<SessionItem> {
    const response = await request<DataResponse<SessionItem>>('/sessions', {
      method: 'POST',
      body: JSON.stringify({ title, knowledge_base_id: knowledgeBaseId }),
    })
    return response.data
  },

  async deleteSession(id: string): Promise<void> {
    await request(`/sessions/${id}`, { method: 'DELETE' })
  },

  async loadMessages(sessionId: string): Promise<MessageItem[]> {
    const response = await request<DataResponse<MessageItem[]>>(
      `/messages/${sessionId}/load`,
    )
    return response.data
  },
}

// ---------------------------------------------------------------- SSE 流式问答

/** 消费回答事件；收到服务端错误或流提前结束时抛错，供页面保留部分回答并提示。 */
export async function streamChat(
  sessionId: string,
  query: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
  agentId = '',
): Promise<void> {
  // 用 XHR 读取 text/event-stream：fetch + ReadableStream 在流结束后会被
  // Chromium 记为 net::ERR_ABORTED（内容其实已完整收到），XHR 无此问题。
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const url = `${BASE}/${agentId ? 'agent-chat' : 'knowledge-chat'}/${sessionId}`
    let offset = 0
    let completed = false
    let failed = false

    const consume = () => {
      const text = xhr.responseText.slice(offset)
      offset += text.length
      for (const segment of text.split('\n\n')) {
        for (const line of segment.split('\n')) {
          if (!line.startsWith('data: ')) continue
          let event: StreamEvent
          try {
            event = JSON.parse(line.slice(6)) as StreamEvent
          } catch {
            continue
          }
          if (event.response_type === 'error') {
            failed = true
            xhr.abort()
            reject(new ApiError(String(event.data?.message || '回答生成失败，请重试'), 0, 0))
            return
          }
          onEvent(event)
          if (event.response_type === 'complete') completed = true
        }
      }
    }

    xhr.open('POST', url)
    for (const [key, value] of Object.entries(
      buildHeaders({ 'Content-Type': 'application/json' }),
    )) {
      xhr.setRequestHeader(key, value)
    }
    xhr.onprogress = () => {
      if (!failed) consume()
    }
    xhr.onload = () => {
      if (failed) return
      consume()
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new ApiError(xhr.responseText.slice(0, 200) || `请求失败 ${xhr.status}`, xhr.status, xhr.status))
        return
      }
      if (!completed) {
        reject(new ApiError('回答连接提前中断，请重试', 0, 0))
        return
      }
      resolve()
    }
    xhr.onerror = () => {
      if (failed) return
      failed = true
      reject(new ApiError('网络异常，请检查后端是否启动', 0, 0))
    }
    xhr.onabort = () => {
      if (failed) return
      failed = true
      reject(new ApiError('回答已取消', 0, 0))
    }
    if (signal) {
      if (signal.aborted) {
        reject(new ApiError('回答已取消', 0, 0))
        return
      }
      signal.addEventListener('abort', () => xhr.abort(), { once: true })
    }
    xhr.send(JSON.stringify(agentId ? { query, agent_id: agentId } : { query }))
  })
}
