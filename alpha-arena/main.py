#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alpha Arena MVP - 主程序
最简化的AI交易决策对比系统
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv
import argparse

# 加载环境变量（以 .env 为准，允许覆盖终端环境）
# 优先加载项目根目录 .env（包含交易所密钥等），再加载私密覆盖与本地覆盖，最后加载当前目录 .env
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
ROOT_ENV_PATH = os.path.join(ROOT_DIR, '.env')
PRIVATE_ENV_PATH = os.path.join(ROOT_DIR, '.env.private')
LOCAL_ENV_PATH = os.path.join(ROOT_DIR, '.env.local')
load_dotenv(dotenv_path=ROOT_ENV_PATH, override=True)
load_dotenv(dotenv_path=PRIVATE_ENV_PATH, override=True)
load_dotenv(dotenv_path=LOCAL_ENV_PATH, override=True)
load_dotenv(override=True)

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.market import MarketData
from core.decision import DecisionMaker
from core.memory import append_memory, load_memory
from adapters.deepseek_adapter import DeepSeekAdapter
from adapters.qwen_adapter import QwenAdapter

# === 自动交易辅助函数 ===
import math

def _symbol_base(symbol: str) -> str:
    if symbol and symbol.endswith('USDT'):
        return symbol[:-4]
    return symbol or ''

def _parse_symbol_filters(info: dict) -> dict:
    out = {}
    try:
        for f in info.get('filters', []):
            ftype = f.get('filterType') or f.get('filter_type')
            if ftype == 'LOT_SIZE':
                out['stepSize'] = float(f.get('stepSize', '0') or 0)
                out['minQty'] = float(f.get('minQty', '0') or 0)
            elif ftype == 'MIN_NOTIONAL':
                out['minNotional'] = float(f.get('minNotional', '0') or 0)
            elif ftype == 'NOTIONAL':
                out['minNotional'] = float(f.get('minNotional', '0') or 0)
    except Exception:
        pass
    return out

def _round_to_step(quantity: float, step_size: float) -> float:
    try:
        if step_size <= 0:
            return quantity
        steps = math.floor(quantity / step_size)
        return max(0.0, steps * step_size)
    except Exception:
        return max(0.0, quantity)


