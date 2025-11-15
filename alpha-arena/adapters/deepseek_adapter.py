#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek适配器
调用DeepSeek模型进行交易决策
"""

import os
from typing import Dict, Any
from .llm_base import LLMAdapter
from openai import OpenAI


class DeepSeekAdapter(LLMAdapter):
    """DeepSeek适配器"""
    
    def __init__(self, api_key: str = None):
        """
        初始化DeepSeek适配器
        
        Args:
            api_key: DeepSeek API密钥，如果为None则从环境变量获取
        """
        if api_key is None:
            api_key = os.getenv('DEEPSEEK_API_KEY')
        
        if not api_key:
            raise ValueError("DeepSeek API密钥未设置，请设置DEEPSEEK_API_KEY环境变量")
        
        super().__init__(api_key)
        
        # 采样参数（可通过环境变量配置）
        try:
            self.temperature = float(os.getenv('DEEPSEEK_TEMPERATURE', '0.2'))
        except Exception:
            self.temperature = 0.2
        try:
            self.top_p = float(os.getenv('DEEPSEEK_TOP_P', '0.9'))
        except Exception:
            self.top_p = 0.9
        
        # 使用OpenAI SDK并指向DeepSeek的base_url
        self.client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
    
    def call(self, prompt: str) -> str:
        """
        调用DeepSeek API
        """
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "你是专业的量化交易分析师。严格遵守：仅输出JSON，无任何额外文字或代码块。若置信度不足或无法满足交易所最小名义额/最小数量，必须返回HOLD或空方案；禁止同时对同一symbol买卖；理由需与输入数据直接相关。优先输出组合方案：{\"buys\": [ { \"symbol\": \"<BASE>USDT\", \"quote_usdt\": <number> } , ... ], \"sells\": [ { \"symbol\": \"<BASE>USDT\", \"quantity\": <number> } , ... ], \"rationale\": \"<简要理由>\", \"confidence\": <0.0-1.0>}；若无法生成组合方案，退回旧格式 {\"symbol\": \"<BASE>USDT|null\", \"action\": \"BUY|SELL|HOLD\", \"confidence\": 0.0-1.0, \"rationale\": \"简短理由\" }"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=400,
                temperature=self.temperature,
                top_p=self.top_p
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"❌ DeepSeek API调用失败: {e}")
            return '{"symbol": null, "action": "HOLD", "confidence": 0.0, "rationale": "API调用失败"}'
    
    def get_model_name(self) -> str:
        """获取模型名称"""
        return "DeepSeek-Chat"