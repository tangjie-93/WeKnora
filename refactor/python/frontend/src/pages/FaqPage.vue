<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api, ApiError } from '../api'
import type { FaqEntry, FaqSearchHit, KnowledgeBase, KnowledgeTag } from '../api'

const kbs = ref<KnowledgeBase[]>([])
const kbId = ref('')
const entries = ref<FaqEntry[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const tags = ref<KnowledgeTag[]>([])
const keyword = ref('')
const tagFilter = ref('')
const enabledFilter = ref('')
const selected = ref<number[]>([])

const editingId = ref(0)
const formRef = ref<HTMLElement | null>(null)
const form = reactive({
  standard_question: '',
  similar: '',
  negative: '',
  answers: '',
  answer_strategy: 'all',
  tagSeq: 0,
  is_enabled: true,
  is_recommended: true,
})

const searchQuery = ref('')
const searchHits = ref<FaqSearchHit[]>([])

const busy = ref(false)
const error = ref('')
const notice = ref('')

const faqKbs = computed(() => kbs.value.filter((kb) => kb.type === 'faq'))
const selectedKb = computed(() => kbs.value.find((kb) => kb.id === kbId.value))
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const editingEntry = computed(() => entries.value.find((item) => item.id === editingId.value))

function fail(err: unknown) {
  error.value = err instanceof ApiError ? err.message : '请求失败，请检查后端是否启动'
}

function splitLines(text: string): string[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

function formPayload(): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    standard_question: form.standard_question.trim(),
    similar_questions: splitLines(form.similar),
    negative_questions: splitLines(form.negative),
    answers: splitLines(form.answers),
    answer_strategy: form.answer_strategy,
    is_enabled: form.is_enabled,
    is_recommended: form.is_recommended,
  }
  if (form.tagSeq) payload.tag_id = form.tagSeq
  return payload
}

function resetForm() {
  editingId.value = 0
  form.standard_question = ''
  form.similar = ''
  form.negative = ''
  form.answers = ''
  form.answer_strategy = 'all'
  form.tagSeq = 0
  form.is_enabled = true
  form.is_recommended = true
}

async function loadKbs() {
  try {
    kbs.value = await api.listKnowledgeBases()
    if (!faqKbs.value.some((kb) => kb.id === kbId.value)) {
      kbId.value = faqKbs.value[0]?.id || ''
    }
  } catch (err) {
    fail(err)
  }
}

async function loadTags() {
  if (!kbId.value) {
    tags.value = []
    return
  }
  try {
    tags.value = (await api.listTags(kbId.value)).data
  } catch (err) {
    fail(err)
  }
}

async function loadEntries() {
  if (!kbId.value) {
    entries.value = []
    total.value = 0
    return
  }
  try {
    const result = await api.listFaqEntries(kbId.value, {
      keyword: keyword.value.trim() || undefined,
      tagId: tagFilter.value ? Number(tagFilter.value) : undefined,
      isEnabled: enabledFilter.value === '' ? undefined : enabledFilter.value === 'true',
      page: page.value,
      pageSize,
    })
    entries.value = result.data
    total.value = result.total
    selected.value = []
  } catch (err) {
    fail(err)
  }
}

async function reload() {
  await loadEntries()
  await loadTags()
}

watch(kbId, async () => {
  error.value = ''
  notice.value = ''
  page.value = 1
  resetForm()
  searchHits.value = []
  await reload()
})

function search(resetPage = true) {
  if (resetPage) page.value = 1
  void loadEntries()
}

function goPage(target: number) {
  if (target < 1 || target > pageCount.value) return
  page.value = target
  void loadEntries()
}

function toggleSelected(id: number) {
  selected.value = selected.value.includes(id)
    ? selected.value.filter((item) => item !== id)
    : [...selected.value, id]
}

function toggleAll() {
  selected.value =
    selected.value.length === entries.value.length ? [] : entries.value.map((item) => item.id)
}

