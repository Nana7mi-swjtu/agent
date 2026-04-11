import concurrent.futures
import importlib
import json
import os
import re
import warnings
from typing import Any, Dict, Optional
from env_loader import load_env_file

load_env_file()


def _suppress_neo4j_apoc_deprecation_warning() -> None:
    """屏蔽 Neo4j/APOC 的弃用告警，避免影响控制台输出。"""
    flag = os.getenv("SUPPRESS_NEO4J_DEPRECATION_WARNING", "true").strip().lower()
    if flag not in {"1", "true", "yes", "y", "on"}:
        return

    try:
        from neo4j.warnings import Neo4jWarning

        warnings.filterwarnings(
            "ignore",
            category=Neo4jWarning,
            message=r".*(FeatureDeprecationWarning|apoc|APOC).*",
        )
    except Exception:
        return


_suppress_neo4j_apoc_deprecation_warning()


SQL_KEYWORDS_PATTERN = re.compile(
    r"\b(SELECT|FROM|WHERE|GROUP\s+BY|ORDER\s+BY|JOIN|HAVING|UNION|INSERT|UPDATE|DELETE)\b",
    re.IGNORECASE,
)

CYPHER_START_KEYWORDS = (
    "MATCH",
    "OPTIONAL MATCH",
    "WITH",
    "UNWIND",
    "CALL",
    "RETURN",
    "MERGE",
    "CREATE",
)


def _build_cypher_prompt_template() -> Any:
    try:
        prompt_cls = importlib.import_module("langchain_core.prompts").PromptTemplate
    except Exception as error:
        raise ImportError(
            "缺少依赖，请安装: pip install langchain-core"
        ) from error

    template = """你是 Neo4j Cypher 专家。请把用户问题转换为可执行的 Cypher。

严格要求：
1) 只能输出 Cypher，不要输出 SQL，不要输出解释文字。
2) 禁止出现 SELECT/UPDATE/INSERT/DELETE/FROM/JOIN 等 SQL 关键字。
3) 仅可使用以下 schema 中出现的标签、关系和属性。

Schema:
{schema}

Question:
{question}
"""
    return prompt_cls(input_variables=["schema", "question"], template=template)


def _extract_llm_text(llm_response: Any) -> str:
    if llm_response is None:
        return ""

    content = getattr(llm_response, "content", llm_response)
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(p.strip() for p in parts if p and p.strip()).strip()

    return str(content).strip()


def _is_empty_graph_context(context: Any) -> bool:
    if context is None:
        return True
    if isinstance(context, (list, tuple, set, dict)) and len(context) == 0:
        return True
    return False


