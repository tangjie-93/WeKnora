<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { api } from './api'
import { auth, clearAuth } from './auth'

const router = useRouter()
const loggedIn = computed(() => Boolean(auth.token))
const initial = computed(() => (auth.userName || '访客').trim().slice(0, 1).toUpperCase())

async function handleLogout() {
  try {
    await api.logout()
  } catch {
    clearAuth()
  }
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="app-shell">
    <header v-if="loggedIn" class="topbar">
      <div class="topbar-inner">
        <RouterLink class="brand" to="/knowledge">
          <span class="mark" aria-hidden="true">W</span>
          <span class="wordmark">WeKnora<span class="tag">Python</span></span>
        </RouterLink>

        <nav class="nav">
          <RouterLink to="/knowledge">知识库</RouterLink>
          <RouterLink to="/faq">FAQ</RouterLink>
          <RouterLink to="/wiki">Wiki</RouterLink>
          <RouterLink to="/retrieval">检索</RouterLink>
          <RouterLink to="/agents">Agent</RouterLink>
          <RouterLink to="/agent-chat">Agent 对话</RouterLink>
          <RouterLink to="/chat">对话</RouterLink>
          <RouterLink to="/models">模型</RouterLink>
        </nav>

        <div class="identity">
          <span class="avatar" aria-hidden="true">{{ initial }}</span>
          <span class="who">
            <strong>{{ auth.userName || '未登录' }}</strong>
            <small>{{ auth.tenantName || '—' }}</small>
          </span>
          <button class="ghost small" @click="handleLogout">退出</button>
        </div>
      </div>
    </header>

    <main :class="loggedIn ? 'content' : 'content plain'">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 30;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}

.topbar-inner {
  display: flex;
  align-items: center;
  gap: 28px;
  width: 100%;
  height: 64px;
  margin: 0 auto;
  padding: 0 28px;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--text);
}

.mark {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  font-size: 14px;
  font-weight: 700;
  color: #fff;
  background: var(--primary);
  border-radius: 9px;
  box-shadow: var(--shadow-xs);
}

.wordmark {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.wordmark .tag {
  margin-left: 6px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}

.nav {
  display: flex;
  align-items: center;
  gap: 4px;
}

.nav a {
  display: inline-flex;
  align-items: center;
  height: 34px;
  padding: 0 14px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-soft);
  border-radius: 999px;
  transition: background 0.16s ease, color 0.16s ease;
}

.nav a:hover {
  color: var(--primary);
  background: var(--surface-muted);
}

.nav a.router-link-active {
  font-weight: 600;
  color: var(--primary);
  background: var(--primary-soft);
}

.identity {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: auto;
}

.avatar {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  font-size: 13px;
  font-weight: 700;
  color: var(--primary);
  background: var(--primary-soft);
  border: 1px solid var(--primary-line);
  border-radius: 999px;
}

.who {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}

.who strong {
  font-size: 13px;
  font-weight: 600;
}

.who small {
  font-size: 11px;
  color: var(--muted);
}

.content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  width: 100%;
  margin: 0 auto;
  padding: 28px 28px 32px;
  overflow-y: auto;
}

.content.plain {
  display: flex;
  align-items: center;
  justify-content: center;
  max-width: none;
  padding: 48px 24px;
  background:
    radial-gradient(ellipse 55% 45% at 18% 8%, #ece8f7 0%, transparent 70%),
    radial-gradient(ellipse 50% 45% at 88% 92%, #f5eade 0%, transparent 70%),
    var(--bg);
}

@media (max-width: 960px) {
  .topbar-inner {
    gap: 16px;
    padding: 0 18px;
  }

  .who {
    display: none;
  }

  .content {
    padding: 20px 18px 24px;
  }
}

@media (max-width: 640px) {
  .topbar-inner {
    gap: 10px;
  }

  .wordmark .tag {
    display: none;
  }

  .nav {
    overflow-x: auto;
    gap: 2px;
  }

  .nav a {
    padding: 0 10px;
    font-size: 13px;
  }

  .avatar {
    display: none;
  }
}
</style>
