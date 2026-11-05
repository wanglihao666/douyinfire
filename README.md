# 抖音私信续火花

项目提供两种运行方式。本地和 GitHub Actions 均默认只检查登录。填写启用好友序号后，才会尝试发送一条私信。工作流支持手动登录检查、单人试发，以及每日定时发送。

## 本地运行

在项目目录执行（推荐 Python 3.11）：

```sh
python -m pip install -r requirements.txt
python -m playwright install chromium
python scripts/get_cookie.py
python main.py
```

获取 Cookie 时，在打开的 Chromium 窗口中手动登录抖音，看到私信列表后回到终端按回车。脚本把会话保存到项目目录的 `cookies.json`。该文件可以用于登录账号，请勿提交、分享或粘贴到聊天中。看到“登录检查通过，已打开私信列表”就表示 Chromium 能使用该会话打开私信页。

要试发一条私信，先确认 `config/friends.json` 中启用好友的顺序，再在默认发送窗口（香港及北京时间 07:00–09:00）执行：

```sh
python main.py --recipient-index 1
```

序号从 1 开始，按配置中启用好友的顺序计算。运行后去对应的抖音会话核对消息。若发送结果不确定，先在抖音核对再重新触发，避免重复消息。

## GitHub Actions

1. 在仓库的 **Settings → Secrets and variables → Actions** 新建或更新仓库 Secret `DOUYIN_COOKIES`，值为本地 `cookies.json` 的完整内容。
2. 打开 **Actions → 抖音自动续火花 → Run workflow**，选择 `main`，让 `recipient_index` 保持为 `0`，运行登录检查。
3. 登录检查通过后，如需试发，在发送窗口内另开一次运行并填写启用好友序号。试发使用新的运行入口，失败后先核对抖音会话。

Actions 日志只显示任务结果和诊断，不上传私信截图或原始日志。Cookie 失效后重新运行本地获取脚本，再更新 Secret。

## 每日定时发送

GitHub Actions 每天香港及北京时间 07:05 触发，处理 `config/friends.json` 里启用的好友。程序按配置的发送窗口检查开跑时间，超出窗口时退出。发送任务禁止直接重跑，以免部分成功后重复发送。失败时先到抖音核对实际送出的消息。

定时触发可能因 GitHub 排队延后。请在 Actions 查看首条标记为 Scheduled 的运行结果。

## 配置

- `config/friends.json` 控制好友和启用状态。运行前请核对实际昵称和序号。
- `config/settings.json` 控制发送窗口、时区、文案和浏览器设置。
- `.github/workflows/send.yml` 控制 GitHub 触发方式。

## 调度延迟与每日记录

定时任务在配置的开始时间后、当天结束前都可以执行。每天 07:05 触发，12:35 和 18:35 补跑。程序在独立的 `douyin-state` 分支记录日期与好友名称摘要，并在按下发送键之前写入记录。补跑会跳过已有记录的好友。记录不含 Cookie、好友原名或聊天内容。

如果发送后页面确认超时或任务意外中断，记录会保留，避免自动重复发送。需要先在抖音确认实际消息，再决定是否人工补发。GitHub 调度和抖音登录状态仍会影响实际送达。