def _sanitize_cypher_text(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""

    cleaned = re.sub(r"```(?:cypher)?", "", raw, flags=re.IGNORECASE).replace("```", "").strip()
    upper_cleaned = cleaned.upper()

    first_pos = -1
    for keyword in CYPHER_START_KEYWORDS:
        pos = upper_cleaned.find(keyword)
        if pos != -1 and (first_pos == -1 or pos < first_pos):
            first_pos = pos

    if first_pos > 0:
        cleaned = cleaned[first_pos:].strip()

    if ";" in cleaned:
        cleaned = cleaned.split(";", 1)[0].strip()

    return cleaned


def _looks_like_cypher(text: str) -> bool:
    normalized = _sanitize_cypher_text(text)
    if not normalized:
        return False
    upper_text = normalized.upper()
    return any(upper_text.startswith(item) for item in CYPHER_START_KEYWORDS)


def _extract_entity_hint(question: str) -> str:
    text = str(question or "").strip()
    if not text:
        return ""

    patterns = [
        r"和(.+?)同行业",
        r"与(.+?)同行业",
        r"(.+?)同行业",
        r"(.+?)相关",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = match.group(1).strip(" ，。！？；：,.!?;:")
            if candidate:
                return candidate

    fallback = re.split(r"[，。！？；：,.!?;:]", text)[0].strip()
    if len(fallback) > 20:
        fallback = fallback[:20]
    return fallback


def _escape_cypher_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


class GraphCypherQueryTool:
    """基于 LangChain GraphCypherQAChain 的 Neo4j 图查询工具。"""

    def __init__(
        self,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        llm: Any,
        enhanced_schema: bool = False,
        validate_cypher: bool = True,
        allow_dangerous_requests: bool = True,
        top_k: int = 20,
        verbose: bool = False,
        return_intermediate_steps: bool = True,
        timeout_seconds: int = 30,
    ):
        neo4j_graph_cls, _ = _load_graph_chain_components()

        self.graph = neo4j_graph_cls(
            url=neo4j_uri,
            username=neo4j_user,
            password=neo4j_password,
            enhanced_schema=enhanced_schema,
        )
        self.llm = llm
        self.top_k = max(1, int(top_k))
        self.timeout_seconds = timeout_seconds

    def ask(self, question: str, conversation_history: Optional[list] = None) -> Dict[str, Any]:
        """
        询问问题，支持对话历史上下文。
        
        Args:
            question: 当前问题
            conversation_history: 对话历史列表，格式 [{"role": "user"|"assistant", "content": "..."}, ...]
        """
        enhanced_question = self._enhance_question(question, conversation_history)
        
        schema = str(getattr(self.graph, "schema", "") or "")
        cypher_prompt_template = _build_cypher_prompt_template()
        cypher_prompt = cypher_prompt_template.format(schema=schema, question=enhanced_question)

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.llm.invoke, cypher_prompt)
                cypher_resp = future.result(timeout=self.timeout_seconds)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(
                f"查询超时（{self.timeout_seconds}s）。"
                f"可设置环境变量 QUERY_TIMEOUT_SECONDS 增加超时时长。"
            )
        except Exception as error:
            return self._fallback_to_llm(
                question=question,
                conversation_history=conversation_history,
                fallback_reason=f"Cypher 生成异常: {error}",
                error=error,
            )

        cypher = _sanitize_cypher_text(_extract_llm_text(cypher_resp))
        answer = ""
        context: Any = None

        if cypher and not _looks_like_cypher(cypher):
            fallback_cypher, fallback_context = self._try_heuristic_graph_query(question)
            if fallback_cypher and not _is_empty_graph_context(fallback_context):
                return self._answer_from_graph_result(question, fallback_cypher, fallback_context)
            return self._fallback_to_llm(
                question=question,
                conversation_history=conversation_history,
                fallback_reason="生成结果不是合法 Cypher，已自动降级到通用回答",
                raw={"cypher": cypher},
            )

        if cypher and SQL_KEYWORDS_PATTERN.search(cypher):
            fallback_cypher, fallback_context = self._try_heuristic_graph_query(question)
            if fallback_cypher and not _is_empty_graph_context(fallback_context):
                return self._answer_from_graph_result(question, fallback_cypher, fallback_context)
            return self._fallback_to_llm(
                question=question,
                conversation_history=conversation_history,
                fallback_reason="检测到非 Cypher 查询语句（疑似 SQL）",
                raw={"cypher": cypher},
            )

        if not cypher or cypher.strip().upper() == "NO_CYPHER":
            fallback_cypher, fallback_context = self._try_heuristic_graph_query(question)
            if fallback_cypher and not _is_empty_graph_context(fallback_context):
                return self._answer_from_graph_result(question, fallback_cypher, fallback_context)
            return self._fallback_to_llm(
                question=question,
                conversation_history=conversation_history,
                fallback_reason="未生成有效 Cypher 语句",
                raw={"cypher": cypher},
            )

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.graph.query, cypher)
                context = future.result(timeout=self.timeout_seconds)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(
                f"图谱查询执行超时（{self.timeout_seconds}s）。"
                f"可设置环境变量 QUERY_TIMEOUT_SECONDS 增加超时时长。"
            )
        except Exception as error:
            return self._fallback_to_llm(
                question=question,
                conversation_history=conversation_history,
                fallback_reason=f"图谱查询异常: {error}",
                error=error,
                raw={"cypher": cypher},
            )

        if isinstance(context, list):
            context = context[: self.top_k]

        if _is_empty_graph_context(context):
            return {
                "question": question,
                "answer": "知识图谱中未检索到相关知识，请尝试更具体的实体名称或关系描述。",
                "cypher": cypher,
                "context": context,
                "source": "knowledge_graph_empty",
                "fallback_reason": "知识图谱中未检索到相关知识",
                "raw": {"cypher": cypher, "context": context},
                "error": "",
            }

        return self._answer_from_graph_result(question, cypher, context)

    def _try_heuristic_graph_query(self, question: str) -> tuple[str, Any]:
        entity = _extract_entity_hint(question)
        if not entity:
            return "", None
        safe_entity = _escape_cypher_string(entity)
        heuristic_cypher = (
            f"MATCH (n)-[r]-(m) "
            f"WHERE any(k IN keys(n) WHERE toString(n[k]) CONTAINS '{safe_entity}') "
            f"RETURN n, r, m LIMIT {self.top_k}"
        )

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.graph.query, heuristic_cypher)
                context = future.result(timeout=self.timeout_seconds)
        except Exception:
            return "", None
        return heuristic_cypher, context

    def _answer_from_graph_result(self, question: str, cypher: str, context: Any) -> Dict[str, Any]:
        answer_prompt = (
            "你是金融知识图谱分析助手。"
            "请严格基于给定图谱查询结果回答用户问题，先给结论，再给简要依据。\n\n"
            f"用户问题：{question}\n"
            f"Cypher：{cypher}\n"
            f"图谱结果(JSON)：{json.dumps(context, ensure_ascii=False)}"
        )

        answer = ""
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.llm.invoke, answer_prompt)
                answer_resp = future.result(timeout=self.timeout_seconds)
            answer = _extract_llm_text(answer_resp)
        except Exception:
            answer = ""

        if not answer:
            answer = f"已检索到 {len(context) if isinstance(context, list) else 1} 条图谱结果。"

        return {
            "question": question,
            "answer": answer,
            "cypher": cypher,
            "context": context,
            "source": "knowledge_graph",
            "fallback_reason": "",
            "raw": {"cypher": cypher, "context": context},
        }

    def _fallback_to_llm(
        self,
        question: str,
        conversation_history: Optional[list],
        fallback_reason: str,
        raw: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None,
    ) -> Dict[str, Any]:
        enhanced_question = self._enhance_question(question, conversation_history)
        fallback_prompt = (
            "以下回答未使用知识图谱检索结果，仅基于大模型通用知识生成。"
            "请优先给出简洁结论，再给出理由。\n\n"
            f"用户问题：{enhanced_question}"
        )

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.llm.invoke, fallback_prompt)
                llm_resp = future.result(timeout=self.timeout_seconds)
            fallback_answer = _extract_llm_text(llm_resp)
        except concurrent.futures.TimeoutError:
            fallback_answer = (
                f"图谱查询失败且降级回答超时（{self.timeout_seconds}s）。"
                "请稍后重试，或提高 QUERY_TIMEOUT_SECONDS。"
            )
        except Exception as fallback_error:
            fallback_answer = f"图谱查询失败，降级回答也不可用：{fallback_error}"

        return {
            "question": question,
            "answer": fallback_answer,
            "cypher": "",
            "context": None,
            "source": "llm_fallback",
            "fallback_reason": fallback_reason,
            "raw": raw or {},
            "error": str(error) if error else "",
        }

    def _enhance_question(self, question: str, conversation_history: Optional[list]) -> str:
        """拼接对话历史和系统提示到问题中，实现上下文理解。"""
        if not conversation_history or len(conversation_history) == 0:
            return question
        
        recent_history = conversation_history[-10:]
        history_text = "【前面的对话记录】\n"
        for msg in recent_history:
            role = "提问" if msg.get("role") == "user" else "回答"
            content = msg.get("content", "").strip()
            if len(content) > 200:
                content = content[:200] + "..."
            history_text += f"\n{role}: {content}"
        
        system_prompt = """你是一个知识图谱专家。请根据前面的对话上下文理解用户的问题。
特别注意：
- 如果用户用了代词（如"它"、"他们"、"这些"等），根据上文推断具体指什么。
- 如果用户提到了前面出现过的公司或概念，继续围绕该主题进行分析。
- 保持回答的连贯性和上下文逻辑。"""
        
        enhanced = f"{system_prompt}\n{history_text}\n\n【当前问题】{question}"
        return enhanced

    def run(self, question: str, conversation_history: Optional[list] = None) -> str:
        return self.ask(question, conversation_history=conversation_history)["answer"]


