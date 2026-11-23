<template>
    <AuthLayout>
        <el-card class="login-page" shadow="never">
            <AppPageHeader eyebrow="WELCOME BACK" title="欢迎回来" description="登录 WeKnora，进入你的个人空间。" />
            <el-alert v-if="registrationNotice" :title="registrationNotice.message" type="success" :closable="false" show-icon />
            <el-alert v-if="session.pendingLogout" title="服务端退出待确认，请先重试退出。" type="warning" :closable="false" show-icon />
            <el-alert v-if="session.storageError || formError" :title="session.storageError || formError" type="error" :closable="false" show-icon />
            <el-form class="login-page__form" label-position="top" @submit.prevent="handleSubmit">
                <el-form-item label="邮箱"><el-input v-model="email" type="email" autocomplete="email" placeholder="you@example.com" :disabled="isSubmitting || !!session.pendingLogout" /></el-form-item>
                <el-form-item label="密码"><el-input v-model="password" :type="isPasswordVisible ? 'text' : 'password'" autocomplete="current-password" show-password :disabled="isSubmitting || !!session.pendingLogout" /></el-form-item>
                <el-button native-type="submit" type="primary" :loading="isSubmitting" :disabled="!!session.pendingLogout">登录</el-button>
                <el-button v-if="session.pendingLogout" :loading="isLoggingOut" @click="retryPendingLogout">重试退出</el-button>
            </el-form>
            <el-divider />
            <el-text size="small">还没有账户？ <RouterLink to="/register">创建账户</RouterLink></el-text>
        </el-card>
    </AuthLayout>
</template>

<script setup lang="ts">
import { onUnmounted, ref } from 'vue';
import { RouterLink } from 'vue-router';
import AuthLayout from '../../components/layout/AuthLayout.vue';
import AppPageHeader from '../../components/layout/AppPageHeader.vue';
import { ApiError, errorMessage } from '../../api/client';
import { useSession } from '../../hooks/useSession';
import { useSessionStore } from '../../stores/session';

const session = useSessionStore();
const { signIn, retryPendingLogout, isLoggingOut, registrationNotice } = useSession();
const email = ref(registrationNotice.value?.email || '');
const password = ref('');
const isSubmitting = ref(false);
const isPasswordVisible = ref(false);
const formError = ref('');
const controller = new AbortController();

/** 提交真实凭据；成功进入账户页，失败保留安全提示并清理密码。 */
async function handleSubmit(): Promise<void> {
    if (isSubmitting.value || session.pendingLogout) return;
    formError.value = '';
    if ([...password.value].length < 6 || new TextEncoder().encode(password.value).length > 72) {
        formError.value = '密码至少 6 个字符，UTF-8 长度最多 72 字节。';
        return;
    }
    isSubmitting.value = true;
    try {
        await signIn({ email: email.value, password: password.value }, controller.signal);
    } catch (error) {
        if (!(error instanceof ApiError && error.kind === 'cancelled')) formError.value = errorMessage(error);
    } finally {
        password.value = '';
        isSubmitting.value = false;
    }
}

onUnmounted(() => { controller.abort(); password.value = ''; });
</script>

<style scoped lang="less">
.login-page {
    width: min(100%, 420px);

    & :deep(.el-card__body) { padding: 18px; }
    & :deep(.el-alert) { margin-bottom: 10px; }
    &__form { margin-top: 14px; }
    & :deep(.el-button + .el-button) { margin-left: 8px; }
}
</style>
