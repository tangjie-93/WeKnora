"""Chinese documentation metadata only; never participate in request handling."""

from copy import deepcopy
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.api.schemas.auth import (
    DEFAULT_BROWSER_SEARCH_INSTRUCTIONS,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
)
from app.api.schemas.knowledge_bases import CreateKnowledgeBaseRequest

AUTH = "/api/v1/auth"
KNOWLEDGE = "/api/v1/knowledge-bases"
DATE = "2026-01-01T00:00:00Z"
ACCESS_TOKEN = "EXAMPLE_ACCESS_TOKEN_NOT_VALID"
REFRESH_TOKEN = "EXAMPLE_REFRESH_TOKEN_NOT_VALID"


def _ref(name: str, description: str = "") -> dict[str, Any]:
    result = {"$ref": f"#/components/schemas/{name}"}
    if description:
        result["description"] = description
    return result


def _field(kind: str | list[str], description: str, **options: Any) -> dict[str, Any]:
    return {"type": kind, "description": description, **options}


def _object(description: str, properties: dict[str, Any], optional: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"type": "object", "description": description, "properties": properties,
            "required": [key for key in properties if key not in optional], "additionalProperties": False}


def _build_request_schemas() -> dict[str, Any]:
    """Describe copies of the real validation schemas, not new runtime models."""
    schemas = {model.__name__: deepcopy(model.model_json_schema(mode="validation"))
               for model in (RegisterRequest, LoginRequest, RefreshRequest, CreateKnowledgeBaseRequest)}
    identifier = "禁止首尾空白及 Unicode 类别以 C 开头的字符；不自动规范化。"
    for name in ("RegisterRequest", "LoginRequest"):
        schema = schemas[name]
        schema["description"] = "严格字符串字段的 JSON 对象；禁止额外字段。"
        schema["properties"]["email"].update(
            description="邮箱，最多 255 字符。" + identifier +
            "使用 email-validator 校验语法，不检查投递能力，也不以规范化地址替换输入。",
            maxLength=255, examples=["docs-user@example.com"])
        schema["properties"]["password"].update(
            description="密码，至少 6 字符、最多 72 个 UTF-8 字节；登录不要求注册复杂度。",
            minLength=6, **{"x-max-utf8-bytes": 72, "writeOnly": True})
    schemas["RegisterRequest"]["properties"]["username"].update(
        description="用户名，2–50 字符。" + identifier, minLength=2, maxLength=50, examples=["docs-user"])
    schemas["RegisterRequest"]["properties"]["password"].update(
        description="注册密码，8–32 字符，含 ASCII 字母和数字，且最多 72 个 UTF-8 字节。",
        minLength=8, maxLength=32)
    schemas["RefreshRequest"]["description"] = "公开刷新接口；刷新令牌在 JSON 请求体中，不是 Bearer 头。"
    schemas["RefreshRequest"]["properties"]["refreshToken"].update(
        description="必填非空刷新令牌，最多 4096 个 UTF-8 字节；字段名为 refreshToken。",
        minLength=1, examples=[REFRESH_TOKEN], **{"x-max-utf8-bytes": 4096, "writeOnly": True})
    create = schemas["CreateKnowledgeBaseRequest"]
    create["description"] = "仅接受五个严格字符串字段；配置、上传和模型不是本次请求能力。"
    create["properties"]["name"].update(
        description="按 Go unicode.IsSpace 对应的 GO_WHITESPACE 去除首尾空白后，须非空且最多 255 字符。"
        "限制作用于处理后值，不限制原始填充空白长度（仍受请求体上限约束）；名称可重复。",
        **{"x-max-length-after-go-whitespace-trim": 255})
    create["properties"]["description"].update(description="知识库描述，最多 4000 字符，保留空白。", maxLength=4000)
    create["properties"]["type"].update(
        description="仅接受空字符串或 document，输出统一为 document。", enum=["", "document"])
    for key, label in (("embedding_model_id", "嵌入"), ("summary_model_id", "摘要")):
        create["properties"][key].update(description=f"{label}模型标识，本轮仅接受空字符串。", enum=[""])
    return schemas


