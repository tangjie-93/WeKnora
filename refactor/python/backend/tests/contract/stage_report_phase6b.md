# 阶段验收报告 · phase6b

- 阶段：**Phase 6B 知识组织：Wiki 页面树 / 版本回滚 / 图谱**
- 执行时间：2026-10-30 00:13:38
- 结果：**18/18 通过**

| # | 步骤 | 结果 | 详情 |
|---|---|---|---|
| 1 | phase6b 阶段测试用例已编写 | ✅ | tests/e2e/test_wiki_api.py |
| 2 | ruff 静态检查 | ✅ | All checks passed |
| 3 | pytest 自动化测试 | ✅ | 81 passed, 2 skipped in 134.69s (0:02:14) |
| 4 | 创建 Wiki 知识库 | ✅ | 62169f18-4137-447f-bce2-6a074001f401 |
| 5 | 创建带内链的页面 | ✅ | 4 pages |
| 6 | 页面反向链接维护 | ✅ | in_links=2 |
| 7 | 更新推进版本号 | ✅ | version=2 |
| 8 | 版本快照列表 | ✅ | revisions=1 |
| 9 | 回滚到历史版本 | ✅ | reverted to v1 -> v3 |
| 10 | 文件夹创建与页面移动 | ✅ | nebula -> 归档 |
| 11 | 含页面的文件夹禁止删除 | ✅ | folder with page cannot delete |
| 12 | 图谱节点与边 | ✅ | nodes=4, edges=4 |
| 13 | Wiki 统计 | ✅ | total_pages=4 |
| 14 | 非 Wiki 库拒绝访问 | ✅ | non-wiki kb rejected |
| 15 | 重复 slug 返回 409 | ✅ | duplicate slug 409 |
| 16 | 过期版本写返回 409 | ✅ | stale version 409 |
| 17 | 未认证访问返回 401 | ✅ | 401 |
| 18 | 数据库落盘校验 | ✅ | wiki_pages=4 |
