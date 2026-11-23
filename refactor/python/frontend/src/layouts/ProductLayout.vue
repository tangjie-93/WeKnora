<template>
    <el-container class="product-layout" @keydown.esc="closeMenu">
        <a class="skip-link" href="#product-content" @click.prevent="focusMainContent">跳至主要内容</a>
        <el-aside class="product-layout__aside" width="232px">
            <div class="product-layout__brand"><AppBrand /></div>
            <div class="product-layout__nav-label">主导航</div>
            <el-menu :default-active="activeMenu" class="product-layout__menu" @select="navigate">
                <el-menu-item index="/account">
                    <span class="product-layout__menu-icon" aria-hidden="true">⌂</span>
                    <span>账户与空间</span>
                </el-menu-item>
                <el-menu-item index="/workbench/health">
                    <span class="product-layout__menu-icon" aria-hidden="true">◈</span>
                    <span>服务检测</span>
                </el-menu-item>
                <el-menu-item index="/workbench/progress">
                    <span class="product-layout__menu-icon" aria-hidden="true">▤</span>
                    <span>开发进度</span>
                </el-menu-item>
            </el-menu>
            <div class="product-layout__aside-footer">WeKnora<br><span>Personal workspace</span></div>
        </el-aside>
        <el-container class="product-layout__workspace">
            <el-header class="product-layout__header" height="56px">
                <span>{{ route.path.startsWith('/workbench') ? '辅助工具 / 工作台' : '个人 / 账户与空间' }}</span>
                <div class="product-layout__header-actions">
                    <el-text truncated>{{ account?.user.username || '正在确认账户' }}</el-text>
                    <el-button plain size="small" :loading="isLoggingOut" @click="signOut">退出登录</el-button>
                </div>
            </el-header>
            <el-main id="product-content" ref="mainContent" class="product-layout__main" tabindex="-1">
                <el-scrollbar class="product-layout__scrollbar">
                    <div class="product-layout__content"><RouterView /></div>
                </el-scrollbar>
            </el-main>
        </el-container>
    </el-container>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { RouterView, useRoute, useRouter } from 'vue-router';
import AppBrand from '../components/layout/AppBrand.vue';
import { useCurrentAccount, useSession } from '../hooks/useSession';

const route = useRoute();
const router = useRouter();
const { account } = useCurrentAccount();
const { signOut, isLoggingOut } = useSession();
const mainContent = ref<HTMLElement | null>(null);
const activeMenu = computed(() => route.path.startsWith('/workbench/progress') ? '/workbench/progress' : route.path.startsWith('/workbench') ? '/workbench/health' : '/account');

/** 将键盘焦点移至独立滚动的主内容区域。 */
function focusMainContent(): void {
    mainContent.value?.focus();
}

/** 根据菜单项切换页面，并维持当前会话与布局。 */
async function navigate(path: string): Promise<void> {
    await router.push(path);
}

/** 保留 Escape 键处理入口，布局没有额外弹层时不改变页面状态。 */
function closeMenu(): void {
    return;
}
</script>

<style scoped lang="less">
.product-layout {
    height: 100dvh;
    overflow: hidden;

    &__aside {
        display: flex;
        flex-direction: column;
        padding: 16px 12px;
        overflow: hidden;
        border-right: 1px solid var(--el-border-color-light);
        background: var(--el-bg-color);
    }

    &__brand {
        display: flex;
        align-items: center;
        min-height: 40px;
        padding: 0 8px;
        margin-bottom: 26px;
    }

    &__nav-label {
        padding: 0 12px 8px;
        color: var(--el-text-color-secondary);
        font-size: 11px;
        font-weight: 600;
        letter-spacing: .08em;
        text-transform: uppercase;
    }

    &__menu {
        border-right: 0;
        background: transparent;

        & :deep(.el-menu-item) {
            height: 42px;
            margin: 3px 0;
            border-radius: 8px;
            color: var(--el-text-color-secondary);
            font-size: 13px;

            &:hover { background: var(--el-fill-color-light); }
            &.is-active { background: var(--el-color-primary-light-9); color: var(--el-color-primary); font-weight: 600; }
        }
    }

    &__menu-icon {
        display: inline-grid;
        width: 24px;
        margin-right: 2px;
        place-items: center;
        color: currentColor;
        font-size: 16px;
        font-weight: 700;
    }

    &__aside-footer {
        margin-top: auto;
        padding: 12px;
        color: var(--el-text-color-secondary);
        font-size: 11px;
        line-height: 1.6;

        & span { color: var(--el-text-color-placeholder); font-size: 10px; }
    }

    &__workspace {
        min-width: 0;
    }

    &__header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding: 0 18px;
        border-bottom: 1px solid var(--el-border-color-light);
        background: var(--el-bg-color);
        color: var(--el-text-color-secondary);
        font-size: 13px;
    }

    &__header-actions {
        display: flex;
        align-items: center;
        min-width: 0;
        gap: 8px;
    }

    &__main {
        height: calc(100dvh - 56px);
        padding: 0;
        overflow: hidden;
        background: var(--el-fill-color-extra-light);
    }

    &__scrollbar {
        height: 100%;
    }

    &__content {
        max-width: 1180px;
        padding: 18px;
        margin: 0 auto;
    }

    @media (max-width: 767px) {
        &__aside {
            display: none;
        }

        &__header {
            padding: 0 12px;
        }

        &__content {
            padding: 12px;
        }

        &__header-actions .el-text {
            display: none;
        }

        &__aside-footer {
            display: none;
        }
    }
}
</style>
