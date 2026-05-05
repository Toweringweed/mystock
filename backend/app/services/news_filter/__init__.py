"""资讯过滤与打分流水线

模块组织：
- keyword_builder  : 从 stocks/aliases/supply_chain 派生关键词库
- entity_matcher   : 多关键词匹配，输出 (stock_id, weight) 列表
- dedup            : SimHash 跨源近似去重
- rule_scorer      : 规则层打分（公告类型、源权威度、时间敏感词、数字命中）
- llm_scorer       : Claude Haiku 批量打分（方向、强度、情感、摘要、相关度）
- urgency_classifier : 紧急/重要/参考三级分类
"""
