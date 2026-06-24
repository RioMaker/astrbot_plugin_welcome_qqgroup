# astrbot_plugin_welcome_qqgroup

一个 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的 **QQ 群入群欢迎插件**：当检测到有新成员加入群聊时，自动发送一条可在控制台自由配置的 **图片 + 文字** 欢迎消息。

> 仅适用于基于 OneBot v11 的 `aiocqhttp` 适配器（如 NapCat、Lagrange、go-cqhttp 等）。

## 功能特性

- 监听群成员增加事件，新人入群即自动发送欢迎。
- 欢迎语、欢迎图片均可在 WebUI 插件配置页中设置。
- 支持 `@` 新成员，提醒到对方。
- 欢迎语支持占位符：`{nickname}`、`{user_id}`、`{group_id}`。
- 图片支持网络 URL、服务器本地文件路径、`base64://` 数据。
- 可设置生效群号白名单，只在指定群欢迎。
- 可设置发送延迟，降低被风控概率。
- 提供管理员预览指令，无需真人入群即可测试效果。

## 工作原理

`aiocqhttp` 适配器会把 OneBot 的 `notice` 类事件（包含 `group_increase` 入群通知）转换为普通的群消息事件，交给 AstrBot 的事件管线处理，原始事件保留在 `event.message_obj.raw_message` 中。

本插件通过框架原生的事件监听器 `@filter.platform_adapter_type(AIOCQHTTP)` 接入，再从 `raw_message` 中识别 `group_increase` 通知。相比直接给底层 client 打 `@client.on_notice` 补丁的做法，这种方式：

- 由框架统一管理监听器的注册与注销，**不会在热重载时造成事件处理器泄漏 / 重复发送**；
- 不依赖 `asyncio.create_task` + `sleep` 等待适配器加载的竞态写法；
- 仅监听阶段触发 `is_wake`，不会让机器人对每条群消息自动回复。

## 配置项

在 WebUI 的「插件管理 → 本插件 → 配置」中设置：

| 配置项 | 说明 |
| --- | --- |
| `welcome_text` | 欢迎语文本，支持占位符 `{nickname}` / `{user_id}` / `{group_id}`，留空则不发文字 |
| `image` | 欢迎图片，填写 `http(s)` 网络地址或服务器本地文件绝对路径，留空则不发图片 |
| `at_new_member` | 是否在欢迎消息开头 `@` 新成员 |
| `send_image_first` | 图片是否在文字之前发送 |
| `enabled_groups` | 生效群号白名单，留空表示所有群生效 |
| `send_delay` | 检测到入群后等待的秒数再发送，默认 0 |

## 指令

| 指令 | 权限 | 说明 |
| --- | --- | --- |
| `/welcometest` | 管理员 | 在当前群把自己当作新成员，预览欢迎消息效果 |

## 安装

将本插件目录放入 AstrBot 的 `data/plugins/` 下，或通过 WebUI 插件市场 / 仓库地址安装，重载插件后在配置页填写欢迎语与图片即可。

## 相关链接

- [AstrBot 仓库](https://github.com/AstrBotDevs/AstrBot)
- [AstrBot 插件开发文档](https://docs.astrbot.app/dev/star/plugin-new.html)
