# 阶段验收报告 · phase1

- 阶段：**Phase 1 基础设施与认证**
- 执行时间：2026-10-28 23:22:10
- 结果：**22/22 通过**

| # | 步骤 | 结果 | 详情 |
|---|---|---|---|
| 1 | phase1 阶段测试用例已编写 | ✅ | tests/e2e/test_auth_flow.py、tests/unit/test_security.py、tests/unit/test_password_policy.py |
| 2 | ruff 静态检查 | ✅ | All checks passed |
| 3 | pytest 自动化测试 | ✅ | 43 passed in 62.87s (0:01:02) |
| 4 | 读取认证配置 | ✅ | self_serve |
| 5 | 注册用户并自动建空间 | ✅ | user=03b8a8cf-33d9-4620-bc12-fe72644a8b9b tenant=1 |
| 6 | 重复注册被拒绝 | ✅ | email already exists |
| 7 | 弱密码被拒绝 | ✅ | password must be 8-32 characters and contain at least one letter and one number |
| 8 | 登录并签发双令牌 | ✅ | tenant=1 role=owner |
| 9 | 错误密码返回 401 | ✅ | Login failed |
| 10 | 不存在用户返回 401 | ✅ | 401 as expected |
| 11 | 令牌校验接口 | ✅ | valid=true |
| 12 | 当前用户信息 | ✅ | tenant=1 |
| 13 | 当前空间信息 | ✅ | alice |
| 14 | 刷新令牌并轮换 | ✅ | new access token valid |
| 15 | 刷新令牌可重复使用 | ✅ | second refresh ok |
| 16 | 非法刷新令牌返回 401 | ✅ | 401 as expected |
| 17 | 注册第二用户 | ✅ | bob tenant=2 |
| 18 | 跨空间访问返回 403 | ✅ | 403 as expected |
| 19 | 未带令牌返回 401 | ✅ | 401 as expected |
| 20 | 登出并吊销令牌 | ✅ | logged out |
| 21 | 登出后令牌失效 | ✅ | 401 as expected |
| 22 | 数据库落盘校验 | ✅ | users=2 tenants=2 members=2 tokens=8 revoked=6 |
