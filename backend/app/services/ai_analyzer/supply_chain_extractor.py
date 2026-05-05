"""供应链 AI 提取器 — 基于公开资料和模型知识"""
import json
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """你是一位专业的A股行业分析师，熟悉中国上市公司的供应链结构。

请根据你对 {name}（股票代码：{code}）的了解，提取其供应链信息。
信息来源：公司年报、行业研报、公开披露的采购/客户信息。

请严格按以下 JSON 格式输出（不要有任何多余文字）：
{{
  "upstream": [
    {{
      "company_name": "供应商名称（如不知道具体公司则填行业描述如'高粱种植基地'）",
      "product_desc": "供应的原材料/服务",
      "percentage": null,
      "is_listed": false,
      "company_code": null,
      "importance": "high"
    }}
  ],
  "downstream": [
    {{
      "company_name": "客户/渠道名称",
      "product_desc": "销售的产品/服务",
      "percentage": null,
      "is_listed": false,
      "company_code": null,
      "importance": "high"
    }}
  ],
  "competitors": [
    {{
      "company_name": "竞争对手名称",
      "product_desc": "竞争领域",
      "percentage": null,
      "is_listed": true,
      "company_code": "000858",
      "importance": "high"
    }}
  ]
}}

要求：
- upstream 填主要原材料/零部件供应商或供应商类型，至少3条
- downstream 填主要客户群体或渠道，至少3条
- competitors 填主要竞争对手（尽量给出A股代码），至少2条
- importance: high（核心/占比大）/ medium / low
- 如果知道具体公司代码请填写，否则 null
- percentage 如不知道确切数据填 null"""


class SupplyChainExtractor:
    async def extract(self, code: str, name: str, text: str = "", db=None) -> list[dict]:
        """调用 AI 提取供应链，返回标准化列表"""
        raw = await self._call_llm(code, name, text, db=db)
        return self._parse(raw)

    async def _call_llm(self, code: str, name: str, text: str, db=None) -> str:
        prompt = EXTRACT_PROMPT.format(code=code, name=name)
        if text:
            prompt += f"\n\n以下是公司年报相关内容供参考：\n{text[:3000]}"

        async def _get(key: str) -> str:
            if db is not None:
                try:
                    from app.services.settings_service import get_effective_value
                    return await get_effective_value(db, key)
                except Exception:
                    pass
            return str(getattr(settings, key, "") or "")

        # ── OpenRouter ────────────────────────────────────────────────
        try:
            or_key = await _get("openrouter_api_key")
            or_model = await _get("openrouter_model") or settings.openrouter_model
            if or_key:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1")
                resp = await client.chat.completions.create(
                    model=or_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    max_tokens=4000,
                )
                return resp.choices[0].message.content or ""
        except Exception as e:
            logger.warning(f"[{code}] OpenRouter 供应链提取失败，尝试下一个: {e}")

        # ── OpenAI ────────────────────────────────────────────────────
        try:
            oai_key = await _get("openai_api_key")
            oai_model = await _get("openai_model") or settings.openai_model
            if oai_key:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=oai_key)
                resp = await client.chat.completions.create(
                    model=oai_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    max_tokens=4000,
                )
                return resp.choices[0].message.content or ""
        except Exception as e:
            logger.warning(f"[{code}] OpenAI 供应链提取失败，尝试下一个: {e}")

        # ── Anthropic ─────────────────────────────────────────────────
        try:
            ant_key = await _get("anthropic_api_key")
            ant_model = await _get("anthropic_model") or settings.anthropic_model
            if ant_key:
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=ant_key)
                resp = await client.messages.create(
                    model=ant_model,
                    max_tokens=4000,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.content[0].text
        except Exception as e:
            logger.error(f"[{code}] Anthropic 供应链提取失败: {e}")

        logger.error(f"[{code}] 所有 LLM provider 均失败，供应链提取无法完成")
        return ""

    def _parse(self, raw: str) -> list[dict]:
        if not raw:
            return []
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            data = json.loads(raw[start:end])
        except Exception as e:
            logger.error(f"供应链 JSON 解析失败: {e}\n原始: {raw[:200]}")
            return []

        result = []
        for rel_type in ("upstream", "downstream", "competitors"):
            db_type = "competitor" if rel_type == "competitors" else rel_type
            for item in data.get(rel_type, []):
                company_name = (item.get("company_name") or "").strip()
                if not company_name:
                    continue
                result.append({
                    "relation_type": db_type,
                    "company_name": company_name,
                    "company_code": item.get("company_code"),
                    "product_desc": item.get("product_desc"),
                    "percentage": item.get("percentage"),
                    "importance": item.get("importance", "medium"),
                    "is_listed": item.get("is_listed", False),
                    "data_source": "ai_knowledge",
                })
        return result