def _load_graph_chain_components():
    try:
        try:
            neo4j_graph_cls = importlib.import_module("langchain_neo4j").Neo4jGraph
        except Exception:
            neo4j_graph_cls = importlib.import_module("langchain_community.graphs").Neo4jGraph
        graph_cypher_chain_cls = importlib.import_module(
            "langchain_community.chains.graph_qa.cypher"
        ).GraphCypherQAChain
        return neo4j_graph_cls, graph_cypher_chain_cls
    except Exception as error:
        raise ImportError(
            "缺少依赖，请安装: pip install langchain langchain-community langchain-neo4j"
        ) from error


def _build_spark_llm(model: Optional[str] = None, temperature: float = 0):
    """
    使用讯飞星火 WebSocket 协议接入（wss://）。
    """
    try:
        from langchain_community.chat_models import ChatSparkLLM
    except Exception as error:
        raise ImportError(
            "缺少依赖，请安装: pip install langchain-community websocket-client"
        ) from error

    spark_app_id = os.getenv("SPARK_APP_ID")
    spark_api_key = os.getenv("SPARK_API_KEY")
    spark_api_secret = os.getenv("SPARK_API_SECRET")
    spark_api_url = os.getenv("SPARK_API_URL", "wss://spark-api.xf-yun.com/v3.5/chat")
    spark_model = model or os.getenv("SPARK_MODEL", "generalv3.5")

    if not spark_app_id:
        raise ValueError("请先设置环境变量 SPARK_APP_ID")
    if not spark_api_key:
        raise ValueError("请先设置环境变量 SPARK_API_KEY")
    if not spark_api_secret:
        raise ValueError("请先设置环境变量 SPARK_API_SECRET")

    return ChatSparkLLM(
        app_id=spark_app_id,
        api_key=spark_api_key,
        api_secret=spark_api_secret,
        api_url=spark_api_url,
        model=spark_model,
        temperature=temperature,
    )


