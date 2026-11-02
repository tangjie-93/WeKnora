<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api, ApiError } from '../api'
import type { AgentItem, AgentToolCatalog, AgentToolInfo } from '../api'

const agents = ref<AgentItem[]>([])
const tools = ref<AgentToolCatalog | null>(null)
const selectedId = ref('')
const busy = ref(false)
const error = ref('')
const notice = ref('')

const editing = ref(false)
const form = reactive({
  name: '',
  description: '',
  avatar: '',
  agent_mode: 'quick-answer',
  system_prompt: '',
  temperature: 0.7,
  max_iterations: 10,
  kb_selection_mode: 'all',
  allowed_tools: [] as string[],
})

const selected = computed(() => agents.value.find((item) => item.id === selectedId.value))
const total = computed(() => agents.value.length)

const toolGroups = computed<[string, AgentToolInfo[]][]>(() => {
  const map = new Map<string, AgentToolInfo[]>()
  for (const tool of tools.value?.tools ?? []) {
    const bucket = map.get(tool.group) || []
    bucket.push(tool)
    map.set(tool.group, bucket)
  }
  return [...map.entries()]
})

const GROUP_LABELS: Record<string, string> = {
  base: '基础',
  rag: '检索',
  wiki_read: 'Wiki 读取',
  wiki_edit: 'Wiki 编辑',
  wiki_issue: 'Wiki 问题',
  data: '数据分析',
}

function fail(err: unknown) {
  error.value = err instanceof ApiError ? err.message : '请求失败，请检查后端是否启动'
}

async function loadAgents() {
  try {
    agents.value = await api.listAgents()
    if (!agents.value.some((item) => item.id === selectedId.value)) {
      selectedId.value = agents.value[0]?.id || ''
    }
  } catch (err) {
    fail(err)
  }
}

async function loadTools() {
  try {
    tools.value = await api.getAgentTools()
  } catch (err) {
    fail(err)
  }
}

function resetForm() {
  editing.value = false
  form.name = ''
  form.description = ''
  form.avatar = ''
  form.agent_mode = 'quick-answer'
  form.system_prompt = ''
  form.temperature = 0.7
  form.max_iterations = 10
  form.kb_selection_mode = 'all'
  form.allowed_tools = []
}

function selectAgent(id: string) {
  selectedId.value = id
  error.value = ''
  notice.value = ''
  const agent = agents.value.find((item) => item.id === id)
  if (!agent) return
  if (agent.is_builtin) {
    editing.value = false
    resetForm()
    return
  }
  editing.value = true
  form.name = agent.name
  form.description = agent.description
  form.avatar = agent.avatar
  form.agent_mode = agent.config.agent_mode || 'quick-answer'
  form.system_prompt = agent.config.system_prompt || ''
  form.temperature = agent.config.temperature ?? 0.7
  form.max_iterations = agent.config.max_iterations ?? 10
  form.kb_selection_mode = agent.config.kb_selection_mode || 'all'
  form.allowed_tools = [...(agent.config.allowed_tools ?? [])]
}

function newAgent() {
  selectedId.value = ''
  editing.value = false
  resetForm()
  error.value = ''
  notice.value = ''
}

