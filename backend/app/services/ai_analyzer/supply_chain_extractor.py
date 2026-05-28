"""供应链 AI 提取器 — 基于公开资料和模型知识"""
import json
import logging

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

        from app.services.ai_analyzer.llm_client import call_llm

        return await call_llm(db, prompt, temperature=0, max_tokens=4000)

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
