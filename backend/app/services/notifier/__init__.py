"""分级推送

  urgent    → 立即推送（在打分流水线尾部触发）
  important → Redis SortedSet 排队，每整点聚合推送
  info      → 仅入库，每日 8:00 摘要
"""