def _build_response_schemas() -> dict[str, Any]:
    """Document the existing credential-free projections, including every nested field."""
    time = _field(["string", "null"], "转为 UTC 的时间字符串；未设置时为 null。", format="date-time")
    user = {
        "id": _field("string", "用户标识。"), "username": _field("string", "用户名。"),
        "email": _field("string", "用户邮箱。"), "avatar": _field(["string", "null"], "头像地址，可为空。"),
        "tenant_id": _field("integer", "当前空间标识。"),
        "is_active": _field("boolean", "账户是否启用。"),
        "can_access_all_tenants": _field("boolean", "跨空间标记，不绕过当前接口授权。"),
        "is_system_admin": _field("boolean", "系统管理员标记，不绕过当前接口授权。"),
        "preferences": _field("object", "用户偏好，键由持久化内容决定，不保证固定键。", additionalProperties=True),
        "created_at": {**time, "description": "用户创建时间，UTC 时间字符串或 null。"},
        "updated_at": {**time, "description": "用户更新时间，UTC 时间字符串或 null。"},
    }
    schemas = {
        "CurrentUser": _object("当前身份的用户投影，不包含 deleted_at。", deepcopy(user)),
        "User": _object("注册和登录用户投影。", {
            **user, "deleted_at": {**time, "description": "用户删除时间，UTC 时间字符串或 null。"},
        }),
        "Tenant": _object("当前空间；容量与使用量单位均为字节。", {
            "id": _field("integer", "空间标识。"), "name": _field("string", "空间名称。"),
            "description": _field(["string", "null"], "空间描述，可为空。"),
            "status": _field("string", "空间状态，成功身份要求 active。"),
            "business": _field("string", "空间业务标记。"),
            "storage_quota": _field("integer", "存储配额，单位字节。"),
            "storage_used": _field("integer", "已用存储，单位字节。"),
            "retriever_engines": _field("array", "检索引擎配置；现有投影不校验元素类型。", items={}),
            "created_at": {**time, "description": "空间创建时间，UTC 时间字符串或 null。"},
            "updated_at": {**time, "description": "空间更新时间，UTC 时间字符串或 null。"},
            "deleted_at": {**time, "description": "空间删除时间，UTC 时间字符串或 null。"},
        }),
        "Membership": _object("用户的空间成员关系。", {
            "tenant_id": _field("integer", "空间标识。"), "tenant_name": _field("string", "空间名称。"),
            "role": _field("string", "成员角色；viewer 可读不可创建知识库。",
                           enum=["owner", "admin", "contributor", "viewer"]),
        }),
        "Error": _object("普通业务错误；业务码不是 HTTP 状态码。", {
            "success": _field("boolean", "操作失败。", const=False),
            "error": _object("安全错误信息。", {
                "code": _field("integer", "业务码：1000 业务请求，1001 未认证，1002 无权限，1006 限流，"
                               "1007 内部或存储，1008 不可用，1010 参数。"),
                "message": _field("string", "安全的错误说明。"),
                "details": _field("null", "当前始终为 null，不包含原始输入或内部异常。"),
            }),
        }),
        "LoginCredentialsError": _object("登录凭据错误的特殊结构，没有 error 或可见业务码。", {
            "success": _field("boolean", "操作失败。", const=False),
            "message": _field("string", "固定凭据错误消息。", const="Invalid email or password"),
            "memberships": _field("array", "凭据失败时为空数组。", items=_ref("Membership"), maxItems=0),
        }),
    }
    schemas["CurrentIdentity"] = _object("当前身份、空间、偏好默认值及能力。", {
        "user": _ref("CurrentUser", "当前用户，无 deleted_at。"), "tenant": _ref("Tenant", "当前空间。"),
        "memberships": _field("array", "有效成员关系。", items=_ref("Membership")),
        "tenant_required": _field("boolean", "当前无需选择空间，固定 false。", const=False),
        "preference_defaults": _object("默认偏好。", {
            "browser_search_instructions": _field("string", "浏览器搜索默认指令。",
                                                  const=DEFAULT_BROWSER_SEARCH_INSTRUCTIONS),
        }),
        "capabilities": _object("身份功能能力。", {
            "can_create_tenant": _field("boolean", "当前不支持创建空间。", const=False),
            "auto_accept_invitation": _field("boolean", "当前不支持自动接受邀请。", const=False),
        }),
    })
    configs = {
        "ChunkingConfig": _object("分块兼容配置，不代表上传或分块能力已就绪。", {
            "chunk_size": _field("integer", "分块大小，当前为 0。", const=0),
            "chunk_overlap": _field("integer", "相邻分块重叠量，当前为 0。", const=0),
            "separators": _field("null", "分隔符，当前为 null。"),
        }),
        "ImageProcessingConfig": _object("图像处理配置。", {
            "model_id": _field("string", "图像处理模型标识，当前为空。", const=""),
        }),
        "VLMConfig": _object("视觉语言模型兼容配置，当前未启用。", {
            "enabled": _field("boolean", "是否启用视觉模型，当前 false。", const=False),
            "model_id": _field("string", "视觉模型标识，当前为空。", const=""),
            "model_name": _field("string", "视觉模型名称，当前为空。", const=""),
            "base_url": _field("string", "视觉模型服务地址，当前为空。", const=""),
            "api_key": _field("string", "空凭据兼容字段，不含真实密钥。", const=""),
            "interface_type": _field("string", "视觉模型接口类型，当前为空。", const=""),
        }),
        "ASRConfig": _object("语音识别兼容配置。", {
            "enabled": _field("boolean", "是否启用语音识别，当前 false。", const=False),
            "model_id": _field("string", "语音识别模型标识，当前为空。", const=""),
            "language": _field("string", "语音识别语言，当前为空。", const=""),
        }),
        "StorageConfig": _object("凭据清空的存储兼容配置。", {
            key: _field("string", label, **({"enum": ["", "local", "minio", "cos", "tos", "s3", "oss", "ks3", "obs"]}
                                           if key == "provider" else {"const": ""}))
            for key, label in (
                ("secret_id", "空凭据标识兼容字段，不含真实秘密。"),
                ("secret_key", "空凭据密钥兼容字段，不含真实秘密。"),
                ("region", "存储区域，当前为空。"), ("bucket_name", "存储桶名称，当前为空。"),
                ("app_id", "存储应用标识，当前为空。"), ("path_prefix", "存储路径前缀，当前为空。"),
                ("provider", "存储提供方，可为空或受支持提供方。"),
            )
        }),
        "StorageProviderConfig": _object("仅提供方的存储配置；整个对象也可为 null。", {
            "provider": _field("string", "存储提供方，可为空。",
                               enum=["", "local", "minio", "cos", "tos", "s3", "oss", "ks3", "obs"]),
        }),
        "IndexingStrategy": _object("索引配置标记，不表示模型和引擎已就绪。", {
            "vector_enabled": _field("boolean", "向量索引标记，当前 true。", const=True),
            "keyword_enabled": _field("boolean", "关键词索引标记，当前 true。", const=True),
            "wiki_enabled": _field("boolean", "百科索引标记，当前 false。", const=False),
            "graph_enabled": _field("boolean", "图谱索引标记，当前 false。", const=False),
        }),
        "KnowledgeCapabilities": _object("知识库能力标记，不代表模型或检索可用。", {
            key: _field("boolean", label, const=key in ("vector", "keyword"))
            for key, label in (("vector", "向量能力标记。"), ("keyword", "关键词能力标记。"),
                               ("wiki", "百科能力标记。"), ("graph", "图谱能力标记。"), ("faq", "问答对能力标记。"))
        }),
    }
    schemas.update(configs)
    kb = {
        "id": _field("string", "知识库标识。"), "name": _field("string", "处理后的知识库名称。"),
        "description": _field("string", "描述；历史 null 投影为空字符串。"),
        "type": _field("string", "当前仅支持文档知识库。", const="document"),
        "tenant_id": _field("integer", "所属空间标识。"),
        "creator_id": _field("string", "创建者标识；历史空创建者投影为空字符串。"),
        "embedding_model_id": _field("string", "嵌入模型标识，当前为空。", const=""),
        "summary_model_id": _field("string", "摘要模型标识，当前为空。", const=""),
        "is_temporary": _field("boolean", "当前可见记录均为非临时知识库。", const=False),
        "created_at": _field("string", "创建时间，UTC RFC3339。", format="date-time"),
        "updated_at": _field("string", "更新时间，UTC RFC3339。", format="date-time"),
        "deleted_at": _field("null", "删除时间；当前可见记录为 null。"),
        "chunking_config": _ref("ChunkingConfig", "分块配置。"),
        "image_processing_config": _ref("ImageProcessingConfig", "图像处理配置。"),
        "vlm_config": _ref("VLMConfig", "视觉语言模型配置。"),
        "asr_config": _ref("ASRConfig", "语音识别配置。"),
        "storage_config": _ref("StorageConfig", "不含真实秘密的存储配置。"),
        "storage_provider_config": {"description": "存储提供方配置，对象或 null。",
                                    "anyOf": [_ref("StorageProviderConfig"), {"type": "null"}]},
        "indexing_strategy": _ref("IndexingStrategy", "索引策略标记。"),
        "capabilities": _ref("KnowledgeCapabilities", "兼容能力标记。"),
        "knowledge_count": _field("integer", "未删除文档数量；创建为 0，列表为聚合值。"),
        "chunk_count": _field("integer", "未删除分块数量；创建为 0，列表为聚合值。"),
        "processing_count": _field("integer", "处理中或待处理的未删除文档数；创建为 0。"),
        "is_processing": _field("boolean", "处理中数量是否大于 0；创建为 false。"),
        "share_count": _field("integer", "当前空间有效分享数；创建为 0。"),
        "is_pinned": _field("boolean", "当前用户是否置顶；创建为 false。"),
        "pinned_at": _field(["string", "null"], "当前用户置顶时间；创建为 null。", format="date-time"),
        "vector_store_source": _field("string", "向量存储来源，当前 unavailable。", const="unavailable"),
        "vector_store_status": _field("string", "向量存储状态，当前 unavailable，不代表外部能力就绪。",
                                     const="unavailable"),
        "storage_backend_id": _field("string", "仅有存储后端绑定时存在，创建也可能提供；无绑定时省略。"),
        "vector_store_id": _field("string", "有向量绑定时才投影；当前子集先拒绝非空绑定，非可用能力。"),
    }
    for key, label in (("extract_config", "提取"), ("faq_config", "问答对"),
                       ("question_generation_config", "问题生成"), ("auto_tag_config", "自动标签"),
                       ("wiki_config", "百科"), ("profile_config", "展示")):
        kb[key] = _field("null", f"{label}配置，字段必定存在，当前成功子集固定 null；不可作为创建参数。")
    schemas["KnowledgeBaseCreated"] = _object(
        "创建的空知识库，无 creator_name；计数为 0，未处理、未置顶，置顶时间为 null。",
        deepcopy(kb), ("storage_backend_id", "vector_store_id"))
    kb["creator_name"] = _field("string", "仅列表查询到非空创建者名称时添加；否则省略，不补 null。")
    schemas["KnowledgeBaseListed"] = _object(
        "知识库列表项，包含聚合统计与当前用户置顶信息。", kb,
        ("creator_name", "storage_backend_id", "vector_store_id"))
    success = _field("boolean", "操作成功。", const=True)
    schemas.update({
        "RegisterSuccess": _object("注册成功，不直接登录。", {
            "success": deepcopy(success), "message": _field("string", "注册成功消息。", const="Registration successful"),
            "user": _ref("User", "新建用户。"),
        }),
        "LoginSuccess": _object("登录成功，访问令牌有效期 24 小时，刷新令牌有效期 7 天。", {
            "success": deepcopy(success), "message": _field("string", "登录成功消息。", const="Login successful"),
            "user": _ref("User", "登录用户。"), "active_tenant": _ref("Tenant", "当前空间。"),
            "memberships": _field("array", "有效成员关系。", items=_ref("Membership")),
            "token": _field("string", "访问令牌，登录响应字段名为 token。"),
            "refresh_token": _field("string", "刷新令牌。"),
        }),
        "RefreshSuccess": _object("轮换令牌对；消费旧刷新令牌，不承诺同时撤销旧访问令牌。", {
            "success": deepcopy(success),
            "message": _field("string", "刷新成功消息。", const="Token refreshed successfully"),
            "access_token": _field("string", "新访问令牌，有效期 24 小时；字段名为 access_token。"),
            "refresh_token": _field("string", "新刷新令牌，有效期 7 天。"),
        }),
        "CurrentSuccess": _object("当前身份结果。", {
            "success": deepcopy(success), "data": _ref("CurrentIdentity", "完整当前身份。"),
        }),
        "LogoutSuccess": _object("撤销该用户全部会话令牌。", {
            "success": deepcopy(success), "message": _field("string", "退出成功消息。", const="Logout successful"),
        }),
        "KnowledgeCreateSuccess": _object("创建结果为对象，无 creator_name。", {
            "success": deepcopy(success), "data": _ref("KnowledgeBaseCreated", "新建空知识库。"),
        }),
        "KnowledgeListSuccess": _object("列表结果为数组，无分页包裹。", {
            "success": deepcopy(success),
            "data": _field("array", "可见知识库列表；无记录为空数组。", items=_ref("KnowledgeBaseListed"), maxItems=100),
        }),
        "HealthSuccess": _object("仅 HTTP 应用存活，不检查数据库、模型、存储或其他依赖就绪。", {
            "status": _field("string", "存活状态。", const="ok"),
        }),
    })
    return schemas


