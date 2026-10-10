# 第三阶段：可复现的 A 股 Agent 研究项目

在第二阶段基础上补充真实 LangChain 工具/模型接入、两个项目 Skill、滚动 walk-forward、分位/滑点敏感性、不同股票池、基准、Docker、GitHub Actions，以及博客和中文字幕演示视频。默认离线，无需密钥；不是自动交易系统。

## 三分钟启动

解压交付包，进入 `ai-hedge-fund-cn` 文件夹。需要 Python 3.11+、首次安装时可访问 PyPI。

```powershell
python start_stage3.py
```

自动创建 `.venv-stage3`、安装锁定依赖、启动单进程 API。打开 http://127.0.0.1:8000 。选 `sample_stage3`、离线模式、启用第三阶段验证，点击开始研究；默认运行约数秒至数十秒，取决于机器。端口占用用 `python start_stage3.py --port 8001`；重新安装用 `--install`。

命令行复现报告，不启动页面：

```powershell
python start_stage3.py --study
.venv-stage3\Scripts\python.exe -m research_agent.study_cli --config configs/study.example.json
.venv-stage3\Scripts\python.exe -m pytest tests -q
.venv-stage3\Scripts\python.exe -m pip check
```

Linux/macOS 将 `.venv-stage3\Scripts\python.exe` 换成 `.venv-stage3/bin/python`。主程序只需 `requirements-stage3-lock.txt`；视频制作另用 `requirements-demo.txt`。不要用上游 Poetry 环境混装新版 LangChain。本地验证为 Windows / Python 3.13.9；CI 包含 Linux/Windows 和 Python 3.11/3.13，尚需上传仓库后实际运行。NumPy 针对 Python 3.11 使用 2.3.3，3.12+ 使用 2.5.3；pywin32 只在 Windows 安装。

## 各框架真正承担的工作

```text
前端 → FastAPI → 后台任务 / SQLite / CSV 快照
                   ↓
          LangGraph：检查 → 因子 → 回测 → 成本 → 验证研究 → 分析
                   ↓                                 ↓
          LangChain StructuredTool          init_chat_model / bind_tools
                   ↓                          （可选真实模型）
             纯 Python 量化核心
                   ↑
           MCP stdio 独立工具入口
```

`ResearchTools.call()` 实际使用 `StructuredTool.invoke()` 做类型化校验和执行；图中数据检查、因子和模型附加工具调用经过此边界。模型默认经 `langchain.chat_models.init_chat_model` 创建客户端，再 `bind_tools().invoke()`。模型结果转成受限工具调用，最多 3 轮工具与 1 次最终请求；每轮最多 3 个调用。计算结果不能被模型覆盖。原 httpx 客户端保留，只有显式 `LLM_BACKEND=legacy` 时使用。

这里使用自定义 LangGraph 研究图；没有为了加包而套第二个 `create_agent` 循环。LangGraph 仍直接调用进程内工具，MCP 是独立协议入口，不能声称图通过 MCP 调用了工具。离线模式不调用模型。

## 两个 Skill

- `.agents/skills/ashare-data-audit/SKILL.md`：行情口径、时点、涨跌停、股票池审计。
- `.agents/skills/walk-forward-review/SKILL.md`：滚动选参、跨窗现金持仓、敏感性和基准解读。

两者是标准 Markdown + YAML frontmatter 的项目 Skill，可复制给支持该格式的编码 Agent。项目模型流程也通过 `research_agent/skills.py` 加载正文到系统上下文，实验 JSON 记录使用的 Skill 名称。它们是工作方法和约束，数值检查仍由代码与测试完成，不是让模型凭指令保证金融正确性。

## Walk-forward 协议

默认：60 个观测交易日训练、2 日间隔、20 日测试；固定长度滚动训练。训练期只输入 train_end 及以前行情，对 `[0.1,0.2,0.5]` 分位的含成本净收益选择最大者，平局选较小分位。每折完整保存候选指标和所选值。训练期末持仓按当时价格估值，不能使用未来退出价格。

测试开始时过去行情仅暖启动因子，不继承训练持仓，也不提前使用测试前信号。之后全部测试窗共享一个现金持仓账本；参数变化只影响新信号，延期卖出仓位继续持有。每折收益以前一窗末净值为基数；各折收益连乘能对账至整体样本外收益。最后不足 4 日的尾段排除，报告中显示实际结束日。

隔夜反转仍为 `-(open_t / close_{t-1} - 1)`。每隔两个观测日于收盘形成信号，次日开盘买、再下一日收盘卖；100 股整手、现金约束、佣金、卖出税、单边滑点、封板/缺行情延迟退出均复用第二阶段引擎。2 日间隔覆盖名义持有跨度，训练卖出受阻时仍只盯市当时结果；延迟退出无需偷看未来。

后续训练窗使用已发生的早期测试数据，属于合法滚动更新，但不等于最终独立 holdout。协议是工程可验证版本，不是统计显著性证明。

