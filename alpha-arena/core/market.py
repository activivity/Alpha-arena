#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据模块
获取和管理市场数据
"""

from typing import Dict, List, Optional
from adapters.exchange_api import ExchangeAPI
import os


class MarketData:
    """市场数据管理器"""
    
    def __init__(self):
        """初始化市场数据管理器"""
        self.exchange_api = ExchangeAPI()
        # 支持从环境变量动态配置交易对，逗号分隔；未配置则使用扩展默认集合
        symbols_env = os.getenv('SYMBOLS') or os.getenv('TRADING_SYMBOLS')
        if symbols_env:
            syms = [s.strip().upper() for s in symbols_env.split(',') if s.strip()]
            normed = [(s if s.endswith('USDT') else f"{s}USDT") for s in syms]
            # 去重并保留原有顺序
            seen = set()
            ordered = []
            for s in normed:
                if s not in seen:
                    seen.add(s)
                    ordered.append(s)
            self.symbols = ordered
        else:
            # 扩展默认交易对集合（不局限于5个）
            self.symbols = [
                'BTCUSDT', 'ETHUSDT', 'XRPUSDT', 'BNBUSDT', 'SOLUSDT',
                'ADAUSDT', 'DOGEUSDT', 'TRXUSDT', 'DOTUSDT', 'MATICUSDT',
                'LINKUSDT', 'LTCUSDT', 'AVAXUSDT', 'ATOMUSDT', 'NEARUSDT',
                'BCHUSDT', 'ETCUSDT', 'XLMUSDT'
            ]
    
    def get_current_prices(self) -> Dict[str, float]:
        """
        获取当前所有代币的价格
        
        Returns:
            价格字典
        """
        return self.exchange_api.get_latest_prices(self.symbols)
    
    def get_price(self, symbol: str) -> float:
        """
        获取指定代币的价格
        
        Args:
            symbol: 代币符号
            
        Returns:
            价格
        """
        return self.exchange_api.get_single_price(symbol)
    
    def get_historical_prices(self, interval: str = None, limit: int = None) -> Dict[str, List[float]]:
        """
        获取所有代币的历史收盘价序列（从旧到新），支持从环境变量读取默认配置
        
        Args:
            interval: K线周期（默认从环境变量HIST_INTERVAL，若无则3m）
            limit: 返回的K线条数（默认从环境变量HIST_LIMIT，若无则20）
        Returns:
            历史价格序列字典，格式为{symbol: [p1, p2, ..., pn]}
        """
        if interval is None:
            interval = os.getenv('HIST_INTERVAL', '3m')
        if limit is None:
            try:
                limit = int(os.getenv('HIST_LIMIT', '20'))
            except Exception:
                limit = 20
        return self.exchange_api.get_historical_prices(self.symbols, interval=interval, limit=limit)
    
    def get_symbols(self) -> List[str]:
        """获取支持的代币列表"""
        return self.symbols.copy()
    
    def is_api_available(self) -> bool:
        """检查API是否可用"""
        return self.exchange_api.is_available()
    
    def format_prices_for_display(self, prices: Dict[str, float]) -> str:
        """
        格式化价格用于显示
        
        Args:
            prices: 价格字典
            
        Returns:
            格式化的价格字符串
        """
        lines = []
        for symbol, price in prices.items():
            if price > 0:
                lines.append(f"   {symbol}: ${price:.4f}")
            else:
                lines.append(f"   {symbol}: 获取失败")
        return "\n".join(lines)
    
    def format_historical_for_display(self, historical: Dict[str, List[float]], max_points: Optional[int] = 8) -> str:
        """
        格式化历史价格用于显示（仅展示前 max_points 个收盘价）
        
        Args:
            historical: 历史价格序列
            max_points: 每个代币展示的点数上限
        Returns:
            格式化字符串
        """
        lines = []
        for symbol, series in historical.items():
            if series:
                show = series[:max_points] if max_points else series
                series_str = ", ".join(f"{p:.2f}" for p in show)
                lines.append(f"   {symbol}: [{series_str}] ... ({len(series)}条)")
            else:
                lines.append(f"   {symbol}: 历史数据获取失败")
        return "\n".join(lines)
    
    def get_account_balances(self) -> Dict[str, float]:
        """获取账户资产余额（现货），返回数量>0的资产"""
        return self.exchange_api.get_account_balances()
    
    def format_balances_for_display(self, balances: Dict[str, float]) -> str:
        """格式化账户持仓用于显示"""
        if not balances:
            return "   无持仓或获取失败"
        lines = []
        for asset, amount in balances.items():
            lines.append(f"   {asset}: {amount:g}")
        return "\n".join(lines)

    # 指标计算
    def _compute_rsi(self, series: List[float], period: int = 14) -> Optional[float]:
        try:
            if not series or len(series) < period + 1:
                return None
            gains = []
            losses = []
            for i in range(1, len(series)):
                change = series[i] - series[i-1]
                gains.append(max(change, 0.0))
                losses.append(max(-change, 0.0))
            def _ema(values: List[float], p: int) -> float:
                k = 2 / (p + 1)
                ema = values[0]
                for v in values[1:]:
                    ema = v * k + ema * (1 - k)
                return ema
            avg_gain = _ema(gains[-period:], period)
            avg_loss = _ema(losses[-period:], period)
            if avg_loss == 0:
                return 100.0
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))
            return max(0.0, min(100.0, rsi))
        except Exception:
            return None

    def _compute_volatility(self, series: List[float]) -> Optional[float]:
        try:
            if not series or len(series) < 3:
                return None
            returns: List[float] = []
            for i in range(1, len(series)):
                prev, cur = series[i-1], series[i]
                if prev <= 0:
                    continue
                returns.append((cur - prev) / prev)
            if not returns:
                return None
            mean = sum(returns) / len(returns)
            var = sum((r - mean) ** 2 for r in returns) / max(1, len(returns) - 1)
            return var ** 0.5
        except Exception:
            return None

    def compute_indicators(self, historical: Dict[str, List[float]], rsi_period: Optional[int] = None) -> Dict[str, Dict[str, Optional[float]]]:
        try:
            if rsi_period is None:
                try:
                    rsi_period = int(os.getenv('RSI_PERIOD', '14'))
                except Exception:
                    rsi_period = 14
            out: Dict[str, Dict[str, Optional[float]]] = {}
            for symbol, series in historical.items():
                rsi = self._compute_rsi(series, period=rsi_period)
                vol = self._compute_volatility(series)
                out[symbol] = {"rsi": rsi, "volatility": vol}
            return out
        except Exception:
            return {}

    def format_indicators_for_display(self, indicators: Dict[str, Dict[str, Optional[float]]]) -> str:
        lines: List[str] = []
        for symbol, ind in indicators.items():
            rsi = ind.get('rsi')
            vol = ind.get('volatility')
            rsi_str = f"{rsi:.2f}" if isinstance(rsi, (int, float)) and rsi is not None else "N/A"
            vol_str = f"{(vol or 0.0)*100:.2f}%" if vol is not None else "N/A"
            lines.append(f"   {symbol}: RSI={rsi_str} | 波动={vol_str}")
        return "\n".join(lines)
