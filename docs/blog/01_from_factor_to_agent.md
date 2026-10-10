# 从一个隔夜反转因子，到可追溯的量化研究 Agent

我在 `virattt/ai-hedge-fund` 的开源 checkout 中新增了 A 股研究模块。目标是实习面试时能说明一个完整问题：模型如何使用工具完成研究，收益数据为什么可信，别人如何复现。上游 MIT 代码和作者归属保留；这里展示的是新增研究子系统，而不是声称重写了上游全部交易框架。

## 先把时间线写对

因子定义为：

```python
overnight_return = open_t / close_previous_session - 1
factor = -overnight_return
```

因子越高，表示隔夜跌幅越大。策略选择排名靠前的分位，但本项目在 t 收盘才形成交易信号，t+1 开盘尝试买，t+2 收盘尝试卖。这个延迟版本可以验证架构，不应该包装成开盘即时反转的强经济假说。股票前一天缺行情时不沿用停牌前价格生成信号。

最危险的实现错误之一，是看到未来退出日没有行情，就从过去的买入候选中删掉它。这样组合权重也使用了未来信息。第二阶段改为逐日事件引擎：信号进入 pending，下一天只判断当时能不能买；卖不出则继续持仓。期末未退出仓位按最新已知收盘估值，缺行情则保留旧估值并记录 stale_marks。交易费、现金、整手、T+1 都进入同一个账本。

具体代码见 `cn_research/backtest.py`。第三阶段又增加回测起止日、逐日分位计划和股票池资格函数，保持同一执行核心。

## 为什么先有工具，再有 Agent

行情校验、因子、回测是确定性 Python；大模型不适合凭文字计算收益。`ResearchTools` 为每个功能定义 Pydantic 输入边界，用 dataset_id 访问白名单目录，禁止任意路径。

第三阶段真实接入 LangChain：

```python
from langchain_core.tools import StructuredTool
tool = StructuredTool.from_function(
    func=invoke,
    name=name,
    description=description,
    args_schema=schema,
)
result = tool.invoke(arguments)
```

`research_agent/langchain_runtime.py` 封装这一步，`ResearchTools.call()` 真正执行 StructuredTool.invoke。它的收益是统一工具 schema、输入校验和模型函数描述，不是换了计算公式。模型默认通过 `langchain.chat_models.init_chat_model` 创建，随后 `bind_tools().invoke()`，代码将 AIMessage 的工具调用转换成受限格式。

LangGraph 控制研究流程：数据检查 → 因子 → 回测 → 成本对照 → 可选验证研究 → 模型分析 → 工具回传 → 分析/结束。基础证据必须生成，模型只在后面做有界的附加查询；最多三轮工具调用，加一次最终请求。验证研究需要用户显式配置，不开放给模型随意扩大计算量。离线模式走同一基础流程，但不调用模型。

## 三个容易混淆的点

LangChain 用于工具封装和模型抽象；LangGraph 用于状态图。这个项目已有专用 LangGraph，没必要再嵌套 create_agent 循环。MCP 是给其他客户端使用的协议入口，目前图直接调用进程内工具，不能声称所有调用都走 MCP。

FastAPI 承担服务边界。POST 实验立即返回 202 和 ID，线程池执行；前端轮询，SQLite 保存事件和结果。实验复制实际 CSV 到私有输入目录，报告记录原始与归一化哈希。它有可追溯的实验记录，但没有分布式任务队列或图 checkpoint 断点续跑；服务重启中断任务会失败并要求重提。

两个 Skill 是可复用的研究工作方法：数据审计与滚动验证解读。它们存放在 `.agents/skills/`，模型系统上下文加载正文。Skill 不能替代计算器、数据来源和自动测试。

## 我会如何在面试介绍

“我做了一个可复现的 A 股隔夜反转研究 Agent。先实现时点正确的回测和现金持仓账本，再通过 LangChain 类型化工具、LangGraph 状态图、FastAPI 和 MCP 提供研究入口。模型只解释工具证据，离线模式也能运行。我的重点是消除未来退出可成交性泄漏、维护跨窗持仓，以及把研究参数和数据指纹保留下来。”

工程能力和投资有效性应分开证明。目前交付包含人工样例，真实模型只完成协议 stub 验证；没有真实密钥时不能声称外部模型效果已经验证。下一步应使用可靠真实行情、历史成分和公司行动数据。

复现：`python start_stage3.py`；源码地图和全部边界见 `README_STAGE3.md`。
