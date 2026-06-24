import asyncio
from pathlib import Path

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

PLUGIN_NAME = "astrbot_plugin_welcome_qqgroup"
DEFAULT_IMAGE = Path(__file__).parent / "assets" / "welcome-kkz.jpg"


@register(
    PLUGIN_NAME,
    "Rio",
    "QQ 群入群欢迎插件：检测到新成员入群时，自动发送可在控制台配置的图片和文字。",
    "1.2.1",
    "https://github.com/YourName/astrbot_plugin_welcome_qqgroup",
)
class WelcomePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    async def on_group_increase(self, event: AstrMessageEvent):
        """监听 aiocqhttp(OneBot v11) 事件，识别群成员增加(group_increase)通知并发送欢迎。

        aiocqhttp 适配器会把 notice 类事件转换成普通的 GROUP_MESSAGE 事件交给事件管线，
        原始 OneBot 事件保留在 event.message_obj.raw_message 中。这里通过框架原生的事件
        监听器接入，避免直接 monkey-patch 底层 client 带来的热重载泄漏与强耦合问题。
        """
        raw = event.message_obj.raw_message
        if not self._is_group_increase(raw):
            return

        group_id = str(self._raw_get(raw, "group_id") or "")
        user_id = str(self._raw_get(raw, "user_id") or "")
        self_id = str(self._raw_get(raw, "self_id") or event.get_self_id() or "")

        # 跳过机器人自己被拉进群的情况
        if user_id and self_id and user_id == self_id:
            return

        # 群白名单过滤
        enabled_groups = self._enabled_groups()
        if enabled_groups and group_id not in enabled_groups:
            return

        delay = self._send_delay()
        if delay > 0:
            await asyncio.sleep(delay)

        chain = await self._build_welcome_chain(event, group_id, user_id)
        if not chain:
            logger.debug("[welcome] 欢迎语和图片均为空，跳过发送。")
            return

        logger.info(f"[welcome] 群 {group_id} 新成员 {user_id} 入群，发送欢迎消息。")
        yield event.chain_result(chain)
        # 这是一条合成的 notice 事件，处理完毕后停止传播，避免触发后续阶段。
        event.stop_event()

    @filter.command("welcometest")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def welcome_test(self, event: AstrMessageEvent):
        """管理员指令：在当前群预览入群欢迎消息（把自己当作新成员）。"""
        group_id = event.get_group_id() or ""
        user_id = event.get_sender_id() or ""
        if not group_id:
            yield event.plain_result("该指令需要在群聊中使用。")
            return
        chain = await self._build_welcome_chain(event, group_id, user_id)
        if not chain:
            yield event.plain_result(
                "当前欢迎语和图片均未配置，请先在插件配置中设置后再预览。"
            )
            return
        yield event.chain_result(chain)

    async def _build_welcome_chain(
        self,
        event: AstrMessageEvent,
        group_id: str,
        user_id: str,
    ) -> list:
        """根据配置构建欢迎消息链。"""
        text = (self.config.get("welcome_text", "") or "").strip()

        text_comp = None
        if text:
            formatted = await self._format_text(event, text, group_id, user_id)
            if formatted:
                text_comp = Comp.Plain(formatted)

        image_comps = self._collect_images()

        if text_comp is None and not image_comps:
            return []

        chain: list = []
        if self.config.get("at_new_member", True) and user_id:
            chain.append(Comp.At(qq=user_id))
            chain.append(Comp.Plain(" "))

        if self.config.get("send_image_first", False):
            chain.extend(image_comps)
            if text_comp is not None:
                chain.append(text_comp)
        else:
            if text_comp is not None:
                chain.append(text_comp)
            chain.extend(image_comps)

        return chain

    async def _format_text(
        self,
        event: AstrMessageEvent,
        text: str,
        group_id: str,
        user_id: str,
    ) -> str:
        """替换欢迎语中的占位符。"""
        nickname = ""
        if "{nickname}" in text:
            nickname = await self._get_nickname(event, group_id, user_id)

        replacements = {
            "{nickname}": nickname or user_id,
            "{user_id}": user_id,
            "{group_id}": group_id,
        }
        for key, value in replacements.items():
            text = text.replace(key, str(value))
        return text

    def _collect_images(self) -> list:
        """收集所有欢迎图片组件：先是控制台上传的图片，再是外部链接/路径。"""
        comps = []

        uploaded = self.config.get("image_file", []) or []
        if isinstance(uploaded, str):
            uploaded = [uploaded]
        for rel in uploaded:
            path = self._resolve_uploaded(str(rel))
            if not path:
                continue
            try:
                comps.append(Comp.Image.fromFileSystem(path))
            except Exception as e:
                logger.error(f"[welcome] 构建上传图片失败（path={path!r}）: {e}")

        image = (self.config.get("image", "") or "").strip()
        comp = self._build_image(image)
        if comp is not None:
            comps.append(comp)

        # 未配置任何图片时，回退使用插件自带的默认欢迎图片
        if not comps and self.config.get("use_default_image", True):
            if DEFAULT_IMAGE.exists():
                try:
                    comps.append(Comp.Image.fromFileSystem(str(DEFAULT_IMAGE)))
                except Exception as e:
                    logger.error(f"[welcome] 构建默认欢迎图片失败: {e}")
            else:
                logger.warning(f"[welcome] 默认欢迎图片缺失: {DEFAULT_IMAGE}")

        return comps

    def _resolve_uploaded(self, rel_path: str):
        """把控制台上传图片的相对路径解析为可读取的绝对路径。"""
        rel_path = (rel_path or "").strip()
        if not rel_path:
            return None
        p = Path(rel_path)
        if p.is_absolute():
            return str(p) if p.exists() else None
        try:
            base = StarTools.get_data_dir(PLUGIN_NAME)
        except Exception as e:
            logger.error(f"[welcome] 获取插件数据目录失败: {e}")
            return None
        full = (Path(base) / rel_path).resolve()
        if full.exists():
            return str(full)
        logger.warning(f"[welcome] 上传的欢迎图片不存在，已跳过: {full}")
        return None

    def _build_image(self, image: str):
        """把配置中的图片地址转成 Image 组件，支持 URL / 本地路径 / base64。"""
        if not image:
            return None
        try:
            if image.startswith(("http://", "https://")):
                return Comp.Image.fromURL(image)
            if image.startswith("base64://"):
                return Comp.Image(file=image)
            return Comp.Image.fromFileSystem(image)
        except Exception as e:
            logger.error(f"[welcome] 构建欢迎图片失败（image={image!r}）: {e}")
            return None

    async def _get_nickname(
        self,
        event: AstrMessageEvent,
        group_id: str,
        user_id: str,
    ) -> str:
        """通过 OneBot API 获取新成员昵称，失败时返回空字符串由调用方回退。"""
        client = getattr(event, "bot", None)
        if client is None or not group_id.isdigit() or not user_id.isdigit():
            return ""
        try:
            info = await client.call_action(
                "get_group_member_info",
                group_id=int(group_id),
                user_id=int(user_id),
                no_cache=True,
            )
            if info:
                return info.get("card") or info.get("nickname") or ""
        except Exception as e:
            logger.debug(f"[welcome] 获取新成员昵称失败，将回退使用 QQ 号: {e}")
        return ""

    def _enabled_groups(self) -> list[str]:
        groups = self.config.get("enabled_groups", []) or []
        return [str(g).strip() for g in groups if str(g).strip()]

    def _send_delay(self) -> float:
        try:
            return max(0.0, float(self.config.get("send_delay", 0) or 0))
        except (TypeError, ValueError):
            return 0.0

    def _is_group_increase(self, raw) -> bool:
        """判断原始事件是否为 OneBot v11 的群成员增加通知。"""
        if raw is None:
            return False
        return (
            self._raw_get(raw, "post_type") == "notice"
            and self._raw_get(raw, "notice_type") == "group_increase"
        )

    @staticmethod
    def _raw_get(raw, key):
        """兼容 dict 与对象两种形式地读取原始事件字段。"""
        if isinstance(raw, dict):
            return raw.get(key)
        return getattr(raw, key, None)

    async def terminate(self):
        """插件卸载/停用时调用。本插件使用框架原生事件监听器，无需手动注销。"""