## 敏感性、股票池与基准

在同一样本外区间比较最多 3 个分位 × 3 个单边滑点 × 3 个池。佣金和税率固定为请求配置。敏感性是事后描述，不用于重选 walk-forward 参数；不能据图表赢家修改实验后还叫样本外。

默认池：文件内全部代码、`60` 开头沪主板、`000/001/002` 开头深主板。它们不是官方指数成分，也不是所有 A 股板块。可通过 `UniverseSpec(selector="custom",codes=[...])` 指定预先声明的静态池，或用 `memberships` 提供 `code/known_at/effective_from/effective_to`。`effective_to` 是不包含的结束日；区间及结束日信息必须在 known_at 已知。样例见 `configs/historical-pool.example.json`，其中日期仅为示范，不代表实际上市或指数调入事件。程序无法替使用者认证历史成分来源。

基准为现金零利息，以及同池等现金买入持有：样本外首日开盘一次买入，100 股整手、相同买入佣金/滑点、缺行情或封板留现金、日收盘盯市。无卖出故不收卖出税。策略与基准日期一致，但换手和暴露不同；收益差不是风险调整 alpha，基准不是沪深 300 等官方指数。

## API 与 MCP

`POST /api/experiments` 的 `study` 可为空（旧流程），或为参数对象（第三阶段）。无需另起 API：

```json
{"dataset_id":"sample_stage3","mode":"offline","study":{"train_sessions":60,"test_sessions":20,"purge_sessions":2}}
```

返回 202 和实验 ID；`GET /api/experiments/{id}` 轮询。完成后 `.../{id}/report` 下载整体 Markdown，`.../{id}/study` 获取完整 JSON，`.../{id}/study?format=md` 下载研究部分。也可在 `/docs` 中提交。敏感性 CSV 和基准曲线 CSV 保存到该实验目录下的 `study/`。

MCP 启动：

```powershell
.venv-stage3\Scripts\python.exe -m mcp_server.server
```

客户端启动 stdio 子进程，cwd 为项目根；七个工具含新增 `run_validation_study`。旧的六个入口保持兼容。新增入口默认有界配置；更细的自定义股票池用 API/CLI。stdout 是 JSON-RPC，不要把启动命令当成交互式程序。客户端配置示例见 `mcp_server/client.stage3.example.json`。

研究上限：每实验最多 20 折、3 个池、3 个候选分位、3 个滑点；行情研究最多 50,000 行/200 只股票。超限显式拒绝。后台仍是单进程线程池，不是分布式队列。重启中断实验标记失败需重提；没有 checkpoint 断点续跑。

## 可选模型

复制 `.stage3.env.example` 为 `.stage3.env`，设置 LLM_BASE_URL、LLM_MODEL、LLM_API_KEY，再重启。默认使用 LangChain 模型客户端。支持工具调用的兼容 chat-completions 服务才适用；密钥仅留服务端。研究问题与工具摘要会发送给所配置服务。没有真实密钥时，模型效果未外部实测；本地用 HTTP stub 验证了实际 LangChain 请求、工具回传和失败回退。

## Docker 与 CI

```sh
docker compose up --build
# 停止，保留结果卷：
docker compose down
```

镜像以非 root 用户运行，暴露 8000，健康检查，named volume 保存实验。Compose 仅绑定本机地址；默认离线。接入模型可按需添加 `env_file: .stage3.env`，真实行情可添加只读数据卷。Dockerfile 不复制任何密钥、个人数据或上游完整环境。

`.github/workflows/stage3.yml` 自动跑四种 Python/系统组合的依赖检查、测试、完整演示研究，并上传结果；另有 Docker build/run/HTTP/core 回测检查。当前机器无 Docker，未完成本机容器启动；工作流已交付但未在 GitHub 执行，不能把 YAML 已写等同于 CI 已绿。仓库初始化/推送命令见 `docs/publish_github.md`。

## 交付材料

- `outputs/stage3_demo/`：已运行的 JSON、Markdown、敏感性表、三个池的基准曲线。
- `docs/blog/`：三篇可发布博客，包含原理、源码、验证和面试表述。
- `docs/demo/stage3-demo.mp4`：实际本地页面截图与代码证据组成的中文演示，配字幕，无旁白。
- `docs/demo/stage3-demo.srt`：可编辑字幕；`docs/demo/demo_script.md`：重录讲稿。
- `docs/stage3_validation.md`：具体验证记录和未验证项。
- 先前 32 页学习 PDF 保留在 `output/pdf/`，对应第二阶段；第三阶段差异以本 README 为准。

人工数据由 `scripts/generate_stage3_data.py` 固定随机种子生成（12 股、182 个工作日）。不使用真实价格，不按因子收益优化生成过程。需要策略研究时换入经过核实的原始行情、历史成分及公司行动处理，冻结协议后保留独立 holdout。工程完成不能保证投资收益。
