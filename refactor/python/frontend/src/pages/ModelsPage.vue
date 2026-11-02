<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ApiError } from '../api'
import type { ModelItem } from '../api'

const models = ref<ModelItem[]>([])
const testResults = ref<Record<string, string>>({})
const busy = ref(false)
const error = ref('')
const notice = ref('')

const name = ref('')
const displayName = ref('')
const type = ref('chat')
const baseUrl = ref('https://api.openai.com/v1')
const apiKey = ref('')
const dimension = ref(1536)
const isDefault = ref(true)

function fail(err: unknown) {
  error.value = err instanceof ApiError ? err.message : '请求失败，请检查后端是否启动'
}

async function load() {
  try {
    models.value = await api.listModels()
  } catch (err) {
    fail(err)
  }
}

async function createModel() {
  if (!name.value.trim() || !baseUrl.value.trim()) return
  busy.value = true
  error.value = ''
  notice.value = ''
  const parameters: Record<string, unknown> = {
    base_url: baseUrl.value.trim(),
    api_key: apiKey.value.trim(),
  }
  if (type.value === 'embedding') {
    parameters.embedding_parameters = { dimension: dimension.value }
  }
  try {
    const model = await api.createModel({
      name: name.value.trim(),
      display_name: displayName.value.trim() || name.value.trim(),
      type: type.value,
      is_default: isDefault.value,
      parameters,
    })
    notice.value = `模型「${model.display_name}」已创建`
    name.value = ''
    displayName.value = ''
    apiKey.value = ''
    await load()
  } catch (err) {
    fail(err)
  } finally {
    busy.value = false
  }
}

async function testModel(model: ModelItem) {
  testResults.value[model.id] = '测试中…'
  try {
    const result = await api.testModel(model.id)
    testResults.value[model.id] = result.ok
      ? `连通正常${result.reply ? `：${result.reply}` : ''}${
          result.dimension ? ` · 维度 ${result.dimension}` : ''
        }`
      : '连通失败'
  } catch (err) {
    testResults.value[model.id] =
      err instanceof ApiError ? `失败：${err.message}` : '测试失败'
  }
}

async function removeModel(model: ModelItem) {
  if (!window.confirm(`删除模型「${model.display_name}」？`)) return
  try {
    await api.deleteModel(model.id)
    notice.value = `已删除「${model.display_name}」`
    await load()
  } catch (err) {
    fail(err)
  }
}

onMounted(load)
</script>

<template>
  <div class="layout">
    <section class="card panel">
      <header class="panel-head">
        <div>
          <span class="eyebrow">模型</span>
          <h2>已接入模型</h2>
        </div>
        <span class="counter">{{ models.length }}</span>
      </header>

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="notice" class="success" role="status">{{ notice }}</p>

      <div v-if="models.length" class="table-wrap">
        <table class="model-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>类型</th>
              <th>默认</th>
              <th>状态</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="model in models" :key="model.id">
              <td>
                <div class="name-line">
                  <span class="model-name">{{ model.display_name }}</span>
                  <span
                    v-if="testResults[model.id]"
                    class="test-note"
                    :title="testResults[model.id]"
                  >
                    {{ testResults[model.id] }}
                  </span>
                </div>
                <div class="model-sub" :title="`${model.name} · ${model.parameters.base_url}`">
                  {{ model.name }} · {{ model.parameters.base_url }}
                </div>
              </td>
              <td><span class="chip">{{ model.type }}</span></td>
              <td>
                <span v-if="model.is_default" class="badge ok">默认</span>
                <span v-else class="muted">—</span>
              </td>
              <td class="muted">{{ model.status }}</td>
              <td>
                <div class="actions">
                  <button class="ghost small" @click="testModel(model)">测试</button>
                  <button class="danger small" @click="removeModel(model)">删除</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty-state">
        <p class="empty-title">还没有配置模型</p>
        <p class="muted">在右侧添加对话或向量模型，之后即可创建知识库并开始问答。</p>
      </div>
    </section>

    <form class="card create-form" @submit.prevent="createModel">
      <span class="eyebrow">新增</span>
      <h2>新建模型</h2>
      <div class="stack form-body">
        <div class="field">
          <label for="model-name">标识名</label>
          <input id="model-name" v-model="name" placeholder="gpt-4o-mini" />
        </div>
        <div class="field">
          <label for="model-display">显示名</label>
          <input id="model-display" v-model="displayName" placeholder="可选" />
        </div>
        <div class="field">
          <label for="model-type">类型</label>
          <select id="model-type" v-model="type">
            <option value="chat">chat</option>
            <option value="embedding">embedding</option>
            <option value="rerank">rerank</option>
          </select>
        </div>
        <div class="field">
          <label for="model-url">Base URL</label>
          <input id="model-url" v-model="baseUrl" placeholder="https://api.openai.com/v1" />
        </div>
        <div class="field">
          <label for="model-key">API Key</label>
          <input id="model-key" v-model="apiKey" type="password" placeholder="sk-..." />
        </div>
        <div v-if="type === 'embedding'" class="field">
          <label for="model-dim">向量维度</label>
          <input id="model-dim" v-model.number="dimension" type="number" min="1" />
        </div>
        <label class="checkbox">
          <input v-model="isDefault" type="checkbox" />
          <span>设为该类型默认模型</span>
        </label>
        <button type="submit" :disabled="busy || !name.trim() || !baseUrl.trim()">
          {{ busy ? '保存中…' : '创建模型' }}
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 20px;
  align-items: start;
}

.panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
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

.model-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.model-table th {
  padding: 8px 12px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  text-align: left;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
}

.model-table td {
  padding: 12px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}

.model-table tbody tr:hover td {
  background: var(--surface-muted);
}

.model-table tbody tr:last-child td {
  border-bottom: none;
}

.name-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.model-name {
  flex: none;
  font-weight: 500;
}

.test-note {
  min-width: 0;
  max-width: 320px;
  padding: 1px 8px;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.6;
  color: var(--primary);
  text-overflow: ellipsis;
  white-space: nowrap;
  background: var(--primary-soft);
  border: 1px solid var(--primary-line);
  border-radius: 999px;
}

.model-sub {
  margin-top: 2px;
  overflow: hidden;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--muted);
  text-overflow: ellipsis;
  white-space: nowrap;
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
  gap: 8px;
  justify-content: flex-end;
  white-space: nowrap;
}

.create-form h2 {
  margin-top: 2px;
}

.form-body {
  margin-top: 16px;
  gap: 14px;
}

.checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-soft);
  cursor: pointer;
}

.form-body > button {
  height: 44px;
  margin-top: 4px;
}

@media (max-width: 1040px) {
  .layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .model-table {
    min-width: 620px;
  }
}
</style>
