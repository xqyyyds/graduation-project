import json
import concurrent.futures
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.core.llm_factory import get_main_llm
from app.core.logger import logger
from app.core.prompts import (
    AGENT_C_CATEGORY_RECHECK_TEMPLATE,
    AGENT_C_EVIDENCE_TEMPLATE,
    AGENT_C_FINAL_TEMPLATE,
)
from app.core.schemas import (
    ViolationCaseStage1Batch,
)
from app.db.chroma_manager import chroma_db
from app.services.utils import normalize_category


class AgentCompliance:
    """
    Agent C（审核 + 证据链两阶段）：
    1. 第一阶段：对主贴/评论一次性做审核判定（违规与否、类别、风险）
    2. 第二阶段：仅对已判违规项补充法规依据与证据链
    3. 保留类别为空时的一次 LLM 类别复核与法规检索链路
    """

    LAW_MATCH_WORKERS = 4
    DISPOSAL_OPTIONS = [
        "限制/更改/屏蔽/删除相关内容的展示",
        "撤销/删除/禁止修改账号认证、个人信息",
        "禁言、禁点赞、禁被关注、禁发送及接收私信",
        "扣除信用积分、中止或扣除广告共享收益、暂停/终止服务、注销账号",
        "向有关监管部门或国家机关报告",
        "其他合理措施",
    ]

    def __init__(self):
        self.audit_llm = get_main_llm(
            temperature=0.1,
            request_timeout=180,
            max_retries=2,
        )

        logger.info(" [Agent C] 已启用两阶段模式：先审核，再补法规与证据链。")
        self.valid_categories = [
            "时政有害-国家安全",
            "时政有害-极端主义",
            "时政有害-英烈历史",
            "时政有害-社会秩序",
            "违法信息-公共秩序",
            "违法信息-色情",
            "违法信息-色情引流",
            "违法信息-违禁品",
            "违法信息-开盒",
            "违法信息-网暴煽动",
            "违法信息-开盒黑产",
            "诈骗信息-仿冒",
            "诈骗信息-兼职",
            "诈骗信息-票务",
            "诈骗信息-投资",
            "诈骗信息-技术手段",
            "不良信息-饭圈",
            "不良信息-网暴",
            "不良信息-违背公序良俗",
            "不良信息-感官不适",
            "人身攻击-侮辱",
            "人身攻击-不友善",
            "人身攻击-仇恨歧视",
            "人身攻击-账号信息",
            "侵权权益-基础权益",
            "侵权权益-抄袭",
            "侵权权益-虚假认证",
            "侵权权益-认证黑产",
            "侵权权益-严重纠纷",
            "不良价值-性别对立",
            "不良价值-拜金炫富",
            "不良价值-恶意营销",
            "不良价值-低俗哗众",
            "不良价值-崇洋媚外",
            "不实信息-造谣",
            "不实信息-冒充",
            "不实信息-技术伪造",
            "AI生成-未标识",
            "AI生成-误导",
            "AI生成-违规内容",
            "违规营销-标题党",
            "违规营销-引战",
            "违规营销-低俗",
            "违规营销-歪曲政策",
            "涉未成年人-色情低俗",
            "涉未成年人-人身权益",
            "涉未成年人-不良诱导",
            "垃圾行为-骚扰",
            "垃圾行为-刷量",
            "垃圾行为-水贴",
            "垃圾行为-导流",
            "垃圾行为-违规招募",
            "垃圾行为-黑产交易",
        ]

    @staticmethod
    def _is_content_filter(e: Exception) -> bool:
        msg = str(e).lower()
        return any(
            kw in msg
            for kw in [
                "content_filter",
                "content filter",
                "content management",
                "sensitive",
                "refused",
                "refusal",
                "harmful",
                "responsibleaipolicy",
                "safety",
            ]
        )

    @staticmethod
    def _is_timeout(e: Exception) -> bool:
        msg = str(e).lower()
        return any(kw in msg for kw in ["timed out", "timeout", "read timeout"])

    @staticmethod
    def _is_retryable_evidence_error(e: Exception) -> bool:
        """证据链增强的轻量重试判定：仅对瞬时异常重试一次。"""
        msg = str(e).lower()

        # 内容策略与提示词/结构化输出错误不做重试，避免无效调用。
        if AgentCompliance._is_content_filter(e):
            return False
        non_retryable_keywords = [
            "missing variables",
            "invalid_prompt_input",
            "validationerror",
            "pydantic",
            "output parser",
            "jsondecodeerror",
            "schema",
        ]
        if any(kw in msg for kw in non_retryable_keywords):
            return False

        if AgentCompliance._is_timeout(e):
            return True

        retryable_keywords = [
            "rate limit",
            "too many requests",
            "429",
            "500",
            "502",
            "503",
            "504",
            "service unavailable",
            "connection",
            "temporarily unavailable",
            "internal server error",
        ]
        return any(kw in msg for kw in retryable_keywords)

    @staticmethod
    def _clean_text(text: Any) -> str:
        value = str(text or "").strip()
        if not value:
            return ""
        return " ".join(value.split())

    @staticmethod
    def _is_stage1_json_parse_error(e: Exception) -> bool:
        """判断是否为阶段1结构化JSON解析失败（如 trailing characters）。"""
        msg = str(e).lower()
        return "validation error for violationcasestage1batch" in msg and (
            "json_invalid" in msg
            or "invalid json" in msg
            or "trailing characters" in msg
        )

    @staticmethod
    def _extract_first_json_object(raw_text: str) -> str:
        """从模型原始文本中提取首个完整JSON对象，容忍前后杂质文本。"""
        if not raw_text:
            return ""

        text = str(raw_text)
        start = text.find("{")
        if start < 0:
            return ""

        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                    continue
                if ch == "\\":
                    escaped = True
                    continue
                if ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

        return ""

    @staticmethod
    def _message_content_to_text(content: Any) -> str:
        """兼容不同provider返回形态，将消息content统一为纯文本。"""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join([p for p in parts if p])
        return str(content or "")

    def _build_candidate_pool(
        self, post_packet: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        pool: List[Dict[str, Any]] = []
        post_content = self._clean_text(post_packet.get("content"))
        if post_content:
            pool.append(
                {
                    "index": -1,
                    "source_type": "post",
                    "source_id": str(post_packet.get("note_id") or ""),
                    "content": post_content,
                }
            )

        for idx, item in enumerate(post_packet.get("audit_comment_items") or []):
            content = self._clean_text(item.get("content"))
            if not content:
                continue
            pool.append(
                {
                    "index": idx,
                    "source_type": "comment",
                    "source_id": str(item.get("comment_id") or ""),
                    "db_id": item.get("db_id", ""),
                    "content": content,
                    "comment_like_count": item.get("comment_like_count", "0"),
                    "create_date_time": item.get("create_date_time", ""),
                }
            )
        return pool

    def _canonicalize_category(self, raw_category: str, fallback: str = "") -> str:
        value = normalize_category(raw_category or "")
        fallback_value = normalize_category(fallback or "")

        if value in self.valid_categories:
            return value

        if fallback_value in self.valid_categories:
            return fallback_value

        # 不做关键词映射与模糊兜底，避免人工规则覆盖模型判定。
        return ""

    def _passes_violation_floor(self, case: Dict[str, Any]) -> bool:
        # 仅做最小结构校验：是否判违规、类别是否在白名单、是否有可定位文本。
        if not bool(case.get("is_violation", True)):
            return False

        category = self._canonicalize_category(case.get("category", ""))
        quote = self._clean_text(case.get("quote"))
        content = self._clean_text(case.get("content"))

        if not category:
            return False

        return bool(quote or content)

    @staticmethod
    def _chunk(items: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
        return [items[i : i + size] for i in range(0, len(items), size)]

    @staticmethod
    def _invoke_finalize_chain(
        llm,
        event_name: str,
        source_keyword: str,
        post_content: str,
        candidate_items: List[Dict[str, Any]],
        categories: List[str],
    ):
        chain = ChatPromptTemplate.from_template(
            AGENT_C_FINAL_TEMPLATE
        ) | llm.with_structured_output(ViolationCaseStage1Batch)
        return chain.invoke(
            {
                "event_name": event_name,
                "source_keyword": source_keyword,
                "categories": ", ".join(categories),
                "post_content": post_content,
                "candidate_items": json.dumps(candidate_items, ensure_ascii=False),
            }
        )

    @staticmethod
    def _invoke_final_chain_lenient(
        llm,
        event_name: str,
        source_keyword: str,
        post_content: str,
        candidate_items: List[Dict[str, Any]],
        categories: List[str],
    ) -> ViolationCaseStage1Batch:
        """结构化解析失败时的宽容回退：同提示词二次调用并提取首个JSON对象。"""
        chain = ChatPromptTemplate.from_template(AGENT_C_FINAL_TEMPLATE) | llm
        raw_message = chain.invoke(
            {
                "event_name": event_name,
                "source_keyword": source_keyword,
                "categories": ", ".join(categories),
                "post_content": post_content,
                "candidate_items": json.dumps(candidate_items, ensure_ascii=False),
            }
        )

        raw_text = AgentCompliance._message_content_to_text(
            getattr(raw_message, "content", raw_message)
        )
        json_text = AgentCompliance._extract_first_json_object(raw_text)
        if not json_text:
            raise ValueError("阶段1宽容解析失败：未从模型输出中提取到JSON对象")
        return ViolationCaseStage1Batch.model_validate_json(json_text)

    @staticmethod
    def _invoke_final_chain(
        llm,
        event_name: str,
        source_keyword: str,
        post_content: str,
        candidate_items: List[Dict[str, Any]],
        categories: List[str],
    ):
        """兼容旧调用口径：统一走第一阶段审核链。"""
        return AgentCompliance._invoke_finalize_chain(
            llm=llm,
            event_name=event_name,
            source_keyword=source_keyword,
            post_content=post_content,
            candidate_items=candidate_items,
            categories=categories,
        )

    def _default_stage1_case(self, item: Dict[str, Any]) -> Dict[str, Any]:
        content = self._clean_text(item.get("content", ""))
        return {
            "index": int(item.get("index", -1)),
            "source_type": item.get("source_type") or "comment",
            "source_id": str(item.get("source_id") or ""),
            "content": content,
            "quote": content[:120],
            "category": "",
            "reasoning": "阶段1未返回有效结果，按不违规处理。",
            "is_violation": False,
        }

    def _finalize_batch(
        self,
        post_content: str,
        candidate_items: List[Dict[str, Any]],
        batch_size: int,
        event_name: str = "",
        source_keyword: str = "",
        llm=None,
        llm_name: str = "strong",
        allow_backup: bool = True,
    ) -> Tuple[List[Dict[str, Any]], int]:
        blocked_count = 0
        if not candidate_items:
            return [], blocked_count

        llm = llm or self.audit_llm
        try:
            result = None
            stage1_error: Optional[Exception] = None
            try:
                result = self._invoke_final_chain(
                    llm=llm,
                    event_name=event_name,
                    source_keyword=source_keyword,
                    post_content=post_content,
                    candidate_items=candidate_items,
                    categories=self.valid_categories,
                )
            except TypeError:
                result = self._invoke_final_chain(
                    llm,
                    post_content,
                    candidate_items,
                )

            except Exception as e:
                stage1_error = e

            if (
                result is None
                and stage1_error
                and self._is_stage1_json_parse_error(stage1_error)
            ):
                logger.warning(
                    " [Agent C] 阶段1结构化解析失败，触发宽容JSON回退解析一次。"
                )
                try:
                    result = self._invoke_final_chain_lenient(
                        llm=llm,
                        event_name=event_name,
                        source_keyword=source_keyword,
                        post_content=post_content,
                        candidate_items=candidate_items,
                        categories=self.valid_categories,
                    )
                except Exception as lenient_error:
                    stage1_error = lenient_error

            if result is None:
                raise stage1_error or RuntimeError("阶段1审核未返回结果")

            candidate_by_index: Dict[int, Dict[str, Any]] = {}
            for item in candidate_items:
                try:
                    idx = int(item.get("index", -1))
                except Exception:
                    continue
                candidate_by_index[idx] = item

            parsed_by_index: Dict[int, Dict[str, Any]] = {}
            for case in result.cases:
                dumped = (
                    case.model_dump() if hasattr(case, "model_dump") else dict(case)
                )
                try:
                    idx = int(dumped.get("index", -1))
                except Exception:
                    continue

                base = candidate_by_index.get(idx)
                if not base:
                    continue

                quote = self._clean_text(dumped.get("quote", ""))
                content = self._clean_text(base.get("content", ""))
                merged = {
                    "index": idx,
                    "source_type": base.get("source_type") or "comment",
                    "source_id": str(base.get("source_id") or ""),
                    "content": content,
                    "quote": quote or content[:120],
                    "category": self._canonicalize_category(
                        dumped.get("category", ""),
                        fallback=base.get("candidate_category", ""),
                    ),
                    "reasoning": self._clean_text(dumped.get("reasoning", "")),
                    "is_violation": bool(dumped.get("is_violation", False)),
                }

                if not merged["is_violation"]:
                    merged["category"] = ""
                parsed_by_index[idx] = merged

            cases: List[Dict[str, Any]] = []
            for item in candidate_items:
                try:
                    idx = int(item.get("index", -1))
                except Exception:
                    continue
                cases.append(
                    parsed_by_index.get(idx) or self._default_stage1_case(item)
                )
            return cases, blocked_count
        except Exception as e:
            is_filtered = self._is_content_filter(e)
            is_timeout = self._is_timeout(e)

            if (is_filtered or is_timeout) and batch_size > 1:
                cases: List[Dict[str, Any]] = []
                for sub_batch in self._chunk(candidate_items, 1):
                    sub_cases, sub_blocked = self._finalize_batch(
                        post_content=post_content,
                        event_name=event_name,
                        source_keyword=source_keyword,
                        candidate_items=sub_batch,
                        batch_size=1,
                        llm=llm,
                        llm_name=llm_name,
                        allow_backup=allow_backup,
                    )
                    cases.extend(sub_cases)
                    blocked_count += sub_blocked
                return cases, blocked_count

            blocked_count += len(candidate_items)
            logger.warning(
                f" [Agent C] 阶段1审核批次失败，已跳过 {len(candidate_items)} 条: {e}"
            )
            return [], blocked_count

    def finalize_candidates(
        self,
        post_content: str,
        candidate_pool: List[Dict[str, Any]],
        suspects: List[Dict[str, Any]],
        event_name: str = "",
        source_keyword: str = "",
    ) -> Tuple[List[Dict[str, Any]], int]:
        by_index = {item["index"]: item for item in candidate_pool}
        blocked_count = 0
        final_cases: List[Dict[str, Any]] = []

        batches: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = []
        for suspect in suspects:
            base = by_index.get(suspect.get("index"))
            if not base:
                continue
            current.append(
                {
                    "index": base["index"],
                    "source_type": base["source_type"],
                    "source_id": base["source_id"],
                    "content": base["content"],
                    "candidate_category": suspect.get("category", ""),
                    "reason_brief": suspect.get("reason_brief", ""),
                }
            )
            if len(current) >= 5:
                batches.append(current)
                current = []
        if current:
            batches.append(current)

        for batch in batches:
            batch_cases, batch_blocked = self._finalize_batch(
                event_name=event_name,
                source_keyword=source_keyword,
                post_content=post_content,
                candidate_items=batch,
                batch_size=len(batch),
            )
            final_cases.extend(batch_cases)
            blocked_count += batch_blocked
        return final_cases, blocked_count

    @staticmethod
    def _risk_value(risk_level: str) -> int:
        return {"Low": 1, "Medium": 2, "High": 3}.get(risk_level or "Low", 1)

    @staticmethod
    def _normalize_risk_level(value: str) -> str:
        text = str(value or "").strip()
        return text if text in {"High", "Medium", "Low"} else ""

    def _derive_risk_level(self, case: Dict[str, Any], law_info: Dict[str, Any]) -> str:
        matched = (law_info or {}).get("matched_laws") or []
        levels: List[str] = []
        for law in matched:
            if not isinstance(law, dict):
                continue
            level = self._normalize_risk_level(
                law.get("risk_level") or law.get("risk") or ""
            )
            if level:
                levels.append(level)

        if levels:
            levels.sort(key=self._risk_value, reverse=True)
            return levels[0]

        fallback = self._normalize_risk_level(case.get("risk_level", ""))
        return fallback or "Low"

    def _normalize_disposal_suggestion(
        self, suggestion: str, risk_level: str, is_violation: bool
    ) -> str:
        text = self._clean_text(suggestion)
        if not is_violation:
            return self.DISPOSAL_OPTIONS[5]

        if text in self.DISPOSAL_OPTIONS:
            return text

        if any(k in text for k in ["认证", "实名", "冒名", "个人信息", "资料"]):
            return self.DISPOSAL_OPTIONS[1]
        if any(k in text for k in ["禁言", "禁赞", "禁点赞", "禁被关注", "私信"]):
            return self.DISPOSAL_OPTIONS[2]
        if any(
            k in text
            for k in ["积分", "信用", "收益", "暂停服务", "终止服务", "注销", "封号"]
        ):
            return self.DISPOSAL_OPTIONS[3]
        if any(k in text for k in ["公安", "监管", "国家机关", "报案", "移交", "举报"]):
            return self.DISPOSAL_OPTIONS[4]
        if any(k in text for k in ["删除", "屏蔽", "下架", "隐藏", "限制", "更改"]):
            return self.DISPOSAL_OPTIONS[0]

        if (risk_level or "").strip() == "High":
            return self.DISPOSAL_OPTIONS[3]
        return self.DISPOSAL_OPTIONS[5]

    class _EvidenceEnhanceResult(BaseModel):
        reasoning: str = Field(default="", description="违规理由精炼表述")
        disposal_suggestion: str = Field(default="", description="处置建议（六选一）")
        evidence_chain: List[str] = Field(
            default_factory=list, description="证据链要点"
        )

    def _invoke_evidence_chain(
        self,
        post_content: str,
        media_context: str,
        violated_items_json: str,
        laws_json: str,
    ) -> "AgentCompliance._EvidenceEnhanceResult":
        chain = ChatPromptTemplate.from_template(
            AGENT_C_EVIDENCE_TEMPLATE
        ) | self.audit_llm.with_structured_output(self._EvidenceEnhanceResult)
        return chain.invoke(
            {
                "post_content": post_content,
                "media_context": media_context,
                "violated_items_json": violated_items_json,
                "laws_json": laws_json,
            }
        )

    class _CategoryRecheckResult(BaseModel):
        category: str = Field(
            default="", description="纠偏后的白名单类别，无法确定则为空"
        )

    def _repair_category_once_by_llm(
        self, case: Dict[str, Any], current_category: str
    ) -> str:
        quote = self._clean_text(case.get("quote"))
        reasoning = self._clean_text(case.get("reasoning"))
        if not quote and not reasoning:
            return ""

        llm = self.audit_llm
        if not getattr(llm, "openai_api_key", None):
            return ""

        try:
            chain = ChatPromptTemplate.from_template(
                AGENT_C_CATEGORY_RECHECK_TEMPLATE
            ) | llm.with_structured_output(self._CategoryRecheckResult)
            result = chain.invoke(
                {
                    "current_category": current_category or "",
                    "categories": ", ".join(self.valid_categories),
                    "quote": quote,
                    "reasoning": reasoning,
                }
            )
            repaired = self._canonicalize_category(getattr(result, "category", ""))
            if (
                repaired
                and repaired in self.valid_categories
                and repaired != current_category
            ):
                return repaired
        except Exception as e:
            logger.warning(f" [Agent C] 类别复核失败，继续后续检索路径: {e}")
        return ""

    def _match_laws_for_case(self, case: Dict[str, Any]) -> Dict[str, Any]:
        canonical_category = self._canonicalize_category(case.get("category", ""))
        category_recheck_note = ""

        query = "；".join(
            [
                canonical_category or normalize_category(case.get("category", "")),
                case.get("quote", ""),
                case.get("reasoning", ""),
            ]
        ).strip("；")

        docs: List[Any] = []

        def _search_by_category(category: str) -> List[Any]:
            if not category:
                return []
            matched = chroma_db.search_related_laws(
                query=query,
                top_k=3,
                category_filter=category,
                use_hyde=False,
            )
            if not matched:
                matched = chroma_db.search_related_laws(
                    query=query,
                    top_k=3,
                    category_filter=category,
                    use_hyde=True,
                )
            return matched

        if canonical_category:
            docs = _search_by_category(canonical_category)

        if not docs:
            repaired_category = self._repair_category_once_by_llm(
                case, canonical_category
            )
            if repaired_category:
                docs = _search_by_category(repaired_category)
                if docs:
                    category_recheck_note = f"类别复核后改为“{repaired_category}”。"
                    canonical_category = repaired_category

        if not docs:
            docs = chroma_db.search_related_laws(
                query=query,
                top_k=3,
                category_filter=None,
                use_hyde=False,
            )
        if not docs:
            docs = chroma_db.search_related_laws(
                query=query,
                top_k=3,
                category_filter=None,
                use_hyde=True,
            )
        if not docs and canonical_category:
            docs = chroma_db.search_related_laws(
                query=canonical_category,
                top_k=3,
                category_filter=None,
                use_hyde=False,
            )

        matched_laws: List[Dict[str, Any]] = []
        for doc in docs or []:
            meta = getattr(doc, "metadata", {}) or {}
            matched_laws.append(
                {
                    "category": meta.get("category", canonical_category),
                    "article": meta.get("article", "未知"),
                    "risk_level": meta.get("risk_level", meta.get("risk", "Low")),
                    "rule": getattr(doc, "page_content", "") or "",
                    "full_desc": meta.get("full_desc", ""),
                }
            )

        if not matched_laws:
            return {
                "matched_laws": [],
                "primary_law": "",
                "law_reason": "未检索到可核验法规条款，按不违规放行。",
            }

        primary_law = matched_laws[0]
        if primary_law:
            desc = primary_law.get("full_desc") or primary_law.get("rule") or ""
            primary_law_text = (
                f"{primary_law.get('article', '未知条款')} {desc}".strip()
            )
            law_reason = (
                f"该内容被认定为“{case.get('category','')}”，与 {primary_law.get('article','未知条款')} "
                f"中关于“{desc[:40] or case.get('category','相关规则')}”的规定最接近。"
            )
            if category_recheck_note:
                law_reason = f"{category_recheck_note}{law_reason}"
        return {
            "matched_laws": matched_laws,
            "primary_law": primary_law_text,
            "law_reason": law_reason,
        }

    @staticmethod
    def _build_case_evidence_chain(
        case: Dict[str, Any], law_info: Dict[str, Any]
    ) -> List[str]:
        chain: List[str] = []
        quote = case.get("quote", "").strip()
        reasoning = case.get("reasoning", "").strip()
        primary_law = (law_info or {}).get("primary_law", "").strip()
        law_reason = (law_info or {}).get("law_reason", "").strip()

        if quote:
            chain.append(f"违规摘录：{quote}")
        if reasoning:
            chain.append(f"判定要点：{reasoning}")
        if primary_law:
            chain.append(f"主要依据：{primary_law}")
        if law_reason:
            chain.append(f"匹配说明：{law_reason}")
        return chain

    def repair_existing_violation_info(
        self, violation_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """修复历史审核结果，避免旧口径误判持续复用。"""
        info = dict(violation_info or {})

        post_case_raw = info.get("post_case") or None
        comment_cases_raw = info.get("comment_cases") or []

        normalized_cases: List[Dict[str, Any]] = []

        def _normalize_case(
            case: Dict[str, Any], source_type: str, default_index: int
        ) -> Optional[Dict[str, Any]]:
            if not isinstance(case, dict):
                return None

            normalized = dict(case)
            normalized["source_type"] = normalized.get("source_type") or source_type
            normalized["index"] = normalized.get("index", default_index)
            normalized["is_violation"] = bool(normalized.get("is_violation", True))
            normalized["category"] = self._canonicalize_category(
                normalized.get("category", "")
            )

            if not normalized.get("is_violation"):
                return None
            if not normalized.get("category"):
                return None
            if not self._passes_violation_floor(normalized):
                return None

            needs_law_patch = not normalized.get("primary_law") or not (
                normalized.get("matched_laws") or []
            )

            law_info = (
                self._match_laws_for_case(normalized)
                if needs_law_patch
                else {
                    "matched_laws": normalized.get("matched_laws") or [],
                    "primary_law": normalized.get("primary_law", ""),
                    "law_reason": normalized.get("law_reason", ""),
                }
            )

            merged = {**normalized, **law_info}
            if not (merged.get("matched_laws") or []):
                return None
            merged["risk_level"] = self._derive_risk_level(merged, law_info)
            merged["evidence_chain"] = self._build_case_evidence_chain(merged, law_info)
            return merged

        if post_case_raw:
            repaired_post = _normalize_case(post_case_raw, "post", -1)
            if repaired_post:
                normalized_cases.append(repaired_post)

        for raw_case in comment_cases_raw:
            repaired_comment = _normalize_case(
                raw_case,
                "comment",
                raw_case.get("index", -1) if isinstance(raw_case, dict) else -1,
            )
            if repaired_comment:
                normalized_cases.append(repaired_comment)

        post_case = None
        comment_cases: List[Dict[str, Any]] = []
        matched_laws_all: List[Dict[str, Any]] = []
        categories: List[str] = []
        overall_risk = "Low"

        for case in normalized_cases:
            if str(case.get("source_type", "")).lower() == "post":
                post_case = case
            else:
                comment_cases.append(case)

            for law in case.get("matched_laws") or []:
                if law not in matched_laws_all:
                    matched_laws_all.append(law)

            category = case.get("category")
            if category and category not in categories:
                categories.append(category)

            if self._risk_value(case.get("risk_level")) > self._risk_value(
                overall_risk
            ):
                overall_risk = case.get("risk_level", "Low")

        violated_comments_legacy = [
            {
                "index": case.get("index"),
                "content_snippet": case.get("quote", ""),
                "quote": case.get("quote", ""),
                "category": case.get("category", ""),
                "reasoning": case.get("reasoning", ""),
                "risk_level": case.get("risk_level", "Low"),
                "primary_law": case.get("primary_law", ""),
                "disposal_suggestion": case.get("disposal_suggestion", ""),
            }
            for case in comment_cases
        ]

        evidence_report = {
            "violated_categories": categories,
            "cited_laws": matched_laws_all[:5],
            "evidence_chain": [case.get("quote", "") for case in normalized_cases[:5]],
            "reasoning": "；".join(
                [
                    case.get("reasoning", "")
                    for case in normalized_cases[:3]
                    if case.get("reasoning")
                ]
            ),
            "disposal_suggestion": "；".join(
                [
                    case.get("disposal_suggestion", "")
                    for case in normalized_cases[:3]
                    if case.get("disposal_suggestion")
                ]
            ),
        }

        return {
            "is_post_violated": bool(post_case),
            "category": (post_case or {}).get("category", ""),
            "reasoning": (post_case or {}).get(
                "reasoning", evidence_report["reasoning"]
            ),
            "post_case": post_case,
            "comment_cases": comment_cases,
            "overall_risk_level": overall_risk,
            "matched_laws": matched_laws_all,
            "evidence_report": evidence_report,
            "violated_comments": violated_comments_legacy,
            "blocked_count": info.get("blocked_count", 0),
        }

    def audit_post_packet(
        self, post_packet: Dict[str, Any], event_name: str = ""
    ) -> Dict[str, Any]:
        post_content = self._clean_text(post_packet.get("content"))
        source_keyword = self._clean_text(post_packet.get("source_keyword"))
        candidate_pool = self._build_candidate_pool(post_packet)

        blocked_stage1_precheck = 0
        suspects = [
            {
                "index": item.get("index", -1),
                "category": "",
                "reason_brief": "阶段1审核",
            }
            for item in candidate_pool
        ]

        final_cases, blocked_stage1 = self.finalize_candidates(
            event_name=event_name,
            source_keyword=source_keyword,
            post_content=post_content,
            candidate_pool=candidate_pool,
            suspects=suspects,
        )

        confirmed_cases: List[Dict[str, Any]] = []
        violation_cases = []
        candidate_by_index: Dict[int, Dict[str, Any]] = {}
        for item in candidate_pool:
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get("index", -1))
            except Exception:
                continue
            candidate_by_index[idx] = item
        for case in final_cases:
            try:
                idx = int(case.get("index", -1))
            except Exception:
                continue
            source_base = candidate_by_index.get(idx) or {}
            case["source_type"] = source_base.get("source_type") or case.get(
                "source_type", "comment"
            )
            case["source_id"] = str(
                source_base.get("source_id") or case.get("source_id") or ""
            )
            case["content"] = source_base.get("content") or case.get("content", "")
            case["category"] = self._canonicalize_category(
                case.get("category", ""),
                fallback=case.get("candidate_category", ""),
            )
            if (
                case.get("is_violation")
                and case.get("category")
                and self._passes_violation_floor(case)
            ):
                violation_cases.append(case)
        if violation_cases:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(self.LAW_MATCH_WORKERS, len(violation_cases))
            ) as executor:
                future_to_index = {
                    executor.submit(self._match_laws_for_case, case): idx
                    for idx, case in enumerate(violation_cases)
                }
                law_infos: List[Optional[Dict[str, Any]]] = [None] * len(
                    violation_cases
                )
                for future in concurrent.futures.as_completed(future_to_index):
                    idx = future_to_index[future]
                    try:
                        law_infos[idx] = future.result()
                    except Exception as e:
                        logger.warning(
                            f" [Agent C] 单条法条匹配失败，该条按不违规放行: {e}"
                        )
                        law_infos[idx] = None

            for case, law_info in zip(violation_cases, law_infos):
                safe_law_info = law_info or {
                    "matched_laws": [],
                    "primary_law": "",
                    "law_reason": "法条匹配失败，该条按不违规放行。",
                }
                if not (safe_law_info.get("matched_laws") or []):
                    continue

                # 第二阶段：仅对已违规且已命中法规的条目补全证据链与处置建议。
                enhanced_reasoning = case.get("reasoning", "")
                enhanced_disposal = case.get("disposal_suggestion", "")
                enhanced_chain = self._build_case_evidence_chain(case, safe_law_info)
                merged_risk_level = self._derive_risk_level(case, safe_law_info)

                def _apply_evidence_result(evidence_result):
                    nonlocal enhanced_reasoning, enhanced_disposal, enhanced_chain
                    enhanced_reasoning = (
                        self._clean_text(getattr(evidence_result, "reasoning", ""))
                        or enhanced_reasoning
                    )
                    enhanced_disposal = self._normalize_disposal_suggestion(
                        getattr(evidence_result, "disposal_suggestion", "")
                        or enhanced_disposal,
                        merged_risk_level,
                        True,
                    )
                    model_chain = getattr(evidence_result, "evidence_chain", []) or []
                    if model_chain:
                        enhanced_chain = [
                            self._clean_text(x)
                            for x in model_chain
                            if self._clean_text(x)
                        ]

                try:
                    evidence_result = self._invoke_evidence_chain(
                        post_content=post_content,
                        media_context=source_keyword,
                        violated_items_json=json.dumps([case], ensure_ascii=False),
                        laws_json=json.dumps(
                            safe_law_info.get("matched_laws") or [],
                            ensure_ascii=False,
                        ),
                    )
                    _apply_evidence_result(evidence_result)
                except Exception as e:
                    if self._is_retryable_evidence_error(e):
                        logger.warning(
                            f" [Agent C] 证据链增强首次失败，准备重试一次: {e}"
                        )
                        try:
                            retry_result = self._invoke_evidence_chain(
                                post_content=post_content,
                                media_context=source_keyword,
                                violated_items_json=json.dumps(
                                    [case], ensure_ascii=False
                                ),
                                laws_json=json.dumps(
                                    safe_law_info.get("matched_laws") or [],
                                    ensure_ascii=False,
                                ),
                            )
                            _apply_evidence_result(retry_result)
                            logger.info(" [Agent C] 证据链增强重试成功")
                        except Exception as retry_error:
                            logger.warning(
                                " [Agent C] 证据链增强重试失败，已回退规则拼装: "
                                f"{retry_error}"
                            )
                    else:
                        logger.warning(
                            " [Agent C] 证据链增强失败（非重试类），已回退规则拼装: "
                            f"{e}"
                        )

                enhanced_disposal = self._normalize_disposal_suggestion(
                    enhanced_disposal,
                    merged_risk_level,
                    True,
                )

                merged_case = {
                    **case,
                    **safe_law_info,
                    "risk_level": merged_risk_level,
                    "reasoning": enhanced_reasoning,
                    "disposal_suggestion": enhanced_disposal,
                    "evidence_chain": enhanced_chain,
                }
                confirmed_cases.append(merged_case)

        post_case = None
        comment_cases: List[Dict[str, Any]] = []
        matched_laws_all: List[Dict[str, Any]] = []
        categories: List[str] = []
        overall_risk = "Low"

        for case in confirmed_cases:
            if case.get("source_type") == "post":
                post_case = case
            else:
                comment_cases.append(case)
            for law in case.get("matched_laws") or []:
                if law not in matched_laws_all:
                    matched_laws_all.append(law)
            category = case.get("category")
            if category and category not in categories:
                categories.append(category)
            if self._risk_value(case.get("risk_level")) > self._risk_value(
                overall_risk
            ):
                overall_risk = case.get("risk_level", "Low")

        violated_comments_legacy = [
            {
                "index": case.get("index"),
                "content_snippet": case.get("quote", ""),
                "quote": case.get("quote", ""),
                "category": case.get("category", ""),
                "reasoning": case.get("reasoning", ""),
                "risk_level": case.get("risk_level", "Low"),
                "primary_law": case.get("primary_law", ""),
                "disposal_suggestion": case.get("disposal_suggestion", ""),
            }
            for case in comment_cases
        ]

        evidence_report = {
            "violated_categories": categories,
            "cited_laws": matched_laws_all[:5],
            "evidence_chain": [case.get("quote", "") for case in confirmed_cases[:5]],
            "reasoning": "；".join(
                [
                    case.get("reasoning", "")
                    for case in confirmed_cases[:3]
                    if case.get("reasoning")
                ]
            ),
            "disposal_suggestion": "；".join(
                [
                    case.get("disposal_suggestion", "")
                    for case in confirmed_cases[:3]
                    if case.get("disposal_suggestion")
                ]
            ),
        }

        violation_info = {
            "is_post_violated": bool(post_case),
            "category": (post_case or {}).get("category", ""),
            "reasoning": (post_case or {}).get(
                "reasoning", evidence_report["reasoning"]
            ),
            "post_case": post_case,
            "comment_cases": comment_cases,
            "overall_risk_level": overall_risk,
            "matched_laws": matched_laws_all,
            "evidence_report": evidence_report,
            "violated_comments": violated_comments_legacy,
            "blocked_count": blocked_stage1_precheck + blocked_stage1,
        }

        return {
            "is_violation": bool(post_case or comment_cases),
            "violation_info": violation_info,
        }


agent_c = AgentCompliance()
