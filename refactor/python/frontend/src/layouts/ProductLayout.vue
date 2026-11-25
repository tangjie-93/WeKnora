<template>
    <el-container class="product-layout" @keydown.esc="closeMenu">
        <a class="skip-link" href="#product-content" @click.prevent="focusMainContent">跳至主要内容</a>
        <el-aside class="product-layout__aside" width="232px">
            <div class="product-layout__brand"><AppBrand /></div>
            <el-menu :default-active="activeMenu" class="product-layout__menu" @select="navigate">
                <el-menu-item index="/knowledge-bases">
                    <span class="product-layout__menu-icon" aria-hidden="true">▣</span>
                    <span>知识库</span>
                </el-menu-item>
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
                <div class="product-layout__header-title">
                    <el-button class="product-layout__mobile-toggle" aria-label="打开主导航" aria-controls="mobile-navigation" :aria-expanded="isMenuOpen" @click="isMenuOpen = true">菜单</el-button>
                    <span>{{ headerTitle }}</span>
                </div>
                <div class="product-layout__header-actions">
                    <el-text truncated>{{ account?.user.username || '正在确认账户' }}</el-text>
                    <el-button plain size="small" :loading="isLoggingOut" @click="signOut">退出登录</el-button>
                </div>
            </el-header>
            <el-main id="product-content" class="product-layout__main" tabindex="-1">
                <el-scrollbar class="product-layout__scrollbar">
                    <AppContent><RouterView /></AppContent>
                </el-scrollbar>
            </el-main>
        </el-container>
        <el-drawer v-model="isMenuOpen" title="主导航" direction="ltr" size="min(300px, 88vw)" @closed="restoreMenuFocus">
            <nav id="mobile-navigation" class="product-layout__mobile-nav" aria-label="主导航">
                <RouterLink v-for="item in navigationItems" :key="item.path" :to="item.path" :aria-current="activeMenu === item.path ? 'page' : undefined" @click="isMenuOpen = false">{{ item.label }}</RouterLink>
                <el-button plain :loading="isLoggingOut" @click="signOutFromMenu">退出登录</el-button>
            </nav>
        </el-drawer>
    </el-container>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router';
import AppBrand from '../components/layout/AppBrand.vue';
import AppContent from '../components/layout/AppContent.vue';
import { useCurrentAccount, useSession } from '../hooks/useSession';

const route = useRoute();
const router = useRouter();
const { account } = useCurrentAccount();
const { signOut, isLoggingOut } = useSession();
const isMenuOpen = ref(false);
const navigationItems = [
    { path: '/knowledge-bases', label: '知识库' },
    { path: '/account', label: '账户与空间' },
    { path: '/workbench/health', label: '服务检测' },
    { path: '/workbench/progress', label: '开发进度' },
];
const activeMenu = computed(() => route.path.startsWith('/knowledge-bases') ? '/knowledge-bases' : route.path.startsWith('/workbench/progress') ? '/workbench/progress' : route.path.startsWith('/workbench') ? '/workbench/health' : '/account');
const headerTitle = computed(() => activeMenu.value === '/knowledge-bases' ? '个人 / 知识库' : activeMenu.value === '/account' ? '个人 / 账户与空间' : activeMenu.value === '/workbench/progress' ? '辅助工具 / 开发进度' : '辅助工具 / 服务检测');

/** 将键盘焦点移至独立滚动的主内容区域。 */
function focusMainContent(): void {
    document.getElementById('product-content')?.focus();
}

/** 根据菜单项切换页面；成功关闭菜单，失败交由路由处理。@param path 目标路径。 */
async function navigate(path: string): Promise<void> {
    await router.push(path);
    closeMenu();
}

/** 关闭移动菜单；抽屉负责焦点圈定与 Escape 键关闭。 */
function closeMenu(): void {
    isMenuOpen.value = false;
}

/** 抽屉关闭后恢复菜单按钮焦点，避免键盘焦点落到隐藏内容。 */
function restoreMenuFocus(): void {
    document.querySelector<HTMLButtonElement>('.product-layout__mobile-toggle')?.focus();
}

/** 关闭移动菜单后执行真实退出；撤销结果及失败恢复由现有会话管理维护。 */
async function signOutFromMenu(): Promise<void> {
    closeMenu();
    await signOut();
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

    &__header-title {
        display: flex;
        align-items: center;
        min-width: 0;
        gap: 8px;
        overflow-wrap: anywhere;
    }

    &__mobile-toggle { display: none; }

    &__mobile-nav {
        display: grid;
        gap: 10px;

        & a {
            padding: 12px;
            border-radius: 8px;
            color: var(--el-text-color-primary);
            text-decoration: none;

            &[aria-current='page'] { color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
            &:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
        }
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

    @media (max-width: 767px) {
        &__aside {
            display: none;
        }

        &__mobile-toggle { display: inline-flex; }

        &__header {
            padding: 0 12px;
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
