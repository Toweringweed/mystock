"""事件检测器（detector）

5 个 detector 模块对应 5 类异常事件：
  - technical_events    : MACD_DIVERGENCE_NEW / VOLUME_SPIKE
  - valuation_events    : PE_EXTREME_LOW / PE_EXTREME_HIGH
  - news_events         : URGENT_NEWS
  - signal_flip_events  : AI_SIGNAL_FLIP
  - detector            : 编排器，每日定时调用

所有 detector 写入 stock_events 表，幂等键 (stock_id, event_type, dedup_key)。
"""
