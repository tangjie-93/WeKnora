# 真实大模型全链路验收报告

- 生成时间：2026-10-30 13:38:55
- 验收库：`data/real_e2e.db`
- 结果：**6/6 通过**
- 总耗时：26.2s

## 模型清单

| 类型 | 模型 | base_url |
|---|---|---|
| deepseek-chat | deepseek-chat @ https://api.deepseek.com/v1 |
| chatgpt | gpt-6 @ https://nimabo.io/v1 |

## 步骤明细

| # | 步骤 | 结果 | 耗时 | 详情 |
|---|---|---|---|---|
| 1 | 健康检查 | 通过 | 0.0s | http://127.0.0.1:60146 |
| 2 | 注册登录 | 通过 | 0.3s | tenant=1 |
| 3 | 创建真实模型 | 通过 | 0.1s | deepseek-chat=c9ef2642、chatgpt=040578ec |
| 4 | 模型连通性 | 通过 | 9.2s | deepseek-chat:pong，chatgpt:pong |
| 5 | DeepSeek SSE 问答 | 通过 | 1.3s | 1247ms，22 事件，答：根据提供的资料，我无法回答 Nebula 默认端口是多少，因为资料中没有相关信息 |
| 6 | ChatGPT SSE 问答 | 通过 | 5.5s | 5465ms，答：我是 WeKnora 知识库助手，会根据提供的资料回答问题，并在资料不足时明确说 |
