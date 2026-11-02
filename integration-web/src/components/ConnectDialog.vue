<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { resolveCredentials } from '../embed'
import type { KnowledgeBase } from '../types/api'

const emit = defineEmits<{ connected: [kbId: string] }>()

const kbs = ref<KnowledgeBase[]>([])
const selected = ref('')
const loading = ref(true)
const connecting = ref(false)
const error = ref('')

async function init() {
  loading.value = true
  error.value = ''
  try {
    const { account, password } = resolveCredentials()
    if (!account || !password) {
      throw new Error('未提供账号密码，请通过 ?account= 与 ?password= 参数传入')
    }
    // 代码内自动登录，界面不展示账号密码表单
    await api.login(account, password)
    kbs.value = await api.listKbs()
    if (!kbs.value.length) {
      error.value = '当前账号下还没有知识库'
    } else if (!selected.value) {
      selected.value = kbs.value[0].id
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '连接失败，请检查后端地址'
  } finally {
    loading.value = false
  }
}

function connect() {
  if (!selected.value || connecting.value) return
  connecting.value = true
  emit('connected', selected.value)
}

onMounted(init)
</script>

<template>
  <div class="dialog-mask">
    <section class="dialog-card" role="dialog" aria-modal="true" aria-label="连接知识库">
      <header class="dialog-head">
        <span class="brand-badge" aria-hidden="true">W</span>
        <div>
          <h2>连接知识库</h2>
          <p>选择要接入的知识库，进入后即可检索与问答</p>
        </div>
      </header>

      <div v-if="loading" class="state">
        <span class="spinner" aria-hidden="true"></span>
        <p>正在连接…</p>
      </div>

      <div v-else-if="error && !kbs.length" class="state">
        <p class="error" role="alert">{{ error }}</p>
        <button class="primary" type="button" @click="init">重试</button>
      </div>

      <template v-else>
        <div class="kb-list" role="radiogroup" aria-label="选择知识库">
          <label
            v-for="kb in kbs"
            :key="kb.id"
            class="kb-item"
            :class="{ active: kb.id === selected }"
          >
            <input v-model="selected" type="radio" name="kb" :value="kb.id" class="kb-radio" />
            <span class="kb-body">
              <span class="kb-name">{{ kb.name }}</span>
              <span class="kb-desc">{{ kb.description || '无描述' }}</span>
            </span>
          </label>
        </div>

        <p v-if="error" class="error" role="alert">{{ error }}</p>

        <button
          class="primary block"
          type="button"
          :disabled="!selected || connecting"
          @click="connect"
        >
          {{ connecting ? '连接中…' : '连接' }}
        </button>
      </template>
    </section>
  </div>
</template>

<style scoped lang="less">
.dialog-mask {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.5);
}

.dialog-card {
  width: min(420px, 100%);
  padding: 32px;
  background: var(--surface);
  border-radius: 16px;
  box-shadow: 0 24px 60px -20px rgba(3, 40, 20, 0.55);
}

.dialog-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.brand-badge {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  flex: none;
  font-size: 18px;
  font-weight: 700;
  color: var(--brand-active);
  background: #fff;
  border: 1px solid var(--brand-line);
  border-radius: 12px;
}

.dialog-head h2 {
  font-size: 20px;
  letter-spacing: -0.01em;
}

.dialog-head p {
  margin-top: 2px;
  font-size: 12.5px;
  color: var(--text-3);
}

.state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 24px 0;
  color: var(--text-2);
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border);
  border-top-color: var(--brand);
  border-radius: 999px;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.kb-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 300px;
  overflow-y: auto;
  margin-bottom: 16px;
}

.kb-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  cursor: pointer;
  border: 1px solid var(--border);
  border-radius: 10px;
  transition: background 0.16s ease, border-color 0.16s ease;
}

.kb-item:hover {
  background: var(--surface-2);
}

.kb-item.active {
  background: var(--brand-weak);
  border-color: var(--brand-line);
}

.kb-radio {
  flex: none;
  accent-color: var(--brand);
}

.kb-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.kb-name {
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kb-desc {
  font-size: 12px;
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.error {
  margin: 0 0 12px;
  padding: 9px 12px;
  font-size: 12.5px;
  color: var(--danger);
  background: var(--danger-weak);
  border: 1px solid var(--danger-line);
  border-radius: var(--radius-sm);
}

.block {
  width: 100%;
  height: 40px;
  font-size: 14px;
}

@media (max-width: 480px) {
  .dialog-card {
    padding: 24px 20px;
  }
}
</style>
