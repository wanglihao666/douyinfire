# 抖音私信自动续火花

基于 Playwright 模拟真人操作，每天凌晨（阴间时间01:00-04:00）自动给指定好友发送一言API文艺文案，维持抖音火花不断。

## ✨ 功能特性

- 🌙 **阴间随机时间**：每天01:00-04:00之间随机时间发送
- 📝 **一言API文案**：自动从一言API获取文艺/诗词/电影台词，永不重样
- 👥 **多好友支持**：同时给17个好友发送，好友间随机间隔30-120秒
- 🤖 **真人模拟**：随机打字速度、发送前停顿、模拟阅读，降低风控风险
- 📸 **截图留证**：每次发送后自动截图存档
- ☁️ **GitHub Action部署**：免费云端24小时运行，电脑关机也能跑
- 🔄 **失败重试**：发送失败自动重试2次

## 📁 项目结构

```
douyin-auto-fire/
├── main.py                  # 主程序
├── requirements.txt         # Python依赖
├── cookies.json             # 抖音登录Cookie（自行获取，勿提交）
├── config/
│   ├── friends.json         # 好友列表（17人）
│   └── settings.json        # 全局设置（时间/文案/真人模拟参数）
├── scripts/
│   └── get_cookie.py        # Cookie获取脚本
├── .github/workflows/
│   └── send.yml             # GitHub Action定时任务
├── logs/                    # 运行日志
└── screenshots/             # 发送截图
```

## 🚀 部署步骤（GitHub Action 方式，推荐）

### 第一步：准备GitHub仓库

1. 在GitHub创建一个新的**私有仓库**（必须私有，防止Cookie泄露）
2. 将本项目所有文件上传到仓库

### 第二步：获取抖音Cookie

在本地电脑上操作：

```bash
# 安装依赖
pip install playwright requests
playwright install chromium

# 运行Cookie获取脚本
python scripts/get_cookie.py
```

脚本会弹出浏览器，扫码登录抖音后回到命令行按回车，Cookie会自动保存到 `cookies.json`。

### 第三步：配置GitHub Secrets

1. 打开你的GitHub仓库 → Settings → Secrets and variables → Actions
2. 点击 "New repository secret"
3. Name 填 `DOUYIN_COOKIES`
4. Value 填 `cookies.json` 文件的**全部内容**（用记事本打开复制）
5. 点击 Add secret

### 第四步：启用GitHub Action

1. 打开仓库的 Actions 标签页
2. 如果提示 "Workflows aren't being run"，点击 "I understand my workflows, go ahead and enable them"
3. 手动触发一次测试：点击 "抖音自动续火花" → "Run workflow" → 选择main分支 → Run
4. 等待运行完成，查看日志确认发送成功

### 第五步：验证

- 运行完成后，在 Actions → 本次运行 → Artifacts 中下载日志和截图
- 确认每个好友都收到了消息
- 之后每天北京时间01:00左右会自动运行

## ⚙️ 配置说明

### 修改好友列表

编辑 `config/friends.json`，添加或删除好友：

```json
{
  "name": "好友昵称",
  "match_type": "nickname",
  "enabled": true,
  "note": "备注"
}
```

### 修改发送时间

编辑 `config/settings.json` 中的 `schedule` 部分：

```json
"schedule": {
  "send_window_start": "01:00",
  "send_window_end": "04:00"
}
```

同时修改 `.github/workflows/send.yml` 中的 cron 表达式（UTC时间 = 北京时间 - 8小时）。

### 修改文案风格

编辑 `config/settings.json` 中的 `message.hitokoto_params.c` 数组，一言API分类：

- `a` - 动画
- `b` - 漫画
- `c` - 游戏
- `d` - 文学
- `e` - 原创
- `f` - 来自网络
- `g` - 其他
- `h` - 影视
- `i` - 诗词
- `j` - 网易云
- `k` - 哲学
- `l` - 抖机灵

## 🖥️ 本地运行测试

```bash
# 安装依赖
pip install -r requirements.txt
playwright install chromium

# 获取Cookie（首次运行）
python scripts/get_cookie.py

# 运行
python main.py
```

测试时建议先把 `config/settings.json` 中的 `browser.headless` 改为 `false`，可以看到浏览器操作过程。

## ⚠️ 注意事项

1. **账号安全**：本工具仅供个人学习使用，使用产生的账号风控/封禁风险由使用者自行承担
2. **Cookie有效期**：抖音Cookie一般1-2个月过期，过期后需要重新获取并更新GitHub Secret
3. **发送频率**：好友之间已设置30-120秒随机间隔，请勿修改过短以免触发风控
4. **私有仓库**：GitHub仓库必须设为私有，防止Cookie泄露
5. **文案长度**：一言API返回的文案可能偶尔过长，已设置50字上限，超长会自动使用备用文案

## 📋 当前好友列表（17人）

| 序号 | 昵称 | 状态 |
|------|------|------|
| 1 | 小宝 | 🔥3天 |
| 2 | 李为俊 | 🔥437天 |
| 3 | 大富坤大坤 | 🔥291天 |
| 4 | 学霸左田总 | 🔥417天 |
| 5 | 张郑 | 🔥20天 |
| 6 | 石岩 | 🔥594天 |
| 7 | 何毅豪 | 🔥3天 |
| 8 | 王周一 | 🔥398天 |
| 9 | 胡洋 | 🔥71天 |
| 10 | 刘金鑫 | 🔥11天 |
| 11 | 陈果 | 重燃中 |
| 12 | 张国仁 | 重燃中 |
| 13 | 胡飞 | 用户指定 |
| 14 | 汪沪博 | 用户指定 |
| 15 | 我同意 | 用户指定 |
| 16 | 陈亚坤 | 💧3天 |
| 17 | 程俊杰 | 💧478天 |

## 🆘 常见问题

**Q: GitHub Action运行失败，提示Cookie失效？**
A: 重新运行 `python scripts/get_cookie.py` 获取新Cookie，更新GitHub Secret。

**Q: 某个好友总是发送失败？**
A: 检查好友昵称是否正确，抖音昵称可能有特殊字符。可以在 `friends.json` 中修改为准确的昵称。

**Q: 可以修改发送的消息内容吗？**
A: 编辑 `config/settings.json` 中的 `message.fallback_messages` 添加备用文案，或修改一言API分类。

**Q: 如何暂停自动发送？**
A: GitHub仓库 → Settings → Actions → Disable Actions，或删除 `.github/workflows/send.yml`。