async function submitForm() {
  if (!kbId.value || busy.value) return
  if (!form.standard_question.trim() || !splitLines(form.answers).length) {
    error.value = '标准问与至少一个答案不能为空'
    return
  }
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    if (editingId.value) {
      const entry = await api.updateFaqEntry(kbId.value, editingId.value, formPayload())
      notice.value = `条目「${entry.standard_question}」已更新`
    } else {
      const entry = await api.createFaqEntry(kbId.value, formPayload())
      notice.value = `条目「${entry.standard_question}」已创建`
    }
    resetForm()
    await reload()
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

function startEdit(entry: FaqEntry) {
  editingId.value = entry.id
  form.standard_question = entry.standard_question
  form.similar = entry.similar_questions.join('\n')
  form.negative = entry.negative_questions.join('\n')
  form.answers = entry.answers.join('\n')
  form.answer_strategy = entry.answer_strategy
  form.tagSeq = entry.tag_id
  form.is_enabled = entry.is_enabled
  form.is_recommended = entry.is_recommended
  error.value = ''
  notice.value = ''
  formRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function toggleEnabled(entry: FaqEntry) {
  if (!kbId.value) return
  try {
    await api.updateFaqFields(kbId.value, {
      by_id: { [String(entry.id)]: { is_enabled: !entry.is_enabled } },
    })
    await loadEntries()
  } catch (err) {
    fail(err)
  }
}

async function removeEntry(entry: FaqEntry) {
  if (!kbId.value || !window.confirm(`删除条目「${entry.standard_question}」？`)) return
  try {
    await api.deleteFaqEntries(kbId.value, [entry.id])
    notice.value = `已删除「${entry.standard_question}」`
    if (editingId.value === entry.id) resetForm()
    await reload()
  } catch (err) {
    fail(err)
  }
}

async function batchSetEnabled(enabled: boolean) {
  if (!kbId.value || !selected.value.length) return
  const byId = Object.fromEntries(
    selected.value.map((id) => [String(id), { is_enabled: enabled }]),
  )
  try {
    const result = await api.updateFaqFields(kbId.value, { by_id: byId })
    notice.value = `已${enabled ? '启用' : '禁用'} ${result.updated} 条条目`
    await loadEntries()
  } catch (err) {
    fail(err)
  }
}

async function batchRemove() {
  if (!kbId.value || !selected.value.length) return
  if (!window.confirm(`删除选中的 ${selected.value.length} 条条目？`)) return
  try {
    await api.deleteFaqEntries(kbId.value, selected.value)
    notice.value = `已删除 ${selected.value.length} 条条目`
    await reload()
  } catch (err) {
    fail(err)
  }
}

async function runSearch() {
  if (!kbId.value || !searchQuery.value.trim()) return
  error.value = ''
  try {
    searchHits.value = await api.searchFaq(kbId.value, searchQuery.value.trim())
    if (!searchHits.value.length) notice.value = '没有匹配的 FAQ 条目'
  } catch (err) {
    fail(err)
  }
}

function formatTime(value: string | null): string {
  if (!value) return '—'
  return value.replace('T', ' ').replace('Z', '').slice(0, 16)
}

onMounted(async () => {
  await loadKbs()
  await reload()
})
</script>

<template>
  <div class="faq-page">
    <section class="card panel">
      <header class="panel-head">
        <div>
          <span class="eyebrow">FAQ</span>
          <h2>{{ selectedKb ? selectedKb.name : 'FAQ 条目' }}</h2>
        </div>
        <span class="counter">{{ total }}</span>
      </header>

      <div v-if="!faqKbs.length" class="empty-state">
        <p class="empty-title">还没有 FAQ 知识库</p>
        <p class="muted">在知识库页新建一个类型为 FAQ 的知识库，即可维护问答条目。</p>
        <RouterLink to="/knowledge"><button class="ghost small">去创建</button></RouterLink>
      </div>

      <template v-else>
        <div class="toolbar">
          <select v-model="kbId" aria-label="FAQ 知识库">
            <option v-for="kb in faqKbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
          </select>
          <input
            v-model="keyword"
            placeholder="搜索标准问 / 相似问 / 答案"
            @keyup.enter="search()"
          />
          <select v-model="tagFilter" aria-label="标签筛选" @change="search()">
            <option value="">全部标签</option>
            <option v-for="tag in tags" :key="tag.id" :value="String(tag.seq_id)">
              {{ tag.name }}
            </option>
          </select>
          <select v-model="enabledFilter" aria-label="启用状态" @change="search()">
            <option value="">全部状态</option>
            <option value="true">已启用</option>
            <option value="false">已禁用</option>
          </select>
          <button class="ghost small" @click="search()">查询</button>
        </div>

        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <p v-if="notice" class="success" role="status">{{ notice }}</p>

        <div v-if="entries.length" class="table-wrap">
          <table class="faq-table">
            <thead>
              <tr>
                <th class="pick">
                  <input
                    type="checkbox"
                    :checked="selected.length === entries.length"
                    aria-label="全选"
                    @change="toggleAll"
                  />
                </th>
                <th>标准问</th>
                <th>标签</th>
                <th>状态</th>
                <th>更新时间</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="entry in entries" :key="entry.id">
                <td class="pick">
                  <input
                    type="checkbox"
                    :checked="selected.includes(entry.id)"
                    :aria-label="`选择 ${entry.standard_question}`"
                    @change="toggleSelected(entry.id)"
                  />
                </td>
                <td>
                  <div class="question-line">
                    <strong>{{ entry.standard_question }}</strong>
                    <span v-if="entry.is_recommended" class="badge plain rec">推荐</span>
                  </div>
                  <p v-if="entry.similar_questions.length" class="sub-line">
                    相似问：{{ entry.similar_questions.join('、') }}
                  </p>
                  <p v-if="entry.answers.length" class="sub-line answer">
                    答案：{{ entry.answers.join(' / ') }}
                  </p>
                </td>
                <td><span class="chip">{{ entry.tag_name || '未分类' }}</span></td>
                <td>
                  <span class="badge" :class="entry.is_enabled ? 'ok' : 'fail'">
                    {{ entry.is_enabled ? '已启用' : '已禁用' }}
                  </span>
                </td>
                <td class="muted nowrap">{{ formatTime(entry.updated_at) }}</td>
                <td>
                  <div class="actions">
                    <button class="ghost small" @click="startEdit(entry)">编辑</button>
                    <button class="ghost small" @click="toggleEnabled(entry)">
                      {{ entry.is_enabled ? '禁用' : '启用' }}
                    </button>
                    <button class="danger small" @click="removeEntry(entry)">删除</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else class="empty-state">
          <p class="empty-title">还没有条目</p>
          <p class="muted">在右侧填写标准问与答案，保存后即可参与 FAQ 检索。</p>
        </div>

        <div v-if="entries.length" class="footer-bar">
          <div class="row">
            <button class="ghost small" :disabled="!selected.length" @click="batchSetEnabled(true)">
              批量启用
            </button>
            <button class="ghost small" :disabled="!selected.length" @click="batchSetEnabled(false)">
              批量禁用
            </button>
            <button class="danger small" :disabled="!selected.length" @click="batchRemove">
              批量删除
            </button>
            <span v-if="selected.length" class="muted">已选 {{ selected.length }} 条</span>
          </div>
          <div class="row">
            <button class="ghost small" :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
            <span class="muted">{{ page }} / {{ pageCount }}</span>
            <button class="ghost small" :disabled="page >= pageCount" @click="goPage(page + 1)">
              下一页
            </button>
          </div>
        </div>
      </template>
    </section>

    <div class="side">
      <form ref="formRef" class="card form-card" @submit.prevent="submitForm">
        <span class="eyebrow">{{ editingId ? '编辑' : '新增' }}</span>
        <h2>{{ editingId ? '修改条目' : '新建条目' }}</h2>
        <div class="stack form-body">
          <div class="field">
            <label for="faq-standard">标准问 <span class="req">*</span></label>
            <input
              id="faq-standard"
              v-model="form.standard_question"
              placeholder="例如：如何申请开发票？"
            />
          </div>
          <div class="field">
            <label for="faq-similar">相似问（每行一条）</label>
            <textarea id="faq-similar" v-model="form.similar" rows="3" />
          </div>
          <div class="field">
            <label for="faq-negative">反例问题（每行一条）</label>
            <textarea id="faq-negative" v-model="form.negative" rows="2" />
          </div>
          <div class="field">
            <label for="faq-answers">答案（每行一条） <span class="req">*</span></label>
            <textarea id="faq-answers" v-model="form.answers" rows="3" />
          </div>
          <div class="field">
            <label for="faq-strategy">答案策略</label>
            <select id="faq-strategy" v-model="form.answer_strategy">
              <option value="all">返回全部答案</option>
              <option value="random">随机返回一条</option>
            </select>
          </div>
          <div class="field">
            <label for="faq-tag">标签</label>
            <select id="faq-tag" v-model.number="form.tagSeq">
              <option :value="0">未分类</option>
              <option v-for="tag in tags" :key="tag.id" :value="tag.seq_id">{{ tag.name }}</option>
            </select>
          </div>
          <label class="checkbox">
            <input v-model="form.is_enabled" type="checkbox" />
            <span>启用该条目（参与检索）</span>
          </label>
          <label class="checkbox">
            <input v-model="form.is_recommended" type="checkbox" />
            <span>标记为推荐条目</span>
          </label>
          <div class="row">
            <button type="submit" :disabled="busy || !kbId">
              {{ busy ? '保存中…' : editingId ? '保存修改' : '创建条目' }}
            </button>
            <button v-if="editingId" type="button" class="ghost" @click="resetForm">取消</button>
          </div>
          <p v-if="editingEntry" class="muted">
            索引模式：{{ editingEntry.index_mode }} · 编号 #{{ editingEntry.id }}
          </p>
        </div>
      </form>

      <section class="card search-card">
        <span class="eyebrow">检索演示</span>
        <h2>FAQ 搜索</h2>
        <div class="row search-row">
          <input v-model="searchQuery" placeholder="输入问题，例如「发票申请入口」" @keyup.enter="runSearch" />
          <button class="small" :disabled="!searchQuery.trim() || !kbId" @click="runSearch">检索</button>
        </div>
        <div v-if="searchHits.length" class="stack hits">
          <div v-for="hit in searchHits" :key="hit.id" class="hit">
            <div class="row between">
              <strong>{{ hit.standard_question }}</strong>
              <span class="badge plain">{{ hit.score.toFixed(2) }}</span>
            </div>
            <p v-if="hit.answers.length" class="muted">{{ hit.answers.join(' / ') }}</p>
            <p class="muted">标签：{{ hit.tag_name || '未分类' }}</p>
          </div>
        </div>
        <p v-else class="muted">输入问题后在这里查看命中条目与得分。</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.faq-page {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: 20px;
  align-items: start;
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
  grid-template-columns: 160px minmax(0, 1fr) 130px 120px auto;
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

.faq-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.faq-table th {
  padding: 8px 12px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  text-align: left;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
}

.faq-table td {
  padding: 12px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}

.faq-table tbody tr:hover td {
  background: var(--surface-muted);
}

.faq-table tbody tr:last-child td {
  border-bottom: none;
}

.pick {
  width: 36px;
}

.question-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.rec {
  color: var(--warning-text);
  background: var(--warning-soft);
  border-color: var(--warning-line);
}

.sub-line {
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--muted);
  overflow-wrap: anywhere;
}

.sub-line.answer {
  color: var(--text-soft);
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

.nowrap {
  white-space: nowrap;
}

.actions {
  display: flex;
  flex-wrap: nowrap;
  gap: 8px;
  justify-content: flex-end;
  white-space: nowrap;
}

.footer-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.side {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}

.form-card h2,
.search-card h2 {
  margin-top: 2px;
}

.form-body {
  margin-top: 16px;
  gap: 14px;
}

.req {
  color: var(--danger);
}

.checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-soft);
  cursor: pointer;
}

.form-body > .row > button[type='submit'] {
  flex: 1;
  height: 44px;
}

.search-row {
  margin-top: 12px;
  align-items: stretch;
}

.search-row input {
  min-width: 0;
}

.hits {
  margin-top: 12px;
  gap: 10px;
}

.hit {
  padding: 12px;
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.hit strong {
  font-size: 13px;
  overflow-wrap: anywhere;
}

@media (max-width: 1080px) {
  .faq-page {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 860px) {
  .toolbar {
    grid-template-columns: 1fr 1fr;
  }

  .faq-table {
    min-width: 720px;
  }
}
</style>
