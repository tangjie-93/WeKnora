<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, ApiError } from '../api'
import type {
  ChunkItem,
  FolderNode,
  FolderTree,
  KnowledgeBase,
  KnowledgeItem,
  KnowledgeTag,
} from '../api'

const kbs = ref<KnowledgeBase[]>([])
const selectedId = ref('')
const documents = ref<KnowledgeItem[]>([])
const chunks = ref<Record<string, ChunkItem[]>>({})
const expanded = ref<Record<string, boolean>>({})

const tags = ref<KnowledgeTag[]>([])
const folderTree = ref<FolderTree | null>(null)
const activeFolder = ref('')
const activeTag = ref('')
const editingTagId = ref('')
const tagEditorFor = ref('')
const selectedTagIds = ref<string[]>([])
const moveFor = ref('')
const movePath = ref('')
const newTagName = ref('')
const folderRenameTo = ref('')

const newKbName = ref('')
const newKbDescription = ref('')
const newKbType = ref<'document' | 'faq' | 'wiki'>('document')
const manualTitle = ref('')
const manualContent = ref('')

const busy = ref(false)
const uploadProgress = ref(0)
const uploading = ref(false)
const error = ref('')
const notice = ref('')

const selectedKb = computed(() => kbs.value.find((kb) => kb.id === selectedId.value))
const isFaqKb = computed(() => selectedKb.value?.type === 'faq')
const tagNameById = computed(() =>
  Object.fromEntries(tags.value.map((tag) => [tag.id, tag.name])),
)

/** 把文件夹树压平，带上层级用于缩进展示。 */
const flatFolders = computed(() => {
  const rows: { node: FolderNode; depth: number }[] = []
  const walk = (items: FolderNode[], depth: number) => {
    items.forEach((node) => {
      rows.push({ node, depth })
      if (node.children?.length) walk(node.children, depth + 1)
    })
  }
  if (folderTree.value) walk(folderTree.value.folders, 0)
  return rows
})

function fail(err: unknown) {
  error.value = err instanceof ApiError ? err.message : '请求失败，请检查后端是否启动'
}

function clearMessages() {
  error.value = ''
  notice.value = ''
}

async function loadKbs() {
  try {
    kbs.value = await api.listKnowledgeBases()
    if (!selectedId.value && kbs.value.length) {
      selectedId.value = kbs.value[0].id
    }
  } catch (err) {
    fail(err)
  }
}

async function loadDocuments() {
  if (!selectedId.value) return
  try {
    documents.value = await api.listKnowledge(selectedId.value, {
      folderPath: activeFolder.value,
      folderScope: activeFolder.value ? 'exact' : undefined,
      tagId: activeTag.value || undefined,
    })
    chunks.value = {}
    expanded.value = {}
    tagEditorFor.value = ''
    moveFor.value = ''
  } catch (err) {
    fail(err)
  }
}

async function loadOrganization() {
  if (!selectedId.value) {
    tags.value = []
    folderTree.value = null
    return
  }
  try {
    const [tagPage, tree] = await Promise.all([
      api.listTags(selectedId.value),
      api.listFolders(selectedId.value),
    ])
    tags.value = tagPage.data
    folderTree.value = tree
  } catch (err) {
    fail(err)
  }
}

async function refreshAll() {
  await loadOrganization()
  await loadDocuments()
}

async function selectKb(id: string) {
  selectedId.value = id
  activeFolder.value = ''
  activeTag.value = ''
  clearMessages()
  await refreshAll()
}