def _build_examples() -> dict[str, Any]:
    """Use only fixed fictional data and deliberately unusable tokens."""
    user = {"id": "docs-user-id", "username": "docs-user", "email": "docs-user@example.com", "avatar": None,
            "tenant_id": 1, "is_active": True, "can_access_all_tenants": False, "is_system_admin": False,
            "preferences": {}, "created_at": DATE, "updated_at": DATE, "deleted_at": None}
    tenant = {"id": 1, "name": "虚构示例空间", "description": None, "status": "active", "business": "",
              "storage_quota": 10737418240, "storage_used": 0, "retriever_engines": [],
              "created_at": DATE, "updated_at": DATE, "deleted_at": None}
    memberships = [{"tenant_id": 1, "tenant_name": "虚构示例空间", "role": "owner"}]
    current_user = {key: value for key, value in user.items() if key != "deleted_at"}
    kb = {"id": "docs-knowledge-base-id", "name": "虚构示例知识库", "description": "仅文档示例", "type": "document",
          "tenant_id": 1, "creator_id": "docs-user-id", "embedding_model_id": "", "summary_model_id": "",
          "is_temporary": False, "created_at": DATE, "updated_at": DATE, "deleted_at": None,
          "chunking_config": {"chunk_size": 0, "chunk_overlap": 0, "separators": None},
          "image_processing_config": {"model_id": ""},
          "vlm_config": {"enabled": False, "model_id": "", "model_name": "", "base_url": "",
                         "api_key": "", "interface_type": ""},
          "asr_config": {"enabled": False, "model_id": "", "language": ""},
          "storage_config": {"secret_id": "", "secret_key": "", "region": "", "bucket_name": "",
                             "app_id": "", "path_prefix": "", "provider": ""},
          "storage_provider_config": {"provider": "local"},
          "indexing_strategy": {"vector_enabled": True, "keyword_enabled": True,
                                "wiki_enabled": False, "graph_enabled": False},
          "capabilities": {"vector": True, "keyword": True, "wiki": False, "graph": False, "faq": False},
          "extract_config": None, "faq_config": None, "question_generation_config": None,
          "auto_tag_config": None, "wiki_config": None, "profile_config": None,
          "knowledge_count": 0, "chunk_count": 0, "processing_count": 0, "is_processing": False,
          "share_count": 0, "is_pinned": False, "pinned_at": None,
          "vector_store_source": "unavailable", "vector_store_status": "unavailable"}
    listed = deepcopy(kb)
    listed.update(creator_name="docs-user", knowledge_count=2, chunk_count=4, processing_count=1,
                  is_processing=True, share_count=1, is_pinned=True, pinned_at=DATE,
                  storage_backend_id="docs-storage-backend-id")
    return {
        "RegisterSuccess": {"success": True, "message": "Registration successful", "user": user},
        "LoginSuccess": {"success": True, "message": "Login successful", "user": deepcopy(user),
                         "active_tenant": tenant, "memberships": memberships,
                         "token": ACCESS_TOKEN, "refresh_token": REFRESH_TOKEN},
        "RefreshSuccess": {"success": True, "message": "Token refreshed successfully",
                           "access_token": ACCESS_TOKEN, "refresh_token": REFRESH_TOKEN},
        "CurrentSuccess": {"success": True, "data": {
            "user": current_user, "tenant": deepcopy(tenant), "memberships": deepcopy(memberships),
            "tenant_required": False,
            "preference_defaults": {"browser_search_instructions": DEFAULT_BROWSER_SEARCH_INSTRUCTIONS},
            "capabilities": {"can_create_tenant": False, "auto_accept_invitation": False}}},
        "LogoutSuccess": {"success": True, "message": "Logout successful"},
        "KnowledgeCreateSuccess": {"success": True, "data": kb},
        "KnowledgeListSuccess": {"success": True, "data": [listed]},
        "HealthSuccess": {"status": "ok"},
    }


