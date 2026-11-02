export interface Tenant { id: number; name: string }
export interface LoginResponse { success: boolean; message?: string; token?: string; refresh_token?: string; active_tenant?: Tenant }
export interface KnowledgeBase { id: string; name: string; description: string; chunking_config?: Record<string, unknown>; capabilities?: Record<string, boolean> }
export interface KnowledgeItem {
  id: string
  title: string
  parse_status: string
  error_message?: string
  file_size?: number
  file_name?: string
  file_type?: string
  source?: string
  description?: string
  created_at?: string
  updated_at?: string
  processed_at?: string
}
export interface SearchHit { id: string; content: string; score: number; knowledge_id: string; chunk_index: number; knowledge_title?: string }
export interface Session {
  id: string
  title: string
  description?: string
  is_pinned?: boolean
  pinned_at?: string
  created_at?: string
  updated_at?: string
}
export interface ChatMessage { id: string; role: string; content: string; created_at?: string }
export interface SessionPage { data: Session[]; total?: number }
export interface WikiGroupItem { slug: string; title: string; summary: string; wiki_path?: string; category_path?: string[]; depth?: number }
export interface WikiGroup { type: string; total: number; items: WikiGroupItem[]; next_cursor?: string }
export interface WikiIndex { intro: string; version: number; groups: WikiGroup[] }
export interface GraphNode { slug: string; title: string; page_type: string; link_count: number }
export interface GraphEdge { source: string; target: string; relation?: string }
export interface WikiGraph { nodes: GraphNode[]; edges: GraphEdge[]; meta?: Record<string, unknown> }
export interface WikiPage {
  id: string
  slug: string
  title: string
  page_type: string
  status: string
  content: string
  summary: string
  aliases?: string[]
  parent_slug?: string
  category_path?: string[]
  wiki_path?: string
  in_links?: string[]
  in_link_titles?: Record<string, string>
  out_links?: string[]
  source_refs?: string[]
  version: number
  updated_at?: string
  created_at?: string
}
export interface WikiSearchResponse { pages: WikiPage[]; total?: number }
export interface WikiStats {
  total_pages: number
  pages_by_type: Record<string, number>
  total_links: number
  orphan_count: number
  recent_updates?: WikiPage[]
  pending_tasks?: number
  pending_issues?: number
  is_active?: boolean
}
