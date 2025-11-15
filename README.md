# Alpha Arena

本项目是一个最简化的 AI 现货交易系统：支持 DeepSeek 与 Qwen 两种大模型，提供数据抓取、提示词驱动的交易决策、风控门控与自动执行管线。

## 整体逻辑
- 行情与账户：拉取实时价格、历史 K 线与账户持仓
- 提示词构建：根据当前/历史数据与持仓生成结构化决策提示词
- LLM 决策：调用 DeepSeek/Qwen 输出组合方案或单一动作
- 决策清洗：校验符号与金额/数量合法性，去重并移除冲突
- 风控门控：RSI、波动率、冷却期等硬性门槛；交易所过滤器校验
- 执行管线：监控/测试/真实单模式；组合方案先卖后买，额度与余额约束

## 特性
- 模型来源切换：`DECISION_MODEL=deepseek|qwen`
- 组合方案与单一决策：优先执行 `buys/sells` 组合；回退 `symbol/action`
- 风控门控：RSI、波动率、每币种冷却期；最小名义额与最小数量过滤器校验
- 执行模式：`monitor` 监控不下单；`test` 测试单；`live` 真实单
- 定时轮询：支持自动循环执行（可关闭）
- 结构化清洗：对 LLM 输出进行合法性校验、冲突移除与去重
- 配置外化：所有阈值与行为通过 `.env` 管理

## 目录结构
- `alpha-arena/main.py` 主流程入口，加载 `.env`、拉取行情与持仓、调用 LLM、门控与执行
- `alpha-arena/core/market.py` 市场数据与指标计算（RSI、波动率）
- `alpha-arena/core/decision.py` 决策引擎与提示词、LLM响应解析与清洗
- `alpha-arena/core/memory.py` 执行记忆管理（可选）
- `alpha-arena/adapters/deepseek_adapter.py` DeepSeek 集成（OpenAI SDK base_url 指向 DeepSeek）
- `alpha-arena/adapters/qwen_adapter.py` Qwen 集成（DashScope）
- `alpha-arena/adapters/exchange_api.py` 币安现货 API 适配器（价格、K线、余额、下单）
- `.env.example` 无密钥的环境模板（入库开源）
- `.env` 私密环境文件（本地使用，已在 `.gitignore` 忽略）
- `.gitignore` 忽略密钥与本地运行产物
- `alpha-arena/requirements.txt` 依赖（主版本上限约束）

## 安装
1) Python 3.10+ 环境
2) 安装依赖：
   - `pip install -r alpha-arena/requirements.txt`

## 配置
- 将仓库根的 `.env.example` 复制为 `.env` 并填写你的密钥：
  - `DEEPSEEK_API_KEY=`
  - `DASHSCOPE_API_KEY=`
  - `BINANCE_API_KEY=`
  - `BINANCE_API_SECRET=`
- 环境加载优先级（后者覆盖前者）：
  - `/.env` → `/.env.private` → `/.env.local` → 当前目录 `.env`
- 交易与风控关键项（可在 `.env` 中调整）：
  - 执行策略：`EXECUTION_POLICY=monitor|consensus`（默认 monitor）
  - 交易模式：`TRADE_MODE=test|live`（默认 test）
  - 模型来源：`DECISION_MODEL=deepseek|qwen`（默认 deepseek）
  - 置信度阈值：`MIN_CONFIDENCE_BUY=0.65`、`MIN_CONFIDENCE_SELL=0.65`、`LLM_MIN_CONF=0.65`
  - 额度控制：`MAX_TRADE_USDT=20`、`MAX_POSITION_USDT_PER_SYMBOL=50`
  - 共识控制：`CONSENSUS_REQUIRE_BOTH=1`
  - 指标门控：`RSI_PERIOD=14`、`RSI_BUY_MAX=65`、`RSI_SELL_MIN=35`、`MAX_VOLATILITY=0.12`
  - 冷却期：`TRADE_COOLDOWN_SEC=300`
  - 历史抓取：`HIST_INTERVAL=3m`、`HIST_LIMIT=20`
  - 交易对集：`TRADING_SYMBOLS=BTCUSDT, ETHUSDT, ...`（可写 BASE 或 BASEUSDT，自动补全 USDT；支持去重保序）

## 运行
- 单次运行：
  - `python alpha-arena/main.py`  
  - 可选参数：`--interval 3m`、`--limit 20`
- 自动运行（轮询）：
  - `.env` 设定：`AUTO_RUN=1`、`AUTO_RUN_INTERVAL_SEC=60`
  - 启动后会每间隔执行一次，`Ctrl+C` 停止

## 风控与执行
- 指标门控：
  - 买入需要 `RSI <= RSI_BUY_MAX` 且 `波动率 <= MAX_VOLATILITY` 且 冷却期已过
  - 卖出需要 `RSI >= RSI_SELL_MIN` 且 `波动率 <= MAX_VOLATILITY` 且 冷却期已过
- 交易过滤器（来自交易所）：
  - `minNotional` 最小名义额、`minQty` 最小数量、`stepSize` 数量步进
- 额度与余额：
  - 买入金额受 `MAX_TRADE_USDT` 与 `MAX_POSITION_USDT_PER_SYMBOL` 控制，并不超过当前 USDT 余额
- 执行策略：
  - `monitor` 模式下仅打印拟执行操作，不下单
  - 测试/真实单：`TRADE_MODE=test|live`

## LLM 决策与清洗
- 组合方案：
  - 清洗非法符号、非正金额/数量、去重，移除同一 symbol 的买卖冲突
- 单一决策：
  - `symbol` 必须在有效价格集合中；`action` 限于 `BUY/SELL/HOLD`，否则置为 `HOLD`

## 依赖与兼容
- 依赖版本（主版本上限约束）：
  - `openai>=1.0,<2`（DeepSeek 适配器使用该 SDK 指向 DeepSeek base_url）
  - `dashscope>=1.0,<2`
  - `requests>=2.28,<3`
  - `python-dotenv>=1.0,<2`
  - `python-binance>=1.0.17,<2`

## 安全与隐私
- `.env`、`.env.local`、`.env.private` 已在 `.gitignore` 忽略，密钥不会入库
- 开源发布时仅保留 `.env.example` 模板，不包含任何密钥

## 提示与注意
- 初次使用建议保持 `EXECUTION_POLICY=monitor` 与 `TRADE_MODE=test`，确认行为与门控后再切换真实单
- 如果提示“API不可用”，请检查密钥与网络；若出现 `-1021` 时间戳错误，适配器会自动重同步并重试

## 下一步可选增强
- 止盈/止损（含 OCO）保护单
- 多时间尺度一致性门控（如 15m/1h 同向）
- 回测与绩效度量（Sharpe、最大回撤、滑点统计）

## 免责声明
本项目不构成投资建议。加密资产交易风险较高，请在合规前提下谨慎操作，自行承担风险。
