import asyncio
from datetime import datetime
import hashlib
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from zhenxun.configs.path_config import TEMP_PATH
from zhenxun.services.log import logger

from ..config import BROWSER_COOLDOWN_SECONDS, base_config
from ..core.queue_manager import draw_queue_manager
from .downloader import ImageDownloader


class ImageGenerationError(Exception):
    """图片生成错误"""

    pass


class DoubaoImageGenerator:
    """豆包AI图片生成器（基于Chromium浏览器自动化）"""

    def __init__(self):
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.playwright = None

        self.base_url = "https://www.doubao.com"
        self.create_image_url = "https://www.doubao.com/chat/create-image"

        self.generated_images: dict[str, dict[str, Any]] = {}
        self._generation_complete_event = asyncio.Event()

        draw_queue_manager.set_browser_cooldown(BROWSER_COOLDOWN_SECONDS)

        logger.info(
            f"豆包图片生成器初始化，使用cookies: {bool(base_config.get('DOUBAO_COOKIES'))}"
        )

    async def initialize(self) -> bool:
        """初始化浏览器"""
        try:
            self.playwright = await async_playwright().start()

            self.browser = await self.playwright.chromium.launch(
                headless=base_config.get("HEADLESS_BROWSER"),
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-extensions",
                ],
            )

            self.context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/137.0.0.0 Safari/537.36"
                ),
            )

            if base_config.get("DOUBAO_COOKIES"):
                await self._set_cookies()

            self.page = await self.context.new_page()

            logger.info("豆包图片生成器浏览器初始化成功")
            return True

        except Exception as e:
            logger.error(f"初始化浏览器失败: {e}")
            await self.cleanup()
            return False

    async def cleanup(self):
        """清理资源"""
        try:
            if self.page:
                await self.page.close()
                self.page = None
            if self.context:
                await self.context.close()
                self.context = None
            if self.browser:
                await self.browser.close()
                self.browser = None
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None

            draw_queue_manager.set_browser_close_time()

            logger.debug("豆包图片生成器资源清理完成")
        except Exception as e:
            error_msg = str(e).lower()
            if any(
                keyword in error_msg
                for keyword in [
                    "target page, context or browser has been closed",
                    "browser has been closed",
                    "context has been closed",
                    "page has been closed",
                ]
            ):
                logger.debug(f"浏览器资源已被关闭（正常情况）: {e}")
            else:
                logger.error(f"清理资源时发生错误: {e}")
        finally:
            try:
                draw_queue_manager.set_browser_close_time()
            except Exception as e:
                logger.error(f"记录浏览器关闭时间失败: {e}")

    async def _set_cookies(self):
        """设置cookies"""
        try:
            cookies = []
            for cookie_pair in base_config.get("DOUBAO_COOKIES").split(";"):
                if "=" in cookie_pair:
                    name, value = cookie_pair.strip().split("=", 1)
                    cookies.append(
                        {
                            "name": name.strip(),
                            "value": value.strip(),
                            "domain": ".doubao.com",
                            "path": "/",
                        }
                    )

            if cookies:
                await self.context.add_cookies(cookies)
                logger.info(f"已设置 {len(cookies)} 个cookies")

        except Exception as e:
            logger.error(f"设置cookies失败: {e}")

    async def navigate_to_create_image(self) -> bool:
        """导航到豆包图片创建页面"""
        if not self.page:
            logger.error("页面未初始化")
            return False

        try:
            self.generated_images = {}
            self._generation_complete_event.clear()
            downloader = ImageDownloader()

            async def handle_response(response):
                """处理 SSE 流的响应拦截器"""
                try:
                    if "completion" in response.url and response.status == 200:
                        content_type = response.headers.get("content-type", "")
                        if "text/event-stream" in content_type:
                            logger.info("🌊 发现豆包SSE流响应，开始实时解析...")
                            body_bytes = await response.body()

                            lines = body_bytes.strip().split(b"\n")
                            for line in lines:
                                if not line.startswith(b"data:"):
                                    continue

                                json_str = (
                                    line[6:].decode("utf-8", errors="ignore").strip()
                                )
                                if not json_str:
                                    continue

                                if '"event_type":2003' in json_str:
                                    logger.info(
                                        "✅ 收到豆包SSE流结束信号 (event_type 2003)"
                                    )
                                    self._generation_complete_event.set()

                                parsed_images = downloader.parse_doubao_image_data(
                                    json_str
                                )
                                for img_info in parsed_images:
                                    img_key = img_info.get("key")
                                    if img_key:
                                        if img_key not in self.generated_images:
                                            logger.info(
                                                f"🖼️ 捕获到新图片 (索引: {img_info['index']})，已聚合 (当前共 {len(self.generated_images) + 1} 张)"
                                            )
                                        self.generated_images[img_key] = img_info
                except Exception as e:
                    logger.debug(f"处理响应时发生错误: {e}")

            self.page.on("response", handle_response)

            logger.info("正在导航到豆包图片创建页面...")
            await self.page.goto(
                self.create_image_url, wait_until="networkidle", timeout=30000
            )

            await asyncio.sleep(5)

            title = await self.page.title()
            logger.info(f"页面标题: {title}")

            return True

        except Exception as e:
            logger.error(f"导航到豆包图片创建页面失败: {e}")
            return False

    async def _upload_image(self, image_path: str) -> bool:
        """上传图片到豆包输入框"""
        if not self.page:
            return False

        try:
            logger.info(f"开始上传图片: {image_path}")

            success = await self._upload_file_input(image_path)
            if success:
                logger.info("文件输入框上传成功")
                return True

            logger.warning("图片上传失败")
            return False

        except Exception as e:
            logger.error(f"上传图片失败: {e}")
            return False

    async def _upload_file_input(self, image_path: str) -> bool:
        """使用文件输入框上传图片"""
        try:
            upload_selectors = [
                'input[type="file"]',
                'input[accept*="image"]',
                'input[accept*="image/*"]',
            ]

            for selector in upload_selectors:
                try:
                    await self.page.evaluate(f"""
                        () => {{
                            const inputs = document.querySelectorAll('{selector}');
                            inputs.forEach(input => {{
                                input.style.display = 'block';
                                input.style.visibility = 'visible';
                                input.style.opacity = '1';
                                input.style.position = 'static';
                            }});
                        }}
                    """)

                    upload_element = await self.page.wait_for_selector(
                        selector, timeout=1000
                    )
                    if upload_element:
                        await upload_element.set_input_files(image_path)
                        logger.info(f"通过文件输入框上传成功: {selector}")
                        await asyncio.sleep(2)
                        return True

                except Exception:
                    continue

            return False

        except Exception as e:
            logger.error(f"文件输入框上传失败: {e}")
            return False

    async def _input_prompt(self, prompt: str) -> bool:
        """输入提示词"""
        if not self.page:
            return False

        try:
            input_selectors = [
                "[contenteditable='true']",
                "textarea",
                "input[type='text']",
                'textarea[placeholder*="描述"]',
                'textarea[placeholder*="输入"]',
                'input[placeholder*="描述"]',
                'input[placeholder*="输入"]',
                ".input-area textarea",
                ".prompt-input",
            ]

            input_element = None
            for selector in input_selectors:
                try:
                    input_element = await self.page.wait_for_selector(
                        selector, timeout=3000
                    )
                    if input_element:
                        logger.info(f"找到豆包输入框: {selector}")
                        break
                except Exception:
                    logger.warning(f"等待元素 {selector} 超时或失败")
                    continue

            if not input_element:
                logger.error("未找到输入框")
                return False

            try:
                await input_element.clear()
            except AttributeError:
                await input_element.click()
                await self.page.keyboard.press("Control+a")
                await asyncio.sleep(0.5)

            await input_element.fill(prompt)
            await asyncio.sleep(1)

            logger.info(f"已输入豆包提示词: {prompt}")
            return True

        except Exception as e:
            logger.error(f"输入提示词失败: {e}")
            return False

    async def _submit_generation(self) -> bool:
        """提交生成请求"""
        if not self.page:
            return False

        try:
            logger.info("使用回车键提交豆包生成请求")
            await self.page.keyboard.press("Enter")

            await asyncio.sleep(2)
            logger.info("等待豆包图片生成...")
            return True

        except Exception as e:
            logger.error(f"提交生成请求失败: {e}")
            return False

    async def _wait_for_images(self, timeout: int = 60) -> list[dict[str, Any]]:
        """等待图片生成完成并获取图片URL列表及其顺序索引。"""
        if not self.page:
            return []

        try:
            logger.info(f"等待豆包图片生成完成 (超时: {timeout}s)...")
            await asyncio.wait_for(
                self._generation_complete_event.wait(), timeout=timeout
            )
            logger.info("✅ 收到生成完成信号，额外等待2秒以确保所有数据被处理。")
            await asyncio.sleep(2)
        except asyncio.TimeoutError:
            logger.warning(
                f"等待生成完成信号超时 ({timeout}s)。将尝试使用已收到的数据。"
            )

        if not self.generated_images:
            logger.error("未收集到任何有效的图片信息。")
            return []

        all_image_infos = list(self.generated_images.values())

        all_image_infos.sort(key=lambda x: x.get("index", 99))

        logger.info(f"最终成功解析并排序了 {len(all_image_infos)} 张图片。")
        return all_image_infos

    async def generate_doubao_image(
        self, prompt: str, image_path: str | None = None
    ) -> list[dict[str, Any]]:
        """使用豆包生成图片，并返回带索引的图片信息列表"""
        try:
            if not await self.navigate_to_create_image():
                raise ImageGenerationError("导航到豆包图片创建页面失败")

            if image_path:
                logger.info(f"检测到图片输入，开始上传图片: {image_path}")
                if not await self._upload_image(image_path):
                    logger.warning("图片上传失败，继续使用纯文本模式")
                else:
                    logger.info("图片上传成功，等待图片处理...")
                    await asyncio.sleep(2)

            if not await self._input_prompt(prompt):
                raise ImageGenerationError("输入提示词失败")

            if not await self._submit_generation():
                raise ImageGenerationError("提交生成请求失败")

            image_infos = await self._wait_for_images(timeout=60)

            if not image_infos:
                raise ImageGenerationError("未获取到生成的图片")

            logger.info(f"豆包图片生成成功，获取到 {len(image_infos)} 张图片信息")
            return image_infos

        except Exception as e:
            logger.error(f"豆包图片生成失败: {e}")
            raise ImageGenerationError(f"豆包图片生成失败: {e}")

    async def download_images_with_browser(
        self, image_infos: list[dict[str, Any]], prompt: str
    ) -> list[dict[str, Any]]:
        """使用浏览器下载图片（避免403错误）"""
        if not self.page:
            logger.error("浏览器页面未初始化")
            return []

        if not image_infos:
            logger.warning("没有有效的图片信息需要下载")
            return []

        urls_with_index = [
            {"url": info["url"], "index": info["index"]} for info in image_infos
        ]

        logger.info(f"开始批量下载 {len(urls_with_index)} 张图片...")

        try:
            download_results = await self.page.evaluate(
                """
                async (urlsWithIndex) => {
                    console.log(`开始批量下载 ${urlsWithIndex.length} 张图片...`);

                    const downloadPromises = urlsWithIndex.map(async (info) => {
                        try {
                            console.log(`开始下载图片 (索引: ${info.index})`);

                            const response = await fetch(info.url);
                            if (!response.ok) {
                                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                            }

                            const arrayBuffer = await response.arrayBuffer();
                            const uint8Array = new Uint8Array(arrayBuffer);

                            console.log(`图片 (索引: ${info.index}) 下载成功，大小: ${uint8Array.length} bytes`);

                            return {
                                url: info.url,
                                data: Array.from(uint8Array),
                                index: info.index, // 返回原始索引
                                success: true,
                                size: uint8Array.length
                            };
                        } catch (error) {
                            console.error(`图片 (索引: ${info.index}) 下载失败:`, error);
                            return {
                                url: info.url,
                                data: null,
                                index: info.index, // 即使失败也返回原始索引
                                success: false,
                                error: error.message
                            };
                        }
                    });

                    // 等待所有下载完成
                    const results = await Promise.all(downloadPromises);

                    const successful = results.filter(r => r.success).length;
                    console.log(`批量下载完成，成功: ${successful}/${results.length}`);

                    return results;
                }
            """,
                urls_with_index,
            )

            downloaded_images = []
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]

            successful_downloads = 0
            for download_result in download_results:
                if download_result["success"] and download_result["data"]:
                    try:
                        filename = f"doubao_{timestamp}_{prompt_hash}_{download_result['index']}.png"
                        filepath = TEMP_PATH / "multimodal-ai" / "image" / filename
                        filepath.parent.mkdir(parents=True, exist_ok=True)

                        import aiofiles

                        async with aiofiles.open(filepath, "wb") as f:
                            await f.write(bytes(download_result["data"]))

                        image_result = {
                            "url": download_result["url"],
                            "local_path": str(filepath.resolve()),
                            "filename": filename,
                            "size_bytes": download_result["size"],
                            "format": "png",
                            "dimensions": {},
                            "index": download_result["index"],
                            "prompt": prompt,
                            "provider": "doubao",
                            "download_time": datetime.now().isoformat(),
                            "download_method": "browser_batch",
                        }

                        downloaded_images.append(image_result)
                        successful_downloads += 1

                    except Exception as e:
                        logger.error(f"保存图片失败: {e}")
                        continue
                else:
                    logger.warning(
                        f"图片下载失败: {download_result.get('error', '未知错误')}"
                    )

            logger.info(
                f"✅ 批量下载完成，成功保存 {successful_downloads}/{len(image_infos)} 张图片"
            )
            return downloaded_images

        except Exception as e:
            logger.error(f"批量下载图片失败: {e}")
            return []

    async def generate_image(
        self,
        prompt: str,
        count: int = 1,
        image_path: str | None = None,
    ) -> dict[str, Any]:
        """生成AI图片"""
        try:
            if image_path:
                logger.info(f"🎨 开始生成AI图片 (基于图片): {prompt}")
                logger.info(f"📷 输入图片: {image_path}")
            else:
                logger.info(f"🎨 开始生成AI图片: {prompt}")

            image_infos = await self.generate_doubao_image(prompt, image_path)
            api_type = "doubao"

            if not image_infos:
                raise ImageGenerationError("未能生成任何图片")

            downloaded_images = await self.download_images_with_browser(
                image_infos, prompt
            )

            if len(downloaded_images) < len(image_infos):
                logger.info(
                    f"浏览器下载了 {len(downloaded_images)}/{len(image_infos)} 张图片，尝试HTTP客户端下载剩余图片..."
                )

                downloaded_urls = {img["url"] for img in downloaded_images}
                remaining_infos = [
                    info for info in image_infos if info["url"] not in downloaded_urls
                ]

                if remaining_infos:
                    async with ImageDownloader() as downloader:
                        additional_images = await downloader.download_images(
                            remaining_infos,
                            prompt,
                            "doubao",
                            max_retries=3,
                            retry_delay=2.0,
                            min_success_count=0,
                        )
                        downloaded_images.extend(additional_images)

            if not downloaded_images:
                raise ImageGenerationError("所有图片下载失败，请稍后重试")
            elif len(downloaded_images) < len(image_infos):
                logger.warning(
                    f"部分图片下载失败，成功下载 {len(downloaded_images)}/{len(image_infos)} 张图片"
                )

            downloaded_images.sort(key=lambda img: img.get("index", 99))
            logger.info("✅ 已根据原始生成顺序对下载的图片进行排序。")

            result = {
                "success": True,
                "prompt": prompt,
                "count": len(downloaded_images),
                "images": downloaded_images,
                "api_type": api_type,
                "use_cookies": bool(base_config.get("DOUBAO_COOKIES")),
            }

            logger.info(
                f"✅ AI图片生成成功: {len(downloaded_images)} 张图片 (使用: {api_type})"
            )
            return result

        except Exception as e:
            logger.error(f"AI图片生成失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "prompt": prompt,
                "count": 0,
                "images": [],
                "api_type": "error",
            }

    async def batch_generate_images(
        self, prompts: list[str], delay: float = 3.0
    ) -> list[dict[str, Any]]:
        """批量生成图片"""
        results = []

        for i, prompt in enumerate(prompts):
            logger.info(f"批量生成 {i + 1}/{len(prompts)}: {prompt}")

            try:
                result = await self.generate_image(prompt)
                results.append(result)

                if i < len(prompts) - 1:
                    await asyncio.sleep(delay)

            except Exception as e:
                logger.error(f"批量生成第{i + 1}张图片失败: {e}")
                results.append(
                    {
                        "success": False,
                        "error": str(e),
                        "prompt": prompt,
                        "count": 0,
                        "images": [],
                    }
                )

        return results


image_generator = DoubaoImageGenerator()