def main():
    """主函数"""
    print("🚀 Alpha Arena - 最简化MVP")
    print("=" * 50)
    print(f"📅 运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 命令行参数
    parser = argparse.ArgumentParser(description="Alpha Arena 参数")
    parser.add_argument("--interval", type=str, help="K线周期，例如3m/15m/1h")
    parser.add_argument("--limit", type=int, help="历史点数，例如20/50/100")
    args = parser.parse_args()
    
    # 计算实际使用的周期与窗口
    interval_used = args.interval if args.interval else os.getenv('HIST_INTERVAL', '3m')
    try:
        limit_used = args.limit if args.limit is not None else int(os.getenv('HIST_LIMIT', '20'))
    except Exception:
        limit_used = args.limit if args.limit is not None else 20
    
    try:
        # 初始化市场数据管理器
        print("📊 初始化市场数据管理器...")
        market_data = MarketData()
        
        if not market_data.is_api_available():
            print("❌ 交易所API不可用，请检查配置")
            return
        
        # 获取实时价格
        print("💰 获取实时价格...")
        prices = market_data.get_current_prices()
        
        print("\n📈 当前市场价格:")
        print(market_data.format_prices_for_display(prices))
        
        # 获取历史价格（可配置：周期与点数）
        print(f"\n🕒 获取历史价格({interval_used} x {limit_used})...")
        historical = market_data.get_historical_prices(interval=interval_used, limit=limit_used)
        print("\n📉 历史价格预览:")
        print(market_data.format_historical_for_display(historical, max_points=8))
        # 计算技术指标
        print("\n🧪 计算技术指标(RSI/波动)...")
        indicators = market_data.compute_indicators(historical)
        print(market_data.format_indicators_for_display(indicators))
        
        # 获取账户持仓
        print("\n📦 获取账户持仓(现货)...")
        balances = market_data.get_account_balances()
        print("\n💼 当前账户持仓:")
        print(market_data.format_balances_for_display(balances))
        
        # 检查是否有有效价格
        valid_prices = {k: v for k, v in prices.items() if v > 0}
        if not valid_prices:
            print("❌ 没有获取到有效价格，请检查网络连接")
            return

        # 读取策略与风控配置（来自 .env，可随时调整）
        exec_policy = os.getenv('EXECUTION_POLICY', 'consensus').strip().lower()
        try:
            min_conf_buy = float(os.getenv('MIN_CONFIDENCE_BUY', '0.65'))
        except Exception:
            min_conf_buy = 0.65
        try:
            min_conf_sell = float(os.getenv('MIN_CONFIDENCE_SELL', '0.65'))
        except Exception:
            min_conf_sell = 0.65
        try:
            max_trade_usdt = float(os.getenv('MAX_TRADE_USDT', '20'))
        except Exception:
            max_trade_usdt = 20.0
        try:
            max_position_usdt = float(os.getenv('MAX_POSITION_USDT_PER_SYMBOL', '50'))
        except Exception:
            max_position_usdt = 50.0
        trade_mode = os.getenv('TRADE_MODE', 'live').strip().lower()
        # 新增：从 .env 读取决策来源（听哪个模型）。支持 deepseek 或 qwen，默认 deepseek
        decision_model = (os.getenv('DECISION_MODEL', 'deepseek') or 'deepseek').strip().lower()
        if decision_model not in ('deepseek', 'qwen'):
            print(f"⚠️ DECISION_MODEL={decision_model} 非法，回退为 deepseek")
            decision_model = 'deepseek'
        consensus_require_both = (os.getenv('CONSENSUS_REQUIRE_BOTH', '1').strip() == '1')
        # 指标门控与冷却配置
        try:
            rsi_buy_max = float(os.getenv('RSI_BUY_MAX', '65'))
        except Exception:
            rsi_buy_max = 65.0
        try:
            rsi_sell_min = float(os.getenv('RSI_SELL_MIN', '35'))
        except Exception:
            rsi_sell_min = 35.0
        try:
            max_volatility = float(os.getenv('MAX_VOLATILITY', '0.12'))
        except Exception:
            max_volatility = 0.12
        try:
            cooldown_sec = int(os.getenv('TRADE_COOLDOWN_SEC', '300'))
        except Exception:
            cooldown_sec = 300

        mode_label = '监控' if exec_policy == 'monitor' else ('真实单' if trade_mode=='live' else '测试单')
        print(f"\n⚙️ 执行策略: {exec_policy} | BUY阈值={min_conf_buy:.2f} SELL阈值={min_conf_sell:.2f} | 单笔上限={max_trade_usdt:.2f} USDT | 单币持仓上限={max_position_usdt:.2f} USDT | 模式={mode_label}")
        print(f"🎛️ 决策来源: {'DeepSeek' if decision_model=='deepseek' else 'Qwen'}")
        print(f"🧱 指标门控: RSI买入≤{rsi_buy_max:.0f} | RSI卖出≥{rsi_sell_min:.0f} | 波动≤{max_volatility*100:.2f}% | 冷却={cooldown_sec}s")

        # 初始化LLM适配器
        print("\n🤖 初始化AI模型...")
        
        # DeepSeek适配器
        try:
            deepseek_adapter = DeepSeekAdapter()
            deepseek_decision_maker = DecisionMaker(deepseek_adapter)
            print(f"✅ DeepSeek ({deepseek_adapter.get_model_name()}) 初始化成功")
        except Exception as e:
            print(f"❌ DeepSeek初始化失败: {e}")
            deepseek_decision_maker = None
        
        # Qwen适配器
        try:
            qwen_adapter = QwenAdapter()
            qwen_decision_maker = DecisionMaker(qwen_adapter)
            print(f"✅ Qwen ({qwen_adapter.get_model_name()}) 初始化成功")
        except Exception as e:
            print(f"❌ Qwen初始化失败: {e}")
            qwen_decision_maker = None
        
        if not deepseek_decision_maker and not qwen_decision_maker:
            print("❌ 没有可用的AI模型，请检查API密钥配置")
            return
        
        # 获取AI决策
        print("\n🧠 获取AI交易决策...")
        
        decisions = {}
        
        # DeepSeek决策
        if deepseek_decision_maker:
            print("\n🤖 DeepSeek决策:")
            try:
                deepseek_decision = deepseek_decision_maker.get_decision(prices, historical, balances)
                decisions['DeepSeek'] = deepseek_decision
                print(deepseek_decision_maker.format_decision_for_display(deepseek_decision))
            except Exception as e:
                print(f"❌ DeepSeek决策获取失败: {e}")
        
        # Qwen决策
        if qwen_decision_maker:
            print("\n🤖 Qwen决策:")
            try:
                qwen_decision = qwen_decision_maker.get_decision(prices, historical, balances)
                decisions['Qwen'] = qwen_decision
                print(qwen_decision_maker.format_decision_for_display(qwen_decision))
            except Exception as e:
                print(f"❌ Qwen决策获取失败: {e}")
        
        # 决策对比
        if len(decisions) >= 2:
            print("\n📊 决策对比:")
            print("-" * 30)
            
            for model_name, decision in decisions.items():
                # 兼容组合方案与旧格式
                def _fmt_model_decision_summary(d: dict) -> str:
                    conf = float(d.get('confidence', 0.0) or 0.0)
                    if isinstance(d, dict) and (('buys' in d) or ('sells' in d)):
                        buys_syms = [x.get('symbol') for x in (d.get('buys') or []) if x.get('symbol')]
                        sells_syms = [x.get('symbol') for x in (d.get('sells') or []) if x.get('symbol')]
                        buys_str = ','.join(buys_syms) if buys_syms else '[]'
                        sells_str = ','.join(sells_syms) if sells_syms else '[]'
                        return f"PLAN buys={buys_str} | sells={sells_str} | conf={conf:.2f}"
                    else:
                        symbol = d.get('symbol', 'None')
                        action = d.get('action', 'HOLD')
                        return f"{action} {symbol} | conf={conf:.2f}"
                print(f"   {model_name}: {_fmt_model_decision_summary(decision)}")
            
            # 检查是否一致（支持组合方案共识）
            if len(decisions) == 2:
                d1 = decisions.get('DeepSeek', {})
                d2 = decisions.get('Qwen', {})
                def _is_plan_local(d: dict) -> bool:
                    return isinstance(d, dict) and (("buys" in d) or ("sells" in d))
                def _conf_ok_for_plan(d: dict) -> bool:
                    conf = float(d.get('confidence', 0.0) or 0.0)
                    has_buy = bool(d.get('buys'))
                    has_sell = bool(d.get('sells'))
                    if has_buy and has_sell:
                        return conf >= max(min_conf_buy, min_conf_sell)
                    elif has_buy:
                        return conf >= min_conf_buy
                    elif has_sell:
                        return conf >= min_conf_sell
                    else:
                        return False
                if _is_plan_local(d1) and _is_plan_local(d2):
                    b1 = {x.get('symbol') for x in (d1.get('buys') or []) if x.get('symbol')}
                    b2 = {x.get('symbol') for x in (d2.get('buys') or []) if x.get('symbol')}
                    s1 = {x.get('symbol') for x in (d1.get('sells') or []) if x.get('symbol')}
                    s2 = {x.get('symbol') for x in (d2.get('sells') or []) if x.get('symbol')}
                    shared_buys = b1 & b2
                    shared_sells = s1 & s2
                    if b1 == b2 and s1 == s2:
                        ok1 = _conf_ok_for_plan(d1)
                        ok2 = _conf_ok_for_plan(d2)
                        if ok1 and ok2:
                            print("   🎯 两个AI在组合方案上完全一致（满足阈值）！")
                        elif ok1 or ok2:
                            if consensus_require_both:
                                print("   🎯 两个AI在组合方案上完全一致，但仅一方达阈值，默认不执行。可设置 CONSENSUS_REQUIRE_BOTH=0 以非严格执行")
                            else:
                                print("   🎯 两个AI在组合方案上完全一致（非严格），将执行置信度更高的一方方案")
                        else:
                            print("   🎯 两个AI在组合方案上完全一致，但均未达阈值，暂不执行")
                    elif shared_buys or shared_sells:
                        msg = []
                        if shared_sells:
                            msg.append(f"卖出共识: {', '.join(sorted(shared_sells))}")
                        if shared_buys:
                            msg.append(f"买入共识: {', '.join(sorted(shared_buys))}")
                        print(f"   🎯 存在部分共识（{'; '.join(msg)}）")
                    else:
                        print("   ⚡ 两个AI组合方案存在分歧")
                else:
                    if (d1.get('symbol') == d2.get('symbol') and d1.get('action') == d2.get('action')):
                        print("   🎯 两个AI达成一致！")
                    else:
                        print("   ⚡ 两个AI意见分歧")
            
            # 选择最终执行决策（支持组合方案buys/sells）
            def _is_plan(d: dict) -> bool:
                return isinstance(d, dict) and (("buys" in d) or ("sells" in d))
            
            def _plan_conf_ok(d: dict) -> bool:
                conf = float(d.get('confidence', 0.0) or 0.0)
                has_buy = bool(d.get('buys'))
                has_sell = bool(d.get('sells'))
                if has_buy and has_sell:
                    return conf >= max(min_conf_buy, min_conf_sell)
                elif has_buy:
                    return conf >= min_conf_buy
                elif has_sell:
                    return conf >= min_conf_sell
                else:
                    return False
            
        def _choose_final(decisions: dict) -> dict:
                # 根据 DECISION_MODEL 选择模型：deepseek 或 qwen
                model_key = 'DeepSeek' if decision_model == 'deepseek' else 'Qwen'
                d = decisions.get(model_key, {})
                if _is_plan(d) and _plan_conf_ok(d):
                    print(f"   🎯 策略：仅听 {model_key} 的组合优化方案")
                    return d
                # 回退到单一动作（仅所选模型）
                sym, act = d.get('symbol'), d.get('action')
                conf = float(d.get('confidence', 0.0) or 0.0)
                if act == 'BUY' and sym and conf >= min_conf_buy:
                    print(f"   🎯 策略：仅听 {model_key} 的单一BUY决策 {sym}")
                    return {'symbol': sym, 'action': 'BUY', 'confidence': conf}
                if act == 'SELL' and sym and conf >= min_conf_sell:
                    print(f"   🎯 策略：仅听 {model_key} 的单一SELL决策 {sym}")
                    return {'symbol': sym, 'action': 'SELL', 'confidence': conf}
                return {}

        # 指标与冷却门控
        from datetime import datetime as _dt
        def _get_ind(symbol: str) -> tuple:
            ind = indicators.get(symbol) or {}
            return (ind.get('rsi'), ind.get('volatility'))
        def _cooldown_ok(symbol: str) -> bool:
            try:
                mem = load_memory()
                if not mem:
                    return True
                last_ts = None
                for rec in reversed(mem):
                    ts = rec.get('timestamp')
                    res = rec.get('results') or []
                    for op in res:
                        if op.get('symbol') == symbol and op.get('ok') and not op.get('monitor_only'):
                            last_ts = ts
                            break
                    if last_ts:
                        break
                if not last_ts:
                    return True
                try:
                    last_dt = _dt.fromisoformat(last_ts)
                except Exception:
                    return True
                delta = (_dt.now() - last_dt).total_seconds()
                return delta >= cooldown_sec
            except Exception:
                return True
        def _gating_buy(symbol: str) -> bool:
            rsi, vol = _get_ind(symbol)
            if rsi is not None and rsi > rsi_buy_max:
                print(f"⏸️ 指标门控：{symbol} RSI={rsi:.2f} > {rsi_buy_max:.2f}，跳过买入")
                return False
            if vol is not None and vol > max_volatility:
                print(f"⏸️ 指标门控：{symbol} 波动={(vol*100):.2f}% > {(max_volatility*100):.2f}%，跳过买入")
                return False
            if not _cooldown_ok(symbol):
                print(f"⏸️ 冷却期未过：{symbol}，跳过买入")
                return False
            return True
        def _gating_sell(symbol: str) -> bool:
            rsi, vol = _get_ind(symbol)
            if rsi is not None and rsi < rsi_sell_min:
                print(f"⏸️ 指标门控：{symbol} RSI={rsi:.2f} < {rsi_sell_min:.2f}，跳过卖出")
                return False
            if vol is not None and vol > max_volatility:
                print(f"⏸️ 指标门控：{symbol} 波动={(vol*100):.2f}% > {(max_volatility*100):.2f}%，跳过卖出")
                return False
            if not _cooldown_ok(symbol):
                print(f"⏸️ 冷却期未过：{symbol}，跳过卖出")
                return False
            return True

        # 明确策略选择日志：仅听所选模型，忽略其他模型输出
        print(f"\n🔧 策略选择：仅听 {'DeepSeek' if decision_model=='deepseek' else 'Qwen'}（忽略其他模型输出）")
        final_decision = _choose_final(decisions)
        op_records = []
        # 调试输出：打印最终选择的决策结构，便于核对与模型输出是否一致
        try:
            print(f"\n🧭 最终选择的执行决策结构: {final_decision}")
        except Exception:
            pass
        if not final_decision:
            print("\n⏸️ 未满足执行条件，跳过交易")
            print("✅ 运行完成！")
            # 记录记忆（可选）
            try:
                append_memory({
                    "timestamp": datetime.now().isoformat(timespec='seconds'),
                    "trade_mode": trade_mode,
                    "decision_model": decision_model,
                    "final_decision": final_decision,
                    "results": []
                })
            except Exception:
                pass
            return

        # 若为组合方案：执行sells再执行buys
        if _is_plan(final_decision):
            buys = final_decision.get('buys') or []
            sells = final_decision.get('sells') or []
            print("\n🚦 执行组合优化方案")
            print(f"   方案置信度: {float(final_decision.get('confidence', 0.0)):.2f}")
            try:
                buy_list_preview = [(x.get('symbol'), float(x.get('quote_usdt') or 0.0)) for x in buys]
                sell_list_preview = [(x.get('symbol'), float(x.get('quantity') or 0.0)) for x in sells]
                print(f"   交集买入清单: {buy_list_preview}")
                print(f"   交集卖出清单: {sell_list_preview}")
            except Exception:
                pass
            if not balances:
                print("❌ 无法获取账户持仓，自动执行中止")
                print("✅ 运行完成！")
                return
            # 估算USDT余额（先卖后买，卖出按当前价格估算USDT入账）
            remaining_usdt = float(balances.get('USDT', 0.0))
            # 先执行卖出
            for s in sells:
                sym = s.get('symbol')
                qty_req = float(s.get('quantity') or 0.0)
                if not sym or qty_req <= 0:
                    continue
                if not _gating_sell(sym):
                    op_records.append({"op": "SELL", "symbol": sym, "qty": qty_req, "ok": True, "skipped": True, "reason": "gating"})
                    continue
                base = _symbol_base(sym)
                current_price = market_data.get_price(sym)
                if current_price <= 0:
                    print(f"⏸️ 跳过卖出 {sym}: 无法获取当前价格")
                    continue
                # 过滤器
                sym_info = market_data.exchange_api.get_symbol_info(sym)
                filters = _parse_symbol_filters(sym_info or {})
                min_notional = filters.get('minNotional', 5.0)
                step_size = filters.get('stepSize', 0.0)
                min_qty = filters.get('minQty', 0.0)
                # 使用可用余额（free）避免锁定仓位导致无法卖出
                base_free = market_data.exchange_api.get_asset_free_balance(base)
                base_total = float(balances.get(base, 0.0))
                if base_free <= 0:
                    print(f"⏸️ 跳过卖出 {sym}: {base} 可用余额为0（total={base_total:g}），可能存在挂单或锁定")
                    continue
                sell_qty = min(base_free, qty_req)
                sell_qty = _round_to_step(sell_qty, step_size)
                if sell_qty <= 0:
                    print(f"⏸️ 跳过卖出 {sym}: 可卖数量不足")
                    continue
                if min_qty > 0 and sell_qty < min_qty:
                    print(f"⏸️ 跳过卖出 {sym}: {sell_qty:g} < 最小数量 {min_qty:g}")
                    continue
                if sell_qty * current_price < min_notional:
                    print(f"⏸️ 跳过卖出 {sym}: 名义额 {sell_qty*current_price:.4f} < 最小名义额 {min_notional:.2f}")
                    continue
                if exec_policy == 'monitor':
                    print(f"👀 监控模式：拟卖出 {sym}, quantity={sell_qty:g}（不执行下单）")
                    op_records.append({"op": "SELL", "symbol": sym, "qty": sell_qty, "ok": True, "monitor_only": True})
                else:
                    print(f"📤 卖出: {sym}, quantity={sell_qty:g}")
                    res = market_data.exchange_api.place_market_sell_qty(sym, sell_qty, test=(trade_mode != 'live'))
                    if res.get('ok'):
                        est_usdt = sell_qty * current_price
                        remaining_usdt += est_usdt
                        print(f"✅ 卖单成功(或测试成功)，估算入账USDT: {est_usdt:.4f}")
                        op_records.append({"op": "SELL", "symbol": sym, "qty": sell_qty, "ok": True, "response": res})
                    else:
                        print(f"❌ 卖单提交失败: {res}")
                        op_records.append({"op": "SELL", "symbol": sym, "qty": sell_qty, "ok": False, "response": res})
            # 再执行买入
            for b in buys:
                sym = b.get('symbol')
                quote_req = float(b.get('quote_usdt') or 0.0)
                # 允许 quote_req 缺失或为 0，后续使用余额与风控兜底
                if not sym:
                    continue
                if not _gating_buy(sym):
                    op_records.append({"op": "BUY", "symbol": sym, "usdt": quote_req, "ok": True, "skipped": True, "reason": "gating"})
                    continue
                base = _symbol_base(sym)
                current_price = market_data.get_price(sym)
                if current_price <= 0:
                    # 回退使用批量价格结果
                    fallback_price = float(prices.get(sym, 0.0) or 0.0)
                    if fallback_price > 0:
                        current_price = fallback_price
                        print(f"ℹ️ 买入 {sym}: 使用回退价格 ${current_price:.6f}")
                    else:
                        print(f"⏸️ 跳过买入 {sym}: 无法获取当前价格")
                        continue
                sym_info = market_data.exchange_api.get_symbol_info(sym)
                filters = _parse_symbol_filters(sym_info or {})
                min_notional = filters.get('minNotional', 5.0)
                # 当前该币种仓位USDT
                base_qty = float(balances.get(base, 0.0))
                current_pos_usdt = base_qty * current_price
                # 可用USDT（剩余额度 + 风控）
                # 若quote_req缺失或为0，兜底使用余额与风控限额
                effective_quote = quote_req if quote_req > 0 else max(0.0, remaining_usdt)
                buy_usdt = min(effective_quote, max_trade_usdt, max(0.0, max_position_usdt - current_pos_usdt), max(0.0, remaining_usdt))
                print(f"🔎 买入检查 {sym}: 价格={current_price:.6f}, minNotional={min_notional:.2f}, USDT余额(估算)={remaining_usdt:.4f}, 当前{base}持仓={base_qty:g} (~{current_pos_usdt:.4f} USDT), 计划金额={quote_req:.4f}, 实际下单金额={buy_usdt:.4f}")
                if buy_usdt < max(min_notional, 1e-6):
                    print(f"⏸️ 跳过买入 {sym}: 金额 {buy_usdt:.4f} < 最小名义额 {min_notional:.2f} 或USDT不足")
                    continue
                if exec_policy == 'monitor':
                    print(f"👀 监控模式：拟买入 {sym}, quoteOrderQty={buy_usdt:.4f} USDT（不执行下单）")
                    op_records.append({"op": "BUY", "symbol": sym, "usdt": buy_usdt, "ok": True, "monitor_only": True})
                else:
                    print(f"🛒 买入: {sym}, quoteOrderQty={buy_usdt:.4f} USDT")
                    res = market_data.exchange_api.place_market_buy_usdt(sym, buy_usdt, test=(trade_mode != 'live'))
                    if res.get('ok'):
                        remaining_usdt -= buy_usdt
                        print(f"✅ 买单成功(或测试成功)，剩余USDT估算: {remaining_usdt:.4f}")
                        op_records.append({"op": "BUY", "symbol": sym, "usdt": buy_usdt, "ok": True, "response": res})
                    else:
                        print(f"❌ 买单提交失败: {res}")
                        op_records.append({"op": "BUY", "symbol": sym, "usdt": buy_usdt, "ok": False, "response": res})

            # 记录记忆（可选）
            try:
                append_memory({
                    "timestamp": datetime.now().isoformat(timespec='seconds'),
                    "trade_mode": trade_mode,
                    "decision_model": decision_model,
                    "final_decision": final_decision,
                    "results": op_records
                })
            except Exception:
                pass
            print("\n✅ 组合方案执行完成！")
            return

        # 旧逻辑：单一symbol/action
        if final_decision.get('action') == 'HOLD' or not final_decision.get('symbol'):
            print("\n⏸️ 最终决策为HOLD或无有效symbol，跳过交易")
            print("✅ 运行完成！")
            return

        symbol = final_decision['symbol']
        action = final_decision['action']
        base = _symbol_base(symbol)
        print(f"\n🚦 执行决策: {action} {symbol} (base={base}), 置信度={float(final_decision.get('confidence', 0.0)):.2f}")

        # 需要持仓与价格信息
        if not balances:
            print("❌ 无法获取账户持仓，自动执行中止")
            print("✅ 运行完成！")
            try:
                append_memory({
                    "timestamp": datetime.now().isoformat(timespec='seconds'),
                    "trade_mode": trade_mode,
                    "decision_model": decision_model,
                    "final_decision": final_decision,
                    "results": op_records
                })
            except Exception:
                pass
            return
        current_price = market_data.get_price(symbol)
        if current_price <= 0:
            print("❌ 无法获取当前价格，自动执行中止")
            print("✅ 运行完成！")
            try:
                append_memory({
                    "timestamp": datetime.now().isoformat(timespec='seconds'),
                    "trade_mode": trade_mode,
                    "decision_model": decision_model,
                    "final_decision": final_decision,
                    "results": op_records
                })
            except Exception:
                pass
            return

        # 交易对过滤器（步长、最小名义额）
        sym_info = market_data.exchange_api.get_symbol_info(symbol)
        filters = _parse_symbol_filters(sym_info or {})
        min_notional = filters.get('minNotional', 5.0)
        step_size = filters.get('stepSize', 0.0)
        min_qty = filters.get('minQty', 0.0)

        if action == 'BUY':
            if not _gating_buy(symbol):
                print("⏸️ 指标/冷却门控未通过，跳过BUY")
                print("✅ 运行完成！")
                return
            usdt_bal = float(balances.get('USDT', 0.0))
            base_qty = float(balances.get(base, 0.0))
            current_pos_usdt = base_qty * current_price
            # 使用全部USDT余额（不再保留）
            spendable = max(0.0, usdt_bal)
            # 目标买入金额：不再受USDT保留与卖出比例影响
            buy_usdt = min(max_trade_usdt, max(0.0, max_position_usdt - current_pos_usdt), spendable)
            if buy_usdt < max(min_notional, 1e-6):
                print(f"⏸️ BUY金额不足(拟买 {buy_usdt:.2f} < 最小名义额 {min_notional:.2f})，跳过")
            else:
                if exec_policy == 'monitor':
                    print(f"👀 监控模式：拟下市场买单 {symbol}, quoteOrderQty={buy_usdt:.2f} USDT（不执行下单）")
                    op_records.append({"op": "BUY", "symbol": symbol, "usdt": buy_usdt, "ok": True, "monitor_only": True})
                else:
                    print(f"🛒 准备下市场买单: {symbol}, quoteOrderQty={buy_usdt:.2f} USDT")
                    res = market_data.exchange_api.place_market_buy_usdt(symbol, buy_usdt, test=(trade_mode != 'live'))
                    if res.get('ok'):
                        print(f"✅ 买单提交成功 ({'测试单' if trade_mode!='live' else '真实单'}) | 详情: {res}")
                        op_records.append({"op": "BUY", "symbol": symbol, "usdt": buy_usdt, "ok": True, "response": res})
                    else:
                        print(f"❌ 买单提交失败: {res}")
                        op_records.append({"op": "BUY", "symbol": symbol, "usdt": buy_usdt, "ok": False, "response": res})
        elif action == 'SELL':
            if not _gating_sell(symbol):
                print("⏸️ 指标/冷却门控未通过，跳过SELL")
                print("✅ 运行完成！")
                return
            base_free = market_data.exchange_api.get_asset_free_balance(base)
            base_total = float(balances.get(base, 0.0))
            if base_free <= 0:
                print(f"⏸️ 当前无可用持仓可卖出（free=0, total={base_total:g}），跳过")
            else:
                sell_qty = _round_to_step(base_free, step_size)
                if min_qty > 0 and sell_qty < min_qty:
                    print(f"⏸️ 卖出数量不足(拟卖 {sell_qty:g} < 最小数量 {min_qty:g})，跳过")
                elif sell_qty * current_price < min_notional:
                    print(f"⏸️ 卖出名义额不足(拟卖额 {sell_qty*current_price:.2f} < 最小名义额 {min_notional:.2f})，跳过")
                else:
                    if exec_policy == 'monitor':
                        print(f"👀 监控模式：拟下市场卖单 {symbol}, quantity={sell_qty:g}（不执行下单）")
                        op_records.append({"op": "SELL", "symbol": symbol, "qty": sell_qty, "ok": True, "monitor_only": True})
                    else:
                        print(f"📤 准备下市场卖单: {symbol}, quantity={sell_qty:g}")
                        res = market_data.exchange_api.place_market_sell_qty(symbol, sell_qty, test=(trade_mode != 'live'))
                        if res.get('ok'):
                            print(f"✅ 卖单提交成功 ({'测试单' if trade_mode!='live' else '真实单'}) | 详情: {res}")
                            op_records.append({"op": "SELL", "symbol": symbol, "qty": sell_qty, "ok": True, "response": res})
                        else:
                            print(f"❌ 卖单提交失败: {res}")
                            op_records.append({"op": "SELL", "symbol": symbol, "qty": sell_qty, "ok": False, "response": res})


        # 记录记忆（可选）
        try:
            append_memory({
                "timestamp": datetime.now().isoformat(timespec='seconds'),
                "trade_mode": trade_mode,
                "decision_model": decision_model,
                "final_decision": final_decision,
                "results": op_records
            })
        except Exception:
            pass
        print("\n✅ 运行完成！")
        
    except KeyboardInterrupt:
        print("\n\n⏹️ 用户中断程序")
        # 若开启自动运行模式，则将中断向外抛出以便外层循环停止
        if os.getenv('AUTO_RUN', '0') == '1':
            raise
    except Exception as e:
        print(f"\n❌ 程序运行出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 支持通过环境变量启用自动运行
    # AUTO_RUN=1 开启自动运行；AUTO_RUN_INTERVAL_SEC 指定间隔秒数（默认60）
    auto = os.getenv('AUTO_RUN', '0') == '1'
    interval_sec_str = os.getenv('AUTO_RUN_INTERVAL_SEC', '60')
    try:
        interval_sec = int(interval_sec_str)
    except Exception:
        interval_sec = 60
    if auto:
        import time
        print(f"⏳ 自动运行模式已开启，每 {interval_sec} 秒运行一次。按 Ctrl+C 停止。")
        try:
            while True:
                main()
                time.sleep(interval_sec)
        except KeyboardInterrupt:
            print("\n⏹️ 已停止自动运行")
    else:
        main()
