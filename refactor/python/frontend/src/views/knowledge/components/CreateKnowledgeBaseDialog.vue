<template>
    <el-dialog :model-value="modelValue" class="create-knowledge-base-dialog" title="创建空知识库" width="min(520px, calc(100vw - 24px))" @update:model-value="updateVisibility" @open="focusName">
        <el-alert title="只创建空文档知识库，模型未配置、向量引擎不可用；暂不支持上传或问答。" type="info" :closable="false" show-icon />
        <el-form class="create-knowledge-base-dialog__form" label-position="top" @submit.prevent="handleSubmit">
            <el-form-item label="名称" for="knowledge-base-name" :error="nameError" required>
                <el-input id="knowledge-base-name" v-model="name" autocomplete="off" :disabled="isSubmitting || isLocallySubmitting" aria-describedby="knowledge-base-name-help" />
                <small id="knowledge-base-name-help">去除两端空白后 {{ nameLength }} / 255 个字符，内部空白保留。</small>
            </el-form-item>
            <el-form-item label="描述" for="knowledge-base-description" :error="descriptionError">
                <el-input id="knowledge-base-description" v-model="description" type="textarea" :rows="4" :disabled="isSubmitting || isLocallySubmitting" aria-describedby="knowledge-base-description-help" />
                <small id="knowledge-base-description-help">{{ descriptionLength }} / 4000 个字符，描述原样保存。</small>
            </el-form-item>
            <el-alert v-if="submitError" :title="submitError" type="warning" :closable="false" show-icon />
            <p class="create-knowledge-base-dialog__notice">关闭只停止接收或隐藏页面，不保证撤销服务端创建。结果未确认时，请先刷新列表核对，不要重复提交。</p>
            <div class="create-knowledge-base-dialog__actions">
                <el-button @click="updateVisibility(false)">{{ isSubmitting || isLocallySubmitting ? '关闭' : '取消' }}</el-button>
                <el-button native-type="submit" type="primary" :loading="isSubmitting || isLocallySubmitting" :disabled="!canCreate || isSubmitting || isLocallySubmitting">创建知识库</el-button>
            </div>
        </el-form>
    </el-dialog>
</template>

<script setup lang="ts">
import type { CreateKnowledgeBaseDialogEmits, CreateKnowledgeBaseDialogProps } from '../../../types/knowledge-bases';
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';

const props = defineProps<CreateKnowledgeBaseDialogProps>();
const emit = defineEmits<CreateKnowledgeBaseDialogEmits>();
const name = ref('');
const description = ref('');
const hasValidated = ref(false);
const isLocallySubmitting = ref(false);
let draftGeneration = 0;
let isMounted = true;
// Go strings.TrimSpace 使用 Unicode White Space，不含 JavaScript trim 会删除的 FEFF。
const GO_EDGE_WHITESPACE = /^\p{White_Space}+|\p{White_Space}+$/gu;
const normalizedName = computed(() => name.value.replace(GO_EDGE_WHITESPACE, ''));
const nameLength = computed(() => Array.from(normalizedName.value).length);
const descriptionLength = computed(() => Array.from(description.value).length);
const nameError = computed(() => !hasValidated.value ? '' : !normalizedName.value ? '名称去除两端空白后不能为空。' : nameLength.value > 255 ? '名称不能超过 255 个字符。' : '');
const descriptionError = computed(() => hasValidated.value && descriptionLength.value > 4000 ? '描述不能超过 4000 个字符。' : '');

/** 同步弹窗显隐；关闭不表示服务端回滚。@param visible 目标可见状态。 */
function updateVisibility(visible: boolean): void {
    emit('update:modelValue', visible);
}

/** 弹窗打开后聚焦名称输入；关闭与卸载后不夺取焦点。 */
async function focusName(): Promise<void> {
    await nextTick();
    if (isMounted && props.modelValue) document.getElementById('knowledge-base-name')?.focus();
}

/** 点击和回车共用同步互斥入口；成功关闭，失败保留输入，迟到结果不修改新草稿。 */
async function handleSubmit(): Promise<void> {
    if (isLocallySubmitting.value || props.isSubmitting || !props.canCreate) return;
    hasValidated.value = true;
    if (nameError.value || descriptionError.value) return;
    isLocallySubmitting.value = true;
    const generation = draftGeneration;
    try {
        const isCreated = await props.submit({ name: normalizedName.value, description: description.value });
        if (isMounted && generation === draftGeneration && isCreated) updateVisibility(false);
    } finally {
        if (isMounted && generation === draftGeneration) isLocallySubmitting.value = false;
    }
}

watch(() => props.modelValue, visible => {
    if (visible) return;
    draftGeneration += 1;
    name.value = '';
    description.value = '';
    hasValidated.value = false;
    isLocallySubmitting.value = false;
}, { flush: 'sync' });
onBeforeUnmount(() => { isMounted = false; draftGeneration += 1; });
</script>

<style scoped lang="less">
.create-knowledge-base-dialog {
    &__form { margin-top: 16px; }
    &__form small { color: var(--el-text-color-secondary); line-height: 1.5; overflow-wrap: anywhere; }
    &__notice { margin: 12px 0; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.6; overflow-wrap: anywhere; }
    &__actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
    &__actions .el-button + .el-button { margin-left: 0; }
}
</style>
