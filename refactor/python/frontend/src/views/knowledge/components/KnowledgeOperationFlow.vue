<template>
  <section class="knowledge-operation-flow" aria-label="创建空知识库的代码流程">
    <p class="knowledge-operation-flow__overview">
      确认身份 → 填写并校验 → 发送创建请求 → 服务端校验与保存 → 重新查询 → 展示当前筛选列表。
    </p>
    <p class="knowledge-operation-flow__guard">
      <strong>全程保护，而非最后一步：</strong>会话、用户、空间或筛选变化，以及离开页面时，取消或废弃旧请求，忽略晚到的成功、错误和清理回调，避免旧结果影响新页面。
      <code>captureOwner()</code> / <code>owns()</code> / <code>ownsSubmission()</code>
    </p>
    <p class="knowledge-operation-flow__guide">沿编号与向下箭头阅读成功路径；每步旁的“异常”说明失败条件和恢复方法。</p>
    <ol class="knowledge-operation-flow__steps" aria-label="创建成功路径，共六步">
      <li class="knowledge-operation-flow__step">
        <article class="knowledge-operation-flow__node">
          <p class="knowledge-operation-flow__lane">浏览器 · 账户与空间</p>
          <h3><span class="knowledge-operation-flow__number">1</span>确认我是谁、在哪个空间</h3>
          <p>共享已验证的真实账户，确认用户有效且属于当前空间，再读取列表并判断创建权限。</p>
          <p class="knowledge-operation-flow__code"><code>useKnowledgeBases()</code> → <code>useCurrentAccount()</code></p>
        </article>
        <aside class="knowledge-operation-flow__branch" aria-label="身份与权限异常">
          <strong>异常 · 账户无法验证 / 无创建权限</strong>
          <p>身份验证失败时不请求业务列表，重试账户验证或退出登录。无创建权限的成员仍可查看列表，但创建按钮禁用。</p>
        </aside>
        <p class="knowledge-operation-flow__connector"><span aria-hidden="true">↓</span> 有创建权限，点击“创建知识库”</p>
      </li>
      <li class="knowledge-operation-flow__step">
        <article class="knowledge-operation-flow__node">
          <p class="knowledge-operation-flow__lane">浏览器 · 表单</p>
          <h3><span class="knowledge-operation-flow__number">2</span>填写名称与描述，点击创建</h3>
          <p>名称去除两端空白后必填，最多 255 个字符；描述最多 4000 个字符，原样保存。提交期间锁定按钮，避免连点重复创建。</p>
          <p class="knowledge-operation-flow__code"><code>CreateKnowledgeBaseDialog</code> → <code>handleSubmit()</code></p>
        </article>
        <aside class="knowledge-operation-flow__branch" aria-label="表单校验异常">
          <strong>异常 · 输入不符合要求</strong>
          <p>表单提示具体原因，保留输入，不发送创建请求；修改后再提交。</p>
        </aside>
        <p class="knowledge-operation-flow__connector"><span aria-hidden="true">↓</span> 校验通过，携带名称与描述</p>
      </li>
      <li class="knowledge-operation-flow__step">
        <article class="knowledge-operation-flow__node">
          <p class="knowledge-operation-flow__lane">浏览器 → 后端 · 一次写入</p>
          <h3><span class="knowledge-operation-flow__number">3</span>只发送一次创建请求</h3>
          <p>请求层携带认证信息，发送名称与描述；创建请求不会自动重试。</p>
          <p class="knowledge-operation-flow__code"><code>submit()</code> → <code>createKnowledgeBase()</code> → <code>requestJson()</code></p>
          <p class="knowledge-operation-flow__code"><code>POST /api/v1/knowledge-bases</code></p>
        </article>
        <aside class="knowledge-operation-flow__branch" aria-label="创建结果未确认">
          <strong>异常 · 断网、超时或创建结果未确认</strong>
          <p>服务端错误、会话或响应归属异常也可能需要核对。不能判断为“没有创建”：先选“全部”并成功刷新列表核对，不直接重复提交。关闭弹窗不代表服务端回滚。</p>
        </aside>
        <p class="knowledge-operation-flow__connector"><span aria-hidden="true">↓</span> 后端收到请求，接口参数校验通过</p>
      </li>
      <li class="knowledge-operation-flow__step">
        <article class="knowledge-operation-flow__node">
          <p class="knowledge-operation-flow__lane">后端 · 数据库事务</p>
          <h3><span class="knowledge-operation-flow__number">4</span>再次校验权限，再保存知识库</h3>
          <p>同一连接内校验令牌、用户及空间成员 → 检查创建角色、100 条容量与存储配置 → 写入 → 读回 → 提交事务。</p>
          <p class="knowledge-operation-flow__code"><code>create_knowledge_base()</code> → <code>KnowledgeBaseService.create()</code></p>
          <p class="knowledge-operation-flow__note">提交成功后尽力追加 <code>kb.created</code> 审计；审计失败不逆转创建成功。</p>
        </article>
        <aside class="knowledge-operation-flow__branch" aria-label="服务端校验与事务异常">
          <strong>异常 · 校验不通过 / 提交前出错</strong>
          <p>权限、容量或存储配置不满足要求时不继续创建；未提交的事务回滚。前端显示安全错误提示；结果未确认时仍先核对全部列表。</p>
        </aside>
        <p class="knowledge-operation-flow__connector"><span aria-hidden="true">↓</span> 后端返回 201，前端校验响应格式及用户、空间归属</p>
      </li>
      <li class="knowledge-operation-flow__step">
        <article class="knowledge-operation-flow__node">
          <p class="knowledge-operation-flow__lane">浏览器 → 后端 · 重读真实数据</p>
          <h3><span class="knowledge-operation-flow__number">5</span>确认创建后，重新查询列表</h3>
          <p>先取消并废弃旧列表请求，再按当前创建者筛选查询；不把表单内容直接拼成一张新卡片。</p>
          <p class="knowledge-operation-flow__code"><code>refreshOwnedList()</code> → <code>fetchKnowledgeBases()</code></p>
          <p class="knowledge-operation-flow__code"><code>GET /api/v1/knowledge-bases?creator=…</code></p>
        </article>
        <aside class="knowledge-operation-flow__branch" aria-label="已创建但列表刷新失败">
          <strong>异常 · 已创建，但列表刷新未成功</strong>
          <p>创建成功仍然成立，弹窗关闭后保留独立提示。只重试列表，不要再次创建，避免重复记录。</p>
        </aside>
        <p class="knowledge-operation-flow__connector"><span aria-hidden="true">↓</span> 列表读取成功，且当前身份、空间与筛选仍匹配</p>
      </li>
      <li class="knowledge-operation-flow__step">
        <article class="knowledge-operation-flow__node knowledge-operation-flow__node--end">
          <p class="knowledge-operation-flow__lane">浏览器 · 页面展示</p>
          <h3><span class="knowledge-operation-flow__number">6</span>关闭弹窗，展示当前筛选的真实列表</h3>
          <p>只展示当前归属的服务端记录。筛选为“其他成员创建的”时，新建条目不会出现；切换到“全部”或“我创建的”查看。</p>
          <p class="knowledge-operation-flow__code"><code>handleSubmit()</code> → <code>updateVisibility(false)</code> · <code>useKnowledgeBases()</code></p>
        </article>
        <aside class="knowledge-operation-flow__branch" aria-label="筛选下没有记录">
          <strong>分支 · 当前筛选下没有记录</strong>
          <p>显示当前筛选的空态，不代表空间为空，也不代表创建失败。切换筛选或刷新列表核对。</p>
        </aside>
      </li>
    </ol>
    <p class="knowledge-operation-flow__short-path">
      <strong>只进入页面查看列表，有一条更短的路：</strong>确认身份 → <code>fetchKnowledgeBases()</code> → 服务端校验空间与查询权限 → 读取记录及计数 → 展示列表。读取失败就是读取失败，不冒充“空间为空”。
    </p>
    <details class="knowledge-operation-flow__references">
      <summary>对照代码：每一步在哪里实现？</summary>
      <p>前端路径相对于 <code>python/frontend/</code>，后端路径相对于 <code>python/backend/</code>。</p>
      <dl>
        <dt>1 · 身份确认与全程归属保护</dt>
        <dd><code>src/hooks/useSession.ts</code>、<code>src/hooks/useKnowledgeBases.ts</code>：共享账户，隔离会话、用户、空间与筛选，拒绝旧回调。</dd>
        <dt>2 · 表单校验与关闭弹窗</dt>
        <dd><code>src/views/knowledge/components/CreateKnowledgeBaseDialog.vue</code>：校验输入，互斥提交，确认创建后关闭弹窗。</dd>
        <dt>3 · 一次请求与响应校验</dt>
        <dd><code>src/hooks/useKnowledgeBases.ts</code>、<code>src/api/knowledge-bases.ts</code>、<code>src/api/client.ts</code>：发送请求，携带认证信息，校验合同及归属。</dd>
        <dt>4 · 服务端校验、持久化与审计</dt>
        <dd><code>app/api/routes/knowledge_bases.py</code>、<code>app/services/knowledge_bases.py</code>、<code>app/repositories/knowledge_bases.py</code>：参数、权限、事务与提交后审计。</dd>
        <dt>5–6 · 重新查询与展示</dt>
        <dd><code>src/hooks/useKnowledgeBases.ts</code>、<code>src/views/knowledge/index.vue</code>：取消旧查询，重读列表，按当前筛选展示真实记录。</dd>
      </dl>
    </details>
  </section>
