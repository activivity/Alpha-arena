#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的交互记忆管理
用于在多轮运行中保存最近的最终决策与下单结果，并在下一轮作为提示的上下文摘要。
"""

import os
import json
from typing import List, Dict, Any


def _get_config() -> Dict[str, Any]:
    """读取记忆相关配置（环境变量）。"""
    path = os.getenv('MEMORY_FILE', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'memory.json'))
    try:
        max_items = int(os.getenv('MEMORY_MAX_ITEMS', '10'))
    except Exception:
        max_items = 10
    enabled = (os.getenv('ENABLE_MEMORY', '0').strip() == '1')
    return {"path": path, "max_items": max_items, "enabled": enabled}


def load_memory() -> List[Dict[str, Any]]:
    """加载记忆列表（按时间顺序存储）。"""
    cfg = _get_config()
    if not cfg["enabled"]:
        return []
    path = cfg["path"]
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        return []


def append_memory(record: Dict[str, Any]) -> None:
    """追加一条记忆记录，并按最大条数截断。"""
    cfg = _get_config()
    if not cfg["enabled"]:
        return
    path = cfg["path"]
    max_items = cfg["max_items"]
    try:
        current = load_memory()
        current.append(record)
        if len(current) > max_items:
            # 保留最新的 max_items 条
            current = current[-max_items:]
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
    except Exception:
        # 记忆保存失败不影响主流程
        pass