async function createKb() {
  if (!newKbName.value.trim()) return
  busy.value = true
  clearMessages()
  try {
    const kb = await api.createKnowledgeBase(
      newKbName.value.trim(),
      newKbDescription.value.trim(),
      newKbType.value,
    )
    newKbName.value = ''
    newKbDescription.value = ''
    newKbType.value = 'document'
    await loadKbs()
    await selectKb(kb.id)
    notice.value = `知识库「${kb.name}」已创建`
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

/** 上传所选文件，显示进度和入库结果；失败提示原因，结束后恢复选择器。 */
async function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || busy.value) return
  if (!selectedId.value) {
    error.value = '请先创建或选择知识库，再上传文档'
    input.value = ''
    return
  }
  busy.value = true
  uploading.value = true
  uploadProgress.value = 0
  clearMessages()
  try {
    const item = await api.uploadKnowledge(selectedId.value, file, (percent) => {
      uploadProgress.value = percent
    })
    if (item.parse_status === 'failed') {
      error.value = `文档「${item.title}」入库失败：${item.error_message || '请检查文档和模型配置后重试'}`
    } else {
      notice.value = `文档「${item.title}」${item.parse_status === 'completed' ? '入库完成' : '已接收，等待处理'}`
    }
    await refreshAll()
  } catch (err) {
    fail(err)
  } finally {
    input.value = ''
    busy.value = false
    uploading.value = false
    uploadProgress.value = 0
  }
}