def create_graph_cypher_tool_from_env(
    llm: Optional[Any] = None,
    validate_cypher: bool = False,
    allow_dangerous_requests: Optional[bool] = None,
    top_k: int = 20,
    verbose: bool = False,
    timeout_seconds: int = 30,
) -> GraphCypherQueryTool:
    """
    创建图查询工具。

    Args:
        validate_cypher: 是否启用 LangChain 的 Cypher 查询矫正（默认 False）。
                        True 时使用正则式矫正可能导致查询卡顿（灾难性回溯）；
                        False 时直接使用 LLM 生成的 Cypher，避免正则回溯问题。
        timeout_seconds: 查询超时时长（秒），默认 30s，可通过 QUERY_TIMEOUT_SECONDS 环境变量覆盖。
    """
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD")

    env_timeout = os.getenv("QUERY_TIMEOUT_SECONDS")
    if env_timeout:
        try:
            timeout_seconds = int(env_timeout)
        except ValueError:
            pass

    env_top_k = os.getenv("GRAPH_QUERY_TOP_K")
    if env_top_k:
        try:
            top_k = max(1, int(env_top_k))
        except ValueError:
            pass

    if not neo4j_password:
        raise ValueError("请先设置环境变量 NEO4J_PASSWORD")

    env_enhanced = os.getenv("ENHANCED_SCHEMA", "false").strip().lower()
    enhanced_schema = env_enhanced in {"1", "true", "yes", "y", "on"}

    env_allow = os.getenv("ALLOW_DANGEROUS_REQUESTS", "true").strip().lower()
    final_allow = allow_dangerous_requests
    if final_allow is None:
        final_allow = env_allow in {"1", "true", "yes", "y", "on"}
    if final_allow is not True:
        raise ValueError(
            "当前项目要求 GraphCypherQAChain 开启 allow_dangerous_requests=True，"
            "请设置 ALLOW_DANGEROUS_REQUESTS=true 或显式传入 allow_dangerous_requests=True"
        )

    final_llm = llm or _build_spark_llm()
    return GraphCypherQueryTool(
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
        llm=final_llm,
        enhanced_schema=enhanced_schema,
        validate_cypher=validate_cypher,
        allow_dangerous_requests=final_allow,
        top_k=top_k,
        verbose=verbose,
        timeout_seconds=timeout_seconds,
    )


_GRAPH_QA_TOOL: Optional[GraphCypherQueryTool] = None


def query_graph(question: str, conversation_history: Optional[list] = None) -> str:
    """给智能体调用的最简接口：输入自然语言问题，返回答案字符串。
    
    Args:
        question: 问题文本
        conversation_history: 对话历史（可选），用于上下文理解
    """
    global _GRAPH_QA_TOOL
    if _GRAPH_QA_TOOL is None:
        _GRAPH_QA_TOOL = create_graph_cypher_tool_from_env()
    result = _GRAPH_QA_TOOL.ask(question, conversation_history=conversation_history)
    return result.get("answer", "")


def query_graph_with_trace(question: str, conversation_history: Optional[list] = None) -> Dict[str, Any]:
    """给智能体调试/思考使用：返回 answer + 生成的 cypher + 查询上下文。
    
    Args:
        question: 问题文本
        conversation_history: 对话历史（可选），用于上下文理解
    """
    global _GRAPH_QA_TOOL
    if _GRAPH_QA_TOOL is None:
        _GRAPH_QA_TOOL = create_graph_cypher_tool_from_env()
    return _GRAPH_QA_TOOL.ask(question, conversation_history=conversation_history)


def _extract_intermediate(raw: Dict[str, Any]):
    cypher = ""
    context: Any = None
    steps = raw.get("intermediate_steps")
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict) and not cypher and "query" in step:
                cypher = step["query"]
            if isinstance(step, dict) and context is None and "context" in step:
                context = step["context"]
    return cypher, context


if __name__ == "__main__":
    demo_question = os.getenv("DEMO_QUESTION", "和贵州茅台同行业的公司有哪些？")
    print("🧠 提问:", demo_question)
    print("📌 回答:", query_graph(demo_question))
