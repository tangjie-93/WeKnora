<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { api, ApiError, streamChat } from '../api'
import type { KnowledgeBase, MessageItem, Reference, SessionItem, StreamEvent } from '../api'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  references: Reference[]
  streaming: boolean
}

const sessions = ref<SessionItem[]>([])
const kbs = ref<KnowledgeBase[]>([])
const selectedId = ref('')
const messages = ref<ChatMessage[]>([])
const input = ref('')
const sending = ref(false)
const error = ref('')
const duration = ref<number | null>(null)
const listEl = ref<HTMLElement | null>(null)

const newTitle = ref('')
const newKbId = ref('')
const selectedSession = computed(() => sessions.value.find((item) => item.id === selectedId.value))

let localId = 0
const nextId = () => `local-${++localId}`

function fail(err: unknown) {
  error.value = err instanceof ApiError ? err.message : '请求失败，请检查后端是否启动'
}

async function scrollToBottom() {
  await nextTick()
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
}

async function loadSessions() {
  try {
    sessions.value = await api.listSessions()
    if (!selectedId.value && sessions.value.length) {
      await selectSession(sessions.value[0].id)
    }
  } catch (err) {
    fail(err)
  }
}

function toChatMessage(item: MessageItem): ChatMessage {
  return {
    id: item.id,
    role: item.role === 'user' ? 'user' : 'assistant',
    content: item.content,
    references: item.knowledge_references || [],
    streaming: false,
  }
}

async function selectSession(id: string) {
  if (sending.value) return
  selectedId.value = id
  error.value = ''
  duration.value = null
  messages.value = []
  try {
    const rows = await api.loadMessages(id)
    messages.value = rows.map(toChatMessage)
    await scrollToBottom()
  } catch (err) {
    fail(err)
  }
}

async function createSession() {
  if (sending.value) return
  error.value = ''
  try {
    const session = await api.createSession(
      newTitle.value.trim() || '新会话',
      newKbId.value,
    )
    newTitle.value = ''
    await loadSessions()
    await selectSession(session.id)
  } catch (err) {
    fail(err)
  }
}

async function removeSession(item: SessionItem) {
  if (sending.value) return
  if (!window.confirm(`删除会话「${item.title}」？`)) return
  try {
    await api.deleteSession(item.id)
    if (selectedId.value === item.id) {
      selectedId.value = ''
      messages.value = []
    }
    sessions.value = await api.listSessions()
    if (!selectedId.value && sessions.value.length) {
      await selectSession(sessions.value[0].id)
    }
  } catch (err) {
    fail(err)
  }
}

function handleEvent(event: StreamEvent, assistant: ChatMessage) {
  const payload = event.data || {}
  if (event.response_type === 'references') {
    const refs = (payload.references ?? payload.knowledge_references ?? []) as Reference[]
    if (Array.isArray(refs) && refs.length) assistant.references = refs
    return
  }
  if (event.response_type === 'answer') {
    const delta = payload.content
    if (typeof delta === 'string' && delta) {
      assistant.content += delta
      void scrollToBottom()
    }
    return
  }
  if (event.response_type === 'complete') {
    const refs = (event.knowledge_references ?? payload.knowledge_references ?? []) as Reference[]
    if (Array.isArray(refs) && refs.length) assistant.references = refs
    const ms = payload.total_duration_ms
    if (typeof ms === 'number') duration.value = ms
  }
}

/** 发送一轮问题并响应式展示答案；失败保留内容，结束后释放发送状态。 */
async function send() {
  const query = input.value.trim()
  if (!query || !selectedId.value || sending.value) return

  error.value = ''
  duration.value = null
  sending.value = true
  input.value = ''
  messages.value.push({ id: nextId(), role: 'user', content: query, references: [], streaming: false })
  const assistant = reactive<ChatMessage>({
    id: nextId(),
    role: 'assistant',
    content: '',
    references: [],
    streaming: true,
  })
  messages.value.push(assistant)
  await scrollToBottom()

  try {
    await streamChat(selectedId.value, query, (event) => handleEvent(event, assistant))
    if (!assistant.content) assistant.content = '（模型没有返回内容）'
  } catch (err) {
    assistant.content = assistant.content || '回答失败'
    fail(err)
  } finally {
    assistant.streaming = false
    sending.value = false
    await scrollToBottom()
  }
}

onMounted(async () => {
  try {
    kbs.value = await api.listKnowledgeBases()
    if (kbs.value.length) newKbId.value = kbs.value[0].id
  } catch (err) {
    fail(err)
  }
  await loadSessions()
})
</script>

