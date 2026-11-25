<template>
    <AuthFormCard title="创建你的账户" description="注册将创建账户、个人空间和所有者成员关系。">
        <el-alert v-if="session.pendingLogout" title="请先完成待确认的服务端退出。" type="warning" :closable="false" show-icon />
        <el-alert v-if="formError" :title="formError" type="error" :closable="false" show-icon />
        <el-form label-position="top" @submit.prevent="handleSubmit">
            <el-form-item label="用户名" :error="fieldErrors.username"><el-input v-model="username" autocomplete="username" maxlength="50" :disabled="isSubmitting || !!session.pendingLogout" /></el-form-item>
            <el-form-item label="邮箱" :error="fieldErrors.email"><el-input v-model="email" type="email" autocomplete="email" maxlength="255" placeholder="you@example.com" :disabled="isSubmitting || !!session.pendingLogout" /></el-form-item>
            <el-form-item label="密码" :error="fieldErrors.password"><el-input v-model="password" type="password" autocomplete="new-password" show-password :disabled="isSubmitting || !!session.pendingLogout" /><div class="register-page__hint">8–32 个字符，至少含一个英文字母和数字。</div></el-form-item>
            <el-form-item label="确认密码" :error="fieldErrors.confirmation"><el-input v-model="confirmation" type="password" autocomplete="new-password" show-password :disabled="isSubmitting || !!session.pendingLogout" /></el-form-item>
            <el-button native-type="submit" type="primary" :loading="isSubmitting" :disabled="!!session.pendingLogout">创建账户</el-button>
        </el-form>
        <template #footer>已有账户？ <RouterLink to="/login">返回登录</RouterLink></template>
    </AuthFormCard>
</template>

<script setup lang="ts">
import { onUnmounted, reactive, ref } from 'vue';
import { RouterLink, useRouter } from 'vue-router';
import AuthFormCard from '../../components/layout/AuthFormCard.vue';
import { registerAccount } from '../../api/auth';
import { ApiError, errorMessage } from '../../api/client';
import { registrationNotice } from '../../hooks/useSession';
import { useSessionStore } from '../../stores/session';

const router = useRouter();
const session = useSessionStore();
const username = ref('');
const email = ref('');
const password = ref('');
const confirmation = ref('');
const isSubmitting = ref(false);
const formError = ref('');
const fieldErrors = reactive({ username: '', email: '', password: '', confirmation: '' });
const controller = new AbortController();

/** 校验注册输入但不改写标识或密码，后端仍为最终校验方。 */
function validateFields(): boolean {
    fieldErrors.username = [...username.value].length < 2 || [...username.value].length > 50 || username.value !== username.value.trim() || /[\p{Cc}\p{Cf}]/u.test(username.value) ? '请输入 2–50 个字符，不含首尾空白或控制字符。' : '';
    fieldErrors.email = email.value !== email.value.trim() || /[\p{Cc}\p{Cf}]/u.test(email.value) ? '邮箱不能含首尾空白或控制字符。' : '';
    const length = [...password.value].length;
    fieldErrors.password = length < 8 || length > 32 || !/[A-Za-z]/.test(password.value) || !/[0-9]/.test(password.value) || new TextEncoder().encode(password.value).length > 72 ? '密码需满足下方全部规则。' : '';
    fieldErrors.confirmation = confirmation.value !== password.value ? '两次输入的密码不一致。' : '';
    return !Object.values(fieldErrors).some(Boolean);
}

/** 创建账户；成功后仅保留邮箱提示并跳转登录，失败保留安全错误提示。 */
async function handleSubmit(): Promise<void> {
    if (isSubmitting.value || session.pendingLogout) return;
    formError.value = '';
    if (!validateFields()) { formError.value = '请修正标记的字段后再提交。'; return; }
    isSubmitting.value = true;
    try {
        await registerAccount({ username: username.value, email: email.value, password: password.value }, controller.signal);
        if (controller.signal.aborted) return;
        registrationNotice.value = { email: email.value, message: '注册成功，个人空间已创建。请登录以查看你的账户与空间。' };
        password.value = '';
        confirmation.value = '';
        await router.replace('/login');
    } catch (error) {
        if (!(error instanceof ApiError && error.kind === 'cancelled')) formError.value = errorMessage(error);
    } finally {
        isSubmitting.value = false;
    }
}

onUnmounted(() => { controller.abort(); password.value = ''; confirmation.value = ''; });
</script>

<style scoped lang="less">
.register-page__hint {
    margin-top: 4px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
    line-height: 1.4;
}
</style>
