<template>
  <section class="knowledge-page">
    <AppPageHeader
      eyebrow="个人空间"
      title="知识库"
      description="创建空文档知识库，查看当前验证空间的真实记录。"
    >
      <template #actions
        ><el-button
          type="primary"
          :disabled="!canCreate || isSubmitting"
          @click="openCreateDialog"
          >创建知识库</el-button
        ></template
      >
    </AppPageHeader>
    <el-alert
      class="knowledge-page__notice"
      title="本轮仅开放空库创建与列表：模型未配置、向量引擎不可用，不支持上传、检索或问答。每个空间最多 100 个非临时、未删除知识库，超出范围会明确报错。"
      type="info"
      :closable="false"
      show-icon
    />
    <el-skeleton
      v-if="accountQuery.isFetching.value || accountQuery.isPending.value"
      :rows="4"
      animated
      aria-label="正在验证账户与空间"
    />
    <div v-else-if="!account" class="knowledge-page__recovery" role="status">
      <el-alert
        title="暂时无法验证当前账户与空间"
        :description="errorMessage(accountQuery.error.value)"
        type="error"
        :closable="false"
        show-icon
      />
      <div class="knowledge-page__actions">
        <el-button @click="accountQuery.refetch()">重试账户验证</el-button
        ><el-button :loading="isLoggingOut" @click="signOut"
          >退出登录</el-button
        >
      </div>
    </div>
    <template v-else>
      <div class="knowledge-page__toolbar">
        <p>
          当前空间：<strong>{{ account.tenant.name }}</strong
          ><span>空间 ID：{{ account.tenant.id }}</span>
        </p>
        <div class="knowledge-page__actions">
          <label for="knowledge-base-creator">创建者</label
          ><el-select
            id="knowledge-base-creator"
            v-model="creator"
            aria-label="按创建者筛选"
            :disabled="isSubmitting"
            ><el-option label="全部" value="all" /><el-option
              label="我创建的"
              value="mine" /><el-option
              label="其他成员创建的"
              value="others" /></el-select
          ><el-button :loading="listQuery.isFetching.value" @click="retryList"
            >刷新列表</el-button
          >
        </div>
      </div>
      <el-alert
        v-if="submitError && !isDialogOpen"
        class="knowledge-page__notice"
        :title="submitError"
        type="warning"
        :closable="false"
        show-icon
      />
      <p v-if="!canCreate" class="knowledge-page__permission">
        当前成员没有创建权限，仅可查看知识库。创建达到容量上限会明确报错；结果未确认时，请选择“全部”并刷新列表核对。
      </p>
      <el-skeleton
        v-if="listQuery.isPending.value || listQuery.isFetching.value"
        :rows="5"
        animated
        aria-label="正在读取知识库"
      />
      <div
        v-else-if="listQuery.isError.value"
        class="knowledge-page__recovery"
        role="status"
      >
        <el-alert
          title="知识库列表读取失败，不代表空间为空"
          :description="listQuery.error.value?.message"
          type="error"
          :closable="false"
          show-icon
        /><el-button @click="retryList">重试列表</el-button>
      </div>
      <el-card v-else-if="items.length === 0" shadow="never"
        ><el-empty
          :description="
            creator === 'all' ? '当前空间还没有知识库' : '当前筛选下没有知识库'
          "
          ><el-button
            type="primary"
            :disabled="!canCreate || isSubmitting"
            @click="openCreateDialog"
            >创建空知识库</el-button
          ></el-empty
        ></el-card
      >
      <div v-else class="knowledge-page__list" aria-label="当前空间知识库列表">
        <el-card
          v-for="item in items"
          :key="item.id"
          class="knowledge-page__item"
          shadow="never"
        >
          <div class="knowledge-page__item-heading">
            <h2>{{ item.name }}</h2>
            <el-tag type="info" size="small">文档知识库</el-tag>
          </div>
          <p class="knowledge-page__description">
            {{ item.description || "未填写描述" }}
          </p>
          <div class="knowledge-page__tags">
            <el-tag type="warning" effect="plain">{{
              !item.embedding_model_id && !item.summary_model_id
                ? "模型未配置"
                : "存在模型配置，当前不可用"
            }}</el-tag
            ><el-tag type="info" effect="plain">向量引擎不可用</el-tag>
          </div>
          <dl class="knowledge-page__metadata">
            <div>
              <dt>知识库 ID</dt>
              <dd>
                <code>{{ item.id }}</code>
              </dd>
            </div>
            <div>
              <dt>创建者</dt>
              <dd>{{ item.creator_name || item.creator_id || "未提供" }}</dd>
            </div>
            <div>
              <dt>创建时间</dt>
              <dd>{{ formatDate(item.created_at) }}</dd>
            </div>
            <div>
              <dt>更新时间</dt>
              <dd>{{ formatDate(item.updated_at) }}</dd>
            </div>
          </dl>
          <p class="knowledge-page__counts">
            文档 {{ item.knowledge_count }} · 分块 {{ item.chunk_count }} ·
            处理中 {{ item.processing_count }} · 共享记录
            {{ item.share_count }}（仅展示真实计数，不开放内容操作）
          </p>
        </el-card>
      </div>
      <CreateKnowledgeBaseDialog
        :key="dialogScope"
        v-model="isDialogOpen"
        :is-submitting="isSubmitting"
        :submit-error="submitError"
        :can-create="canCreate"
        :submit="submit"
      />
    </template>
    <el-collapse class="knowledge-page__explanation"
      ><el-collapse-item title="本次操作如何工作？" name="call-chain"
        ><p>以下是代码调用关系说明，不是实时运行追踪。</p>
        <KnowledgeOperationFlow /></el-collapse-item
      ></el-collapse
    >
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import AppPageHeader from "../../components/layout/AppPageHeader.vue";
import CreateKnowledgeBaseDialog from "./components/CreateKnowledgeBaseDialog.vue";
import KnowledgeOperationFlow from "./components/KnowledgeOperationFlow.vue";
import { errorMessage } from "../../api/client";
import { useKnowledgeBases } from "../../hooks/useKnowledgeBases";
import { useSession } from "../../hooks/useSession";

