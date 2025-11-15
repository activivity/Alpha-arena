#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
决策引擎
处理LLM交易决策
"""

import json
from typing import Dict, Any, List, Optional
from adapters.llm_base import LLMAdapter
import os
from .memory import load_memory



class DecisionMaker:
    """交易决策引擎"""
    
    def __init__(self, llm_adapter: LLMAdapter):
        """
        初始化决策引擎
        
        Args:
            llm_adapter: LLM适配器实例
        """
        self.llm_adapter = llm_adapter
        self.model_name = llm_adapter.get_model_name()
        # 提示词约束的最小置信度阈值（低于该值必须HOLD）
        try:
            self.min_conf = float(os.getenv('LLM_MIN_CONF', '0.65'))
        except Exception:
            self.min_conf = 0.65

    def _sanitize_plan(self, plan: Dict[str, Any], prices: Dict[str, float], balances: Dict[str, float]) -> Dict[str, Any]:
        try:
            valid_syms = {s for s, p in prices.items() if (p or 0) > 0}
            buys_in = plan.get("buys") or []
            sells_in = plan.get("sells") or []
            buys_out: List[Dict[str, Any]] = []
            sells_out: List[Dict[str, Any]] = []
            seen_buy = set()
            seen_sell = set()
            for b in buys_in:
                sym = (b.get("symbol") or "").upper()
                amt = float(b.get("quote_usdt") or 0.0)
                if not sym or sym not in valid_syms or amt <= 0:
                    continue
                if sym in seen_buy:
                    continue
                seen_buy.add(sym)
                buys_out.append({"symbol": sym, "quote_usdt": amt})
            for s in sells_in:
                sym = (s.get("symbol") or "").upper()
                qty = float(s.get("quantity") or 0.0)
                if not sym or sym not in valid_syms or qty <= 0:
                    continue
                if sym in seen_sell:
                    continue
                seen_sell.add(sym)
                sells_out.append({"symbol": sym, "quantity": qty})
            # 去除同一symbol同时买卖的冲突
            conflict = {sym for sym in seen_buy & seen_sell}
            if conflict:
                buys_out = [x for x in buys_out if x["symbol"] not in conflict]
                sells_out = [x for x in sells_out if x["symbol"] not in conflict]
            out = {
                "buys": buys_out,
                "sells": sells_out,
                "rationale": plan.get("rationale", ""),
                "confidence": float(plan.get("confidence", 0.0) or 0.0)
            }
            return out
        except Exception:
            return {
                "buys": [],
                "sells": [],
                "rationale": plan.get("rationale", ""),
                "confidence": float(plan.get("confidence", 0.0) or 0.0)
            }

    def build_prompt(self, market_data: Dict[str, float]) -> str:
        """
        构建交易决策提示词（仅当前价格，结构化约束版）
        """
        lines = []
        lines.append("角色与目标：")
        lines.append("- 你是专业的量化交易分析师，目标是在当前时刻基于输入数据输出一个明确的交易决策。")
        lines.append("")
        lines.append("输入数据（当前价格，单位：USDT）：")
        syms = [s for s, p in market_data.items() if (p or 0) > 0]
        for sym in syms:
            lines.append(f"- {sym}: ${market_data.get(sym, 0):.4f}")
        lines.append("")
        lines.append("决策原则：")
        lines.append("- 结合趋势、动量与波动性做出判断；若信息不足或不确定，请选择HOLD。")
        lines.append("- 只在必要时选择BUY或SELL，并给出简短理由。")
        lines.append("")
        lines.append("严格输出要求（仅返回JSON，不要任何其他文字或代码块）：")
        lines.append("{")
        lines.append("    \"symbol\": \"<BASE>USDT|null\",")
        lines.append("    \"action\": \"BUY|SELL|HOLD\",")
        lines.append("    \"confidence\": 0.0-1.0,")
        lines.append("    \"rationale\": \"简短理由（不超过50字）\"")
        lines.append("}")
        lines.append("")
        lines.append("约束：")
        lines.append("- 仅从上方列出的有效交易对(价格>0)中选择symbol；若无明确选择则返回null。")
        lines.append("- action为HOLD表示观望。confidence为数字，范围[0,1]。")
        lines.append("- 禁止输出解释性文本、标题、前后缀或代码框。")
        # 强化限制，避免无意义决策
        lines.append(f"- 当置信度低于{self.min_conf:.2f}或理由模糊/泛泛而谈时，必须返回HOLD，不要勉强BUY/SELL。")
        lines.append("- 禁止提出金额或数量不足以执行的交易：若无法满足交易所最小名义额(≈5 USDT)或最小数量限制，请返回HOLD。")
        # 新增：手续费考量
        lines.append("- 在金额与数量的建议中考虑交易所手续费（如0.1%），避免成交后因手续费扣减导致名义额或数量不足；买入可适度上浮金额，卖出可适度下调数量以满足过滤器。")
        lines.append("- 禁止同时对同一symbol给出BUY与SELL。")
        lines.append("- 理由需与输入数据直接相关（趋势/动量/波动），禁止空话或与交易无关的内容。")
        # 新增：禁止BUY/SELL与空symbol的组合
        lines.append("- 若action为BUY或SELL，symbol必须为具体<BASE>USDT，禁止为null或\"None\"。")
        lines.append("")
        lines.append("JSON：")
        return "\n".join(lines)

    def build_prompt_with_history(self, current_prices: Dict[str, float], historical: Dict[str, List[float]]) -> str:
        """
        构建包含历史价格信息的提示词（结构化约束版）：提供每个交易对最近N个收盘价、区间涨跌幅、当前价格，并要求基于趋势与动量做出决策。
        """
        def pct_change(series: List[float]) -> Optional[float]:
            if not series or len(series) < 2:
                return None
            try:
                start, end = series[0], series[-1]
                if start == 0:
                    return None
                return (end - start) / start
            except Exception:
                return None
        
        # 简单衍生特征：近N点收益率均值、标准差（波动）、末端两点变化率（动量）
        def features(series: List[float]) -> Dict[str, Optional[float]]:
            try:
                if not series or len(series) < 2:
                    return {"ret_mean": None, "ret_std": None, "last_momentum": None}
                returns = []
                for i in range(1, len(series)):
                    prev, cur = series[i-1], series[i]
                    if prev == 0:
                        returns.append(0.0)
                    else:
                        returns.append((cur - prev) / prev)
                # 均值
                ret_mean = sum(returns) / len(returns)
                # 标准差
                mean = ret_mean
                var = sum((r - mean) ** 2 for r in returns) / max(1, len(returns) - 1)
                ret_std = var ** 0.5
                # 末端动量（最后一段收益率）
                last_momentum = returns[-1]
                return {"ret_mean": ret_mean, "ret_std": ret_std, "last_momentum": last_momentum}
            except Exception:
                return {"ret_mean": None, "ret_std": None, "last_momentum": None}
        
        lines: List[str] = []
        lines.append("角色与目标：")
        lines.append("- 你是专业的量化交易分析师，基于历史序列与当前价格输出一个明确的交易决策。")
        lines.append("")
        # 最近操作记忆摘要（可选）
        try:
            mem = load_memory()
            if mem:
                lines.append("最近操作记忆（最多展示部分）：")
                # 仅展示最近5条摘要
                for rec in mem[-5:]:
                    ts = rec.get('timestamp', 'N/A')
                    src = rec.get('decision_model', 'N/A')
                    fd = rec.get('final_decision', {})
                    if isinstance(fd, dict) and ('buys' in fd or 'sells' in fd):
                        buys_syms = [x.get('symbol') for x in (fd.get('buys') or []) if x.get('symbol')]
                        sells_syms = [x.get('symbol') for x in (fd.get('sells') or []) if x.get('symbol')]
                        lines.append(f"- [{ts}] 来源={src} | 方案 buys={','.join(buys_syms) or '[]'} sells={','.join(sells_syms) or '[]'}")
                    else:
                        lines.append(f"- [{ts}] 来源={src} | 决策 {fd.get('action','HOLD')} {fd.get('symbol','None')}")
                lines.append("")
        except Exception:
            pass
        lines.append("历史价格（从旧到新，单位：USDT）与特征摘要：")
        # 动态选择需要分析的交易对：仅考虑当前价格有效(>0)或存在历史数据的交易对
        syms = sorted({k for k, p in current_prices.items() if (p or 0) > 0} | set(historical.keys()))
        for sym in syms:
            series = historical.get(sym, [])
            if series:
                change = pct_change(series)
                change_str = f"{change*100:.2f}%" if change is not None else "N/A"
                preview = ", ".join(f"{p:.2f}" for p in series[:8])
                fts = features(series)
                ft_ret_mean = f"{(fts['ret_mean'] or 0.0)*100:.2f}%" if fts['ret_mean'] is not None else "N/A"
                ft_ret_std = f"{(fts['ret_std'] or 0.0)*100:.2f}%" if fts['ret_std'] is not None else "N/A"
                ft_last_mom = f"{(fts['last_momentum'] or 0.0)*100:.2f}%" if fts['last_momentum'] is not None else "N/A"
                lines.append(f"- {sym}: [{preview} ... 共{len(series)}条] | 区间涨跌幅: {change_str} | 近N点: 均值 {ft_ret_mean}, 波动 {ft_ret_std}, 动量 {ft_last_mom}")
            else:
                lines.append(f"- {sym}: 历史数据不可用")
        
        lines.append("")
        lines.append("当前价格（USDT）：")
        for sym in syms:
            price = current_prices.get(sym, 0)
            lines.append(f"- {sym}: ${price:.4f}")
        lines.append("")
        lines.append("分析指引：")
        lines.append("- 关注区间涨跌幅、近N点收益率均值与波动、末端动量的综合信号；避免过度拟合。")
        lines.append("- 若信号不一致或不可靠，优先选择HOLD。")
        lines.append("")
        lines.append("严格输出要求（仅返回JSON，不要任何额外文字或代码块）：")
        lines.append("{")
        lines.append("    \"symbol\": \"<BASE>USDT|null\",")
        lines.append("    \"action\": \"BUY|SELL|HOLD\",")
        lines.append("    \"confidence\": 0.0-1.0,")
        lines.append("    \"rationale\": \"简短理由（不超过50字）\"")
        lines.append("}")
        lines.append("")
        lines.append("约束：")
        lines.append("- 仅允许从上方列出的交易对中选择；若无明确选择则返回null。")
        lines.append("- confidence为数字，范围[0,1]；action为HOLD表示观望。")
        lines.append("- 禁止输出解释性文本、标题、前后缀或代码框。")
        # 强化限制
        lines.append(f"- 当置信度低于{self.min_conf:.2f}或信号不一致/不可靠时，必须选择HOLD。")
        lines.append("- 禁止提出不满足最小名义额(≈5 USDT)或最小数量的交易。")
        # 新增：手续费考量
        lines.append("- 在金额与数量的建议中考虑交易所手续费（如0.1%），避免成交后因手续费扣减导致名义额或数量不足；买入可适度上浮金额，卖出可适度下调数量以满足过滤器。")
        lines.append("- 禁止同时对同一symbol给出BUY与SELL。")
        lines.append("- 理由需具体且与所给历史特征(涨跌幅/均值/波动/末端动量)相关，禁止泛泛而谈。")
        # 新增：禁止BUY/SELL与空symbol的组合
        lines.append("- 若action为BUY或SELL，symbol必须为具体<BASE>USDT，禁止为null或\"None\"。")
        lines.append("")
        lines.append("JSON：")
        return "\n".join(lines)

    def build_prompt_with_holdings(self, prices: dict, historical: dict, balances: dict) -> str:
        # 强化提示：生成持仓优化方案，明确输出JSON架构
        lines = []
        lines.append("你是一名加密货币现货交易顾问。请基于当前价格、历史走势与账户持仓，给出可执行的持仓优化方案。")
        lines.append("目标：在控制风险的前提下提高账户的风险回报，允许卖出与买入多个币种。")
        lines.append("")
        lines.append("输入数据：")
        lines.append(f"- 当前价格(USDT计价): {prices}")
        lines.append(f"- 历史数据概览(可能省略细节): {[k for k in historical.keys()]}")
        lines.append(f"- 账户持仓: {balances}")
        # 新增：将USDT余额与风控上限明确结构化给出，避免模型误判“余额不足”
        try:
            usdt_bal = float(balances.get('USDT', 0.0) or 0.0)
        except Exception:
            usdt_bal = 0.0
        try:
            max_trade_usdt = float(os.getenv('MAX_TRADE_USDT', '20') or 20)
        except Exception:
            max_trade_usdt = 20.0
        try:
            max_position_usdt = float(os.getenv('MAX_POSITION_USDT_PER_SYMBOL', '50') or 50)
        except Exception:
            max_position_usdt = 50.0
        lines.append(f"- USDT余额(可用于买入): {usdt_bal:.4f}")
        lines.append(f"- 风控上限: 单笔买入≤{max_trade_usdt:.2f} USDT, 单币持仓≤{max_position_usdt:.2f} USDT")
        lines.append("- 通用最小名义额参考: 5.00 USDT（不同交易对可能略有差异，最终以交易所过滤器为准）")
        lines.append("")
        # 最近操作记忆摘要（可选）
        try:
            mem = load_memory()
            if mem:
                lines.append("最近操作记忆（最多展示部分）：")
                for rec in mem[-5:]:
                    ts = rec.get('timestamp', 'N/A')
                    src = rec.get('decision_model', 'N/A')
                    fd = rec.get('final_decision', {})
                    if isinstance(fd, dict) and ('buys' in fd or 'sells' in fd):
                        buys_syms = [x.get('symbol') for x in (fd.get('buys') or []) if x.get('symbol')]
                        sells_syms = [x.get('symbol') for x in (fd.get('sells') or []) if x.get('symbol')]
                        lines.append(f"- [{ts}] 来源={src} | 方案 buys={','.join(buys_syms) or '[]'} sells={','.join(sells_syms) or '[]'}")
                    else:
                        lines.append(f"- [{ts}] 来源={src} | 决策 {fd.get('action','HOLD')} {fd.get('symbol','None')}")
                lines.append("")
        except Exception:
            pass
        lines.append("请严格输出以下JSON格式（不要包含多余文本）：")
        lines.append("{")
        lines.append("  \"buys\": [ { \"symbol\": \"<BASE>USDT\", \"quote_usdt\": <number> } , ... ],")
        lines.append("  \"sells\": [ { \"symbol\": \"<BASE>USDT\", \"quantity\": <number> } , ... ],")
        lines.append("  \"rationale\": \"<简要理由>\",")
        lines.append("  \"confidence\": <0.0-1.0>")
        lines.append("}")
        lines.append("要求：")
        lines.append("- buys中的quote_usdt为买入金额(USDT)，sells中的quantity为卖出数量(基础币数量)。")
        lines.append("- 仅使用你在当前价格中看到的USDT交易对(symbol形如<BASE>USDT)。")
        lines.append("- 如果不需要买或卖，对应数组给空列表[].")
        lines.append("- confidence为整体方案置信度，范围[0,1]。")
        lines.append("- 每一笔买入的quote_usdt应尽量≥5.00（满足交易所最小名义额），若当前可用USDT不足5.00，请优先通过卖出释放USDT后再规划买入，否则将buys设为空。")
        lines.append("- 卖出数量尽量为账户中该资产的全部或合理整数步进，考虑到交易所的数量步长(stepSize)与最小数量(minQty)，可将数量四舍五入到3~6位小数的合理值。")
        lines.append("- 方案中买入金额总和不要超过预计的可用USDT（当前USDT余额 + 卖出预计可入账的USDT）。")
        # 新增：手续费考量
        lines.append("- 在买入金额与卖出数量的规划中考虑交易所手续费（maker/taker），为避免成交后因手续费扣减导致名义额低于最小限额或数量不达步进，可对买入金额适度上浮、卖出数量适度下调。")
        lines.append("- 如果信息不确定或不需要调整，返回buys和sells均为空，confidence给出合理数值。")
        # 新增：针对“余额不足”误判的明确约束
        lines.append("- 若USDT余额≥5.00，则不得以‘余额不足’作为理由导致空方案；如选择不买入，应以行情信号/置信度等原因解释，并与输入数据一致。")
        lines.append("- 买入建议的quote_usdt范围为[5.00, min(USDT余额, 单笔上限, 单币持仓上限剩余额度)]，不要编造与输入相矛盾的理由（例如余额充足却声称不足）。")
        # 新增：当USDT余额充足时，鼓励至少一个买入以便执行层验证
        lines.append("- 当USDT余额≥5.00时，若无显著下跌信号，请在buys中至少给出一个买入项；若选择不买入，必须给出具体信号与风险解释，并降低confidence以反映不确定性。")
        return "\n".join(lines)

    def get_decision(self, prices: dict, historical: dict, balances: dict) -> dict:
        # 构建提示（优先包含持仓）
        try:
            prompt = self.build_prompt_with_holdings(prices, historical, balances) if balances else self.build_prompt_with_history(prices, historical)
        except Exception:
            prompt = self.build_prompt_with_history(prices, historical)
        # 调用模型
        response = self.llm_adapter.call(prompt)
        # 解析：支持新格式(buys/sells)与旧格式(symbol/action)
        import json
        decision = {}
        try:
            parsed = json.loads(response)
            # 新格式
            if isinstance(parsed, dict) and ("buys" in parsed or "sells" in parsed):
                cleaned = self._sanitize_plan(parsed, prices, balances)
                return cleaned
            # 旧格式（加入符号与动作合法性校验）
            valid_syms = {s for s, p in prices.items() if (p or 0) > 0}
            sym_raw = parsed.get("symbol")
            act_raw = parsed.get("action")
            action = (str(act_raw or "HOLD").upper())
            symbol = (str(sym_raw).upper()) if sym_raw else None
            if symbol and symbol not in valid_syms:
                symbol = None
            if action not in ("BUY", "SELL", "HOLD"):
                action = "HOLD"
            decision["symbol"] = symbol
            decision["action"] = action
            decision["confidence"] = float(parsed.get("confidence", 0.0) or 0.0)
            return decision
        except Exception:
            # 兜底：简单文本解析（旧逻辑）
            txt = str(response).upper()
            if "BUY" in txt:
                decision["action"] = "BUY"
            elif "SELL" in txt:
                decision["action"] = "SELL"
            else:
                decision["action"] = "HOLD"
            decision["symbol"] = None
            decision["confidence"] = 0.5
            return decision

    def format_decision_for_display(self, decision: dict) -> str:
        # 扩展展示：优先展示组合方案
        if decision.get("buys") is not None or decision.get("sells") is not None:
            buys = decision.get("buys", [])
            sells = decision.get("sells", [])
            lines = ["组合优化方案:"]
            if buys:
                lines.append("  买入:")
                for b in buys:
                    lines.append(f"    - {b.get('symbol')} | {float(b.get('quote_usdt', 0.0)):.4f} USDT")
            else:
                lines.append("  买入: []")
            if sells:
                lines.append("  卖出:")
                for s in sells:
                    lines.append(f"    - {s.get('symbol')} | {float(s.get('quantity', 0.0)):.8f} 份")
            else:
                lines.append("  卖出: []")
            lines.append(f"  置信度: {float(decision.get('confidence', 0.0)):.2f}")
            reason = decision.get("rationale")
            if reason:
                lines.append(f"  理由: {reason}")
            return "\n".join(lines)
        # 旧格式回退
        symbol = decision.get('symbol', 'None')
        action = decision.get('action', 'HOLD')
        confidence = float(decision.get('confidence', 0.0) or 0.0)
        rationale = decision.get('rationale', '无理由')
        return f"   决策: {action} {symbol}\n   信心: {confidence:.2f}\n   理由: {rationale}"

    def get_default_decision(self) -> Dict[str, Any]:
        """获取默认决策"""
        return {
            "symbol": None,
            "action": "HOLD",
            "confidence": 0.0,
            "rationale": "解析失败，默认观望"
        }
