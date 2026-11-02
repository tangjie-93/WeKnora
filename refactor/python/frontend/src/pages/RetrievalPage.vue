<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, ApiError } from '../api'
import type { KnowledgeBase, SearchHit } from '../api'

const kbs = ref<KnowledgeBase[]>([])
const selectedId = ref('')
const query = ref('')
const topK = ref(10)
const hits = ref<SearchHit[]>([])
const busy = ref(false)
const error = ref('')
const notice = ref('')

const selectedKb = computed(() => kbs.value.find((kb) => kb.id === selectedId.value))
const isFaqKb = computed(() => selectedKb.value?.type === 'faq')

function fail(err: unknown) {
  error.value = err instanceof ApiError ? err.message : '请求失败，请检查后端是否启动'
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

async function runSearch() {
  if (!selectedId.value || !query.value.trim()) return
  error.value = ''
  notice.value = ''
  busy.value = true
  try {
    hits.value = await api.hybridSearch(selectedId.value, query.value.trim(), topK.value)
    if (!hits.value.length) notice.value = '没有命中任何分块'
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

onMounted(loadKbs)
</script>

<template>
  <div class="page">
    <header class="card head">
      <div>
        <span class="eyebrow">调试</span>
        <h1>检索测试</h1>
        <p class="muted">输入问题，查看混合检索命中的分块与得分。</p>
      </div>

      <div class="field kb-field">
        <label for="kb-select">知识库</label>
        <select id="kb-select" v-model="selectedId" aria-label="选择知识库">
          <option v-for="kb in kbs" :key="kb.id" :value="kb.id">
            {{ kb.name }}（{{ kb.type === 'faq' ? 'FAQ' : kb.type === 'wiki' ? 'Wiki' : '文档' }}）
          </option>
        </select>
      </div>
    </header>

    <div class="card search-box">
      <div class="query-row">
        <input
          v-model="query"
          aria-label="检索关键词"
          placeholder="例如：Nebula 默认端口是多少"
          @keyup.enter="runSearch"
        />
        <button :disabled="busy || !query.trim() || isFaqKb" @click="runSearch">
          {{ busy ? '检索中…' : '检索' }}
        </button>
      </div>
      <div class="options">
        <label class="topk" for="topk-select">
          返回条数
          <select id="topk-select" v-model.number="topK" aria-label="返回条数">
            <option :value="5">5</option>
            <option :value="10">10</option>
            <option :value="20">20</option>
          </select>
        </label>
        <span v-if="isFaqKb" class="muted">FAQ 知识库请到 FAQ 页面检索。</span>
      </div>
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="success" role="status">{{ notice }}</p>

    <section v-if="hits.length" class="hits" aria-live="polite">
      <article v-for="hit in hits" :key="hit.id" class="hit">
        <div class="hit-head">
          <span class="muted">chunk #{{ hit.chunk_index }}</span>
          <span class="badge plain">score {{ hit.score }}</span>
        </div>
        <p class="content">{{ hit.content }}</p>
        <p class="scores">
          vector {{ hit.vector_score }} · keyword {{ hit.keyword_score }}
        </p>
      </article>
    </section>

    <div v-else-if="!error" class="empty-state">
      <p class="empty-title">等待检索</p>
      <p class="muted">选择一个知识库并输入问题，命中结果会在这里展示。</p>
    </div>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
}

.head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  flex-wrap: wrap;
}

.head h1 {
  margin-top: 2px;
}

.kb-field {
  width: 320px;
  max-width: 100%;
}

.search-box {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.query-row {
  display: flex;
  gap: 12px;
}

.query-row input {
  flex: 1;
  height: 52px;
  font-size: 16px;
  padding: 0 16px;
}

.query-row button {
  flex: none;
  height: 52px;
  padding: 0 28px;
  font-size: 15px;
}

.options {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.topk {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-soft);
}

.topk select {
  width: 72px;
  height: 32px;
}

.hits {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.hit {
  padding: 16px 18px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.hit-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.content {
  margin: 10px 0 0;
  font-size: 15px;
  line-height: 1.8;
  color: var(--text-soft);
  white-space: pre-wrap;
  word-break: break-word;
}

.scores {
  margin: 10px 0 0;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--muted);
}

@media (max-width: 640px) {
  .query-row {
    flex-direction: column;
  }

  .query-row button {
    width: 100%;
  }
}
</style>
