#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qwen适配器
调用阿里云Qwen模型进行交易决策
"""

import os
from typing import Dict, Any
from .llm_base import LLMAdapter

try:
    import dashscope
except ImportError:
    print("❌ 请安装dashscope: pip install dashscope")
    dashscope = None


class QwenAdapter(LLMAdapter):
    """Qwen适配器"""
    def __init__(self, api_key: str = None):
        """
        初始化Qwen适配器
        
        Args:
            api_key: 阿里云API密钥，如果为None则从环境变量获取
        """
        if api_key is None:
            api_key = os.getenv('DASHSCOPE_API_KEY')
        
        if not api_key:
            raise ValueError("阿里云API密钥未设置，请设置DASHSCOPE_API_KEY环境变量")
        
        super().__init__(api_key)
        
        # 初始化Qwen客户端
        if dashscope:
            dashscope.api_key = self.api_key
        else:
            raise ImportError("DashScope库未安装")
        
        # 采样参数（可通过环境变量配置）
        try:
            self.temperature = float(os.getenv('QWEN_TEMPERATURE', '0.2'))
        except Exception:
            self.temperature = 0.2
        try:
            self.top_p = float(os.getenv('QWEN_TOP_P', '0.9'))
        except Exception:
            self.top_p = 0.9
    
    def call(self, prompt: str) -> str:
        """调用Qwen API"""
        try:
            response = dashscope.Generation.call(
                model='qwen-max',
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是专业的量化交易分析师。严格遵守以下规则：\n"
                            "1) 仅输出JSON，无任何额外文字或代码块。\n"
                            "2) 若置信度不足或无法满足交易所最小名义额/最小数量，必须返回HOLD或空方案。\n"
                            "3) 禁止同时对同一symbol买卖；禁止输出未在用户提示列出的交易对。\n"
                            "4) 理由需与输入数据直接相关，避免空话与套话。\n"
                            "优先输出组合方案：{\"buys\": [ { \"symbol\": \"<BASE>USDT\", \"quote_usdt\": <number> } , ... ], \"sells\": [ { \"symbol\": \"<BASE>USDT\", \"quantity\": <number> } , ... ], \"rationale\": \"<简要理由>\", \"confidence\": <0.0-1.0>}；若无法生成组合方案，退回旧格式 {\"symbol\": \"<BASE>USDT|null\", \"action\": \"BUY|SELL|HOLD\", \"confidence\": 0.0-1.0, \"rationale\": \"简短理由\" }"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                result_format="message",
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=400,
            )
            # 统一按 message 返回解析，避免 output_text 属性异常
            if getattr(response, 'status_code', None) == 200:
                output = getattr(response, 'output', None)
                choices = getattr(output, 'choices', None)
                if choices and len(choices) > 0 and hasattr(choices[0], 'message') and hasattr(choices[0].message, 'content'):
                    return choices[0].message.content.strip()
                else:
                    return '{"symbol": null, "action": "HOLD", "confidence": 0.0, "rationale": "Qwen返回结构缺少choices"}'
            else:
                print(f"❌ Qwen API调用失败: {getattr(response, 'code', 'unknown')} - {getattr(response, 'message', 'unknown')}")
                return '{"symbol": null, "action": "HOLD", "confidence": 0.0, "rationale": "API调用失败"}'
        except Exception as e:
            print(f"❌ Qwen API调用失败: {e}")
            return '{"symbol": null, "action": "HOLD", "confidence": 0.0, "rationale": "API调用失败"}'
    
    def get_model_name(self) -> str:
        """获取模型名称"""
        return "qwen-max"