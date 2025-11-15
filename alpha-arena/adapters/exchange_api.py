#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易所API适配器
基于币安(Binance) API获取真实价格数据
"""

import os
import sys
import requests
from typing import Dict, List

try:
    from binance.client import Client as BinanceClient
    from binance.exceptions import BinanceAPIException
except ImportError:
    print("❌ 请安装python-binance: pip install python-binance")
    BinanceClient = None
    BinanceAPIException = Exception


class ExchangeAPI:
    """交易所API适配器"""
    
    def __init__(self):
        """初始化交易所API"""
        if BinanceClient is None:
            raise ImportError("BinanceClient未找到，请安装python-binance")
        
        try:
            api_key = os.getenv('BINANCE_API_KEY')
            api_secret = os.getenv('BINANCE_API_SECRET')
            
            if not api_key or not api_secret:
                raise ValueError("币安API密钥未设置，请设置BINANCE_API_KEY和BINANCE_API_SECRET环境变量")
            
            self.client = BinanceClient(api_key, api_secret, requests_params={'timeout': int(os.getenv('BINANCE_HTTP_TIMEOUT_SEC', '10') or '10')})
            # 同步时间偏移，降低-1021错误概率
            try:
                server_time = self.client.get_server_time()
                if isinstance(server_time, dict) and 'serverTime' in server_time:
                    import time
                    # 使用正确的属性名timestamp_offset以与python-binance兼容
                    self.client.timestamp_offset = int(server_time['serverTime']) - int(time.time() * 1000)
                    print(f"⏱️ 与服务器时间偏移: {getattr(self.client, 'timestamp_offset', 0)} ms")
            except Exception as te:
                print(f"⚠️ 时间同步失败: {te}")
            print("✅ 币安API客户端初始化成功")
        except Exception as e:
            print(f"❌ 币安API客户端初始化失败: {e}")
            self.client = None
    
    def get_latest_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        获取多个代币的最新价格
        
        Args:
            symbols: 代币符号列表，如['BTCUSDT', 'ETHUSDT']
            
        Returns:
            价格字典，格式为{symbol: price}
        """
        if self.client is None:
            print("❌ API客户端未初始化")
            return {symbol: 0.0 for symbol in symbols}
        
        prices = {}
        
        try:
            # 使用币安API获取所有交易对的价格
            tickers = self.client.get_all_tickers()
            ticker_dict = {ticker['symbol']: float(ticker['price']) for ticker in tickers}
            
            for symbol in symbols:
                if symbol in ticker_dict:
                    price = ticker_dict[symbol]
                    prices[symbol] = price
                    print(f"✅ {symbol}: ${price:.4f}")
                else:
                    print(f"❌ 未找到{symbol}的价格信息")
                    prices[symbol] = 0.0
        except Exception as e:
            print(f"❌ 获取价格失败: {e}")
            return {symbol: 0.0 for symbol in symbols}
        
        return prices
    
    def get_single_price(self, symbol: str) -> float:
        """
        获取单个代币的价格
        
        Args:
            symbol: 代币符号，如'BTCUSDT'
            
        Returns:
            价格
        """
        if self.client is None:
            return 0.0
        # 依次尝试多种API以提升兼容性
        try:
            data = self.client.get_symbol_ticker(symbol=symbol)
            price = float(data.get('price', 0.0) or 0.0)
            if price > 0:
                return price
        except Exception:
            pass
        try:
            data = self.client.get_symbol_price_ticker(symbol=symbol)
            price = float(data.get('price', 0.0) or 0.0)
            if price > 0:
                return price
        except Exception:
            pass
        try:
            data = self.client.get_ticker(symbol=symbol)
            price = float((data.get('lastPrice') or data.get('weightedAvgPrice') or 0.0) or 0.0)
            if price > 0:
                return price
        except Exception:
            pass
        try:
            data = self.client.get_avg_price(symbol=symbol)
            price = float(data.get('price', 0.0) or 0.0)
            if price > 0:
                return price
        except Exception as e:
            print(f"❌ 获取{symbol}价格失败: {e}")
        return 0.0
    
    def get_historical_prices(self, symbols: List[str], interval: str = '3m', limit: int = 10) -> Dict[str, List[float]]:
        """
        获取多个代币的历史收盘价序列（按时间从旧到新）
        
        Args:
            symbols: 代币符号列表
            interval: K线周期，可选'1m','3m','5m','15m','1h'等
            limit: 返回的K线条数
        Returns:
            历史价格序列字典，格式为{symbol: [p1, p2, ..., pn]}
        """
        if self.client is None:
            print("❌ API客户端未初始化")
            return {symbol: [] for symbol in symbols}
        
        # 将字符串周期映射到Binance SDK常量
        interval_map = {
            '1m': BinanceClient.KLINE_INTERVAL_1MINUTE,
            '3m': BinanceClient.KLINE_INTERVAL_3MINUTE,
            '5m': BinanceClient.KLINE_INTERVAL_5MINUTE,
            '15m': BinanceClient.KLINE_INTERVAL_15MINUTE,
            '30m': BinanceClient.KLINE_INTERVAL_30MINUTE,
            '1h': BinanceClient.KLINE_INTERVAL_1HOUR,
            '4h': BinanceClient.KLINE_INTERVAL_4HOUR,
            '1d': BinanceClient.KLINE_INTERVAL_1DAY,
        }
        interval_const = interval_map.get(interval, BinanceClient.KLINE_INTERVAL_3MINUTE)
        
        series: Dict[str, List[float]] = {}
        try:
            for symbol in symbols:
                try:
                    klines = self.client.get_klines(symbol=symbol, interval=interval_const, limit=limit)
                    # kline结构: [open_time, open, high, low, close, volume, close_time, ...]
                    closes = [float(k[4]) for k in klines]
                    series[symbol] = closes
                    print(f"✅ {symbol} 历史K线获取成功: {len(closes)} 条")
                except Exception as se:
                    print(f"❌ 获取{symbol}历史K线失败: {se}")
                    series[symbol] = []
        except Exception as e:
            print(f"❌ 批量获取历史K线失败: {e}")
            return {symbol: [] for symbol in symbols}
        
        return series
    
    def _resync_time(self):
        """与服务器时间重同步，更新client.timestamp_offset"""
        if self.client is None:
            return
        try:
            server_time = self.client.get_server_time()
            if isinstance(server_time, dict) and 'serverTime' in server_time:
                import time
                self.client.timestamp_offset = int(server_time['serverTime']) - int(time.time() * 1000)
                print(f"🔄 重新同步时间偏移: {getattr(self.client, 'timestamp_offset', 0)} ms")
        except Exception as e:
            print(f"⚠️ 重同步时间失败: {e}")
    
    def get_account_balances(self) -> Dict[str, float]:
        """
        获取现货账户的资产余额（free+locked），仅返回数量>0的资产
        
        Returns:
            余额字典，格式为{asset: amount}
        """
        if self.client is None:
            print("❌ API客户端未初始化")
            return {}
        # 通过recvWindow放宽时间窗口，降低-1021错误概率
        import os as _os
        try:
            recv_window = int(_os.getenv('BINANCE_RECVWINDOW', '60000'))
            if recv_window > 60000:
                recv_window = 60000
        except Exception:
            recv_window = 60000
        attempts = 0
        while attempts < 2:
            try:
                account = self.client.get_account(recvWindow=recv_window)
                balances: Dict[str, float] = {}
                for b in account.get('balances', []):
                    asset = b.get('asset')
                    try:
                        free_amt = float(b.get('free', 0) or 0)
                        locked_amt = float(b.get('locked', 0) or 0)
                        total = free_amt + locked_amt
                        if asset and total > 0:
                            balances[asset] = total
                    except Exception:
                        continue
                return balances
            except BinanceAPIException as e:
                # 处理-1021错误：时间戳超前，重同步后重试
                if getattr(e, 'code', None) == -1021 or 'ahead of the server' in str(e) or 'outside of the recvWindow' in str(e):
                    print(f"⚠️ 时间戳错误({getattr(e, 'code', 'unknown')}), 尝试重同步时间后重试")
                    self._resync_time()
                    attempts += 1
                    continue
                else:
                    print(f"❌ 获取账户余额失败: {e}")
                    return {}
            except Exception as e:
                print(f"❌ 获取账户余额失败: {e}")
                return {}
        print("❌ 获取账户余额失败: 重试次数耗尽")
        return {}
    
    def is_available(self) -> bool:
        """检查API是否可用"""
        return self.client is not None

    def get_symbol_info(self, symbol: str) -> Dict:
        """获取交易对信息（过滤器、精度等）"""
        if self.client is None:
            return {}
        try:
            return self.client.get_symbol_info(symbol)
        except Exception as e:
            print(f"⚠️ 获取交易对信息失败: {e}")
            return {}
    
    def get_asset_balance(self, asset: str) -> float:
        """获取指定资产余额（free+locked）"""
        if self.client is None:
            return 0.0
        try:
            account = self.get_account_balances()
            return float(account.get(asset, 0.0))
        except Exception:
            return 0.0

    def get_asset_balance_detail(self, asset: str) -> Dict[str, float]:
        """获取指定资产余额明细：free、locked与total（free+locked）。"""
        if self.client is None:
            return {"free": 0.0, "locked": 0.0, "total": 0.0}
        try:
            bal = self.client.get_asset_balance(asset=asset)
            try:
                free = float(bal.get('free', 0) or 0)
            except Exception:
                free = 0.0
            try:
                locked = float(bal.get('locked', 0) or 0)
            except Exception:
                locked = 0.0
            return {"free": free, "locked": locked, "total": free + locked}
        except Exception as e:
            print(f"⚠️ 获取资产余额明细失败({asset}): {e}")
            return {"free": 0.0, "locked": 0.0, "total": 0.0}

    def get_asset_free_balance(self, asset: str) -> float:
        """获取指定资产的可用余额（free）。"""
        try:
            detail = self.get_asset_balance_detail(asset)
            return float(detail.get('free', 0.0) or 0.0)
        except Exception:
            return 0.0
    
    def place_market_buy_usdt(self, symbol: str, usdt_amount: float, test: bool = True) -> Dict:
        """下达市场买单，按USDT金额（quoteOrderQty）下单。test=True使用测试单。"""
        if self.client is None:
            return {"ok": False, "error": "client_not_initialized"}
        # 配置超时与重试
        import os as _os
        try:
            recv_window = int(_os.getenv('BINANCE_RECVWINDOW', '60000'))
            if recv_window > 60000:
                recv_window = 60000
        except Exception:
            recv_window = 60000
        try:
            max_attempts = int(_os.getenv('BINANCE_RETRY_ATTEMPTS', '2'))
        except Exception:
            max_attempts = 2
        attempts = 0
        while attempts < max_attempts:
            try:
                # 处理 quoteOrderQty 精度：根据交易对的 quotePrecision/quoteAssetPrecision 做量化，避免 -1111
                from decimal import Decimal, ROUND_DOWN
                raw_amount = float(usdt_amount)
                precision = 2
                try:
                    info = self.get_symbol_info(symbol) or {}
                    precision = int(info.get('quotePrecision', info.get('quoteAssetPrecision', 2)) or 2)
                except Exception:
                    precision = 2
                try:
                    quant = Decimal(str(raw_amount)).quantize(Decimal('1').scaleb(-precision), rounding=ROUND_DOWN)
                    rounded_amount = float(quant)
                except Exception:
                    rounded_amount = float(f"{raw_amount:.{precision}f}")
                if rounded_amount <= 0:
                    return {"ok": False, "error": "quoteOrderQty_non_positive_after_rounding"}
                params = {
                    'symbol': symbol,
                    'side': BinanceClient.SIDE_BUY,
                    'type': BinanceClient.ORDER_TYPE_MARKET,
                    'quoteOrderQty': float(rounded_amount),
                    'recvWindow': recv_window,
                    'newOrderRespType': 'RESULT',
                }
                if abs(rounded_amount - raw_amount) > 1e-12:
                    print(f"ℹ️ 订单金额精度调整: 原始={raw_amount:.10f} -> 下单={rounded_amount:.{precision}f} (精度={precision})")
                print(f"⏳ 正在提交市价买单(第{attempts+1}/{max_attempts}次)：{symbol} 金额={float(rounded_amount)} USDT, test={test}")
                if test:
                    self.client.create_test_order(**params)
                    print(f"✅ 市价买单测试提交成功：{symbol} 金额={float(rounded_amount)} USDT")
                    return {"ok": True, "type": "test", "symbol": symbol, "side": "BUY", "quoteOrderQty": float(usdt_amount)}
                else:
                    order = self.client.create_order(**params)
                    print(f"✅ 市价买单提交成功：{symbol} 金额={float(rounded_amount)} USDT")
                    return {"ok": True, "type": "live", "order": order}
            except BinanceAPIException as e:
                code = getattr(e, 'code', None)
                msg = str(e)
                # 时间戳与窗口错误，尝试重同步时间后重试
                if code == -1021 or 'ahead of the server' in msg or 'outside of the recvWindow' in msg:
                    print(f"⚠️ 时间戳/窗口错误({code})，尝试重同步时间后重试")
                    self._resync_time()
                    attempts += 1
                    continue
                print(f"❌ 下单失败(BinanceAPIException): {e}")
                return {"ok": False, "error": str(e), "code": code}
            except requests.exceptions.RequestException as e:
                print(f"⚠️ 网络异常/请求超时，自动重试：{e}")
                attempts += 1
                continue
            except Exception as e:
                print(f"❌ 下单失败: {e}")
                return {"ok": False, "error": str(e)}
        print("❌ 下单失败：重试次数耗尽")
        return {"ok": False, "error": "retry_exhausted"}

    def place_market_sell_qty(self, symbol: str, quantity: float, test: bool = True) -> Dict:
        """下达市场卖单，按数量（base asset）下单。test=True使用测试单。"""
        if self.client is None:
            return {"ok": False, "error": "client_not_initialized"}
        # 配置超时与重试
        import os as _os
        try:
            recv_window = int(_os.getenv('BINANCE_RECVWINDOW', '60000'))
            if recv_window > 60000:
                recv_window = 60000
        except Exception:
            recv_window = 60000
        try:
            max_attempts = int(_os.getenv('BINANCE_RETRY_ATTEMPTS', '2'))
        except Exception:
            max_attempts = 2
        attempts = 0
        while attempts < max_attempts:
            try:
                params = {
                    'symbol': symbol,
                    'side': BinanceClient.SIDE_SELL,
                    'type': BinanceClient.ORDER_TYPE_MARKET,
                    'quantity': float(quantity),
                    'recvWindow': recv_window,
                    'newOrderRespType': 'RESULT',
                }
                print(f"⏳ 正在提交市价卖单(第{attempts+1}/{max_attempts}次)：{symbol} 数量={float(quantity)}, test={test}")
                if test:
                    self.client.create_test_order(**params)
                    print(f"✅ 市价卖单测试提交成功：{symbol} 数量={float(quantity)}")
                    return {"ok": True, "type": "test", "symbol": symbol, "side": "SELL", "quantity": float(quantity)}
                else:
                    order = self.client.create_order(**params)
                    print(f"✅ 市价卖单提交成功：{symbol} 数量={float(quantity)}")
                    return {"ok": True, "type": "live", "order": order}
            except BinanceAPIException as e:
                code = getattr(e, 'code', None)
                msg = str(e)
                if code == -1021 or 'ahead of the server' in msg or 'outside of the recvWindow' in msg:
                    print(f"⚠️ 时间戳/窗口错误({code})，尝试重同步时间后重试")
                    self._resync_time()
                    attempts += 1
                    continue
                print(f"❌ 下单失败(BinanceAPIException): {e}")
                return {"ok": False, "error": str(e), "code": code}
            except requests.exceptions.RequestException as e:
                print(f"⚠️ 网络异常/请求超时，自动重试：{e}")
                attempts += 1
                continue
            except Exception as e:
                print(f"❌ 下单失败: {e}")
                return {"ok": False, "error": str(e)}
        print("❌ 下单失败：重试次数耗尽")
        return {"ok": False, "error": "retry_exhausted"}
