import json
from typing import Dict, Any, List

# LangChain 组件
from langchain_openai import ChatOpenAI  # 推荐使用标准的 ChatOpenAI 类
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# 引入配置和数据库
from app.core.config import settings
from app.db.chroma_manager import chroma_db

# 🔥 引入分离出去的 Schema 和 Prompt
from app.core.schemas import (
    AuditAnalysis,
    BatchComplianceResult,
    ComplianceEvidenceReport,
)
from app.core.prompts import (
    AGENT_C_ANALYSIS_TEMPLATE,
    AGENT_C_REPORT_TEMPLATE,
    AGENT_C_BATCH_TEMPLATE,
    AGENT_C_EVIDENCE_TEMPLATE,
)


# ==========================================
# Agent C (合规审查官)
# ==========================================
class AgentCompliance:
    def __init__(self):
        # 初始化大脑
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,  # 例如 "glm-4-flash"
            openai_api_key=settings.ZHIPU_API_KEY,
            openai_api_base=settings.LLM_BASE_URL,  # 这里的 URL 必须是智谱的地址
            temperature=0.1,
        )
        # 单条模式解析器
        self.parser = JsonOutputParser(pydantic_object=AuditAnalysis)
        # 批量模式解析器
        self.batch_parser = JsonOutputParser(pydantic_object=BatchComplianceResult)

        # Batch+RAG 证据链解析器
        self.evidence_parser = JsonOutputParser(
            pydantic_object=ComplianceEvidenceReport
        )

        # 完整的标签列表 (保留用于单条模式的 RAG 检索或参考)
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

    # =======================================================
    # 🔥 新增：Batch Audit (一次性审查 主贴 + 列表评论)
    # =======================================================
    def batch_audit(
        self,
        post_content: str,
        comments_text: str,
        media_context: str = "",
        note_id: str = "Unknown_ID",
    ) -> BatchComplianceResult:
        """
        执行批量审查流程
        :param post_content: 主贴正文
        :param comments_text: 格式化好的评论列表字符串
        :param media_context: 媒体链接上下文
        :param note_id: 帖子真实 ID (用于 Prompt 上下文)
        :return: BatchComplianceResult 对象
        """
        print(f"👮 [Agent C] 正在进行批量审查 (Batch Audit) ID: {note_id}...")

        # 1. 组装 Prompt
        prompt = ChatPromptTemplate.from_template(AGENT_C_BATCH_TEMPLATE).partial(
            format_instructions=self.batch_parser.get_format_instructions()
        )

        # 2. 构造链
        chain = prompt | self.llm | self.batch_parser

        try:
            # 3. 调用 LLM
            # 🔥 关键修改：传入真实的 note_id 给 Prompt 里的 {post_id}
            res_dict = chain.invoke(
                {
                    "post_id": note_id,
                    "post_content": post_content,
                    "media_context": media_context,
                    "comments_text": comments_text,
                }
            )

            # 4. 转换为 Pydantic 对象返回
            return BatchComplianceResult(**res_dict)

        except Exception as e:
            print(f"❌ [Agent C] Batch Audit Error (ID: {note_id}): {e}")
            # 出错时返回默认的安全结果
            return BatchComplianceResult(
                is_post_violated=False, violated_comments=[], overall_risk_level="Low"
            )

    def batch_audit_with_rag(
        self,
        post_content: str,
        comments_text: str,
        media_context: str = "",
        note_id: str = "Unknown_ID",
        top_k_per_category: int = 2,
    ) -> Dict[str, Any]:
        """Batch 审查 + RAG 检索 + 证据链生成（用于写回 Mongo）。

        返回值是 dict，包含：
        - batch_result: BatchComplianceResult 的 model_dump
        - matched_laws: List[LawReference-dict]
        - evidence_report: ComplianceEvidenceReport 的 dict（若无违规则为空）
        """

        batch_res = self.batch_audit(
            post_content=post_content,
            comments_text=comments_text,
            media_context=media_context,
            note_id=note_id,
        )

        batch_dict = (
            batch_res.model_dump()
            if hasattr(batch_res, "model_dump")
            else dict(batch_res)
        )
        violated_items = batch_dict.get("violated_comments") or []

        # 无违规：直接返回
        if not (batch_dict.get("is_post_violated") or violated_items):
            return {
                "batch_result": batch_dict,
                "matched_laws": [],
                "evidence_report": {},
            }

        # 1) 收集违规标签
        categories = []
        for it in violated_items:
            cat = (it or {}).get("category")
            if cat and cat not in categories:
                categories.append(cat)

        # 2) Chroma 检索（按标签过滤，保证命中条款可解释）
        matched_laws: List[Dict[str, Any]] = []
        for cat in categories:
            try:
                docs = chroma_db.search_related_laws(
                    query=cat,
                    top_k=top_k_per_category,
                    category_filter=cat,
                )
            except Exception as e:
                print(f"⚠️ [Agent C] RAG 检索失败 (category={cat}): {e}")
                docs = []

            for d in docs or []:
                meta = getattr(d, "metadata", {}) or {}
                matched_laws.append(
                    {
                        "category": meta.get("category", cat),
                        "article": meta.get("article", "未知"),
                        "risk_level": meta.get(
                            "risk_level", meta.get("risk", "Unknown")
                        ),
                        "rule": getattr(d, "page_content", "") or "",
                    }
                )

        # 限制条款数量，防止 token 膨胀
        if len(matched_laws) > 12:
            matched_laws = matched_laws[:12]

        # 3) 生成证据链（结构化 JSON）
        try:
            # 截断违规项，避免 token 爆炸
            violated_items_trimmed = violated_items[:20]

            prompt = ChatPromptTemplate.from_template(
                AGENT_C_EVIDENCE_TEMPLATE
            ).partial(
                format_instructions=self.evidence_parser.get_format_instructions()
            )
            chain = prompt | self.llm | self.evidence_parser

            evidence_obj = chain.invoke(
                {
                    "post_content": post_content,
                    "media_context": media_context,
                    "violated_items_json": json.dumps(
                        violated_items_trimmed, ensure_ascii=False
                    ),
                    "laws_json": json.dumps(matched_laws, ensure_ascii=False),
                }
            )
            evidence_report = (
                evidence_obj.model_dump()
                if hasattr(evidence_obj, "model_dump")
                else dict(evidence_obj)
            )
        except Exception as e:
            print(f"⚠️ [Agent C] 证据链生成失败 (ID: {note_id}): {e}")
            evidence_report = {}

        return {
            "batch_result": batch_dict,
            "matched_laws": matched_laws,
            "evidence_report": evidence_report,
        }

    # =======================================================
    # 旧方法：单条审查 (保留用于兼容性或精细化 RAG)
    # =======================================================
    def _get_analysis_prompt(self):
        return ChatPromptTemplate.from_template(AGENT_C_ANALYSIS_TEMPLATE).partial(
            categories=", ".join(self.valid_categories),
            format_instructions=self.parser.get_format_instructions(),
        )

    def audit_content(self, text: str) -> Dict[str, Any]:
        """
        (Legacy) 执行单条审查流程：Thinking -> Retrieval -> Verdict
        """
        print(f"👮 [Agent C] 单条审查: “{text[:20]}...”")

        # 1. 定性分析
        analysis_chain = self._get_analysis_prompt() | self.llm | self.parser
        try:
            analysis: AuditAnalysis = analysis_chain.invoke({"user_input": text})
        except Exception as e:
            return {"error": str(e), "verdict": "Error"}

        # 2. 快速通道：无违规
        if not analysis["is_violation"] or analysis["category"] in ["无", "None"]:
            return {
                "verdict": "✅ 通过",
                "analysis": dict(analysis),
                "evidence": "无违规风险",
            }

        # 3. 精准检索 (Agentic RAG)
        target_category = analysis["category"]
        docs = chroma_db.search_related_laws(
            query=target_category, top_k=1, category_filter=target_category
        )

        rule_content = "通用条款（未精准命中细则）"
        article = "未知"

        if docs:
            rule_doc = docs[0]
            if target_category in rule_doc.metadata.get("category", ""):
                rule_content = rule_doc.page_content
                article = rule_doc.metadata.get("article", "未知条款")

        # 4. 生成判决书
        final_report = self._generate_report(text, analysis, rule_content, article)

        return {
            "verdict": "❌ 违规",
            "analysis": dict(analysis),
            "evidence": {"article": article, "rule": rule_content},
            "report": final_report,
        }

    def _generate_report(self, text, analysis, rule_content, article):
        """生成自然语言判决书"""
        chain = ChatPromptTemplate.from_template(AGENT_C_REPORT_TEMPLATE) | self.llm
        return chain.invoke(
            {
                "text": text,
                "category": analysis["category"],
                "risk": analysis["risk_level"],
                "article": article,
                "rule_content": rule_content,
            }
        ).content


# 单例导出
agent_c = AgentCompliance()