const {
  account,
  accountQuery,
  listQuery,
  items,
  canCreate,
  creator,
  submit,
  isSubmitting,
  submitError,
  retryList,
  clearDraftState,
} = useKnowledgeBases();
const { signOut, isLoggingOut } = useSession();
const isDialogOpen = ref(false);
const dialogScope = computed(() =>
  account.value
    ? `${account.value.user.id}:${account.value.tenant.id}:${creator.value}`
    : "no-verified-account",
);

/** 打开新草稿；清理旧提示但不解除数据层未确认写入保护。 */
function openCreateDialog(): void {
  if (!canCreate.value || isSubmitting.value) return;
  clearDraftState();
  isDialogOpen.value = true;
}

/** 将真实服务端时间转为本地显示，不用当前时间填补缺失值。@param value 服务端时间。@returns 可读时间或原始值。 */
function formatDate(value: string | null): string {
  if (!value) return "未提供";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("zh-CN", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
}

watch(
  dialogScope,
  () => {
    isDialogOpen.value = false;
  },
  { flush: "sync" },
);
watch(
  isDialogOpen,
  (visible) => {
    if (!visible && isSubmitting.value) clearDraftState();
  },
  { flush: "sync" },
);
</script>

<style scoped lang="less">
.knowledge-page {
  container-type: inline-size;
  min-width: 0;
  overflow-wrap: anywhere;

  &__notice,
  &__toolbar,
  &__permission {
    margin-bottom: 12px;
  }
  &__toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  &__toolbar p {
    min-width: 0;
    margin: 0;
    font-size: 13px;
  }
  &__toolbar span {
    display: block;
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }
  &__actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }
  &__actions .el-select {
    width: 154px;
  }
  &__actions .el-button + .el-button {
    margin-left: 0;
  }
  &__recovery {
    display: grid;
    gap: 12px;
    justify-items: start;
  }
  &__recovery .el-alert {
    width: 100%;
  }
  &__permission {
    color: var(--el-text-color-secondary);
    font-size: 12px;
    line-height: 1.6;
  }
  &__list {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 12px;

    @container (min-width: 640px) {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    @container (min-width: 960px) {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    @container (min-width: 1280px) {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
  }
  &__item {
    min-width: 0;
  }
  &__item-heading {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    gap: 8px;
  }
  &__item-heading h2 {
    min-width: 0;
    margin: 0;
    color: var(--el-text-color-primary);
    font-size: 16px;
  }
  &__description {
    margin: 10px 0;
    white-space: pre-wrap;
    color: var(--el-text-color-regular);
    font-size: 13px;
    line-height: 1.6;
  }
  &__tags {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  &__metadata {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    margin: 14px 0;
    font-size: 12px;
  }
  &__metadata dt {
    margin-bottom: 4px;
    color: var(--el-text-color-secondary);
  }
  &__metadata dd {
    margin: 0;
  }
  &__counts {
    margin: 0;
    color: var(--el-text-color-secondary);
    font-size: 12px;
    line-height: 1.6;
  }
  &__explanation {
    margin-top: 16px;
    line-height: 1.7;
  }
  & :deep(.el-card__body) {
    padding: 16px;
  }
  & :deep(.el-alert__content) {
    min-width: 0;
  }
  & :deep(.el-alert__title) {
    overflow-wrap: anywhere;
  }

  @media (max-width: 767px) {
    & :deep(.app-page-header) {
      flex-direction: column;
    }
    &__toolbar {
      align-items: flex-start;
      flex-direction: column;
    }
    &__metadata {
      grid-template-columns: minmax(0, 1fr);
    }
  }
}
</style>