<template>
  <div class="layout">
    <aside class="card sidebar">
      <div class="panel-head">
        <div>
          <span class="eyebrow">会话</span>
          <h2>历史对话</h2>
        </div>
        <span class="counter">{{ sessions.length }}</span>
      </div>

      <ul class="session-list">
        <li
          v-for="item in sessions"
          :key="item.id"
          :class="{ active: item.id === selectedId }"
          @click="selectSession(item.id)"
        >
          <span class="title">{{ item.title }}</span>
          <button class="danger small" @click.stop="removeSession(item)">删除</button>
        </li>
      </ul>
      <p v-if="!sessions.length" class="muted hint">还没有会话，先创建一个。</p>

      <div class="create-box">
        <span class="eyebrow">新建会话</span>
        <input id="session-title" v-model="newTitle" aria-label="会话标题" placeholder="会话标题" />
        <select v-model="newKbId" aria-label="绑定知识库">
          <option value="">不绑定知识库</option>
          <option v-for="kb in kbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
        </select>
        <button @click="createSession">创建会话</button>
      </div>
    </aside>

    <section class="card chat">
      <header class="chat-head">
        <div class="chat-title">
          <span class="eyebrow">对话</span>
          <h2>{{ selectedSession ? selectedSession.title : '请选择或创建会话' }}</h2>
        </div>
        <span v-if="duration !== null" class="badge ok">耗时 {{ duration }} ms</span>
      </header>

      <p v-if="error" class="error">{{ error }}</p>

      <div ref="listEl" class="messages">
        <div v-if="!messages.length" class="empty-state">
          <p class="empty-title">开始一次知识问答</p>
          <p class="muted">在下方输入问题，系统会检索知识库并流式回答。</p>
        </div>
        <article v-for="message in messages" :key="message.id" class="message" :class="message.role">
          <div class="avatar" :class="message.role">{{ message.role === 'user' ? '我' : 'AI' }}</div>
          <div class="bubble">
            <p v-if="message.content" class="text">{{ message.content }}</p>
            <p v-else-if="message.streaming" class="muted">思考中…</p>
            <div v-if="message.references.length" class="refs">
              <div class="ref-title">引用（{{ message.references.length }}）</div>
              <article v-for="ref in message.references" :key="ref.id" class="ref">
                <div class="ref-meta">chunk #{{ ref.chunk_index }} · score {{ ref.score }}</div>
                <p>{{ ref.content }}</p>
              </article>
            </div>
          </div>
        </article>
      </div>

      <form class="composer" @submit.prevent="send">
        <textarea
          v-model="input"
          rows="3"
          aria-label="输入问题"
          placeholder="输入问题后按发送（Ctrl+Enter）"
          @keydown.ctrl.enter.prevent="send"
        />
        <button type="submit" :disabled="sending || !input.trim() || !selectedId">
          {{ sending ? '生成中…' : '发送' }}
        </button>
      </form>
    </section>
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  gap: 20px;
  flex: 1;
  min-height: 0;
  align-items: stretch;
}

.sidebar {
  display: flex;
  flex-direction: column;
  gap: 16px;
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

.session-list {
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

.session-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 8px 6px 12px;
  cursor: pointer;
  border: 1px solid transparent;
  border-radius: 10px;
  transition: background 0.16s ease, border-color 0.16s ease;
}

.session-list li:hover {
  background: var(--surface-muted);
}

.session-list li.active {
  background: var(--primary-soft);
  border-color: var(--primary-line);
}

.title {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (hover: hover) and (pointer: fine) {
  .session-list li .danger {
    opacity: 0;
  }

  .session-list li:hover .danger,
  .session-list li:focus-within .danger,
  .session-list li.active .danger {
    opacity: 1;
  }
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
.create-box select {
  height: 36px;
}

.create-box button {
  height: 36px;
}

.chat {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  padding: 18px;
  overflow: hidden;
}

.chat-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.chat-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.chat-title h2 {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.messages {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-height: 0;
  overflow-y: auto;
  padding: 2px 8px 2px 2px;
  scrollbar-gutter: stable;
}

.messages > .empty-state {
  margin: auto;
  width: 100%;
}

.message {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 86%;
}

.message.user {
  align-self: flex-end;
  align-items: flex-end;
}

.avatar {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  font-size: 11px;
  font-weight: 700;
  border-radius: 999px;
}

.avatar.user {
  color: #fff;
  background: var(--primary);
}

.avatar.assistant {
  color: var(--primary);
  background: var(--surface-muted);
  border: 1px solid var(--primary-line);
}

.bubble {
  padding: 11px 15px;
  border-radius: 14px;
}

.message.assistant .bubble {
  color: var(--text-soft);
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}

.message.user .bubble {
  color: #fff;
  background: var(--primary);
  border: 1px solid var(--primary);
  border-bottom-right-radius: 4px;
  box-shadow: 0 6px 16px -12px rgba(63, 58, 140, 0.9);
}

.message.user .bubble p {
  color: #fff;
}

.bubble > p,
.text {
  margin: 0;
  font-size: 14.5px;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
}

.message.assistant .bubble .muted {
  color: var(--muted);
}

.refs {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--border-strong);
}

.ref-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--primary);
}

.ref {
  padding: 8px 10px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.ref-meta {
  font-size: 11px;
  color: var(--muted);
}

.ref p {
  margin: 4px 0 0;
  font-size: 13px;
  line-height: 1.65;
  color: var(--text-soft);
}

.composer {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.composer textarea {
  flex: 1;
  min-height: 84px;
  background: var(--surface-muted);
}

.composer textarea:focus {
  background: var(--surface);
}

.composer button {
  flex: none;
  height: 44px;
  min-width: 96px;
}

@media (max-width: 1040px) {
  .layout {
    display: flex;
    flex-direction: column;
    flex: none;
    gap: 16px;
  }

  .sidebar {
    flex: none;
  }

  .session-list {
    flex: none;
    max-height: 240px;
  }

  .chat {
    min-height: 64vh;
  }

  .messages {
    max-height: 58vh;
  }
}

@media (max-width: 640px) {
  .card {
    padding: 18px;
  }

  .message {
    max-width: 94%;
  }

  .composer {
    flex-direction: column;
    align-items: stretch;
  }

  .composer button {
    width: 100%;
  }
}
</style>
