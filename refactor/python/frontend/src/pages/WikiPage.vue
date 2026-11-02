<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api, ApiError } from '../api'
import type {
  KnowledgeBase,
  WikiFolder,
  WikiGraph,
  WikiPage,
  WikiRevision,
  WikiStats,
} from '../api'

const kbs = ref<KnowledgeBase[]>([])
const kbId = ref('')
const pages = ref<WikiPage[]>([])
const folders = ref<WikiFolder[]>([])
const total = ref(0)

const query = ref('')
const typeFilter = ref('')
const statusFilter = ref('')

const selectedSlug = ref('')
const current = ref<WikiPage | null>(null)
const tab = ref<'page' | 'revisions' | 'graph' | 'stats'>('page')

const busy = ref(false)
const error = ref('')
const notice = ref('')

const editing = ref(false)
const form = reactive({
  slug: '',
  title: '',
  page_type: 'summary',
  status: 'published',
  folder_id: '',
  summary: '',
  content: '',
})

const revisions = ref<WikiRevision[]>([])
const currentVersion = ref(0)
const preview = ref<WikiRevision | null>(null)

const graph = ref<WikiGraph | null>(null)
const stats = ref<WikiStats | null>(null)

const PAGE_TYPES = ['summary', 'entity', 'concept', 'index', 'synthesis', 'comparison']
const STATUSES = ['published', 'draft', 'archived']

const isWikiKb = (kb: KnowledgeBase) =>
  kb.type === 'wiki' || Boolean(kb.indexing_strategy?.wiki_enabled)

const wikiKbs = computed(() => kbs.value.filter(isWikiKb))
const selectedKb = computed(() => kbs.value.find((kb) => kb.id === kbId.value))

function fail(err: unknown) {
  error.value = err instanceof ApiError ? err.message : '请求失败，请检查后端是否启动'
}

function formatTime(value: string | null): string {
  if (!value) return '—'
  return value.replace('T', ' ').replace('Z', '').slice(0, 16)
}

async function loadKbs() {
  try {
    kbs.value = await api.listKnowledgeBases()
    if (!wikiKbs.value.some((kb) => kb.id === kbId.value)) {
      kbId.value = wikiKbs.value[0]?.id || ''
    }
  } catch (err) {
    fail(err)
  }
}

async function loadTree() {
  if (!kbId.value) {
    pages.value = []
    folders.value = []
    total.value = 0
    current.value = null
    selectedSlug.value = ''
    return
  }
  try {
    const [pageList, folderList] = await Promise.all([
      api.listWikiPages(kbId.value, {
        query: query.value.trim() || undefined,
        pageType: typeFilter.value || undefined,
        status: statusFilter.value || undefined,
      }),
      api.listWikiFolders(kbId.value),
    ])
    pages.value = pageList.pages
    total.value = pageList.total
    folders.value = folderList.folders
  } catch (err) {
    fail(err)
  }
}

const pagesByFolder = computed(() => {
  const map = new Map<string, WikiPage[]>()
  for (const page of pages.value) {
    const key = page.folder_id || ''
    const bucket = map.get(key) || []
    bucket.push(page)
    map.set(key, bucket)
  }
  return map
})

const rootPages = computed(() => pagesByFolder.value.get('') || [])

function folderPages(folderId: string): WikiPage[] {
  return pagesByFolder.value.get(folderId) || []
}

function resetForm() {
  editing.value = false
  form.slug = ''
  form.title = ''
  form.page_type = 'summary'
  form.status = 'published'
  form.folder_id = ''
  form.summary = ''
  form.content = ''
}

async function loadPage(slug: string) {
  if (!kbId.value || !slug) return
  selectedSlug.value = slug
  error.value = ''
  notice.value = ''
  tab.value = 'page'
  try {
    current.value = await api.getWikiPage(kbId.value, slug)
    form.slug = current.value.slug
    form.title = current.value.title
    form.page_type = current.value.page_type
    form.status = current.value.status
    form.folder_id = current.value.folder_id
    form.summary = current.value.summary
    form.content = current.value.content
    editing.value = true
  } catch (err) {
    fail(err)
  }
}

