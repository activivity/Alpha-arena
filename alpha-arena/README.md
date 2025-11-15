# 🧠 Alpha Arena

> 一个让 AI 模型在真实市场中进行实盘交易与对抗的实验平台。  
> "让智能体在不确定性中生存，并最终学会盈利。"

[![Version](https://img.shields.io/badge/version-v0.1.0--MVP-blue.svg)](VERSION.md)
[![Status](https://img.shields.io/badge/status-开发中-yellow.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.8+-green.svg)](requirements.txt)

---

## 📘 项目简介

**Alpha Arena** 是一个以真实市场为测试场的 AI 智能体交易实验平台。  
每个模型（如 GPT-5、Claude、DeepSeek、Gemini 等）都会获得相同的实时市场数据与初始资金，独立决策、执行交易，并实时比较收益、回撤和风险控制能力。

### 🎯 MVP 目标与边界

**核心目标（能跑、可比、可复现）：**
1. 同一时刻、同一数据、同一规则下，让 2–6 个 LLM 给出**统一结构化交易决策**
2. 对每个模型维持**独立资金账户**，执行撮合并**实时统计净值曲线**与核心指标
3. **全链路可追溯**：每个决策可回看 Prompt、上下文行情快照、执行回报

**MVP 边界（先不做）：**
- 不做杠杆/合约（先用现货 **BTCUSDT/ETHUSDT** 两个标的）
- 不做做空（先做多或空仓）
- 不做复杂下单类型（先用市价单 + 固定滑点假设）
- 决策周期固定（如**每 5 分钟**一次），统一同根时钟

### 🔬 探索方向

该项目旨在探索：
- 大语言模型是否能在真实金融市场中形成可持续的交易逻辑
- 不同模型在风险、反应速度、决策稳定性方面的差异
- 如何通过强化学习、策略蒸馏等手段让 AI 智能体不断进化

---

## 🏗️ 系统架构

```
/arena-mvp
├─ apps/
│  ├─ orchestrator/        # 调度器（定时拉数据、调用LLM、收单、风控、记账）
│  ├─ exchange_adapter/    # 交易所适配（Bitget/OKX/CCXT任选其一，先接 paper）
│  ├─ llm_gateway/         # LLM统一网关（OpenAI/DeepSeek/Anthropic/Google 等）
│  ├─ portfolio/           # 账本&风控（每模型一账本）
│  └─ dashboard/           # 简易可视化（Streamlit 或极简React前端）
├─ storage/
│  ├─ postgres/            # 交易、K线、模型输出、成交、资产…表
│  └─ redis/               # 短期队列/去重/限速
├─ docker-compose.yml
└─ README.md
```

### 📋 服务职责

| 模块 | 说明 |
|------|------|
| **Orchestrator** | 每 5 分钟触发一次 → 拉两只币最近 60 分钟 K 线 + 当前盘口快照 → 生成统一 Prompt → 并行请求各 LLM → 校验响应 schema → 丢给风控/执行层 |
| **LLM Gateway** | 为不同家 LLM 适配统一的请求/重试/限速/超时（如 8s 超时，超时=默认 Hold） |
| **Exchange Adapter** | 先接 **paper-trading**（仿真撮合+固定滑点），可一键切换到 **Bitget 现货实盘** |
| **Portfolio** | 每模型单独资产账簿（现金、持仓、浮盈），统一费率（如万 5）、统一滑点（如 5–10 bp） |
| **Dashboard** | 净值曲线、当日 PnL、持仓表、成交表、模型延迟、错误率 |

---

## ⚙️ 技术栈

- **Backend**：Python 3.11 / FastAPI / pandas / asyncio  
- **Database**：PostgreSQL + Redis  
- **Frontend**：Streamlit (或 Next.js 可视化面板)  
- **LLM 接口**：OpenAI / DeepSeek / Anthropic / Google / Qwen  
- **交易所**：Bitget / OKX / CCXT（paper-trading 优先）

---

## 📊 交易规范

### 🎯 统一 Prompt 与输出规范

**系统 Prompt（摘要版）：**
```
System: 你是量化交易代理，请在唯一JSON中输出交易指令，严格遵守schema。
Market Time (UTC): {ts}
Account: cash_usdt: {cash}, positions: [{symbol, qty, avg_px}]
Universe: [BTCUSDT, ETHUSDT] (spot only)
Last 60m 1m-bars (ohlcv): {per-symbol arrays}
Live Ticker: {bid, ask, mid, spread_bp}
Fees: 5 bp; Slippage: 10 bp (est.)
Constraints:
  - Decision cadence: 5m once
  - Max gross exposure: 20% of NAV per trade
  - Long only, at most 1 open symbol
  - Provide TP/SL as absolute prices
Task: If have position: hold/close with reasons; If flat: buy/hold with reasons
Return JSON only. No extra text.
```

**输出 Schema（严格校验）：**
```json
{
  "symbol": "BTCUSDT|ETHUSDT|null",
  "action": "BUY|SELL|HOLD",
  "position_size_pct": 0.0,
  "take_profit": 0.0,
  "stop_loss": 0.0,
  "confidence": 0.0,
  "rationale": "short text (<=200 chars)"
}
```

### ⚖️ 风控与执行规则

- **初始资金**：每模型 USDT 10,000
- **单次下单**：不超过净值 20%
- **持仓限制**：最多同时持 1 个标的
- **止损止盈**：模型给出，风控兜底强平阈值 -5%
- **手续费**：万 5
- **滑点**：10bp（paper-trading）
- **去重**：5 分钟内仅一次新决策
- **超时处理**：LLM 超时 8s → 默认 HOLD

### 📈 评价指标

**实时指标：**
- 净值、当日 PnL、持仓、暴露比例
- 上次推理延迟/超时率

**阶段统计：**
- 累计收益、最大回撤（MDD）
- Calmar/Sharpe 比率
- 胜率、平均盈亏比、交易次数
- 平均持仓时长、滑点/费率占比

**合规性指标：**
- 越权（超额下单）、JSON 违规、超时、拒答次数

---

## 🚀 实现计划（5-7 天可跑）

| 天数 | 任务 |
|------|------|
| **Day 1** | 初始化仓库与 Docker；建表（trades, positions, nav, prompts, decisions, metrics）；接交易所（paper）+ 行情抓取 |
| **Day 2** | 完成 Orchestrator 基本循环（5m 定时、行情→Prompt→LLM→schema→执行→记账）；接入 1 家 LLM 跑通 E2E |
| **Day 3** | 接入 2–3 家 LLM；并行推理、超时回退、JSON 校验；完成风控兜底（限仓、止盈止损、强平） |
| **Day 4** | Dashboard（Streamlit）+ 指标计算（实时+日内）；审计追溯视图（Prompt/JSON/行情快照） |
| **Day 5-7** | 稳定性与回测回灌测试；可选切换 **Bitget 现货实盘**（极小资金验证成交路径） |

---

## 🔧 关键配置

| 参数 | 默认值 |
|------|--------|
| 决策周期 | **5m** |
| 标的 | **BTCUSDT、ETHUSDT（现货）** |
| 初始资金 | **$10,000 / 模型** |
| 单笔最大下单 | **20% NAV** |
| 手续费 | **万 5**（paper） |
| 滑点 | **10 bp**（paper） |
| 强平阈值 | **-5%** |
| LLM 超时 | **8s**；超时→HOLD |
| 并发 | **按模型并行**，串行写库 |

---

## 🛡️ 合规与安全

- **只读 API Key** + 现货、单向做多
- **隔离资金**：每模型独立子账户 / 子账本
- **Kill-Switch**：净值回撤超过 10% 立即停机（全平+禁用新单）
- **速率限制**：LLM 与交易所均加限速与熔断
- **日志**：审计日志落库 + 本地滚动文件备份

---

## 🚀 快速开始

### 当前版本：v0.1.0 (MVP)

**最简化MVP**：真实价格获取 + AI决策对比

```bash
# 1. 克隆项目
git clone https://github.com/AmadeusGB/alpha-arena.git
cd alpha-arena

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置API密钥
cp env.example .env
# 编辑.env文件，填入你的API密钥

# 4. 运行程序
python main.py
```

### 📋 版本信息
- **详细版本说明**：[VERSION.md](VERSION.md)
- **变更日志**：[CHANGELOG.md](CHANGELOG.md)
- **当前功能**：5个代币价格获取 + OpenAI vs Claude决策对比

---

## 🔮 后续迭代（非 MVP）

- 引入**做空/杠杆**、更多下单类型（限价+冰山）
- 多时间框（1m+5m+1h）+ 归纳型多轮推理
- **策略蒸馏**：从 LLM 决策中提取规则/特征，给到轻量 Policy
- **实盘风控**：交易所回报校验、风控分级、OMS 异常自动降级
- **公平性工具**：时延对齐、成本对齐、数据漂移告警
