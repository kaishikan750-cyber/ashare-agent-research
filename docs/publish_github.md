# GitHub 发布说明

本交付保留上游 `virattt/ai-hedge-fund` 的 MIT License 与源码归属，新增 A 股研究模块。博客/视频均为本地材料，没有向外部账号发布。

建议先在 GitHub 创建自己的空仓库或 fork，再确认本地 remote 指向自己的仓库。不要向上游默认分支推送。本文命令需由你在确认路径与 remote 后执行：

```sh
git status
git remote -v
# 如果从 zip 解压且没有 Git：
git init
git add .
git status
git commit -m "Add A-share research agent stage 3"
# 将下面地址替换成自己的空仓库：
git remote add origin https://github.com/YOUR_NAME/ashare-agent-research.git
git branch -M main
git push -u origin main
```

已有 checkout 应使用自己的 feature 分支和 remote，不重复 init 或覆盖已有 origin。检查未误收 `.env`、`.stage2.env`、`.stage3.env`、个人行情、实验数据库或虚拟环境。仓库 `.gitignore` 忽略输出研究目录；CI 会生成结果作为 workflow artifact。`docs/demo/` 的公开演示截图与视频可以进入仓库；报告示例来自人工行情。

推送后在 Actions 看 `Stage 3 reproducible research` 是否通过，特别是容器和 Python 3.11 作业。未运行或失败时不要在简历标“CI 全绿”。README 配上页面截图，博客按 01→02→03 发布，视频可上传自己的 B 站/视频平台，并在 README 中填实际链接。保留“人工演示”“未验证外部模型效果”“容器未本机实测”等说明，等获得实测证据后再更新。