</template>

<style scoped lang="less">
.knowledge-operation-flow {
  min-width: 0;
  color: var(--el-text-color-regular);
  overflow-wrap: anywhere;
  font-size: 13px;
  line-height: 1.7;

  p { margin: 0; }
  code {
    padding: 2px 4px;
    border-radius: var(--el-border-radius-small);
    background: var(--el-fill-color-light);
    font-size: 12px;
    white-space: normal;
  }
  &__overview { padding: 12px 0; color: var(--el-text-color-primary); }
  &__guard,
  &__short-path {
    padding: 12px;
    border: 1px solid var(--el-border-color);
    border-radius: var(--el-border-radius-base);
    background: var(--el-fill-color-light);
  }
  &__guide { padding: 14px 0; color: var(--el-text-color-secondary); }
  &__steps { margin: 0; padding: 0; list-style: none; }
  &__step {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 0.6fr);
    column-gap: 28px;
    align-items: center;
    margin-bottom: 12px;
  }
  &__node {
    min-width: 0;
    padding: 14px;
    border: 1px solid var(--el-border-color);
    border-radius: var(--el-border-radius-base);
    background: var(--el-bg-color);

    h3 { display: flex; align-items: baseline; gap: 8px; margin: 6px 0; font-size: 15px; color: var(--el-text-color-primary); }
    &--end { border: 2px solid var(--el-color-primary); }
  }
  &__lane { color: var(--el-text-color-secondary); font-size: 12px; }
  &__number {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    width: 24px;
    height: 24px;
    border: 1px solid var(--el-border-color-darker);
    border-radius: 50%;
    font-size: 12px;
  }
  &__code { padding-top: 8px; }
  &__note { margin-top: 10px !important; padding-top: 8px; border-top: 1px solid var(--el-border-color-light); }
  &__branch {
    position: relative;
    min-width: 0;
    padding: 12px;
    border: 1px dashed var(--el-border-color-darker);
    border-radius: var(--el-border-radius-base);
    background: var(--el-fill-color-light);

    strong { display: block; margin-bottom: 4px; color: var(--el-text-color-primary); }
    &::before { content: "→"; position: absolute; left: -25px; top: calc(50% - 16px); color: var(--el-text-color-regular); font-size: 22px; }
  }
  &__connector {
    grid-column: 1;
    padding-top: 10px;
    text-align: center;
    font-size: 12px;

    span { margin-right: 6px; font-size: 22px; vertical-align: middle; }
  }
  &__references {
    margin-top: 16px;
    padding-top: 12px;
    border-top: 1px solid var(--el-border-color);

    summary {
      cursor: pointer;
      color: var(--el-text-color-primary);
      font-weight: 600;
      &:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 4px; }
    }
    p { margin-top: 10px; }
    dl { margin: 12px 0 0; }
    dt { margin-top: 12px; font-weight: 600; }
    dd { margin: 4px 0 0; }
  }
  @container (max-width: 760px) {
    &__step { grid-template-columns: minmax(0, 1fr); gap: 10px; }
    &__branch {
      margin-left: 24px;
      &::before { content: "↳"; top: 8px; }
    }
    &__connector { padding-top: 0; }
  }
}
</style>
