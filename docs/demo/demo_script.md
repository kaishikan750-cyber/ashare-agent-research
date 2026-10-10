# 第三阶段演示讲稿

视频为本地 Chromium 页面截图与真实源码/研究结果组成的演示剪辑，中文字幕，无音频。默认使用人工 sample_stage3 和离线模式，不演示真实模型效果。以下每段约 12 秒，共 120 秒；可以按这个顺序重录带个人旁白的版本。

1. 展示项目定位：A 股隔夜反转研究 Agent，离线也能复现，工程完成不代表投资收益。
2. 页面选择 sample_stage3，60/20/2 日训练/测试/间隔配置，点击开始研究。
3. 展示工具事件、基础回测与研究结论，说明确定性计算负责收益，模型只解释证据。
4. 展示 LangChain StructuredTool、init_chat_model 与 bind_tools，说明 LangGraph 管流程，MCP 是独立入口。
5. 展示三个池和样本外表、基准曲线。全池、沪主板、深主板不是官方指数。
6. 展示逐折日期和分位，训练选参只读取 train_end 之前，样本外持仓连续。
7. 切换深主板，展示池与基准差异；选股范围和样本对结果有影响，不挑赢家冒称稳健。
8. 展示分位/滑点敏感性表；它是事后描述，不回写本折参数。
9. 展示两个 Skill、47 项自动测试及未来价格扰动反例；说明 Skill 不能替代测试。
10. 展示启动命令、Docker/CI 文件、报告下载和项目限制，结束。

自行重做截图：先启动服务，再运行 `python scripts/capture_demo.py --url http://127.0.0.1:8001`。视频制作依赖安装 `pip install -r requirements-demo.txt` 和 `python -m playwright install chromium`；随后运行 `python scripts/build_demo_video.py`。字体默认 Windows 微软雅黑，可用 `--font /path/to/CJK.ttf` 指定其他中文字体。