def _error_response(description: str, cases: dict[str, tuple[int, str]], *, login: bool = False,
                    retry: bool = False) -> dict[str, Any]:
    examples = {name: {"summary": message, "value": {
        "success": False, "error": {"code": code, "message": message, "details": None}}}
        for name, (code, message) in cases.items()}
    schema = _ref("Error")
    if login:
        schema = {"oneOf": [_ref("LoginCredentialsError"), _ref("Error")]}
        examples["invalidCredentials"] = {"summary": "登录凭据错误，无 error 和业务码", "value": {
            "success": False, "message": "Invalid email or password", "memberships": []}}
    headers = {"Cache-Control": {"description": "禁止缓存认证和知识库结果。",
                                 "schema": {"type": "string", "const": "no-store"}}}
    if retry:
        headers["Retry-After"] = {"description": "重试等待秒数。", "schema": {"type": "string", "const": "60"}}
    return {"description": description, "headers": headers,
            "content": {"application/json": {"schema": schema, "examples": examples}}}


def _build_operation_metadata() -> dict[tuple[str, str], dict[str, Any]]:
    examples = _build_examples()
    operations = {}
    definitions = [
        (f"{AUTH}/register", "post", "账户与认证", "注册账户", "原子创建账户、默认空间和 owner 成员关系，不直接登录。",
         "RegisterSuccess", "201", "RegisterRequest", False),
        (f"{AUTH}/login", "post", "账户与认证", "登录账户", "验证邮箱密码，返回身份、空间、成员和令牌对。",
         "LoginSuccess", "200", "LoginRequest", False),
        (f"{AUTH}/refresh", "post", "账户与认证", "刷新令牌", ("通过请求体 refreshToken 轮换令牌对，消费旧刷新令牌。"
         "不承诺同时撤销旧访问令牌。"), "RefreshSuccess", "200", "RefreshRequest", False),
        (f"{AUTH}/me", "get", "账户与认证", "获取当前身份", "返回当前用户、空间、成员、偏好默认值和能力，仅接受有效访问令牌。",
         "CurrentSuccess", "200", None, True),
        (f"{AUTH}/logout", "post", "账户与认证", "退出全部会话", ("撤销该用户全部会话令牌。接受访问或刷新令牌，"
         "允许已过期或撤销但可匹配记录的令牌用于重复退出；不解析 X-Tenant-ID，不要求 JSON 请求体。"),
         "LogoutSuccess", "200", None, True),
        (KNOWLEDGE, "get", "知识库管理", "列出当前空间知识库", ("返回当前空间非临时、未删除的知识库，viewer 也可读取。"
         "无分页；过滤前可见记录超过 100 即 503/1008。排序：当前用户置顶优先、置顶时间降序、创建时间降序、标识降序。"),
         "KnowledgeListSuccess", "200", None, True),
        (KNOWLEDGE, "post", "知识库管理", "创建空文档知识库", ("仅 owner/admin/contributor 可创建；当前不支持模型、上传或检索。"
         "已有 100 个时返回 400/1000。名称可重复，无幂等承诺，响应丢失后不建议自动重试。"
         "提交后审计失败不改变成功结果。"), "KnowledgeCreateSuccess", "201", "CreateKnowledgeBaseRequest", True),
        ("/health", "get", "服务健康", "检查应用存活", ("仅检查 HTTP 应用存活，不检查数据库、模型、存储或依赖就绪。"
         "诊断头不是可信认证信息。"), "HealthSuccess", "200", None, False),
    ]
    no_store = {"Cache-Control": {"description": "禁止缓存。", "schema": {"type": "string", "const": "no-store"}}}
    tenant = {"name": "X-Tenant-ID", "in": "header", "required": False,
              "description": "可选空间核对头；纯 ASCII 十进制数字，最多 19 位且值大于 0，允许前导零。"
              "仅核对当前空间，不能授予权限或切换空间；非法 400/1010，不匹配 403/1002。",
              "schema": {"type": "string", "pattern": "^[0-9]{1,19}$", "maxLength": 19,
                         "description": "数值须大于 0，不施加 int64 或前端安全整数限制。"}, "example": "0001"}
    for path, method, tag, summary, description, response, status, request, protected in definitions:
        content = {"schema": _ref(response), "examples": {"success": {"summary": "完整虚构成功示例",
                                                                                  "value": examples[response]}}}
        if response == "KnowledgeListSuccess":
            content["examples"]["empty"] = {"summary": "空列表", "value": {"success": True, "data": []}}
        headers = deepcopy(no_store) if path != "/health" else {
            "X-WeKnora-Implementation": {"description": "仅诊断实现来源，不是可信认证。",
                                         "schema": {"type": "string", "const": "python-fastapi"}}}
        operation = {"tags": [tag], "summary": summary, "description": description,
                     "security": [{"BearerAuth": []}] if protected else [],
                     "responses": {status: {"description": "成功。", "headers": headers,
                                            "content": {"application/json": content}}}}
        if request:
            operation["requestBody"] = {"required": True, "description": "application/json；严格字符串，禁止额外字段。",
                                        "content": {"application/json": {"schema": _ref(request)}}}
        if path == f"{AUTH}/me" or path == KNOWLEDGE:
            operation["parameters"] = [deepcopy(tenant)]
        if protected:
            operation["description"] += (" Bearer 头须恰好两段，方案名大小写不敏感，令牌最多 4096 个 UTF-8 字节。"
                                         "在 Authorize 只输入令牌，不手写 Bearer 前缀。")
        operations[path, method] = operation
    operations[KNOWLEDGE, "get"]["parameters"].append({
        "name": "creator", "in": "query", "required": False,
        "description": "仅允许至多一个 creator，重复或其他查询参数返回 400/1000。按 GO_WHITESPACE 去首尾后小写："
        "mine 为非空创建者等于当前用户，others 为非空且不等于；all、空、省略和未知值均返回全部。"
        "历史空创建者仅在全部结果出现，creator_id 投影为空字符串。",
        "schema": {"type": "string", "default": "all"}, "example": "mine"})
    operations[KNOWLEDGE, "post"]["requestBody"]["description"] += (
        " 不允许查询参数。媒体类型取分号前部分，去首尾空白后大小写不敏感地匹配 application/json；参数不参与匹配。"
        "最多 1 MiB，超限返回 400/1000（不是 413）。必须是 UTF-8 单个对象；拒绝重复键、非有限常量、"
        "孤立代理码点和尾随额外内容。体积限制先于令牌与空间头，随后查询、媒体类型、严格解析，最后才验证服务身份。"
        "严格类型等 ValidationError 统一为 Invalid knowledge base request；业务字段验证的具体错误保留。")
    for suffix in ("register", "login", "refresh"):
        operation = operations[f"{AUTH}/{suffix}", "post"]
        operation["description"] += " 请求体最多 8 KiB；媒体类型按分号前部分大小写不敏感匹配 application/json，不去首尾空白。"
        operation["requestBody"]["content"]["application/json"]["examples"] = {"request": {"value": {
            "RegisterRequest": {"username": "docs-user", "email": "docs-user@example.com", "password": ""},
            "LoginRequest": {"email": "docs-user@example.com", "password": ""},
            "RefreshRequest": {"refreshToken": REFRESH_TOKEN},
        }[operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].rsplit("/", 1)[-1]],
            "summary": "虚构请求；密码留空以避免提供秘密，实际提交须满足密码规则"}}
    operations[KNOWLEDGE, "post"]["requestBody"]["content"]["application/json"]["example"] = {
        "name": "虚构示例知识库", "description": "仅文档示例", "type": "document",
        "embedding_model_id": "", "summary_model_id": ""}
    _add_error_metadata(operations)
    return operations


