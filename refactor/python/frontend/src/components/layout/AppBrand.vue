<template>
    <RouterLink class="app-brand" to="/account">
        <span class="app-brand__mark" aria-hidden="true">W</span>
        <span>WeKnora</span>
    </RouterLink>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router';
</script>

<style scoped lang="less">
.app-brand {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: var(--el-text-color-primary);
    font-size: 18px;
    font-weight: 700;
    text-decoration: none;

    &__mark {
        display: grid;
        width: 30px;
        height: 30px;
        place-items: center;
        border-radius: 8px;
        background: var(--el-color-primary);
        color: #fff;
        font-size: 17px;
    }
}
</style>
