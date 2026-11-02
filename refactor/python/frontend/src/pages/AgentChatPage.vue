<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, ApiError, streamChat } from '../api'
import type { AgentItem, KnowledgeBase, Reference } from '../api'

interface ToolStep {
  name: string
  arguments: Record<string, unknown>
  output?: string
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  references: Reference[]
  toolSteps: ToolStep[]
  done: boolean
}

const agents = ref<AgentItem[]>([])
const kbs = ref<KnowledgeBase[]>([])
const agentId = ref('')
const kbId = ref('')
const messages = ref<ChatMessage[]>([])
const input = ref('')
const sending = ref(false)
const error = ref('')

let localId = 0
const nextId = () => `local-${++localId}`

const selectedAgent = computed(() => agents.value.find((item) => item.id === agentId.value))

function fail(err: unknown) {
  error.value = err instanceof ApiError ? err.message : '请求失败，请检查后端是否启动'
}

async function loadAgents() {
  try {
    agents.value = await api.listAgents()
    if (!agentId.value) agentId.value = agents.value[0]?.id || ''
  } catch (err) {
    fail(err)
  }
}

async function loadKbs() {
  try {
    kbs.value = await api.listKnowledgeBases()
  } catch (err) {
    fail(err)
  }
}

function handleEvent(event: { response_type: string; data?: Record<string, unknown> }, assistant: ChatMessage) {
  const payload = event.data || {}
  if (event.response_type === 'answer') {
    const delta = String(payload.content ?? '')
    if (delta) assistant.content += delta
  } else if (event.response_type === 'tool_call') {
    assistant.toolSteps.push({
      name: String(payload.name ?? ''),
      arguments: (payload.arguments ?? {}) as Record<string, unknown>,
    })
  } else if (event.response_type === 'tool_result') {
    const last = assistant.toolSteps[assistant.toolSteps.length - 1]
    if (last) last.output = String(payload.content ?? '')
  } else if (event.response_type === 'complete') {
    assistant.done = true
  }
}

async function send() {
  const query = input.value.trim()
  if (!query || sending.value) return
  if (!agentId.value) {
    error.value = '请先选择智能体'
    return
  }
  sending.value = true
  error.value = ''
  input.value = ''

  messages.value.push({ id: nextId(), role: 'user', content: query, references: [], toolSteps: [], done: true })
  const assistant = { id: nextId(), role: 'assistant' as const, content: '', references: [], toolSteps: [], done: false }
  messages.value.push(assistant)

  try {
    // 复用现有会话管理：先确保存在一个会话（无会话时用固定会话 id 走 agent-chat）
    const session = await api.createSession('Agent 对话', kbId.value)
    await streamChat(session.id, query, (event) => handleEvent(event, assistant), undefined, agentId.value)
  } catch (err) {
    fail(err)
    assistant.done = true
  } finally {
    sending.value = false
  }
}

onMounted(async () => {
  await loadAgents()
  await loadKbs()
})
</script>

<template>
  <div class="agent-chat">
    <section class="card panel">
      <header class="panel-head">
        <div>
          <span class="eyebrow">Agent 对话</span>
          <h2>{{ selectedAgent ? selectedAgent.name : '智能体' }}</h2>
        </div>
      </header>

      <div class="toolbar">
        <select v-model="agentId" aria-label="智能体">
          <option v-for="agent in agents" :key="agent.id" :value="agent.id">
            {{ agent.is_builtin ? `${agent.name}（内置）` : agent.name }}
          </option>
        </select>
        <select v-model="kbId" aria-label="知识库">
          <option value="">不绑定知识库</option>
          <option v-for="kb in kbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
        </select>
      </div>

      <p v-if="error" class="error" role="alert">{{ error }}</p>

      <div v-if="messages.length" class="messages">
        <div v-for="message in messages" :key="message.id" class="msg" :class="message.role">
          <div class="bubble">
            <p class="content">{{ message.content || (message.role === 'assistant' && !message.done ? '思考中…' : '') }}</p>
            <div v-if="message.toolSteps.length" class="tool-steps">
              <details v-for="(step, index) in message.toolSteps" :key="index" class="tool-step">
                <summary>{{ step.name }}</summary>
                <pre class="tool-out">{{ step.output || JSON.stringify(step.arguments, null, 2) }}</pre>
              </details>
            </div>
          </div>
        </div>
      </div>

      <div class="input-row">
        <textarea
          v-model="input"
          rows="2"
          placeholder="输入问题，Agent 会调用检索工具回答"
          @keydown.enter.exact.prevent="send"
        />
        <button :disabled="sending || !input.trim()" @click="send">
          {{ sending ? '运行中…' : '发送' }}
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.agent-chat {
  display: block;
}

.panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.panel-head h2 {
  margin-top: 2px;
}

.toolbar {
  display: grid;
  grid-template-columns: 220px 220px;
  gap: 10px;
}

.toolbar select {
  height: 38px;
}

.messages {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 200px;
}

.msg {
  display: flex;
}

.msg.user {
  justify-content: flex-end;
}

.msg.assistant {
  justify-content: flex-start;
}

.bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 12px;
  background: var(--surface-muted);
  border: 1px solid var(--border);
}

.msg.user .bubble {
  background: var(--primary-soft);
  border-color: var(--primary-line);
}

.content {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.6;
}

.tool-steps {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tool-step summary {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--primary);
  cursor: pointer;
}

.tool-out {
  margin: 6px 0 0;
  padding: 8px;
  font-family: var(--font-mono);
  font-size: 12px;
  background: var(--surface);
  border-radius: 6px;
  overflow: auto;
  white-space: pre-wrap;
}

.input-row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.input-row textarea {
  flex: 1;
  resize: vertical;
  min-height: 48px;
}
</style>
