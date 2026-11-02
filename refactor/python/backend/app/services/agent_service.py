"""Agent 服务：自定义 Agent CRUD + 编辑器元数据（工具/类型预设/占位符）。

对齐 Go `internal/application/service` + `internal/agent/tools` + `types/placeholder.go`：
- 内置 agent（quick-answer / smart-reasoning）由内存提供，不落库
- `config` 为 JSON dict，`ensure_defaults` 补关键默认值
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request, not_found
from app.domain.entities import (
    AGENT_MODE_QUICK_ANSWER,
    AGENT_MODE_SMART_REASONING,
    AGENT_MODES,
    AGENT_TYPE_CUSTOM,
    AGENT_TYPE_DATA_ANALYSIS,
    AGENT_TYPE_HYBRID_RAG_WIKI,
    AGENT_TYPE_RAG_QA,
    AGENT_TYPE_WIKI_QA,
    AGENT_TYPES,
    BUILTIN_QUICK_ANSWER_ID,
    BUILTIN_SMART_REASONING_ID,
    KB_SELECTION_ALL,
    KB_SELECTION_MODES,
    KB_SELECTION_NONE,
    KB_SELECTION_SELECTED,
    MAX_AGENT_AVATAR_CHARS,
    CustomAgent,
)
from app.repositories import agent_repository


def _iso(value) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------
# 默认值与校验
# --------------------------------------------------------------------------


def ensure_defaults(config: dict[str, Any]) -> dict[str, Any]:
    """对齐 `CustomAgent.EnsureDefaults` 的关键默认值。"""
    config = dict(config or {})
    if float(config.get("temperature") or 0) < 0:
        config["temperature"] = 0.7
    if int(config.get("max_iterations") or 0) == 0:
        config["max_iterations"] = 10
    if int(config.get("web_search_max_results") or 0) == 0:
        config["web_search_max_results"] = 5
    if int(config.get("history_turns") or 0) == 0:
        config["history_turns"] = 5
    if int(config.get("embedding_top_k") or 0) == 0:
        config["embedding_top_k"] = 10
    if float(config.get("keyword_threshold") or 0) == 0:
        config["keyword_threshold"] = 0.3
    if float(config.get("vector_threshold") or 0) == 0:
        config["vector_threshold"] = 0.5
    if int(config.get("rerank_top_k") or 0) == 0:
        config["rerank_top_k"] = 5
    if not config.get("fallback_strategy"):
        config["fallback_strategy"] = "model"
    if config.get("agent_mode") == AGENT_MODE_SMART_REASONING:
        config["multi_turn_enabled"] = True
    # 工具列表 / KB 模式为空时给默认值
    if config.get("allowed_tools") is None:
        config["allowed_tools"] = DEFAULT_TOOLS
    if config.get("kb_selection_mode") is None:
        config["kb_selection_mode"] = KB_SELECTION_ALL
    if config.get("mcp_selection_mode") is None:
        config["mcp_selection_mode"] = KB_SELECTION_NONE
    return config


def _validate_agent_mode(mode: str) -> str:
    mode = (mode or "").strip()
    if mode and mode not in AGENT_MODES:
        raise bad_request(f"无效的 agent_mode: {mode}")
    return mode


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    config = dict(config or {})
    mode = _validate_agent_mode(str(config.get("agent_mode") or ""))
    agent_type = str(config.get("agent_type") or "")
    if agent_type and agent_type not in AGENT_TYPES:
        raise bad_request(f"无效的 agent_type: {agent_type}")
    kb_mode = str(config.get("kb_selection_mode") or "")
    if kb_mode and kb_mode not in KB_SELECTION_MODES:
        raise bad_request(f"无效的 kb_selection_mode: {kb_mode}")
    for key in ("mcp_selection_mode", "skills_selection_mode"):
        value = str(config.get(key) or "")
        if value and value not in KB_SELECTION_MODES:
            raise bad_request(f"无效的 {key}: {value}")
    if mode:
        config["agent_mode"] = mode
    return ensure_defaults(config)


def _validate_avatar(avatar: str) -> str:
    avatar = str(avatar or "")
    if len(avatar) > MAX_AGENT_AVATAR_CHARS:
        raise bad_request(f"avatar 不能超过 {MAX_AGENT_AVATAR_CHARS} 个字符")
    return avatar


def agent_payload(agent: CustomAgent) -> dict[str, Any]:
    return {
        "id": agent.id,
        "tenant_id": agent.tenant_id,
        "name": agent.name,
        "description": agent.description or "",
        "avatar": agent.avatar or "",
        "is_builtin": bool(agent.is_builtin),
        "created_by": agent.created_by or "",
        "runnable_by_viewer": bool(agent.runnable_by_viewer),
        "config": agent.config or {},
        "created_at": _iso(agent.created_at),
        "updated_at": _iso(agent.updated_at),
    }


# --------------------------------------------------------------------------
# 内置 agent
# --------------------------------------------------------------------------


def _builtin_agents(tenant_id: int) -> list[CustomAgent]:
    now = datetime.now(UTC)
    quick = CustomAgent(
        id=BUILTIN_QUICK_ANSWER_ID,
        tenant_id=tenant_id,
        name="快速回答",
        description="基于知识库的检索式快速问答（RAG）",
        is_builtin=True,
        runnable_by_viewer=True,
        config=ensure_defaults({"agent_mode": AGENT_MODE_QUICK_ANSWER}),
        created_at=now,
        updated_at=now,
    )
    smart = CustomAgent(
        id=BUILTIN_SMART_REASONING_ID,
        tenant_id=tenant_id,
        name="智能推理",
        description="多步推理智能体（ReAct），可调用检索工具",
        is_builtin=True,
        runnable_by_viewer=True,
        config=ensure_defaults({"agent_mode": AGENT_MODE_SMART_REASONING}),
        created_at=now,
        updated_at=now,
    )
    return [quick, smart]


def _get_builtin(tenant_id: int, agent_id: str) -> CustomAgent | None:
    for agent in _builtin_agents(tenant_id):
        if agent.id == agent_id:
            return agent
    return None


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------


async def list_agents(
    session: AsyncSession, tenant_id: int, creator: str = "", caller_user_id: str = ""
) -> list[dict[str, Any]]:
    builtins = _builtin_agents(tenant_id)
    customs = await agent_repository.list_agents(session, tenant_id)

    if creator in ("mine", "others") and caller_user_id:
        filtered = [agent for agent in customs if agent.created_by]
        if creator == "mine":
            filtered = [agent for agent in filtered if agent.created_by == caller_user_id]
        else:
            filtered = [agent for agent in filtered if agent.created_by != caller_user_id]
        customs = filtered

    return [agent_payload(agent) for agent in [*builtins, *customs]]


async def get_agent(
    session: AsyncSession, tenant_id: int, agent_id: str
) -> dict[str, Any]:
    builtin = _get_builtin(tenant_id, agent_id)
    if builtin is not None:
        return agent_payload(builtin)
    agent = await agent_repository.get_agent(session, tenant_id, agent_id)
    if agent is None:
        raise not_found("Agent not found")
    return agent_payload(agent)


async def create_agent(
    session: AsyncSession, tenant_id: int, user_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise bad_request("agent name is required")

    config = _validate_config(payload.get("config") or {})
    avatar = _validate_avatar(str(payload.get("avatar") or ""))
    now = datetime.now(UTC)
    agent = CustomAgent(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=name,
        description=str(payload.get("description") or ""),
        avatar=avatar,
        is_builtin=False,
        created_by=user_id,
        runnable_by_viewer=True,
        config=config,
        created_at=now,
        updated_at=now,
    )
    await agent_repository.save_agent(session, agent)
    await session.commit()
    await session.refresh(agent)
    return agent_payload(agent)


async def update_agent(
    session: AsyncSession, tenant_id: int, agent_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    agent = await agent_repository.get_agent(session, tenant_id, agent_id)
    if agent is None:
        if _get_builtin(tenant_id, agent_id) is not None:
            raise bad_request("无法修改内置智能体")
        raise not_found("Agent not found")

    name = str(payload.get("name") or agent.name).strip()
    if not name:
        raise bad_request("agent name is required")
    agent.name = name
    agent.description = str(payload.get("description") or agent.description or "")
    if payload.get("avatar") is not None:
        agent.avatar = _validate_avatar(str(payload["avatar"]))
    agent.config = _validate_config(payload.get("config") or agent.config)
    agent.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(agent)
    return agent_payload(agent)


async def patch_agent(
    session: AsyncSession, tenant_id: int, agent_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    agent = await agent_repository.get_agent(session, tenant_id, agent_id)
    if agent is None:
        if _get_builtin(tenant_id, agent_id) is not None:
            raise bad_request("无法修改内置智能体")
        raise not_found("Agent not found")

    if payload.get("name") is not None:
        name = str(payload["name"]).strip()
        if not name:
            raise bad_request("agent name is required")
        agent.name = name
    if payload.get("description") is not None:
        agent.description = str(payload["description"])
    config = dict(agent.config or {})
    if payload.get("agent_mode") is not None:
        config["agent_mode"] = _validate_agent_mode(str(payload["agent_mode"]))
    if payload.get("system_prompt") is not None:
        config["system_prompt"] = str(payload["system_prompt"])
    if payload.get("model_id") is not None:
        config["model_id"] = str(payload["model_id"])
    if payload.get("kb_selection_mode") is not None:
        config["kb_selection_mode"] = str(payload["kb_selection_mode"])
    if payload.get("knowledge_bases") is not None:
        config["knowledge_bases"] = list(payload["knowledge_bases"])
        config["kb_selection_mode"] = KB_SELECTION_SELECTED
    if payload.get("mcp_selection_mode") is not None:
        config["mcp_selection_mode"] = str(payload["mcp_selection_mode"])
    if payload.get("mcp_services") is not None:
        config["mcp_services"] = list(payload["mcp_services"])
        config["mcp_selection_mode"] = KB_SELECTION_SELECTED
    if payload.get("web_search_enabled") is not None:
        config["web_search_enabled"] = bool(payload["web_search_enabled"])
    if payload.get("multi_turn_enabled") is not None:
        config["multi_turn_enabled"] = bool(payload["multi_turn_enabled"])
    agent.config = _validate_config(config)
    agent.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(agent)
    return agent_payload(agent)


async def delete_agent(
    session: AsyncSession, tenant_id: int, agent_id: str
) -> None:
    agent = await agent_repository.get_agent(session, tenant_id, agent_id)
    if agent is None:
        if _get_builtin(tenant_id, agent_id) is not None:
            raise bad_request("无法删除内置智能体")
        raise not_found("Agent not found")
    await agent_repository.delete_agent(session, agent)
    await session.commit()


async def copy_agent(
    session: AsyncSession, tenant_id: int, agent_id: str, user_id: str
) -> dict[str, Any]:
    source = await agent_repository.get_agent(session, tenant_id, agent_id)
    if source is None:
        raise not_found("Agent not found")

    now = datetime.now(UTC)
    agent = CustomAgent(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=f"{source.name}（副本）",
        description=source.description or "",
        avatar=source.avatar or "",
        is_builtin=False,
        created_by=user_id,
        runnable_by_viewer=True,
        config=dict(source.config or {}),
        created_at=now,
        updated_at=now,
    )
    await agent_repository.save_agent(session, agent)
    await session.commit()
    await session.refresh(agent)
    return agent_payload(agent)


# --------------------------------------------------------------------------
# 编辑器元数据（静态，不依赖模型）
# --------------------------------------------------------------------------

# 工具目录：对齐 `internal/agent/tools/definitions.go`
_AVAILABLE_TOOLS: list[dict[str, Any]] = [
    {"name": "thinking", "label": "思考", "description": "动态和反思性的问题解决思考工具", "group": "base"},
    {"name": "todo_write", "label": "制定计划", "description": "创建结构化的研究计划", "group": "base"},
    {"name": "ask_user", "label": "向用户提问", "description": "需要用户补充信息或做选择时，弹出卡片等待回答", "group": "base"},
    {"name": "search_conversations", "label": "回顾历史对话", "description": "在用户自己的历史会话中查找之前聊过的内容", "group": "base"},
    {"name": "search_knowledge", "label": "检索知识库", "description": "语义、关键词或混合检索知识库分块", "group": "rag"},
    {"name": "read_document", "label": "阅读文档", "description": "读取文档元数据与分块内容，支持分页和文内查找", "group": "rag"},
    {"name": "list_documents", "label": "浏览文档列表", "description": "分页列出知识库中的文档", "group": "rag"},
    {"name": "query_knowledge_graph", "label": "查询知识图谱", "description": "从知识图谱中查询关系", "group": "rag"},
    {"name": "database_query", "label": "查询数据库", "description": "查询数据库中的信息", "group": "rag"},
    {"name": "wiki_search", "label": "搜索Wiki", "description": "在Wiki中搜索页面", "group": "wiki_read"},
    {"name": "wiki_read_page", "label": "读取Wiki页面", "description": "读取指定的Wiki页面内容", "group": "wiki_read"},
    {"name": "wiki_flag_issue", "label": "标记Wiki问题", "description": "标记页面中存在的事实错误或合并冲突问题", "group": "wiki_read"},
    {"name": "wiki_write_page", "label": "创建/覆盖Wiki", "description": "创建新页面或完全覆盖已有页面", "group": "wiki_edit", "danger": True},
    {"name": "wiki_replace_text", "label": "局部替换Wiki", "description": "替换Wiki页面中的特定文本", "group": "wiki_edit", "danger": True},
    {"name": "wiki_rename_page", "label": "重命名Wiki", "description": "重命名Wiki页面并自动更新关联链接", "group": "wiki_edit", "danger": True},
    {"name": "wiki_delete_page", "label": "删除Wiki", "description": "删除Wiki页面并自动清理关联死链", "group": "wiki_edit", "danger": True},
    {"name": "wiki_read_issue", "label": "查看Wiki问题", "description": "查看特定的Wiki页面问题详情", "group": "wiki_issue"},
    {"name": "wiki_update_issue", "label": "更新Wiki问题状态", "description": "更新特定的Wiki页面问题状态", "group": "wiki_issue"},
    {"name": "data_analysis", "label": "数据分析", "description": "理解数据文件并进行数据分析", "group": "data"},
    {"name": "data_schema", "label": "查看数据元信息", "description": "获取表格文件的元信息", "group": "data"},
]

# 工具能力要求（对齐 `internal/agent/tools/capabilities.go`）
_TOOL_REQUIREMENTS: dict[str, dict[str, list[str]]] = {
    "search_knowledge": {"any_of": ["vector", "keyword"]},
    "read_document": {"any_of": ["vector", "keyword", "wiki"]},
    "list_documents": {"any_of": ["vector", "keyword", "wiki"]},
    "query_knowledge_graph": {"all_of": ["graph"]},
    "database_query": {"any_of": ["vector", "keyword"]},
    "wiki_search": {"all_of": ["wiki"]},
    "wiki_read_page": {"all_of": ["wiki"]},
    "wiki_flag_issue": {"all_of": ["wiki"]},
    "wiki_write_page": {"all_of": ["wiki"]},
    "wiki_replace_text": {"all_of": ["wiki"]},
    "wiki_rename_page": {"all_of": ["wiki"]},
    "wiki_delete_page": {"all_of": ["wiki"]},
    "wiki_read_issue": {"all_of": ["wiki"]},
    "wiki_update_issue": {"all_of": ["wiki"]},
    "data_analysis": {"any_of": ["vector", "keyword"]},
    "data_schema": {"any_of": ["vector", "keyword"]},
}

DEFAULT_TOOLS = [
    "search_knowledge",
    "read_document",
    "list_documents",
    "search_conversations",
    "ask_user",
]

SWITCH_MANAGED_TOOLS = [
    "web_search",
    "web_fetch",
    "search_memory",
    "shell_exec",
    "read_file",
    "list_sandbox_files",
    "write_sandbox_file",
    "edit_sandbox_file",
    "write_skill_file",
    "edit_skill_file",
    "discover_mcp_tools",
    "call_mcp_tool",
]


def tool_catalog() -> dict[str, Any]:
    tools = []
    for tool in _AVAILABLE_TOOLS:
        info = dict(tool)
        requirement = _TOOL_REQUIREMENTS.get(tool["name"], {})
        info["requirement"] = {
            "any_of": requirement.get("any_of", []),
            "all_of": requirement.get("all_of", []),
        }
        tools.append(info)
    return {
        "tools": tools,
        "default_tools": list(DEFAULT_TOOLS),
        "switch_managed_tools": list(SWITCH_MANAGED_TOOLS),
    }


# 类型预设（对齐 `config/agent_type_presets.yaml`，仅保留 default + zh-CN）
_TYPE_PRESETS: list[dict[str, Any]] = [
    {
        "id": AGENT_TYPE_RAG_QA,
        "i18n": {
            "default": {"label": "RAG Q&A", "description": "Evidence-based retrieval over document chunks."},
            "zh-CN": {"label": "RAG 问答", "description": "基于文档分块的检索式问答。"},
        },
        "config": {
            "temperature": 0.7,
            "max_iterations": 30,
            "allowed_tools": ["search_knowledge", "read_document", "list_documents"],
            "faq_priority_enabled": True,
            "kb_selection_mode": "all",
        },
    },
    {
        "id": AGENT_TYPE_WIKI_QA,
        "i18n": {
            "default": {"label": "Wiki Q&A", "description": "Wiki-first answering across pages."},
            "zh-CN": {"label": "Wiki 问答", "description": "以 Wiki 为主的检索与图谱跳转回答。"},
        },
        "config": {
            "temperature": 0.7,
            "max_iterations": 30,
            "allowed_tools": ["wiki_search", "wiki_read_page", "read_document", "wiki_flag_issue"],
            "kb_selection_mode": "all",
        },
    },
    {
        "id": AGENT_TYPE_HYBRID_RAG_WIKI,
        "i18n": {
            "default": {"label": "Hybrid (Wiki + RAG)", "description": "Uses wiki pages and chunk retrieval together."},
            "zh-CN": {"label": "Wiki + RAG 混合", "description": "先用 Wiki 建立导航，再用分块检索精确引用。"},
        },
        "config": {
            "temperature": 0.7,
            "max_iterations": 40,
            "allowed_tools": [
                "wiki_search", "wiki_read_page", "search_knowledge",
                "read_document", "list_documents", "wiki_flag_issue",
            ],
            "faq_priority_enabled": True,
            "kb_selection_mode": "all",
        },
    },
    {
        "id": AGENT_TYPE_DATA_ANALYSIS,
        "i18n": {
            "default": {"label": "Data Analysis", "description": "SQL queries and statistics over tabular files."},
            "zh-CN": {"label": "数据分析", "description": "对 CSV / Excel 等表格文件执行 SQL 查询和统计分析。"},
        },
        "config": {
            "temperature": 0.3,
            "max_iterations": 30,
            "allowed_tools": ["data_schema", "data_analysis"],
            "web_search_enabled": False,
            "supported_file_types": ["csv", "xlsx"],
            "kb_selection_mode": "all",
        },
        "kb_filter": {"none_of": ["faq"]},
    },
    {
        "id": AGENT_TYPE_CUSTOM,
        "i18n": {
            "default": {"label": "Custom", "description": "Full control."},
            "zh-CN": {"label": "自定义", "description": "完全自定义：自行选择工具、提示词和知识库。"},
        },
    },
]


def type_presets() -> list[dict[str, Any]]:
    return [dict(item) for item in _TYPE_PRESETS]


# 占位符（对齐 `internal/types/placeholder.go`）
_PLACEHOLDERS: dict[str, list[dict[str, str]]] = {
    "all": [
        {"name": "query", "label": "用户问题", "description": "用户当前的问题或查询内容"},
        {"name": "contexts", "label": "检索内容", "description": "从知识库检索到的相关内容列表"},
        {"name": "current_time", "label": "当前时间", "description": "当前日期"},
        {"name": "current_week", "label": "当前星期", "description": "当前星期几"},
        {"name": "conversation", "label": "历史对话", "description": "格式化的历史对话内容"},
        {"name": "yesterday", "label": "昨天日期", "description": "昨天的日期"},
        {"name": "answer", "label": "助手回答", "description": "助手的回答内容"},
        {"name": "knowledge_bases", "label": "知识库列表", "description": "自动格式化的知识库列表"},
        {"name": "web_search_status", "label": "网络搜索状态", "description": "网络搜索工具是否启用的状态"},
        {"name": "language", "label": "用户语言", "description": "用户界面的语言偏好"},
    ],
    "system_prompt": [
        {"name": "query", "label": "用户问题", "description": "用户当前的问题或查询内容"},
        {"name": "contexts", "label": "检索内容", "description": "从知识库检索到的相关内容列表"},
        {"name": "current_time", "label": "当前时间", "description": "当前日期"},
        {"name": "current_week", "label": "当前星期", "description": "当前星期几"},
        {"name": "language", "label": "用户语言", "description": "用户界面的语言偏好"},
    ],
    "agent_system_prompt": [
        {"name": "knowledge_bases", "label": "知识库列表", "description": "自动格式化的知识库列表"},
        {"name": "web_search_status", "label": "网络搜索状态", "description": "网络搜索工具是否启用的状态"},
        {"name": "current_time", "label": "当前时间", "description": "当前日期"},
        {"name": "language", "label": "用户语言", "description": "用户界面的语言偏好"},
    ],
    "context_template": [
        {"name": "query", "label": "用户问题", "description": "用户当前的问题或查询内容"},
        {"name": "contexts", "label": "检索内容", "description": "从知识库检索到的相关内容列表"},
        {"name": "current_time", "label": "当前时间", "description": "当前日期"},
        {"name": "current_week", "label": "当前星期", "description": "当前星期几"},
        {"name": "language", "label": "用户语言", "description": "用户界面的语言偏好"},
    ],
    "rewrite_system_prompt": [
        {"name": "query", "label": "用户问题", "description": "用户当前的问题或查询内容"},
        {"name": "conversation", "label": "历史对话", "description": "格式化的历史对话内容"},
        {"name": "current_time", "label": "当前时间", "description": "当前日期"},
        {"name": "yesterday", "label": "昨天日期", "description": "昨天的日期"},
        {"name": "language", "label": "用户语言", "description": "用户界面的语言偏好"},
    ],
    "rewrite_prompt": [
        {"name": "query", "label": "用户问题", "description": "用户当前的问题或查询内容"},
        {"name": "conversation", "label": "历史对话", "description": "格式化的历史对话内容"},
        {"name": "current_time", "label": "当前时间", "description": "当前日期"},
        {"name": "yesterday", "label": "昨天日期", "description": "昨天的日期"},
        {"name": "language", "label": "用户语言", "description": "用户界面的语言偏好"},
    ],
    "fallback_prompt": [
        {"name": "query", "label": "用户问题", "description": "用户当前的问题或查询内容"},
        {"name": "language", "label": "用户语言", "description": "用户界面的语言偏好"},
    ],
}


def placeholders() -> dict[str, list[dict[str, str]]]:
    return {key: [dict(item) for item in value] for key, value in _PLACEHOLDERS.items()}