async function saveAgent() {
  if (busy.value) return
  if (!form.name.trim()) {
    error.value = '智能体名称不能为空'
    return
  }
  busy.value = true
  error.value = ''
  notice.value = ''
  const config = {
    agent_mode: form.agent_mode,
    system_prompt: form.system_prompt,
    temperature: form.temperature,
    max_iterations: form.max_iterations,
    kb_selection_mode: form.kb_selection_mode,
    allowed_tools: form.allowed_tools,
  }
  try {
    if (editing.value && selectedId.value) {
      const agent = await api.updateAgent(selectedId.value, {
        name: form.name.trim(),
        description: form.description,
        avatar: form.avatar,
        config,
      })
      notice.value = `智能体「${agent.name}」已更新`
      selectedId.value = agent.id
    } else {
      const agent = await api.createAgent({
        name: form.name.trim(),
        description: form.description,
        avatar: form.avatar,
        config,
      })
      notice.value = `智能体「${agent.name}」已创建`
      selectedId.value = agent.id
    }
    await loadAgents()
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

async function removeAgent() {
  const agent = selected.value
  if (!agent || agent.is_builtin) return
  if (!window.confirm(`删除智能体「${agent.name}」？`)) return
  try {
    await api.deleteAgent(agent.id)
    notice.value = `已删除「${agent.name}」`
    resetForm()
    selectedId.value = ''
    await loadAgents()
  } catch (err) {
    fail(err)
  }
}

async function copyAgent(agent: AgentItem) {
  if (agent.is_builtin) return
  try {
    const copied = await api.copyAgent(agent.id)
    notice.value = `已复制为「${copied.name}」`
    await loadAgents()
    selectAgent(copied.id)
  } catch (err) {
    fail(err)
  }
}

function toggleTool(name: string) {
  form.allowed_tools = form.allowed_tools.includes(name)
    ? form.allowed_tools.filter((item) => item !== name)
    : [...form.allowed_tools, name]
}

function toolLabel(name: string): string {
  return tools.value?.tools.find((tool) => tool.name === name)?.label || name
}

function toolDesc(name: string): string {
  return tools.value?.tools.find((tool) => tool.name === name)?.description || ''
}

function toolDanger(name: string): boolean {
  return Boolean(tools.value?.tools.find((tool) => tool.name === name)?.danger)
}

function modeLabel(mode: string | undefined): string {
  return mode === 'smart-reasoning' ? '智能推理（ReAct）' : '快速问答（RAG）'
}

function kbLabel(mode: string | undefined): string {
  if (mode === 'selected') return '指定知识库'
  if (mode === 'none') return '不关联知识库'
  return '全部知识库'
}

onMounted(async () => {
  await loadAgents()
  await loadTools()
})
</script>

<template>
  <div class="agents-page">
    <section class="card panel">
      <header class="panel-head">
        <div>
          <span class="eyebrow">Agent</span>
          <h2>智能体</h2>
        </div>
        <span class="counter">{{ total }}</span>
      </header>

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="notice" class="success" role="status">{{ notice }}</p>

      <div class="body-grid">
        <aside class="list">
          <button class="new-btn" @click="newAgent">+ 新建智能体</button>
          <div v-if="!agents.length" class="empty-state">
            <p class="muted">暂无智能体。</p>
          </div>
          <div v-else class="agent-list">
            <button
              v-for="agent in agents"
              :key="agent.id"
              class="agent-item"
              :class="{ active: selectedId === agent.id }"
              @click="selectAgent(agent.id)"
            >
              <div class="agent-row">
                <span class="agent-avatar" aria-hidden="true">{{ agent.avatar || agent.name.slice(0, 1) }}</span>
                <div class="agent-meta">
                  <span class="agent-name">
                    {{ agent.name }}
                    <span v-if="agent.is_builtin" class="badge plain">内置</span>
                  </span>
                  <span class="muted small">{{ agent.description || '无描述' }}</span>
                </div>
              </div>
            </button>
          </div>
        </aside>

        <div class="detail">
          <div v-if="selected && selected.is_builtin" class="builtin-view">
            <header class="detail-head">
              <span class="agent-avatar lg" aria-hidden="true">
                {{ selected.avatar || selected.name.slice(0, 1) }}
              </span>
              <div class="detail-title">
                <h3>{{ selected.name }}</h3>
                <p class="muted">{{ selected.description }}</p>
              </div>
              <span class="badge plain">内置</span>
            </header>

            <div class="kv">
              <div class="kv-card">
                <span class="kv-key">运行模式</span>
                <span class="kv-val">{{ modeLabel(selected.config.agent_mode) }}</span>
              </div>
              <div class="kv-card">
                <span class="kv-key">温度</span>
                <span class="kv-val">{{ selected.config.temperature ?? 0.7 }}</span>
              </div>
              <div class="kv-card">
                <span class="kv-key">最大迭代</span>
                <span class="kv-val">{{ selected.config.max_iterations ?? 10 }}</span>
              </div>
              <div class="kv-card">
                <span class="kv-key">知识库范围</span>
                <span class="kv-val">{{ kbLabel(selected.config.kb_selection_mode) }}</span>
              </div>
            </div>

            <section class="detail-block grow">
              <h4>允许工具（{{ (selected.config.allowed_tools || []).length }}）</h4>
              <div v-if="(selected.config.allowed_tools || []).length" class="tool-list">
                <article v-for="name in selected.config.allowed_tools || []" :key="name" class="tool-row">
                  <div class="tool-row-head">
                    <span class="tool-row-name">{{ toolLabel(name) }}</span>
                    <span v-if="toolDanger(name)" class="badge fail">写操作</span>
                  </div>
                  <p v-if="toolDesc(name)" class="tool-row-desc">{{ toolDesc(name) }}</p>
                </article>
              </div>
              <p v-else class="muted">未配置工具。</p>
            </section>

            <section class="detail-block">
              <h4>系统提示词</h4>
              <pre v-if="selected.config.system_prompt" class="prompt">{{ selected.config.system_prompt }}</pre>
              <p v-else class="muted">使用默认提示词，未自定义。</p>
            </section>

            <p class="hint muted">内置智能体为空间级默认配置，不可编辑或删除。</p>
          </div>

          <form v-else class="editor" @submit.prevent="saveAgent">
            <div class="editor-body">
              <div class="editor-head">
                <h3>{{ editing ? '编辑智能体' : '新建智能体' }}</h3>
                <p class="muted">{{ editing ? '修改配置后点击保存生效' : '填写基础信息与运行参数' }}</p>
              </div>

              <div class="row two">
                <div class="field">
                  <label for="agent-name">名称 <span class="req">*</span></label>
                  <input id="agent-name" v-model="form.name" placeholder="例如：研究助手" />
                </div>
                <div class="field">
                  <label for="agent-avatar">头像（emoji）</label>
                  <input id="agent-avatar" v-model="form.avatar" placeholder="例如：🤖" />
                </div>
              </div>
              <div class="field">
                <label for="agent-desc">描述</label>
                <input id="agent-desc" v-model="form.description" placeholder="这个智能体用来做什么" />
              </div>
              <div class="row three">
                <div class="field">
                  <label for="agent-mode">运行模式</label>
                  <select id="agent-mode" v-model="form.agent_mode">
                    <option value="quick-answer">快速问答（RAG）</option>
                    <option value="smart-reasoning">智能推理（ReAct）</option>
                  </select>
                </div>
                <div class="field">
                  <label for="agent-temp">温度</label>
                  <input id="agent-temp" v-model.number="form.temperature" type="number" min="0" max="2" step="0.1" />
                </div>
                <div class="field">
                  <label for="agent-iter">最大迭代</label>
                  <input id="agent-iter" v-model.number="form.max_iterations" type="number" min="1" />
                </div>
              </div>
              <div class="field">
                <label for="agent-kb">知识库范围</label>
                <select id="agent-kb" v-model="form.kb_selection_mode">
                  <option value="all">全部知识库</option>
                  <option value="selected">指定知识库</option>
                  <option value="none">不关联知识库</option>
                </select>
              </div>
              <div class="field">
                <label for="agent-prompt">系统提示词</label>
                <textarea id="agent-prompt" v-model="form.system_prompt" rows="5" placeholder="可选，自定义系统提示词" />
              </div>

              <div class="field">
                <label>允许的工具</label>
                <div class="tool-groups">
                  <div v-for="(group, index) in toolGroups" :key="index" class="tool-group">
                    <div class="tool-group-head">{{ GROUP_LABELS[group[0]] || group[0] }}</div>
                    <div class="tool-grid">
                      <label v-for="tool in group[1]" :key="tool.name" class="checkbox tool-check">
                        <input
                          type="checkbox"
                          :checked="form.allowed_tools.includes(tool.name)"
                          @change="toggleTool(tool.name)"
                        />
                        <span>{{ tool.label }}</span>
                        <span v-if="tool.danger" class="badge fail">写</span>
                      </label>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="editor-foot">
              <button type="submit" :disabled="busy">
                {{ busy ? '保存中…' : editing ? '保存修改' : '创建智能体' }}
              </button>
              <button v-if="editing" type="button" class="ghost" @click="newAgent">取消</button>
              <button v-if="editing" type="button" class="ghost" @click="copyAgent(selected!)">复制</button>
              <button v-if="editing" type="button" class="danger" @click="removeAgent">删除</button>
            </div>
          </form>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.agents-page {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px;
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

.body-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 288px minmax(0, 1fr);
  gap: 18px;
  min-width: 0;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  padding-right: 2px;
}

.new-btn {
  height: 36px;
  font-weight: 600;
  flex: none;
}

.agent-list {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
  padding: 1px 4px 1px 1px;
}

.agent-item {
  display: block;
  width: 100%;
  height: auto;
  min-height: 56px;
  padding: 10px 12px;
  text-align: left;
  white-space: normal;
  color: var(--text);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.agent-item:hover {
  background: var(--surface-muted);
}

.agent-item.active {
  background: var(--primary-soft);
  border-color: var(--primary-line);
}

.agent-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.agent-avatar {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  font-size: 16px;
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.agent-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.agent-meta .muted {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.detail {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
  min-height: 0;
  flex: 1;
}

.builtin-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
}

.detail-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.detail-title {
  flex: 1;
  min-width: 0;
}

.detail-title h3 {
  margin-bottom: 2px;
}

.detail-title .muted {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-avatar.lg {
  width: 44px;
  height: 44px;
  font-size: 22px;
}

.kv {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(168px, 1fr));
  gap: 10px;
}

.kv-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.kv-key {
  font-size: 12px;
  color: var(--muted);
}

.kv-val {
  font-size: 14px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.detail-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.detail-block.grow {
  flex: 1;
  min-height: 140px;
  overflow: hidden;
}

.tool-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-right: 4px;
}

.tool-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 9px 11px;
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.tool-row-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tool-row-name {
  font-size: 13px;
  font-weight: 600;
}

.tool-row-desc {
  font-size: 12px;
  color: var(--muted);
  line-height: 1.5;
}

.detail-block h4 {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--muted);
  text-transform: uppercase;
}

.prompt {
  margin: 0;
  padding: 12px;
  max-height: 180px;
  overflow-y: auto;
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.65;
  color: var(--text-soft);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.hint {
  padding-top: 2px;
}

.editor {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.editor-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow-y: auto;
  padding: 0 6px 16px 0;
}

.editor-head h3 {
  margin-bottom: 2px;
}

.editor-head .muted {
  font-size: 13px;
}

.editor-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: none;
  padding-top: 12px;
  border-top: 1px solid var(--border);
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

.tool-groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tool-group {
  padding: 10px 12px;
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.tool-group-head {
  margin-bottom: 8px;
  font-size: 11px;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.tool-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
  gap: 6px 12px;
}

.tool-check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.small {
  font-size: 12px;
}

.badge.fail {
  color: var(--danger);
  background: var(--danger-soft, #fdeaea);
}

@media (max-width: 1040px) {
  .body-grid {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(0, 1fr);
    gap: 12px;
  }

  .list {
    padding-right: 0;
  }

  .agent-list {
    flex: none;
    max-height: 148px;
  }

  .tool-grid {
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  }
}
</style>