def _add_error_metadata(operations: dict[tuple[str, str], dict[str, Any]]) -> None:
    """List only observable error messages and statuses for each operation."""
    unauthorized = {"invalidToken": (1001, "Invalid or expired authentication token")}
    workspace = {"membershipUnavailable": (1002, "Current workspace or membership is unavailable")}
    mismatch = {"workspaceMismatch": (1002, "Current workspace does not match authentication")}
    tenant_invalid = {"invalidTenant": (1010, "X-Tenant-ID must be a positive integer")}
    too_long = {"tokenTooLong": (1010, "Authentication token is too long")}
    for (path, method), operation in operations.items():
        responses = operation["responses"]
        if path == "/health":
            responses["500"] = _error_response("未预期异常经现有全局处理器处理。", {
                "internal": (1007, "Internal authentication failure")})
            continue
        knowledge = path == KNOWLEDGE
        suffix = path.rsplit("/", 1)[-1]
        bad = {}
        if knowledge:
            bad.update(tenant_invalid)
            bad.update(too_long)
            bad["unsupportedQuery"] = (1000, "Unsupported knowledge base query parameters")
            # The global RequestValidationError / HTTP 400 handlers also normalize to this message.
            bad["invalidRequest"] = (1000, "Invalid knowledge base request")
            if method == "post":
                bad.update({
                    "mediaType": (1000, "Content-Type must be application/json"),
                    "unsupportedFields": (1000, "Unsupported knowledge base fields"),
                    "emptyName": (1000, "name cannot be empty"),
                    "longName": (1000, "Knowledge base name exceeds 255 characters"),
                    "longDescription": (1000, "Knowledge base description exceeds 4000 characters"),
                    "unsupportedType": (1000, "Unsupported knowledge base type"),
                    "unsupportedModels": (1000, "Models are not supported for empty knowledge bases"),
                    "bodyTooLarge": (1000, "Knowledge base request body exceeds 1 MiB"),
                    "capacity": (1000, "Knowledge base limit reached"),
                    "storageBinding": (1000, "storage backend is unavailable"),
                })
        else:
            bad["invalidParameters"] = (1010, "Invalid request parameters")
            if suffix in ("register", "login", "refresh"):
                bad["mediaType"] = (1010, "Content-Type must be application/json")
            if suffix == "register":
                bad["duplicateAccount"] = (1000, "Email or username already registered")
            if suffix in ("me", "logout"):
                bad.update(too_long)
            if suffix == "me":
                bad.update(tenant_invalid)
            if suffix == "logout":
                bad["missingBearer"] = (1010, "Bearer authentication token is required")
        responses["400"] = _error_response("请求无效；各命名示例对应真实可见分支。", bad)
        if suffix != "register":
            responses["401"] = _error_response("未认证；登录还保留无 error 的凭据失败结构。" if suffix == "login"
                                               else "令牌缺失、无效、过期、已消费或不匹配。",
                                               deepcopy(unauthorized), login=suffix == "login")
        if knowledge or suffix in ("login", "refresh", "me"):
            forbidden = deepcopy(workspace)
            if knowledge or suffix == "me":
                forbidden.update(mismatch)
            if knowledge and method == "post":
                forbidden["roleDenied"] = (1002, "Knowledge base creation is not permitted")
            responses["403"] = _error_response("当前空间或成员不可用、不匹配，或无创建权限。", forbidden)
        if not knowledge:
            responses["413"] = _error_response("认证路径所有方法均受请求体上限约束，包括 me 和 logout。", {
                "bodyTooLarge": (1010, "Request body exceeds 8 KiB")})
            if suffix in ("register", "login", "refresh"):
                limited = {"rateLimited": (1006, "Authentication rate limit exceeded; retry later")}
                if suffix in ("register", "login"):
                    limited["passwordCapacity"] = (1006, "Password computation capacity exceeded; retry later")
                responses["429"] = _error_response("认证限流或密码计算槽不足。", limited, retry=True)
        responses["500"] = _error_response("存储或内部失败，不暴露异常细节。", {
            "storage": (1007, "Knowledge base storage failure" if knowledge else "Authentication storage failure"),
            "internal": (1007, "Internal knowledge base failure" if knowledge else "Internal authentication failure"),
        })
        unavailable = {"unavailable": (1008, "Knowledge base service unavailable" if knowledge else
                                      "Authentication unavailable; initialize an owned authentication database")}
        if knowledge:
            unavailable["unsupportedConfiguration"] = (1008, "Knowledge base configuration is outside supported scope")
            if method == "get":
                unavailable["listCapacity"] = (1008, "Knowledge base list exceeds supported capacity")
        responses["503"] = _error_response(
            "数据库忙、锁、无法打开、配置缺失或基线不符等不可用；知识库合法但超子集的配置也不可用，损坏配置为 500。",
            unavailable)