function newPage() {
  current.value = null
  selectedSlug.value = ''
  editing.value = false
  tab.value = 'page'
  resetForm()
  error.value = ''
  notice.value = ''
}

async function savePage() {
  if (!kbId.value || busy.value) return
  if (!form.slug.trim()) {
    error.value = '页面 slug 不能为空'
    return
  }
  busy.value = true
  error.value = ''
  notice.value = ''
  const payload: Record<string, unknown> = {
    slug: form.slug.trim(),
    title: form.title.trim() || form.slug.trim(),
    page_type: form.page_type,
    status: form.status,
    summary: form.summary,
    content: form.content,
  }
  if (form.folder_id) payload.folder_id = form.folder_id
  try {
    if (editing.value && current.value) {
      payload.version = current.value.version
      const page = await api.updateWikiPage(kbId.value, current.value.slug, payload)
      notice.value = `页面「${page.title}」已更新（v${page.version}）`
      selectedSlug.value = page.slug
    } else {
      const page = await api.createWikiPage(kbId.value, payload)
      notice.value = `页面「${page.title}」已创建`
      selectedSlug.value = page.slug
    }
    await loadTree()
    await loadPage(selectedSlug.value)
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

async function removePage() {
  if (!kbId.value || !current.value) return
  if (!window.confirm(`删除页面「${current.value.title}」？`)) return
  try {
    await api.deleteWikiPage(kbId.value, current.value.slug)
    notice.value = `已删除「${current.value.title}」`
    resetForm()
    current.value = null
    selectedSlug.value = ''
    await loadTree()
  } catch (err) {
    fail(err)
  }
}

async function loadRevisions() {
  if (!kbId.value || !current.value) return
  tab.value = 'revisions'
  error.value = ''
  preview.value = null
  try {
    const data = await api.listWikiRevisions(kbId.value, current.value.slug)
    revisions.value = data.revisions
    currentVersion.value = data.current_version
  } catch (err) {
    fail(err)
  }
}

async function previewRevision(version: number) {
  if (!kbId.value || !current.value) return
  try {
    const data = await api.listWikiRevisions(kbId.value, current.value.slug, version)
    preview.value = data.revisions[0] || null
  } catch (err) {
    fail(err)
  }
}

async function revertTo(version: number) {
  if (!kbId.value || !current.value) return
  if (!window.confirm(`回滚「${current.value.title}」到版本 ${version}？`)) return
  try {
    const page = await api.revertWikiPage(kbId.value, current.value.slug, version)
    notice.value = `已回滚到 v${version}，当前为 v${page.version}`
    await loadPage(current.value.slug)
  } catch (err) {
    fail(err)
  }
}

async function loadGraph() {
  if (!kbId.value) return
  tab.value = 'graph'
  error.value = ''
  try {
    graph.value = await api.getWikiGraph(kbId.value)
  } catch (err) {
    fail(err)
  }
}

async function loadStats() {
  if (!kbId.value) return
  tab.value = 'stats'
  error.value = ''
  try {
    stats.value = await api.getWikiStats(kbId.value)
  } catch (err) {
    fail(err)
  }
}

async function createFolder() {
  if (!kbId.value) return
  const name = window.prompt('新文件夹名称')
  if (!name || !name.trim()) return
  try {
    await api.createWikiFolder(kbId.value, '', name.trim())
    notice.value = `文件夹「${name.trim()}」已创建`
    await loadTree()
  } catch (err) {
    fail(err)
  }
}

async function search() {
  await loadTree()
}

watch(kbId, async () => {
  error.value = ''
  notice.value = ''
  resetForm()
  current.value = null
  selectedSlug.value = ''
  graph.value = null
  stats.value = null
  await loadTree()
})

onMounted(async () => {
  await loadKbs()
  await loadTree()
})
</script>

<template>
  <div class="wiki-page">
    <section class="card panel">
      <header class="panel-head">
        <div>
          <span class="eyebrow">Wiki</span>
          <h2>{{ selectedKb ? selectedKb.name : 'Wiki 页面' }}</h2>
        </div>
        <span class="counter">{{ total }}</span>
      </header>

      <div v-if="!wikiKbs.length" class="empty-state">
        <p class="empty-title">还没有 Wiki 知识库</p>
        <p class="muted">在知识库页新建一个类型为 Wiki 的知识库，即可维护页面树。</p>
        <RouterLink to="/knowledge"><button class="ghost small">去创建</button></RouterLink>
      </div>

      <template v-else>
        <div class="toolbar">
          <select v-model="kbId" aria-label="Wiki 知识库">
            <option v-for="kb in wikiKbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
          </select>
          <input v-model="query" placeholder="搜索标题 / 正文" @keyup.enter="search" />
          <select v-model="typeFilter" aria-label="页面类型" @change="search">
            <option value="">全部类型</option>
            <option v-for="t in PAGE_TYPES" :key="t" :value="t">{{ t }}</option>
          </select>
          <select v-model="statusFilter" aria-label="状态" @change="search">
            <option value="">全部状态</option>
            <option v-for="s in STATUSES" :key="s" :value="s">{{ s }}</option>
          </select>
          <button class="ghost small" @click="search">查询</button>
          <button class="small" @click="newPage">新建页面</button>
          <button class="ghost small" @click="createFolder">新建文件夹</button>
        </div>

        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <p v-if="notice" class="success" role="status">{{ notice }}</p>

        <div class="body-grid">
          <aside class="tree">
            <h3 class="tree-title">页面树</h3>
            <div v-if="!pages.length && !folders.length" class="empty-state">
              <p class="muted">还没有页面，点击「新建页面」开始。</p>
            </div>

            <template v-else>
              <div v-if="rootPages.length" class="tree-group">
                <div class="tree-group-head">根目录</div>
                <button
                  v-for="page in rootPages"
                  :key="page.id"
                  class="tree-item"
                  :class="{ active: selectedSlug === page.slug }"
                  @click="loadPage(page.slug)"
                >
                  <span class="tree-title-text">{{ page.title || page.slug }}</span>
                  <span class="muted mono">{{ page.slug }}</span>
                </button>
              </div>

              <div v-for="folder in folders" :key="folder.id" class="tree-group">
                <div class="tree-group-head">
                  <span class="folder-name">{{ folder.name }}</span>
                  <span class="muted">{{ folder.page_count ?? folderPages(folder.id).length }}</span>
                </div>
                <button
                  v-for="page in folderPages(folder.id)"
                  :key="page.id"
                  class="tree-item"
                  :class="{ active: selectedSlug === page.slug }"
                  @click="loadPage(page.slug)"
                >
                  <span class="tree-title-text">{{ page.title || page.slug }}</span>
                  <span class="muted mono">{{ page.slug }}</span>
                </button>
              </div>
            </template>
          </aside>

          <div class="detail">
            <div class="tabs">
              <button :class="{ on: tab === 'page' }" @click="tab = 'page'">编辑</button>
              <button :class="{ on: tab === 'revisions' }" :disabled="!current" @click="loadRevisions">
                版本
              </button>
              <button :class="{ on: tab === 'graph' }" @click="loadGraph">图谱</button>
              <button :class="{ on: tab === 'stats' }" @click="loadStats">统计</button>
            </div>

            <form v-if="tab === 'page'" class="editor" @submit.prevent="savePage">
              <div class="row two">
                <div class="field">
                  <label for="wiki-title">标题</label>
                  <input id="wiki-title" v-model="form.title" placeholder="页面标题" />
                </div>
                <div class="field">
                  <label for="wiki-slug">Slug <span class="req">*</span></label>
                  <input
                    id="wiki-slug"
                    v-model="form.slug"
                    placeholder="唯一标识，如 nebula"
                    :disabled="editing"
                  />
                </div>
              </div>
              <div class="row three">
                <div class="field">
                  <label for="wiki-type">类型</label>
                  <select id="wiki-type" v-model="form.page_type">
                    <option v-for="t in PAGE_TYPES" :key="t" :value="t">{{ t }}</option>
                  </select>
                </div>
                <div class="field">
                  <label for="wiki-status">状态</label>
                  <select id="wiki-status" v-model="form.status">
                    <option v-for="s in STATUSES" :key="s" :value="s">{{ s }}</option>
                  </select>
                </div>
                <div class="field">
                  <label for="wiki-folder">文件夹</label>
                  <select id="wiki-folder" v-model="form.folder_id">
                    <option value="">根目录</option>
                    <option v-for="folder in folders" :key="folder.id" :value="folder.id">
                      {{ folder.path || folder.name }}
                    </option>
                  </select>
                </div>
              </div>
              <div class="field">
                <label for="wiki-summary">摘要</label>
                <input id="wiki-summary" v-model="form.summary" placeholder="一句话摘要（可选）" />
              </div>
              <div class="field">
                <label for="wiki-content">正文</label>
                <textarea id="wiki-content" v-model="form.content" rows="14" placeholder="正文内容；用 [[slug]] 或 [[slug|显示名]] 建立页面内链" />
              </div>

              <div v-if="current" class="meta-line muted">
                <span>slug：{{ current.slug }}</span>
                <span>v{{ current.version }}</span>
                <span>{{ formatTime(current.updated_at) }}</span>
                <span v-if="current.out_links.length">出链：{{ current.out_links.join('、') }}</span>
                <span v-if="current.in_links.length">被引用：{{ current.in_links.join('、') }}</span>
              </div>

              <div class="row">
                <button type="submit" :disabled="busy || !kbId">
                  {{ busy ? '保存中…' : editing ? '保存修改' : '创建页面' }}
                </button>
                <button v-if="editing" type="button" class="ghost" @click="newPage">取消</button>
                <button v-if="current" type="button" class="danger" @click="removePage">删除</button>
              </div>
            </form>

            <div v-else-if="tab === 'revisions'" class="revisions">
              <template v-if="current">
                <p class="muted">当前版本 v{{ currentVersion }} · 共 {{ revisions.length }} 个历史快照</p>
                <div v-if="revisions.length" class="rev-list">
                  <div v-for="rev in revisions" :key="rev.id" class="rev-item">
                    <div class="rev-head">
                      <strong>v{{ rev.version }}</strong>
                      <span class="muted">{{ formatTime(rev.edited_at) }}</span>
                      <span class="chip">{{ rev.edit_source || 'pipeline' }}</span>
                      <button class="ghost small" @click="previewRevision(rev.version)">预览</button>
                      <button
                        class="ghost small"
                        :disabled="rev.version === currentVersion"
                        @click="revertTo(rev.version)"
                      >
                        回滚
                      </button>
                    </div>
                    <p v-if="preview && preview.version === rev.version" class="rev-preview">
                      {{ preview.content || '（空正文）' }}
                    </p>
                  </div>
                </div>
                <div v-else class="empty-state">
                  <p class="muted">暂无历史版本快照。</p>
                </div>
              </template>
              <div v-else class="empty-state">
                <p class="muted">先在左侧选择或新建一个页面。</p>
              </div>
            </div>

            <div v-else-if="tab === 'graph'" class="graph">
              <template v-if="graph && graph.nodes.length">
                <div class="graph-meta muted">
                  共 {{ graph.meta.total }} 个页面，返回 {{ graph.nodes.length }} 个节点、
                  {{ graph.edges.length }} 条边
                </div>
                <div class="graph-nodes">
                  <span
                    v-for="node in graph.nodes"
                    :key="node.slug"
                    class="g-node"
                    :class="`g-${node.page_type}`"
                    :title="`${node.title} · 链接 ${node.link_count}`"
                  >
                    {{ node.title }}
                  </span>
                </div>
                <div class="graph-edges">
                  <div v-for="(edge, index) in graph.edges" :key="index" class="g-edge">
                    <span class="mono">{{ edge.source }}</span>
                    <span class="arrow">→</span>
                    <span class="mono">{{ edge.target }}</span>
                  </div>
                </div>
              </template>
              <div v-else class="empty-state">
                <p class="muted">暂无图谱数据。</p>
              </div>
            </div>

            <div v-else-if="tab === 'stats'" class="stats">
              <template v-if="stats">
                <div class="stat-grid">
                  <div class="stat">
                    <strong>{{ stats.total_pages }}</strong>
                    <span>页面总数</span>
                  </div>
                  <div class="stat">
                    <strong>{{ stats.total_links }}</strong>
                    <span>内链总数</span>
                  </div>
                  <div class="stat">
                    <strong>{{ stats.orphan_count }}</strong>
                    <span>孤立页面</span>
                  </div>
                </div>
                <div v-if="Object.keys(stats.pages_by_type).length" class="type-counts">
                  <div v-for="(count, type) in stats.pages_by_type" :key="type" class="chip">
                    {{ type }}：{{ count }}
                  </div>
                </div>
                <div v-if="stats.recent_updates.length" class="recent">
                  <h4>最近更新</h4>
                  <div v-for="page in stats.recent_updates" :key="page.id" class="recent-item">
                    <button class="ghost small" @click="loadPage(page.slug)">{{ page.title }}</button>
                    <span class="muted">{{ formatTime(page.updated_at) }}</span>
                  </div>
                </div>
              </template>
              <div v-else class="empty-state">
                <p class="muted">暂无统计信息。</p>
              </div>
            </div>
          </div>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.wiki-page {
  display: block;
}

.panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.panel-head h2 {
  margin-top: 2px;
}

.toolbar {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr) 130px 120px auto auto auto;
  gap: 10px;
  align-items: center;
}

.toolbar input,
.toolbar select {
  height: 36px;
}

.toolbar input {
  min-width: 0;
}

.body-grid {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 20px;
  align-items: start;
  min-width: 0;
}

.tree {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 70vh;
  overflow-y: auto;
  padding-right: 4px;
}

.tree-title {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}

.tree-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tree-group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 8px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-soft);
  background: var(--surface-muted);
  border-radius: 6px;
}

