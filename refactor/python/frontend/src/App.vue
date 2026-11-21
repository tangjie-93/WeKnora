<template>
    <WorkbenchLayout>
        <RouterView />
    </WorkbenchLayout>
</template>

<script setup lang="ts">
import { RouterView } from 'vue-router';
import WorkbenchLayout from './layouts/WorkbenchLayout.vue';
</script>