def build_openapi(application: FastAPI) -> dict[str, Any]:
    """Build metadata lazily and cache only on this application instance."""
    if application.openapi_schema is not None:
        return application.openapi_schema
    schema = deepcopy(get_openapi(
        title=application.title, version=application.version, openapi_version=application.openapi_version,
        summary=application.summary, description=application.description, routes=application.routes,
        webhooks=application.webhooks.routes, tags=application.openapi_tags, servers=application.servers,
        terms_of_service=application.terms_of_service, contact=application.contact, license_info=application.license_info,
        separate_input_output_schemas=application.separate_input_output_schemas,
        external_docs=application.openapi_external_docs,
    ))
    overview = (
        "当前仅提供账户与认证、当前空间的空文档知识库创建与列表，以及 HTTP 存活检查，共八个操作。"
        "不提供文档上传、模型调用、检索、空间切换或依赖就绪检查；兼容配置与能力标记不代表引擎已就绪。\n\n"
        "所有示例均为固定虚构数据；示例令牌不可用，秘密字段为空。Authorize 只输入令牌，不手写 Bearer 前缀。"
        "认证和知识库成功及失败均有 Cache-Control: no-store，认证 429 另有 Retry-After: 60。"
        "业务错误码与 HTTP 状态不同；框架 404/405 返回 {\"detail\":\"...\"}，没有业务码，405 保留 Allow 头。"
        "认证参数错误为 400 而非默认 422；数据库不可用为 503，健康接口不据此返回 503。"
    )
    schema["info"]["description"] = "\n\n".join(filter(None, (schema["info"].get("description"), overview)))
    tags = schema.setdefault("tags", [])
    for name, description in (("账户与认证", "账户创建、登录、刷新、当前身份与退出。"),
                              ("知识库管理", "当前空间空文档知识库管理兼容子集。"),
                              ("服务健康", "仅 HTTP 应用存活诊断。")):
        if not any(tag["name"] == name for tag in tags):
            tags.append({"name": name, "description": description})
    components = schema.setdefault("components", {})
    components.setdefault("schemas", {}).update(_build_request_schemas())
    components["schemas"].update(_build_response_schemas())
    components.setdefault("securitySchemes", {})["BearerAuth"] = {
        "type": "http", "scheme": "bearer", "bearerFormat": "JWT",
        "description": "在 Authorize 只输入令牌，不手写 Bearer 前缀。me 和知识库仅接受有效访问令牌；"
        "logout 接受访问或刷新令牌，包括可匹配记录的过期或撤销令牌。",
    }
    for (path, method), metadata in _build_operation_metadata().items():
        operation = schema["paths"][path][method]
        operation.update(deepcopy({key: value for key, value in metadata.items() if key != "responses"}))
        operation.setdefault("responses", {}).pop("422", None)
        operation["responses"].update(deepcopy(metadata["responses"]))
    application.openapi_schema = schema
    return schema


def install_openapi(application: FastAPI) -> None:
    """Install an instance-local generator after every application route is registered."""
    def custom_openapi() -> dict[str, Any]:
        return build_openapi(application)

    application.openapi = custom_openapi