.tree-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  font-size: 13px;
  text-align: left;
  color: var(--text-soft);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.tree-item:hover {
  background: var(--surface-muted);
}

.tree-item.active {
  color: var(--primary);
  background: var(--primary-soft);
  border-color: var(--primary-line);
}

.tree-title-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border);
}

.tabs button {
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-soft);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
}

.tabs button.on {
  color: var(--primary);
  font-weight: 600;
  border-bottom-color: var(--primary);
}

.tabs button:disabled {
  color: var(--muted);
  cursor: not-allowed;
}

.editor {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.row.two {
  display: grid;
  grid-template-columns: 1fr 1fr;
}

.row.three {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
}

.req {
  color: var(--danger);
}

.meta-line {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-size: 12px;
}

.rev-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.rev-item {
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.rev-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.rev-preview {
  margin-top: 10px;
  padding: 10px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-soft);
  background: var(--surface-muted);
  border-radius: 6px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.graph-meta {
  margin-bottom: 12px;
  font-size: 12px;
}

.graph-nodes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.g-node {
  padding: 6px 12px;
  font-size: 13px;
  color: var(--text-soft);
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: 999px;
  cursor: default;
}

.g-edge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
  color: var(--text-soft);
  border-bottom: 1px dashed var(--border);
}

.arrow {
  color: var(--muted);
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 16px;
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.stat strong {
  font-size: 24px;
  font-weight: 700;
}

.stat span {
  font-size: 12px;
  color: var(--muted);
}

.type-counts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.recent {
  margin-top: 16px;
}

.recent h4 {
  margin: 0 0 8px;
}

.recent-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
}

.mono {
  font-family: var(--font-mono);
  font-size: 12px;
}

@media (max-width: 1080px) {
  .body-grid {
    grid-template-columns: 1fr;
  }

  .tree {
    max-height: 40vh;
  }

  .toolbar {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
