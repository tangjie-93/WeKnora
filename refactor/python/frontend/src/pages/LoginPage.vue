<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, ApiError } from '../api'

const router = useRouter()
const mode = ref<'login' | 'register'>('login')
const account = ref('')
const username = ref('')
const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
const notice = ref('')

async function submit() {
  if (loading.value) return
  error.value = ''
  notice.value = ''
  loading.value = true
  try {
    if (mode.value === 'register') {
      await api.register(username.value.trim(), email.value.trim(), password.value)
      notice.value = '注册成功，正在登录…'
    }
    const loginName = mode.value === 'register' ? email.value : account.value
    await api.login(loginName.trim(), password.value)
    await router.push({ name: 'knowledge' })
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '请求失败，请检查后端是否启动'
  } finally {
    loading.value = false
  }
}

function setMode(next: 'login' | 'register') {
  if (mode.value === next) return
  mode.value = next
  error.value = ''
  notice.value = ''
}
</script>

<template>
  <div class="login card">
    <div class="brand-head">
      <span class="mark" aria-hidden="true">W</span>
      <div>
        <h1>WeKnora</h1>
        <p class="muted">企业知识库 · 检索增强问答</p>
      </div>
    </div>

    <div class="switch" role="tablist" aria-label="登录或注册">
      <button
        type="button"
        role="tab"
        :aria-selected="mode === 'login'"
        :class="{ active: mode === 'login' }"
        @click="setMode('login')"
      >
        登录
      </button>
      <button
        type="button"
        role="tab"
        :aria-selected="mode === 'register'"
        :class="{ active: mode === 'register' }"
        @click="setMode('register')"
      >
        注册
      </button>
    </div>

    <form class="stack" @submit.prevent="submit">
      <div v-if="mode === 'login'" class="field">
        <label for="account">用户名或邮箱</label>
        <input
          id="account"
          v-model="account"
          type="text"
          autocomplete="username"
          placeholder="alice 或 alice@example.com"
        />
      </div>
      <template v-else>
        <div class="field">
          <label for="username">用户名</label>
          <input id="username" v-model="username" autocomplete="username" placeholder="alice" />
        </div>
        <div class="field">
          <label for="email">邮箱</label>
          <input
            id="email"
            v-model="email"
            type="email"
            autocomplete="email"
            placeholder="alice@example.com"
          />
        </div>
      </template>
      <div class="field">
        <label for="password">密码</label>
        <input
          id="password"
          v-model="password"
          type="password"
          :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
          placeholder="至少 8 位，包含字母和数字"
        />
      </div>

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="notice" class="success" role="status">{{ notice }}</p>

      <button type="submit" :disabled="loading">
        {{ loading ? '处理中…' : mode === 'login' ? '登录' : '注册并登录' }}
      </button>
    </form>

    <p class="foot muted">
      {{ mode === 'login' ? '还没有账号？' : '已有账号？' }}
      <button type="button" class="link" @click="setMode(mode === 'login' ? 'register' : 'login')">
        {{ mode === 'login' ? '创建一个' : '直接登录' }}
      </button>
    </p>
  </div>
</template>

<style scoped>
.login {
  width: min(420px, 100%);
  padding: 36px;
  border-radius: 20px;
  box-shadow: var(--shadow-md);
}

.brand-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 26px;
}

.mark {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  font-size: 17px;
  font-weight: 700;
  color: #fff;
  background: var(--primary);
  border-radius: 12px;
}

h1 {
  font-size: 22px;
  letter-spacing: -0.02em;
}

.switch {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  padding: 4px;
  margin-bottom: 22px;
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: 12px;
}

.switch button {
  height: 34px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-soft);
  background: transparent;
  border-radius: 8px;
}

.switch button:hover:not(:disabled) {
  color: var(--primary);
  background: transparent;
}

.switch button.active {
  color: var(--primary);
  background: var(--surface);
  box-shadow: var(--shadow-xs);
}

form {
  gap: 16px;
}

form button {
  height: 44px;
  margin-top: 4px;
}

.foot {
  margin-top: 20px;
  text-align: center;
}

.link {
  height: auto;
  padding: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--primary);
  background: none;
}

.link:hover:not(:disabled) {
  color: var(--primary-strong);
  background: none;
  text-decoration: underline;
}

@media (max-width: 480px) {
  .login {
    padding: 28px 24px;
  }
}
</style>