async function addManual() {
  if (!selectedId.value || !manualTitle.value.trim() || !manualContent.value.trim()) return
  busy.value = true
  clearMessages()
  try {
    const item = await api.createManualKnowledge(
      selectedId.value,
      manualTitle.value.trim(),
      manualContent.value.trim(),
    )
    manualTitle.value = ''
    manualContent.value = ''
    notice.value = `知识「${item.title}」已入库`
    await refreshAll()
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

async function toggleChunks(item: KnowledgeItem) {
  if (expanded.value[item.id]) {
    expanded.value[item.id] = false
    return
  }
  try {
    chunks.value[item.id] = await api.listChunks(item.id)
    expanded.value[item.id] = true
  } catch (err) {
    fail(err)
  }
}

async function removeDocument(item: KnowledgeItem) {
  if (!window.confirm(`删除「${item.title}」？`)) return
  try {
    await api.deleteKnowledge(item.id)
    notice.value = `已删除「${item.title}」`
    await refreshAll()
  } catch (err) {
    fail(err)
  }
}

/** 打开单条知识的标签编辑器，预填当前标签。 */
function openTagEditor(item: KnowledgeItem) {
  if (tagEditorFor.value === item.id) {
    tagEditorFor.value = ''
    return
  }
  moveFor.value = ''
  tagEditorFor.value = item.id
  selectedTagIds.value = [...(item.tag_ids || [])]
}

function toggleSelectedTag(tagId: string) {
  selectedTagIds.value = selectedTagIds.value.includes(tagId)
    ? selectedTagIds.value.filter((id) => id !== tagId)
    : [...selectedTagIds.value, tagId]
}

async function saveTags(item: KnowledgeItem) {
  if (!selectedId.value) return
  busy.value = true
  clearMessages()
  try {
    await api.setKnowledgeTags(selectedId.value, { [item.id]: selectedTagIds.value })
    tagEditorFor.value = ''
    notice.value = `已更新「${item.title}」的标签`
    await refreshAll()
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

function openMove(item: KnowledgeItem) {
  if (moveFor.value === item.id) {
    moveFor.value = ''
    return
  }
  tagEditorFor.value = ''
  moveFor.value = item.id
  movePath.value = item.folder_path || ''
}

async function saveMove(item: KnowledgeItem) {
  if (!selectedId.value) return
  busy.value = true
  clearMessages()
  try {
    await api.moveKnowledge(selectedId.value, [item.id], movePath.value.trim())
    moveFor.value = ''
    notice.value = `「${item.title}」已移动到 ${movePath.value.trim() || '根目录'}`
    await refreshAll()
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

async function addTag() {
  if (!selectedId.value || !newTagName.value.trim()) return
  busy.value = true
  clearMessages()
  try {
    const tag = await api.createTag(selectedId.value, newTagName.value.trim())
    newTagName.value = ''
    notice.value = `标签「${tag.name}」已创建`
    await loadOrganization()
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

function startRenameTag(tag: KnowledgeTag) {
  editingTagId.value = editingTagId.value === tag.id ? '' : tag.id
}

async function saveTagName(tag: KnowledgeTag, name: string) {
  if (!selectedId.value) return
  const trimmed = name.trim()
  if (!trimmed || trimmed === tag.name) {
    editingTagId.value = ''
    return
  }
  clearMessages()
  try {
    await api.updateTag(selectedId.value, tag.id, { name: trimmed })
    editingTagId.value = ''
    notice.value = `标签已重命名为「${trimmed}」`
    await loadOrganization()
  } catch (err) {
    fail(err)
  }
}

async function removeTag(tag: KnowledgeTag) {
  if (!selectedId.value) return
  clearMessages()
  try {
    await api.deleteTag(selectedId.value, tag.seq_id)
    notice.value = `标签「${tag.name}」已删除`
    await loadOrganization()
    await loadDocuments()
  } catch (err) {
    if (err instanceof ApiError && err.status === 400) {
      const force = window.confirm(
        `${err.message}\n\n是否强制删除？删除标签会一并清除该标签下的文档或 FAQ 条目。`,
      )
      if (!force) return
      try {
        await api.deleteTag(selectedId.value, tag.seq_id, true)
        notice.value = `标签「${tag.name}」已强制删除`
        await refreshAll()
      } catch (forceErr) {
        fail(forceErr)
      }
      return
    }
    fail(err)
  }
}

async function renameFolder() {
  if (!selectedId.value || !activeFolder.value || !folderRenameTo.value.trim()) return
  const target = folderRenameTo.value.trim()
  clearMessages()
  try {
    await api.renameFolder(selectedId.value, activeFolder.value, target)
    activeFolder.value = target
    folderRenameTo.value = ''
    notice.value = `文件夹已重命名为「${target}」`
    await refreshAll()
  } catch (err) {
    fail(err)
  }
}

function selectFolder(path: string) {
  activeFolder.value = path
  folderRenameTo.value = ''
  void loadDocuments()
}

function selectTag(tagId: string) {
  activeTag.value = activeTag.value === tagId ? '' : tagId
  void loadDocuments()
}

onMounted(async () => {
  await loadKbs()
  await refreshAll()
})
</script>

<template>
  <div class="layout">
    <aside class="card sidebar">
      <div class="panel-head">
        <div>
          <span class="eyebrow">工作区</span>
          <h2>知识库</h2>
        </div>
        <span class="counter">{{ kbs.length }}</span>
      </div>

      <p v-if="!kbs.length" class="muted hint">还没有知识库，先在下方创建一个。</p>
      <ul class="kb-list">
        <li
          v-for="kb in kbs"
          :key="kb.id"
          :class="{ active: kb.id === selectedId }"
          @click="selectKb(kb.id)"
        >
          <span class="kb-name">
            {{ kb.name }}
            <span class="kind">{{ kb.type === 'faq' ? 'FAQ' : kb.type === 'wiki' ? 'Wiki' : '文档' }}</span>
          </span>
          <span class="kb-desc">{{ kb.description || '无描述' }}</span>
        </li>
      </ul>

      <div class="create-box">
        <span class="eyebrow">新建知识库</span>
        <input
          id="kb-name"
          v-model="newKbName"
          aria-label="知识库名称"
          placeholder="例如：产品手册"
        />
        <input
          v-model="newKbDescription"
          aria-label="知识库描述"
          placeholder="描述（可选）"
        />
        <select v-model="newKbType" aria-label="知识库类型">
          <option value="document">文档知识库</option>
          <option value="faq">FAQ 知识库</option>
          <option value="wiki">Wiki 知识库</option>
        </select>
        <button :disabled="busy || !newKbName.trim()" @click="createKb">创建</button>
      </div>
    </aside>

    <section class="main">
      <div class="card panel">
        <header class="panel-head">
          <div class="panel-title">
            <span class="eyebrow">当前知识库</span>
            <h2>{{ selectedKb ? selectedKb.name : '请选择知识库' }}</h2>
            <p v-if="selectedKb" class="muted meta">
              分块大小 {{ selectedKb.chunking_config?.chunk_size ?? 600 }}
              · 文档 {{ folderTree?.total_document_count ?? documents.length }} 篇
            </p>
          </div>
          <label v-if="!isFaqKb" class="upload">
            <input :disabled="busy" type="file" accept=".txt,.md,.csv,.json,.pdf,.docx" @change="onFileChange" />
            <span>上传文档</span>
          </label>
          <RouterLink v-else class="upload link" to="/faq">去维护 FAQ 条目</RouterLink>
        </header>

        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <p v-if="notice" class="success" role="status">{{ notice }}</p>
        <div v-if="uploading" class="upload-status" role="status" aria-live="polite">
          <progress :value="uploadProgress < 100 ? uploadProgress : undefined" max="100" aria-label="文档上传与处理进度" />
          <span>{{ uploadProgress < 100 ? `正在上传 ${uploadProgress}%` : '上传完成，正在解析并入库，请稍候…' }}</span>
        </div>

        <div v-if="!isFaqKb && selectedId" class="org-bar">
          <div class="org-row">
            <span class="org-label">文件夹</span>
            <button
              class="chip-btn"
              :class="{ on: activeFolder === '' }"
              @click="selectFolder('')"
            >
              根目录
            </button>
            <button
              v-for="row in flatFolders"
              :key="row.node.path"
              class="chip-btn"
              :class="{ on: activeFolder === row.node.path }"
              :style="{ marginLeft: `${row.depth * 12}px` }"
              :title="`${row.node.path}（${row.node.document_count} 篇）`"
              @click="selectFolder(row.node.path)"
            >
              {{ row.node.name }}
              <span class="count">{{ row.node.document_count }}</span>
            </button>
            <template v-if="activeFolder">
              <input
                v-model="folderRenameTo"
                class="inline-input"
                aria-label="重命名文件夹"
                placeholder="重命名为…"
                @keyup.enter="renameFolder"
              />
              <button class="ghost small" :disabled="!folderRenameTo.trim()" @click="renameFolder">重命名</button>
            </template>
          </div>

          <div class="org-row">
            <span class="org-label">标签</span>
            <button class="chip-btn" :class="{ on: activeTag === '' }" @click="activeTag = ''; loadDocuments()">
              全部
            </button>
            <button
              v-for="tag in tags"
              :key="tag.id"
              class="chip-btn tag"
              :class="{ on: activeTag === tag.id }"
              @click="selectTag(tag.id)"
            >
              <span class="dot" :style="{ background: tag.color || '#94a3b8' }" aria-hidden="true"></span>
              {{ tag.name }}
              <span class="count">{{ tag.knowledge_count }}</span>
            </button>
            <span v-if="!tags.length" class="muted hint">还没有标签，在右侧新建。</span>
          </div>
        </div>

        <div class="panel-body">
          <div v-if="isFaqKb" class="empty-state">
            <p class="empty-title">FAQ 知识库</p>
            <p class="muted">FAQ 条目按问答对维护，请到 FAQ 页面新增、编辑、检索。</p>
          </div>
          <div v-else-if="documents.length" class="table-wrap">
            <table class="doc-table">
              <thead>
                <tr>
                  <th class="col-title">标题</th>
                  <th class="col-place">位置 / 标签</th>
                  <th class="col-status">状态</th>
                  <th class="col-actions"></th>
                </tr>
              </thead>
              <tbody>
                <template v-for="item in documents" :key="item.id">
                  <tr>
                    <td class="cell-title" :title="item.title">{{ item.title }}</td>
                    <td class="cell-place">
                      <div class="place">{{ item.folder_path || '根目录' }}</div>
                      <div class="tag-line">
                        <span v-for="tagId in item.tag_ids || []" :key="tagId" class="tag-pill">
                          {{ tagNameById[tagId] || tagId }}
                        </span>
                        <span v-if="!(item.tag_ids || []).length" class="muted tiny">无标签</span>
                      </div>
                    </td>
                    <td>
                      <span
                        class="badge"
                        :class="item.parse_status === 'completed' ? 'ok' : item.parse_status === 'failed' ? 'fail' : 'pending'"
                      >
                        {{ item.parse_status }}
                      </span>
                    </td>
                    <td>
                      <div class="actions">
                        <button class="ghost small" @click="openTagEditor(item)">打标</button>
                        <button class="ghost small" @click="openMove(item)">移动</button>
                        <button class="ghost small" @click="toggleChunks(item)">
                          {{ expanded[item.id] ? '收起' : '分块' }}
                        </button>
                        <button class="danger small" @click="removeDocument(item)">删除</button>
                      </div>
                    </td>
                  </tr>
                  <tr v-if="tagEditorFor === item.id" class="edit-row">
                    <td colspan="4">
                      <div class="editor">
                        <span class="editor-label">设置标签</span>
                        <label v-for="tag in tags" :key="tag.id" class="tag-check">
                          <input
                            type="checkbox"
                            :checked="selectedTagIds.includes(tag.id)"
                            @change="toggleSelectedTag(tag.id)"
                          />
                          <span>{{ tag.name }}</span>
                        </label>
                        <span v-if="!tags.length" class="muted tiny">请先在右侧新建标签</span>
                        <button class="small" :disabled="busy" @click="saveTags(item)">保存</button>
                      </div>
                    </td>
                  </tr>
                  <tr v-if="moveFor === item.id" class="edit-row">
                    <td colspan="4">
                      <div class="editor">
                        <span class="editor-label">移动到</span>
                        <input
                          v-model="movePath"
                          class="inline-input wide"
                          aria-label="目标文件夹路径"
                          placeholder="留空表示根目录，例如：售后/退款"
                          @keyup.enter="saveMove(item)"
                        />
                        <button class="small" :disabled="busy" @click="saveMove(item)">确定</button>
                      </div>
                    </td>
                  </tr>
                  <tr v-if="expanded[item.id]" class="expand-row">
                    <td colspan="4">
                      <div class="chunks">
                        <article v-for="chunk in chunks[item.id] || []" :key="chunk.id" class="chunk">
                          <div class="chunk-index">#{{ chunk.chunk_index }}</div>
                          <p>{{ chunk.content }}</p>
                        </article>
                      </div>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
          <div v-else-if="!isFaqKb" class="empty-state">
            <p class="empty-title">这里还没有文档</p>
            <p class="muted">
              {{ activeFolder || activeTag ? '当前筛选条件下没有文档，换个文件夹或标签看看。' : '上传 PDF、Word 或 Markdown，系统会自动切分并写入向量库。' }}
            </p>
          </div>
        </div>
      </div>
    </section>

    <div class="rail">
      <form v-if="!isFaqKb" class="card manual" @submit.prevent="addManual">
        <span class="eyebrow">手工录入</span>
        <h3>手工知识</h3>
        <div class="rail-body">
          <input v-model="manualTitle" aria-label="知识标题" placeholder="标题" />
          <textarea v-model="manualContent" aria-label="知识内容" placeholder="内容" />
          <button
            type="submit"
            :disabled="busy || !manualTitle.trim() || !manualContent.trim()"
          >
            入库
          </button>
        </div>
      </form>

      <div class="card tag-panel">
        <span class="eyebrow">知识组织</span>
        <h3>标签管理</h3>
        <form class="tag-create" @submit.prevent="addTag">
          <input v-model="newTagName" aria-label="新标签名称" placeholder="新标签名称" />
          <button :disabled="busy || !newTagName.trim()">新建</button>
        </form>
        <ul class="tag-list">
          <li v-for="tag in tags" :key="tag.id">
            <span class="dot" :style="{ background: tag.color || '#94a3b8' }" aria-hidden="true"></span>
            <input
              v-if="editingTagId === tag.id"
              class="inline-input"
              :value="tag.name"
              aria-label="标签新名称"
              @keyup.enter="saveTagName(tag, ($event.target as HTMLInputElement).value)"
            />
            <span v-else class="tag-name" @dblclick="startRenameTag(tag)">{{ tag.name }}</span>
            <span class="tag-stat">{{ tag.knowledge_count }} 文档 · {{ tag.chunk_count }} 分块</span>
            <button class="ghost tiny" @click="startRenameTag(tag)">改名</button>
            <button class="danger tiny" @click="removeTag(tag)">删除</button>
          </li>
        </ul>
        <p v-if="!tags.length" class="muted hint">新建标签后，可在文档行点「打标」绑定。</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 252px minmax(0, 1fr) 380px;
  grid-template-areas: 'side main rail';
  gap: 18px;
  flex: 1;
  min-height: 0;
}

.sidebar {
  grid-area: side;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  padding: 18px;
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

.hint {
  line-height: 1.6;
}

.kb-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  list-style: none;
  margin: 0;
  padding: 0 2px 0 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kb-list li {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  cursor: pointer;
  border: 1px solid transparent;
  border-radius: 10px;
  transition: background 0.16s ease, border-color 0.16s ease;
}

.kb-list li:hover {
  background: var(--surface-muted);
}

.kb-list li.active {
  background: var(--primary-soft);
  border-color: var(--primary-line);
}

.kb-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kind {
  flex: none;
  padding: 1px 6px;
  font-size: 10px;
  font-weight: 700;
  color: var(--primary);
  background: var(--primary-soft);
  border-radius: 999px;
}

.kb-desc {
  font-size: 12px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.create-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: auto;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}

.create-box input,
.create-box select,
.create-box button {
  height: 36px;
}

.main {
  grid-area: main;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px;
  overflow: hidden;
}

.panel-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.meta {
  margin-top: 2px;
}

.upload {
  position: relative;
  display: inline-flex;
  flex: none;
  align-items: center;
  height: 34px;
  padding: 0 14px;
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  background: var(--primary);
  border-radius: 9px;
  cursor: pointer;
  transition: background 0.16s ease;
}

.upload.link {
  text-decoration: none;
}

.upload:hover {
  background: var(--primary-strong);
}

.upload:focus-within {
  box-shadow: var(--ring);
}

.upload input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  padding: 0;
  opacity: 0;
  cursor: pointer;
}

.upload-status {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  font-size: 13px;
  color: var(--text-soft);
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.upload-status progress {
  width: 180px;
  height: 6px;
  accent-color: var(--primary);
}

.org-bar {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.org-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.org-label {
  flex: none;
  width: 48px;
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
}

.chip-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 26px;
  padding: 0 10px;
  font-size: 12px;
  color: var(--text-soft);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 999px;
  cursor: pointer;
  transition: background 0.16s ease, border-color 0.16s ease, color 0.16s ease;
}

.chip-btn:hover {
  color: var(--primary);
  border-color: var(--primary-line);
}

.chip-btn.on {
  color: var(--primary);
  background: var(--primary-soft);
  border-color: var(--primary-line);
}

.chip-btn .count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
}

.dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  flex: none;
  border-radius: 999px;
}

.inline-input {
  height: 26px;
  padding: 0 8px;
  font-size: 12px;
  width: 130px;
}

.inline-input.wide {
  flex: 1;
  min-width: 180px;
  height: 30px;
  font-size: 13px;
}

.panel-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.panel-body > .table-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
  margin: 0;
  padding: 0;
}

.panel-body > .empty-state {
  margin: auto;
  width: 100%;
}

.doc-table {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
  font-size: 14px;
}

.col-place {
  width: 190px;
}

.col-status {
  width: 88px;
}

.col-actions {
  width: 210px;
}

.doc-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 8px 12px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  text-align: left;
  color: var(--muted);
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}

.doc-table td {
  padding: 11px 12px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}

.doc-table tbody tr:hover td {
  background: var(--surface-muted);
}

.doc-table tbody tr:last-child td {
  border-bottom: none;
}

.cell-title {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-place {
  display: table-cell;
}

.place {
  font-size: 12px;
  color: var(--text-soft);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-line {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.tag-pill {
  padding: 1px 7px;
  font-size: 11px;
  color: var(--primary);
  background: var(--primary-soft);
  border-radius: 999px;
}

.tiny {
  font-size: 11px;
}

.chip {
  display: inline-block;
  padding: 2px 8px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-soft);
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: 6px;
}

.actions {
  display: flex;
  flex-wrap: nowrap;
  gap: 6px;
  justify-content: flex-end;
  white-space: nowrap;
}

.small {
  font-size: 12px;
  padding: 0 10px;
  height: 28px;
}

.ghost.small,
.danger.small {
  height: 28px;
  padding: 0 10px;
  font-size: 12px;
}

.tiny-btn,
.ghost.tiny,
.danger.tiny {
  height: 24px;
  padding: 0 8px;
  font-size: 11px;
}

.edit-row td {
  padding: 6px 12px 12px;
  background: var(--surface-muted);
}

.editor {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.editor-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
}

.tag-check {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-soft);
}

.expand-row td {
  padding: 4px 12px 16px;
  background: var(--surface-muted);
}

.expand-row:hover td {
  background: var(--surface-muted);
}

.chunks {
  display: grid;
  gap: 8px;
}

.chunk {
  padding: 10px 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.chunk-index {
  font-size: 12px;
  font-weight: 600;
  color: var(--primary);
}

.chunk p {
  margin: 6px 0 0;
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-soft);
}

.rail {
  grid-area: rail;
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-height: 0;
  overflow-y: auto;
}

.manual,
.tag-panel {
  flex: 1 1 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  padding: 18px;
}

.manual h3,
.tag-panel h3 {
  margin-top: 2px;
}

.rail-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.rail-body textarea {
  flex: 1;
  min-height: 70px;
  resize: none;
}

.rail-body button {
  flex: none;
}

.tag-create {
  display: flex;
  gap: 8px;
}

.tag-create input {
  flex: 1;
  height: 32px;
}

.tag-create button {
  flex: none;
  height: 32px;
  padding: 0 14px;
}

.tag-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tag-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  font-size: 12px;
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.tag-name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-stat {
  flex: none;
  font-size: 11px;
  color: var(--muted);
}

@media (max-width: 1180px) {
  .layout {
    grid-template-columns: 240px minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) auto;
    grid-template-areas:
      'side main'
      'side rail';
  }

  .rail {
    flex-direction: row;
  }

  .rail > .card {
    min-height: 230px;
  }
}

@media (max-width: 900px) {
  .layout {
    display: flex;
    flex-direction: column;
    flex: none;
    gap: 16px;
  }

  .sidebar,
  .manual,
  .tag-panel {
    flex: none;
  }

  .kb-list {
    flex: none;
    max-height: 260px;
    overflow-y: auto;
  }

  .panel {
    flex: none;
    min-height: 460px;
  }

  .panel-body > .table-wrap {
    flex: none;
    max-height: 46vh;
    overflow: auto;
  }

  .rail {
    flex-direction: column;
  }

  .rail-body textarea {
    min-height: 96px;
  }

  .tag-list {
    max-height: 240px;
  }

  .doc-table {
    min-width: 720px;
  }
}
</style>
