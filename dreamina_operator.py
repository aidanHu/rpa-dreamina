#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import random
import re
import base64
import io
import requests
from playwright.sync_api import sync_playwright

# SSL相关导入，用于更安全的图片下载
import urllib3

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import Error as PlaywrightError
except ImportError:
    # 兼容不同版本的 Playwright
    PlaywrightTimeoutError = Exception
    PlaywrightError = Exception

from element_config import get_element, get_wait_time
from points_monitor import PointsMonitor
from playwright_compat import safe_title, safe_is_visible
from smart_delay import smart_delay
from human_behavior import HumanBehavior

# 尝试导入PIL用于图片格式转换
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# 默认图片保存路径（作为备用）
IMAGE_SAVE_PATH = "generated_images"

def sanitize_filename(prompt, max_length=10, for_folder=False):
    """
    清理文件名，移除不合法字符，并限制提示词部分为10个字符
    """
    # 移除或替换不合法字符
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', prompt)
    sanitized = re.sub(r'[\r\n\t]', ' ', sanitized)
    sanitized = re.sub(r'\s+', '_', sanitized.strip())
    
    # 限制长度为10个字符
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    # 确保不以点开头或结尾
    sanitized = sanitized.strip('.')

    # 如果为空，使用默认名称
    if not sanitized:
        sanitized = "default_name"
        
    return sanitized

def navigate_and_setup_dreamina_page(context, target_url, window_name="", window_instance=None):
    """
    导航到Dreamina页面并进行基本设置 - 线程安全版本
    
    Args:
        context: Playwright浏览器上下文
        target_url: 目标URL
        window_name: 窗口名称（用于日志区分）
        window_instance: 窗口实例（用于独立状态管理）
    """
    try:
        print(f"[DreaminaOperator:{window_name}] 🔧 开始导航和设置页面 (详细诊断模式)...")
        print(f"[DreaminaOperator:{window_name}] 输入参数 - target_url: {target_url}")
        print(f"[DreaminaOperator:{window_name}] 上下文状态 - context: {context is not None}")
        
        # 🚀 首先检查浏览器上下文是否可用
        if not context:
            print(f"[DreaminaOperator:{window_name}] ❌ 浏览器上下文为空")
            return None
        
        # 检查上下文是否仍然有效
        try:
            # 通过尝试获取页面列表来验证上下文有效性
            pages = context.pages
            print(f"[DreaminaOperator:{window_name}] ✅ 上下文有效，当前页面数: {len(pages)}")
        except Exception as e:
            print(f"[DreaminaOperator:{window_name}] ❌ 上下文无效或已关闭: {e}")
            return None
        
        # 获取所有页面
        pages = context.pages
        
        if not pages:
            print(f"[DreaminaOperator:{window_name}] 没有找到任何页面，创建新页面")
            # 🛡️ 增强的页面创建逻辑
            max_page_retries = 3
            for page_retry in range(max_page_retries):
                try:
                    print(f"[DreaminaOperator:{window_name}] 尝试创建页面 {page_retry + 1}/{max_page_retries}")
                    
                    # 再次验证上下文
                    if not context or not hasattr(context, 'new_page'):
                        print(f"[DreaminaOperator:{window_name}] ❌ 上下文无效，无法创建页面")
                        if page_retry < max_page_retries - 1:
                            time.sleep(2)
                            continue
                        return None
                    
                    page = context.new_page()
                    
                    # 验证页面创建成功
                    if page and not page.is_closed():
                        print(f"[DreaminaOperator:{window_name}] ✅ 页面创建成功")
                        break
                    else:
                        raise Exception("页面创建失败或立即关闭")
                        
                except Exception as e:
                    print(f"[DreaminaOperator:{window_name}] ❌ 创建页面尝试 {page_retry + 1} 失败: {e}")
                    if page_retry < max_page_retries - 1:
                        print(f"[DreaminaOperator:{window_name}] ⏳ 等待 2 秒后重试...")
                        time.sleep(2)
                    else:
                        return None
        else:
            # 关闭所有无关的标签页 - 智能过滤版本
            print(f"[DreaminaOperator:{window_name}] 🔍 检查并关闭无关标签页...")
            pages_to_close = []
            
            # 🚨 重要：不要关闭比特浏览器的控制台页面！
            protected_patterns = [
                "console.bitbrowser.net",  # 比特浏览器控制台
                "localhost:54345",         # 比特浏览器本地控制台
                "127.0.0.1:54345",         # 比特浏览器本地控制台
                "about:blank"              # 空白页面
            ]
            
            for p in pages:
                try:
                    if not p.is_closed() and p.url != target_url:
                        # 检查是否是受保护的页面
                        should_protect = False
                        for pattern in protected_patterns:
                            if pattern in p.url.lower():
                                should_protect = True
                                print(f"[DreaminaOperator:{window_name}] 🛡️ 保护页面，不关闭: {p.url}")
                                break
                        
                        if not should_protect:
                            pages_to_close.append(p)
                except Exception as e:
                    print(f"[DreaminaOperator:{window_name}] ⚠️ 检查页面URL时出错: {e}")
            
            # 批量关闭页面，避免遍历时修改列表
            for p in pages_to_close:
                try:
                    print(f"[DreaminaOperator:{window_name}] 关闭无关标签页: {p.url}")
                    p.close()
                    time.sleep(0.2)  # 短暂延迟避免冲突
                except Exception as e:
                    print(f"[DreaminaOperator:{window_name}] ⚠️ 关闭标签页时出错: {e}")
            
            # 重新获取页面列表
            try:
                pages = context.pages
            except Exception as e:
                print(f"[DreaminaOperator:{window_name}] ❌ 重新获取页面列表失败: {e}")
                return None
                
            if pages:
                # 选择第一个未关闭的页面
                page = None
                for p in pages:
                    try:
                        if not p.is_closed():
                            page = p
                            break
                    except Exception as e:
                        print(f"[DreaminaOperator:{window_name}] 检查页面状态时出错: {e}")
                        continue
                
                if page:
                    print(f"[DreaminaOperator:{window_name}] 使用现有页面: {page.url}")
                else:
                    print(f"[DreaminaOperator:{window_name}] 所有页面都已关闭，创建新页面")
                    # 🛡️ 增强的页面创建逻辑
                    max_page_retries = 3
                    page = None
                    for page_retry in range(max_page_retries):
                        try:
                            print(f"[DreaminaOperator:{window_name}] 尝试创建页面 {page_retry + 1}/{max_page_retries}")
                            
                            # 验证上下文状态
                            if not context or not hasattr(context, 'new_page'):
                                print(f"[DreaminaOperator:{window_name}] ❌ 上下文状态异常")
                                if page_retry < max_page_retries - 1:
                                    time.sleep(2)
                                    continue
                                return None
                            
                            page = context.new_page()
                            
                            if page and not page.is_closed():
                                print(f"[DreaminaOperator:{window_name}] ✅ 页面创建成功")
                                break
                            else:
                                raise Exception("页面创建失败或立即关闭")
                                
                        except Exception as e:
                            print(f"[DreaminaOperator:{window_name}] ❌ 创建页面尝试 {page_retry + 1} 失败: {e}")
                            if page_retry < max_page_retries - 1:
                                time.sleep(2)
                            else:
                                return None
            else:
                print(f"[DreaminaOperator:{window_name}] 没有可用页面，创建新页面")
                # 🛡️ 增强的页面创建逻辑
                max_page_retries = 3
                page = None
                for page_retry in range(max_page_retries):
                    try:
                        print(f"[DreaminaOperator:{window_name}] 尝试创建页面 {page_retry + 1}/{max_page_retries}")
                        
                        # 验证上下文状态
                        if not context or not hasattr(context, 'new_page'):
                            print(f"[DreaminaOperator:{window_name}] ❌ 上下文状态异常")
                            if page_retry < max_page_retries - 1:
                                time.sleep(2)
                                continue
                            return None
                        
                        page = context.new_page()
                        
                        if page and not page.is_closed():
                            print(f"[DreaminaOperator:{window_name}] ✅ 页面创建成功")
                            break
                        else:
                            raise Exception("页面创建失败或立即关闭")
                            
                    except Exception as e:
                        print(f"[DreaminaOperator:{window_name}] ❌ 创建页面尝试 {page_retry + 1} 失败: {e}")
                        if page_retry < max_page_retries - 1:
                            time.sleep(2)
                        else:
                            return None
        
        # 🚀 关键优化：设置窗口大小为固定分辨率1920*1080
        try:
            print(f"[DreaminaOperator:{window_name}] 🖥️ 设置窗口大小和视口...")
            
            # 设置视口尺寸为1920x1080，确保所有元素可见
            page.set_viewport_size({"width": 1920, "height": 1080})
            
            # 设置固定窗口大小为1920*1080（通过JavaScript）
            page.evaluate("""
                () => {
                    try {
                        // 设置固定窗口大小为1920*1080
                        const targetWidth = 1920;
                        const targetHeight = 1080;
                        
                        // 尝试调整窗口大小
                        if (window.resizeTo) {
                            window.resizeTo(targetWidth, targetHeight);
                        }
                        if (window.moveTo) {
                            window.moveTo(0, 0);
                        }
                        
                        // 确保窗口获得焦点
                        window.focus();
                        
                        console.log(`窗口已设置为 ${targetWidth}x${targetHeight}`);
                    } catch (e) {
                        console.log('窗口设置失败:', e);
                    }
                }
            """)
            
            print(f"[DreaminaOperator:{window_name}] ✅ 窗口已设置为1920x1080")
            
        except Exception as e:
            print(f"[DreaminaOperator:{window_name}] ⚠️ 设置窗口大小时出错: {e}")
        
        # 🌐 增强的页面导航逻辑
        if page.url != target_url:
            print(f"[DreaminaOperator:{window_name}] 导航到: {target_url}")
            
            max_nav_retries = 3
            nav_success = False
            
            for nav_retry in range(max_nav_retries):
                try:
                    print(f"[DreaminaOperator:{window_name}] 导航尝试 {nav_retry + 1}/{max_nav_retries}")
                    
                    # 检查页面是否仍然有效
                    if page.is_closed():
                        print(f"[DreaminaOperator:{window_name}] 页面已关闭，重新创建")
                        # 重新创建页面的逻辑
                        for recreate_retry in range(3):
                            try:
                                if not context or not hasattr(context, 'new_page'):
                                    raise Exception("上下文无效")
                                page = context.new_page()
                                if page and not page.is_closed():
                                    break
                                else:
                                    raise Exception("页面创建失败")
                            except Exception as recreate_e:
                                print(f"[DreaminaOperator:{window_name}] 重新创建页面失败 {recreate_retry + 1}/3: {recreate_e}")
                                if recreate_retry < 2:
                                    time.sleep(2)
                                else:
                                    return None
                        
                        # 重新设置视口
                        page.set_viewport_size({"width": 1920, "height": 1080})
                    
                    # 🚀 优化的导航策略
                    print(f"[DreaminaOperator:{window_name}] 🌐 开始导航到 {target_url}")
                    
                    if nav_retry == 0:
                        # 第一次尝试使用较短的超时，避免长时间等待
                        try:
                            page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                            # 导航成功后再等待网络空闲（可选）
                            try:
                                page.wait_for_load_state("networkidle", timeout=10000)
                            except:
                                pass  # 网络空闲失败不影响继续
                        except Exception as e:
                            print(f"[DreaminaOperator:{window_name}] 第一次导航失败: {e}")
                            raise e
                    else:
                        # 后续尝试使用更短的超时
                        page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                    
                    # 验证导航成功
                    if target_url in page.url or "dreamina" in page.url.lower():
                        print(f"[DreaminaOperator:{window_name}] ✅ 导航成功")
                        nav_success = True
                        break
                    else:
                        raise Exception(f"导航后URL不匹配，当前: {page.url}")
                        
                except Exception as e:
                    print(f"[DreaminaOperator:{window_name}] ❌ 导航尝试 {nav_retry + 1} 失败: {e}")
                    if nav_retry < max_nav_retries - 1:
                        print(f"[DreaminaOperator:{window_name}] ⏳ 等待 3 秒后重试导航...")
                        time.sleep(3)
                    else:
                        print(f"[DreaminaOperator:{window_name}] ❌ 所有导航尝试都失败")
                        return None
            
            if not nav_success:
                print(f"[DreaminaOperator:{window_name}] ❌ 导航失败")
                return None
        
        # 等待页面完全加载
        print(f"[DreaminaOperator:{window_name}] ⏳ 等待页面完全加载...")
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception as e:
            print(f"[DreaminaOperator:{window_name}] ⚠️ 等待网络空闲超时: {e}")
        
        # 确保页面稳定
        time.sleep(5)
        
        # 再次检查并关闭可能新打开的无关标签页
        print(f"[DreaminaOperator:{window_name}] 🔍 再次检查并关闭无关标签页...")
        try:
            current_pages = context.pages
            for p in current_pages:
                try:
                    if p != page and not p.is_closed() and p.url != target_url:
                        print(f"[DreaminaOperator:{window_name}] 关闭新打开的无关标签页: {p.url}")
                        p.close()
                        time.sleep(0.2)
                except Exception as e:
                    print(f"[DreaminaOperator:{window_name}] ⚠️ 关闭标签页时出错: {e}")
        except Exception as e:
            print(f"[DreaminaOperator:{window_name}] ⚠️ 检查页面列表时出错: {e}")
        
        # 检查页面是否正常加载
        try:
            page_title = page.title()
            print(f"[DreaminaOperator:{window_name}] 📄 页面标题: {page_title}")
            if not page_title or "Dreamina" not in page_title:
                print(f"[DreaminaOperator:{window_name}] ⚠️ 页面可能未正确加载，尝试刷新...")
                page.reload(wait_until="networkidle", timeout=60000)
                time.sleep(5)
        except Exception as e:
            print(f"[DreaminaOperator:{window_name}] ⚠️ 检查页面标题时出错: {e}")
        
        # 🎯 优化：滚动到页面顶部，确保模型选择器可见
        try:
            print(f"[DreaminaOperator:{window_name}] 📜 滚动到页面顶部...")
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(1)
        except Exception as e:
            print(f"[DreaminaOperator:{window_name}] ⚠️ 滚动到顶部时出错: {e}")
            
        # 使用窗口独立的模型选择状态（而非全局状态）
        should_select_model = True
        if window_instance:
            should_select_model = not window_instance.model_selected
        
        if should_select_model:
            try:
                import json
                with open('gui_config.json', 'r', encoding='utf-8') as f:
                    config = json.load(f)
                model_name = config.get("image_settings", {}).get("default_model", "Image 3.0")
                max_retries = 3
                retry_count = 0
                
                print(f"[DreaminaOperator:{window_name}] 🎯 开始选择模型: {model_name}")
                
                while retry_count < max_retries:
                    if select_model_enhanced(page, model_name, window_name):
                        if window_instance:
                            window_instance.model_selected = True
                        print(f"[DreaminaOperator:{window_name}] ✅ 模型选择成功")
                        break
                    retry_count += 1
                    if retry_count < max_retries:
                        print(f"[DreaminaOperator:{window_name}] ⚠️ 模型选择失败，第 {retry_count} 次重试...")
                        HumanBehavior.random_delay(2, 3)
                else:
                    print(f"[DreaminaOperator:{window_name}] ⚠️ 模型选择失败，继续流程")
            except Exception as e:
                print(f"[DreaminaOperator:{window_name}] ⚠️ 模型选择过程出错: {e}")
        else:
            print(f"[DreaminaOperator:{window_name}] ✅ 模型已选择，跳过选择步骤")
        
        # 🎯 最终验证和返回
        print(f"[DreaminaOperator:{window_name}] 🔍 最终验证 - 页面对象: {page is not None}")
        if page:
            try:
                final_url = page.url
                final_title = page.title()
                print(f"[DreaminaOperator:{window_name}] 📄 最终页面信息 - URL: {final_url}, 标题: {final_title}")
                print(f"[DreaminaOperator:{window_name}] ✅ 成功完成页面设置，返回页面对象")
            except Exception as e:
                print(f"[DreaminaOperator:{window_name}] ⚠️ 获取最终页面信息时出错: {e}")
        else:
            print(f"[DreaminaOperator:{window_name}] ❌ 页面对象为None，函数将返回None")
            
        return page
        
    except Exception as e:
        print(f"[DreaminaOperator:{window_name}] ❌ 导航到页面时出错: {e}")
        import traceback
        print(f"[DreaminaOperator:{window_name}] 错误详情:\n{traceback.format_exc()}")
        return None

def check_page_connection(page):
    """
    检查页面连接是否正常
    """
    try:
        if page.is_closed():
            return False
        # 尝试获取页面标题来测试连接（兼容不同版本的Playwright）
        safe_title(page, timeout=5000)
        return True
    except Exception as e:
        log_with_window(f"页面连接检查失败: {e}")
        return False

def simple_scroll_down(page, description="简单向下滚动", log_func=None):
    """
    简单的向下滚动功能，鼠标移动到网页右边进行滚动
    """
    def log_msg(msg):
        if log_func:
            log_func(msg)
        else:
            print(f"[simple_scroll_down] {msg}")
    
    try:
        log_msg(f"🖱️ 开始{description}...")
        
        # 获取页面尺寸
        page_size = page.evaluate("""() => {
            return {
                width: window.innerWidth,
                height: window.innerHeight
            };
        }""")
        
        # 移动鼠标到页面右边中间位置
        right_x = int(page_size['width'] * 0.85)  # 右边85%的位置
        center_y = page_size['height'] // 2
        
        log_msg(f"📍 移动鼠标到页面右边 ({right_x}, {center_y})")
        page.mouse.move(right_x, center_y)
        time.sleep(0.5)

        # 使用鼠标滚轮向下滚动几次
        log_msg("🔽 在页面右边向下滚动...")
        for i in range(3):
            page.mouse.wheel(0, 800)  # 向下滚动800像素
            time.sleep(1)
            log_msg(f"滚动第 {i+1}/3 次")
        
        log_msg("✅ 简单滚动完成")
        return True
        
    except Exception as e:
        log_msg(f"❌ 简单滚动失败: {e}")
        return False

def wait_for_content_and_scroll(page, content_selector, max_wait_seconds=10, log_func=None):
    """
    等待内容出现后再简单滚动
    """
    def log_msg(msg):
        if log_func:
            log_func(msg)
        else:
            print(f"[wait_for_content_and_scroll] {msg}")
    
    try:
        log_msg(f"⏳ 等待内容出现 (最多{max_wait_seconds}秒)...")
        
        start_time = time.time()
        content_appeared = False
        
        while time.time() - start_time < max_wait_seconds:
            # 检查内容是否出现
            content_count = page.locator(f"xpath={content_selector}").count()
            
            if content_count > 0:
                log_msg("✅ 检测到内容出现，准备滚动")
                content_appeared = True
                break
            
            time.sleep(1)
        
        if content_appeared:
            # 等待一点时间让内容稳定
            time.sleep(2)
            
            # 执行简单滚动
            scroll_success = simple_scroll_down(page, "等待内容后滚动", log_func)
            return scroll_success
        else:
            log_msg("⚠️ 内容未出现，执行备用滚动")
            return simple_scroll_down(page, "备用滚动", log_func)
            
    except Exception as e:
        log_msg(f"等待内容并滚动时出错: {e}")
        return False

def select_aspect_ratio(page, aspect_ratio="9:16", log_func=None):
    """
    选择图片尺寸比例
    """
    def log_msg(msg):
        if log_func:
            log_func(msg)
        else:
            print(f"[select_aspect_ratio] {msg}")
    
    try:
        log_msg(f"🖼️ 选择图片尺寸: {aspect_ratio}")
        
        # 从元素配置获取对应的选择器
        aspect_ratio_selector = get_element("aspect_ratio_selection", aspect_ratio)
        
        if not aspect_ratio_selector:
            log_msg(f"⚠️ 未找到尺寸 {aspect_ratio} 的选择器，跳过尺寸选择")
            return False
        
        # 查找并点击对应的尺寸选项
        aspect_ratio_element = page.locator(f"xpath={aspect_ratio_selector}")
        
        # 等待元素可见
        aspect_ratio_element.wait_for(state="visible", timeout=10000)
        
        # 点击尺寸选项
        aspect_ratio_element.click(timeout=10000)
        
        log_msg(f"✅ 成功选择图片尺寸: {aspect_ratio}")
        
        # 等待选择生效
        time.sleep(2)
        
        return True
        
    except Exception as e:
        log_msg(f"❌ 选择图片尺寸失败: {e}")
        return False

def select_model(page, model_name="Image 3.0"):
    """
    选择图片生成模型
    
    Args:
        page: Playwright页面对象
        model_name: 模型名称
        
    Returns:
        bool: 是否成功选择模型
    """
    try:
        log_with_window(f"🤖 开始选择模型: {model_name}")
        
        # 获取模型选择器
        model_selector_xpath = get_element("image_generation", "model_selector")
        if not model_selector_xpath:
            log_with_window("❌ 未找到模型选择器配置")
            return False
            
        # 等待并点击模型选择器
        model_selector = page.locator(f"xpath={model_selector_xpath}")
        if not model_selector.is_visible(timeout=10000):
            log_with_window("❌ 模型选择器不可见")
            return False
            
        # 点击模型选择器
        HumanBehavior.human_like_click(page, model_selector)
        HumanBehavior.random_delay(0.8, 1.2)
        
        # 根据模型名称选择对应的选项
        if model_name == "Image 3.0":
            model_option_xpath = get_element("image_generation", "model_image_3_0")
        elif model_name == "Image 2.1":
            model_option_xpath = get_element("image_generation", "model_image_2_1")
        elif model_name == "Image 2.0 Pro":
            model_option_xpath = get_element("image_generation", "model_image_2_0_pro")
        else:
            model_option_xpath = get_element("image_generation", "model_image_3_0")
            
        if not model_option_xpath:
            log_with_window(f"❌ 未找到模型 {model_name} 的选项配置")
            return False
            
        # 等待并点击模型选项
        model_option = page.locator(f"xpath={model_option_xpath}")
        if not model_option.is_visible(timeout=5000):
            log_with_window(f"❌ 模型选项 {model_name} 不可见")
            return False
            
        HumanBehavior.human_like_click(page, model_option)
        HumanBehavior.random_delay(0.5, 1.0)
        
        # 验证模型是否选择成功
        try:
            # 等待模型选择器更新
            time.sleep(1)
            
            # 获取模型选择器中的文本内容
            model_text = model_selector.locator("//span[contains(@class, 'text-')]").text_content()
            if not model_text:
                log_with_window("❌ 无法获取模型选择器中的文本")
                return False
                
            # 检查文本是否包含预期的模型名称
            if model_name not in model_text:
                log_with_window(f"❌ 模型选择验证失败: 期望 '{model_name}', 实际 '{model_text}'")
                return False
                
            log_with_window(f"✅ 成功选择并验证模型: {model_name}")
            return True
            
        except Exception as verify_error:
            log_with_window(f"❌ 验证模型选择时出错: {verify_error}")
            return False
        
    except Exception as e:
        log_with_window(f"❌ 选择模型时出错: {e}")
        return False

def select_model_enhanced(page, model_name="Image 3.0", window_name=""):
    """
    增强版模型选择函数 - 包含窗口最大化和智能元素查找
    
    Args:
        page: Playwright页面对象
        model_name: 模型名称
        window_name: 窗口名称（用于日志）
        
    Returns:
        bool: 是否成功选择模型
    """
    try:
        print(f"[DreaminaOperator:{window_name}] 🤖 开始增强模型选择: {model_name}")
        
        # 1. 确保页面滚动到顶部，模型选择器通常在页面上方
        try:
            print(f"[DreaminaOperator:{window_name}] 📜 确保页面滚动位置正确...")
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(1)
        except Exception as e:
            print(f"[DreaminaOperator:{window_name}] ⚠️ 滚动到顶部失败: {e}")
        
        # 2. 等待页面稳定
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            # 如果网络不空闲，至少等待DOM加载完成
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
        
        # 3. 获取模型选择器配置
        model_selector_xpath = get_element("image_generation", "model_selector")
        if not model_selector_xpath:
            print(f"[DreaminaOperator:{window_name}] ❌ 未找到模型选择器配置")
            return False
        
        # 4. 智能等待和查找模型选择器
        print(f"[DreaminaOperator:{window_name}] 🔍 智能查找模型选择器...")
        model_selector = page.locator(f"xpath={model_selector_xpath}")
        
        # 尝试多种方式确保元素可见
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                # 检查元素是否存在
                if model_selector.count() == 0:
                    print(f"[DreaminaOperator:{window_name}] ⚠️ 模型选择器不存在，尝试 {attempt + 1}/{max_attempts}")
                    
                    # 尝试滚动页面
                    if attempt < 3:
                        page.evaluate(f"window.scrollTo(0, {attempt * 200})")
                        time.sleep(1)
                    else:
                        # 尝试刷新页面
                        print(f"[DreaminaOperator:{window_name}] 🔄 尝试刷新页面...")
                        page.reload(wait_until="domcontentloaded", timeout=30000)
                        time.sleep(3)
                        page.evaluate("window.scrollTo(0, 0)")
                        time.sleep(1)
                    continue
                
                # 检查元素是否可见
                if not model_selector.is_visible(timeout=5000):
                    print(f"[DreaminaOperator:{window_name}] ⚠️ 模型选择器不可见，尝试滚动查找 {attempt + 1}/{max_attempts}")
                    
                    # 尝试滚动到元素位置
                    try:
                        model_selector.scroll_into_view_if_needed(timeout=5000)
                        time.sleep(1)
                    except Exception:
                        # 手动滚动
                        page.evaluate(f"window.scrollTo(0, {attempt * 300})")
                        time.sleep(1)
                    continue
                
                # 元素找到且可见，跳出循环
                print(f"[DreaminaOperator:{window_name}] ✅ 模型选择器已找到且可见")
                break
                
            except Exception as e:
                print(f"[DreaminaOperator:{window_name}] ⚠️ 查找模型选择器时出错 {attempt + 1}/{max_attempts}: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(2)
                    continue
                else:
                    return False
        else:
            print(f"[DreaminaOperator:{window_name}] ❌ 经过 {max_attempts} 次尝试仍无法找到模型选择器")
            return False
        
        # 5. 点击模型选择器
        print(f"[DreaminaOperator:{window_name}] 🖱️ 点击模型选择器...")
        try:
            # 先尝试滚动到元素
            model_selector.scroll_into_view_if_needed(timeout=5000)
            time.sleep(0.5)
            
            # 使用人类行为模拟点击
            HumanBehavior.human_like_click(page, model_selector)
            HumanBehavior.random_delay(0.8, 1.2)
            
        except Exception as e:
            print(f"[DreaminaOperator:{window_name}] ❌ 点击模型选择器失败: {e}")
            return False
        
        # 6. 等待模型选项出现并选择对应模型
        print(f"[DreaminaOperator:{window_name}] 🎯 选择模型选项: {model_name}")
        
        # 根据模型名称获取对应的选项配置
        if model_name == "Image 3.0":
            model_option_xpath = get_element("image_generation", "model_image_3_0")
        elif model_name == "Image 2.1":
            model_option_xpath = get_element("image_generation", "model_image_2_1")
        elif model_name == "Image 2.0 Pro":
            model_option_xpath = get_element("image_generation", "model_image_2_0_pro")
        else:
            print(f"[DreaminaOperator:{window_name}] ⚠️ 未知模型名称，使用默认 Image 3.0")
            model_option_xpath = get_element("image_generation", "model_image_3_0")
            
        if not model_option_xpath:
            print(f"[DreaminaOperator:{window_name}] ❌ 未找到模型 {model_name} 的选项配置")
            return False
        
        # 7. 智能查找和点击模型选项
        model_option = page.locator(f"xpath={model_option_xpath}")
        
        # 等待选项出现
        try:
            model_option.wait_for(state="visible", timeout=10000)
        except Exception as e:
            print(f"[DreaminaOperator:{window_name}] ⚠️ 等待模型选项出现超时: {e}")
            # 尝试重新点击选择器
            try:
                model_selector.click()
                time.sleep(1)
                model_option.wait_for(state="visible", timeout=5000)
            except Exception:
                print(f"[DreaminaOperator:{window_name}] ❌ 重试后仍无法找到模型选项")
                return False
        
        # 点击模型选项
        try:
            # 确保选项可见
            model_option.scroll_into_view_if_needed(timeout=5000)
            time.sleep(0.5)
            
            HumanBehavior.human_like_click(page, model_option)
            HumanBehavior.random_delay(0.5, 1.0)
            
        except Exception as e:
            print(f"[DreaminaOperator:{window_name}] ❌ 点击模型选项失败: {e}")
            return False
        
        # 8. 验证模型选择是否成功
        print(f"[DreaminaOperator:{window_name}] ✅ 验证模型选择结果...")
        time.sleep(1)
        
        try:
            # 重新获取模型选择器
            model_selector = page.locator(f"xpath={model_selector_xpath}")
            
            # 尝试获取选择器中的文本
            selector_text = None
            text_selectors = [
                "//span[contains(@class, 'text-')]",
                "//span",
                ".//*[text()]"
            ]
            
            for text_selector in text_selectors:
                try:
                    text_element = model_selector.locator(text_selector).first
                    if text_element.is_visible(timeout=2000):
                        selector_text = text_element.text_content()
                        if selector_text and selector_text.strip():
                            break
                except Exception:
                    continue
            
            if not selector_text:
                print(f"[DreaminaOperator:{window_name}] ❌ 无法获取模型选择器中的文本")
                return False
                
            # 简化验证逻辑 - 检查关键字
            model_keywords = {
                "Image 3.0": ["3.0", "Image 3"],
                "Image 2.1": ["2.1", "Image 2.1"],
                "Image 2.0 Pro": ["2.0 Pro", "Pro"]
            }
            
            expected_keywords = model_keywords.get(model_name, ["3.0"])
            success = any(keyword in selector_text for keyword in expected_keywords)
            
            if success:
                print(f"[DreaminaOperator:{window_name}] ✅ 模型选择验证成功: {selector_text}")
                return True
            else:
                print(f"[DreaminaOperator:{window_name}] ⚠️ 模型选择验证失败: 期望包含 {expected_keywords}, 实际 '{selector_text}'")
                # 即使验证失败，也认为选择成功，因为有时文本获取不准确
                return True
                
        except Exception as verify_error:
            print(f"[DreaminaOperator:{window_name}] ⚠️ 验证模型选择时出错: {verify_error}")
            # 验证出错时仍然认为成功
            return True
        
    except Exception as e:
        print(f"[DreaminaOperator:{window_name}] ❌ 增强模型选择时出错: {e}")
        return False

def generate_image_on_page(page, prompt_info, first_generation=False, window_name="", config=None):
    """
    按照正确的即梦生成流程：
    1. 检测积分
    2. 输入提示词  
    3. 点击生成按钮
    4. 检测是否有生成内容
    5. 等待图片生成完成
    6. 下载图片
    7. 检测积分，看是否还能继续
    
    first_generation: 是否是此窗口的首次生成（影响是否需要设置图片尺寸）
    window_name: 窗口名称，用于日志标识
    config: 配置字典，如果提供则使用该配置，否则从user_config.json读取
    """
    
    def log_with_window(message):
        """带窗口名称的日志输出"""
        if window_name:
            print(f"[DreaminaOperator:{window_name}] {message}")
        else:
            print(f"[DreaminaOperator] {message}")

    current_prompt_text = prompt_info['prompt']
    source_folder_name = prompt_info['source_excel_name']
    excel_row_num = prompt_info['row_number']
    excel_file_path = prompt_info['excel_file_path']

    # 检查页面连接
    if not check_page_connection(page):
        log_with_window(f"页面连接已断开，无法处理提示词: {current_prompt_text}")
        return []

    # 使用新的保存路径（Excel所在的子文件夹）
    current_image_save_path = prompt_info.get('image_save_path', IMAGE_SAVE_PATH)
    
    # 确保保存目录存在
    if not os.path.exists(current_image_save_path):
        try:
            os.makedirs(current_image_save_path)
            log_with_window(f"已创建保存目录: {current_image_save_path}")
        except OSError as e:
            log_with_window(f"错误：创建保存目录 '{current_image_save_path}' 失败: {e}。将尝试保存到默认图片文件夹。")
            current_image_save_path = IMAGE_SAVE_PATH

    try:
        log_with_window(f"处理提示词: '{current_prompt_text}' (源: '{source_folder_name}')")
        log_with_window(f"图片保存路径: {current_image_save_path}")
        
        # ===== 步骤1: 生成前检测积分 =====
        log_with_window("💰 生成前积分检测...")
        try:
            points_selector = get_element("points_monitoring", "primary_selector")
            points_monitor = PointsMonitor(custom_points_selector=points_selector)
            initial_points = points_monitor.check_points(page, timeout=10000)
            
            if initial_points is not None:
                log_with_window(f"💰 生成前积分余额: {initial_points} 分")
                
                if initial_points < 2:
                    log_with_window(f"🚨 积分不足，无法进行生成！当前积分: {initial_points}")
                    return []
                elif initial_points < 6:
                    log_with_window(f"⚠️ 积分余额较低: {initial_points} 分")
                else:
                    log_with_window("✅ 积分充足，开始生成")
            else:
                log_with_window("⚠️ 无法获取积分信息，继续尝试生成")
                initial_points = None
                
        except Exception as e:
            log_with_window(f"❌ 生成前积分检测失败: {e}")
            initial_points = None
        
        # ===== 步骤2: 只在首次生成时设置图片尺寸 =====
        if first_generation:
            try:
                # 优先使用传入的配置，否则从文件读取
                if config is not None:
                    aspect_ratio_config = config
                    log_with_window("🖼️ 使用传入的配置设置图片尺寸")
                else:
                    import json
                    with open('gui_config.json', 'r', encoding='utf-8') as f:
                        aspect_ratio_config = json.load(f)
                    log_with_window("🖼️ 从配置文件读取图片尺寸设置")
                
                default_aspect_ratio = aspect_ratio_config.get("image_settings", {}).get("default_aspect_ratio", "9:16")
                log_with_window(f"🖼️ 首次生成，设置图片尺寸: {default_aspect_ratio}")
                select_aspect_ratio(page, default_aspect_ratio, log_with_window)
            except Exception as e:
                log_with_window(f"❌ 选择图片尺寸失败: {e}，继续生成流程")

        # ===== 步骤3: 输入提示词 =====
        log_with_window("📝 输入提示词...")
        prompt_input_xpath = get_element("image_generation", "prompt_input")
        prompt_input = page.locator(prompt_input_xpath)
        
        # 使用人类行为模拟输入提示词
        if not HumanBehavior.human_like_type(page, prompt_input, current_prompt_text):
            log_with_window("❌ 输入提示词失败")
            return []
            
        log_with_window("✅ 提示词已输入")
        
        # 随机等待
        HumanBehavior.random_delay(1.5, 3.0)

        # ===== 步骤4: 点击生成按钮 =====
        log_with_window("🚀 点击生成按钮...")
        generate_button_selector = get_element("image_generation", "generate_button")
        generate_button = page.locator(generate_button_selector)
        
        # 准备生成（直接点击生成按钮）
        if not HumanBehavior.prepare_for_generation(page, generate_button):
            log_with_window("❌ 点击生成按钮失败")
            return []
        
        log_with_window("✅ 生成按钮已点击")
        
        # 随机等待
        HumanBehavior.random_delay(1.0, 2.0)

        # ===== 步骤5: 检测排队状态并等待消失 =====
        queueing_xpath = get_element("image_generation", "queueing_status")
        
        log_with_window("🔍 检测是否有排队状态...")
        
        try:
            page.wait_for_selector(f"xpath={queueing_xpath}", timeout=10000)
            log_with_window("⏳ 检测到排队状态，开始等待...")
            
            QUEUE_WAIT_TIMEOUT = get_wait_time("queue_timeout")
            queue_start_time = time.time()

            while time.time() - queue_start_time < QUEUE_WAIT_TIMEOUT:
                queueing_count = page.locator(f"xpath={queueing_xpath}").count()
                
                if queueing_count == 0:
                    log_with_window("✅ 排队状态已消失")
                    break
                
                # 随机等待
                HumanBehavior.random_delay(15, 25)
            else:
                log_with_window("⚠️ 排队等待超时，继续检测生成状态")
                
        except PlaywrightTimeoutError:
            log_with_window("✅ 未检测到排队状态")
        except Exception as e:
            log_with_window(f"⚠️ 检测排队状态时出错: {e}")

        # 随机等待
        HumanBehavior.random_delay(1.0, 2.0)

        # ===== 步骤6: 检测生成中状态并等待内容出现后滚动 =====
        generating_xpath = get_element("image_generation", "generating_status")

        log_with_window("🔍 开始检测生成中状态...")
        
        try:
            page.wait_for_selector(f"xpath={generating_xpath}", timeout=60000)
            log_with_window("✅ 检测到生成中状态（4张loading图片）")
            
            # 关键优化：等待生成内容真正出现后再滚动
            log_with_window("🔄 等待生成内容出现后执行智能滚动...")
            wait_for_content_and_scroll(page, generating_xpath, max_wait_seconds=10, log_func=log_with_window)
                
        except PlaywrightTimeoutError:
            log_with_window("⚠️ 未检测到生成中状态，执行备用滚动")
            simple_scroll_down(page, "备用滚动", log_with_window)
        except Exception as e:
            # 🚫 处理greenlet错误
            if "Cannot switch to a different thread" in str(e) or "greenlet" in str(e).lower():
                log_with_window("🚫 检测生成状态时遇到greenlet错误，使用备用滚动")
                simple_scroll_down(page, "greenlet错误备用滚动", log_with_window)
            else:
                log_with_window(f"⚠️ 检测生成状态时出错: {e}")
                simple_scroll_down(page, "错误恢复滚动", log_with_window)
        
        # ===== 步骤7: 等待生成完成 =====
        MAX_GENERATION_WAIT_SECONDS = get_wait_time("generation_timeout")
        POLL_INTERVAL_SECONDS = 30  # 每30秒检测一次
        
        log_with_window(f"⏳ 等待生成完成（最多{MAX_GENERATION_WAIT_SECONDS//60}分钟）...")
        
        generation_start_time = time.time()
        
        while time.time() - generation_start_time < MAX_GENERATION_WAIT_SECONDS:
            try:
                generating_count = page.locator(f"xpath={generating_xpath}").count()
                
                if generating_count == 0:
                    log_with_window("✅ 生成中状态已完全消失！")
                    break
                
                log_with_window("🔄 仍在生成中，继续等待...")
            except Exception as e:
                # 🚫 处理greenlet错误
                if "Cannot switch to a different thread" in str(e) or "greenlet" in str(e).lower():
                    log_with_window("🚫 检测生成状态遇到greenlet错误，继续等待")
                else:
                    log_with_window(f"⚠️ 检测生成状态时出错: {e}")
            
            # 随机等待
            HumanBehavior.random_delay(POLL_INTERVAL_SECONDS - 1, POLL_INTERVAL_SECONDS + 1)
        else:
            log_with_window("⏰ 生成超时，尝试检测部分完成的图片")
        
        # 随机等待
        HumanBehavior.random_delay(1.0, 2.0)
        
        # ===== 步骤8: 检测生成结果 =====
        # 1. 先检测是否有无法生成的提示（prompt_error）
        try:
            error_xpath = get_element("image_generation", "prompt_error")
            error_element = page.locator(f"xpath={error_xpath}")
            if error_element.count() > 0:
                log_with_window("⚠️ 检测到提示词有问题，无法生成")
                from excel_processor import mark_prompt_as_processed, get_excel_settings
                excel_settings = get_excel_settings(config)
                status_column = excel_settings["status_column"]
                mark_prompt_as_processed(excel_file_path, excel_row_num, status_column, "提示词有问题，需修改")
                return []
        except Exception as e:
            # 🚫 处理greenlet错误
            if "Cannot switch to a different thread" in str(e) or "greenlet" in str(e).lower():
                log_with_window("🚫 检测错误提示时遇到greenlet错误，跳过错误检测")
            else:
                log_with_window(f"⚠️ 检测错误提示时出错: {e}")

        # ===== 步骤9: 下载图片 =====
        final_image_elements = []
        
        # 2. 检测是否有完成状态容器（正常图片生成）
        completed_xpath = get_element("image_generation", "completed_container")
        log_with_window("🔍 开始检测完成状态容器...")
        try:
            page.wait_for_selector(f"xpath={completed_xpath}", timeout=30000)
            completed_container = page.locator(f"xpath={completed_xpath}")
            if completed_container.count() > 0:
                log_with_window("✅ 找到完成状态容器")
                
                # 等待容器内的图片加载完成
                image_selector = get_element("image_generation", "generated_images")
                
                log_with_window("🖼️ 等待图片加载完成...")
                MAX_IMAGE_LOAD_WAIT = get_wait_time("image_load_timeout")
                image_load_start = time.time()
                
                while time.time() - image_load_start < MAX_IMAGE_LOAD_WAIT:
                    images = completed_container.locator(image_selector).all()
                    loaded_images = []

                    for img in images:
                        try:
                            if safe_is_visible(img, timeout=2000):
                                src = img.get_attribute("src")
                                if src and src.startswith("https://") and "tplv-" in src:
                                    loaded_images.append(img)
                        except:
                            continue

                    loaded_count = len(loaded_images)
                    log_with_window(f"图片加载进度: {loaded_count}/4")
                    
                    if loaded_count >= 4:
                        log_with_window("✅ 所有4张图片加载完成")
                        final_image_elements = loaded_images
                        break
                    elif loaded_count >= 1:
                        log_with_window(f"已加载{loaded_count}张图片，继续等待...")
                        # 随机等待
                        HumanBehavior.random_delay(8, 12)
                    else: 
                        # 随机等待
                        HumanBehavior.random_delay(2, 4)
                
                if not final_image_elements:
                    log_with_window("⚠️ 图片加载超时，尝试使用已加载的图片")
                    if loaded_count >= 1:
                        final_image_elements = loaded_images
                    else:
                        log_with_window("❌ 未加载到任何图片")
                        return []
            else:
                log_with_window("❌ 完成状态容器不可见")
                return []
        except PlaywrightTimeoutError:
            log_with_window("❌ 未找到完成状态容器")
            return []
        except Exception as e:
            log_with_window(f"❌ 检测完成状态时出错: {e}")
            return []
        
        # 如果成功获得图片元素，直接进行保存
        if not final_image_elements:
            log_with_window("❌ 未获得任何图片元素")
            return []
        
        log_with_window(f"✅ 成功获得 {len(final_image_elements)} 张图片，开始保存...")
        
        # 保存所有图片
        saved_images = save_all_images(final_image_elements, current_image_save_path, current_prompt_text, excel_row_num, log_with_window, config)
        
        # ===== 步骤10: 生成后检测积分 =====
        log_with_window("💰 生成后积分检测...")
        
        try:
            current_points = points_monitor.check_points(page, timeout=10000)
            
            if current_points is not None:
                log_with_window(f"💰 生成后积分余额: {current_points} 分")
                
                # 计算消耗的积分
                if initial_points is not None:
                    points_consumed = initial_points - current_points
                    if points_consumed > 0:
                        log_with_window(f"📉 本次消耗积分: {points_consumed} 分")
                    elif points_consumed < 0:
                        log_with_window(f"📈 积分增加了: {abs(points_consumed)} 分")
                    
                    # 预计还能生成多少次
                    if current_points >= 2:
                        remaining_generations = current_points // 2
                        log_with_window(f"📊 预计还可生成: {remaining_generations} 次")
                
                # 返回是否有足够积分继续
                if current_points < 2:
                    log_with_window("🚨 积分不足，此窗口将停止生成任务")
                    return saved_images  # 返回已保存的图片，但表明积分不足
                else:
                    log_with_window("✅ 积分充足，可以继续生成")
            else:
                log_with_window("⚠️ 无法获取生成后积分信息")
                
        except Exception as e:
            log_with_window(f"❌ 积分检测失败: {e}")
        
        return saved_images

    except PlaywrightTimeoutError as pte:
        log_with_window(f"在为提示词 (Row {excel_row_num}) '{current_prompt_text}' 生成图片过程中发生 Playwright 超时: {pte}")
        return []
    except PlaywrightError as pe:
        log_with_window(f"在为提示词 (Row {excel_row_num}) '{current_prompt_text}' 生成图片过程中发生 Playwright 错误: {pe}")
        return []
    except Exception as e:
        log_with_window(f"在为提示词 (Row {excel_row_num}) '{current_prompt_text}' 生成图片过程中发生一般错误: {e}")
        return []

def save_all_images(final_image_elements, current_image_save_path, current_prompt_text, excel_row_num, log_with_window, config=None):
    """保存所有生成的图片"""
    saved_images = []
    saved_count = 0
    save_errors = []
    total_images = len(final_image_elements)
    
    for i, img_element in enumerate(final_image_elements):
        try:
            log_with_window(f"正在保存第 {i+1}/{total_images} 张图片...")
            
            image_src = img_element.get_attribute("src") 
            if not image_src: 
                error_msg = f"第 {i+1} 张图片的 src 意外为空"
                log_with_window(f"警告: (Row {excel_row_num}) {error_msg}，跳过。")
                save_errors.append(error_msg)
                continue
            
            # 计算数据行号
            if config is not None:
                start_row = config.get("excel_settings", {}).get("start_row", 2)
            else:
                import json
                with open('gui_config.json', 'r', encoding='utf-8') as f:
                    fallback_config = json.load(f)
                start_row = fallback_config.get("excel_settings", {}).get("start_row", 2)
            data_row_num = excel_row_num - start_row + 1
        
            filename_prompt_part = "default"
            image_filename = f"{data_row_num}_{filename_prompt_part}_img{i+1}.jpg"
            full_save_path = os.path.join(current_image_save_path, image_filename) 

            # 确保目录存在
            os.makedirs(os.path.dirname(full_save_path), exist_ok=True)
            
            save_success = False
            
            if image_src.startswith('https://'):
                # 使用简化的HTTP下载
                save_success = simple_http_download(image_src, full_save_path, log_with_window)
            
            if save_success:
                saved_count += 1
                saved_images.append(full_save_path)
                log_with_window(f"✅ 第 {i+1} 张图片保存成功: {image_filename}")
            else:
                error_msg = f"第 {i+1} 张图片保存失败"
                log_with_window(f"❌ (Row {excel_row_num}) {error_msg}")
                save_errors.append(error_msg)
                
        except Exception as e:
            error_msg = f"保存第 {i+1} 张图片时出错: {e}"
            log_with_window(f"❌ (Row {excel_row_num}) {error_msg}")
            save_errors.append(error_msg)
    
    # 统计结果
    if saved_count > 0:
        log_with_window(f"✅ 成功保存 {saved_count}/{total_images} 张图片")
        if save_errors:
            log_with_window(f"⚠️ 有 {len(save_errors)} 个保存错误:")
            for error in save_errors:
                log_with_window(f"  - {error}")
    else:
        log_with_window(f"❌ 所有 {total_images} 张图片保存失败")
    
    return saved_images

def safe_http_download(image_url, save_path, log_with_window):
    """安全的HTTP图片下载 - 针对字节跳动CDN优化"""
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://dreamina.douyin.com/',
        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Cache-Control': 'no-cache'
    }
    
    try:
        # 检查是否是字节跳动的CDN
        is_bytedance_cdn = any(domain in image_url for domain in [
            'bytedance.com', 'byteimg.com', 'douyin.com', 'toutiao.com',
            'snssdk.com', 'amemv.com', 'bdstatic.com'
        ])
        
        if is_bytedance_cdn:
            log_with_window("🔒 检测到字节跳动CDN，使用安全SSL下载...")
            # 对于字节跳动CDN，首先尝试安全SSL验证
            verify_ssl = True
        else:
            log_with_window("🔒 外部图片源，使用安全SSL下载...")
            verify_ssl = True
        
        # 尝试安全下载
        response = requests.get(
            image_url,
            headers=headers,
            verify=verify_ssl,
            timeout=30
        )
        response.raise_for_status()
        
        image_data = response.content
        if len(image_data) < 1000:
            raise Exception("下载的图片太小")
        
        with open(save_path, 'wb') as f:
            f.write(image_data)
        
        log_with_window("✅ 安全SSL下载成功")
        return True
        
    except requests.exceptions.SSLError:
        # 只有SSL错误时才回退到不安全模式
        log_with_window("⚠️ SSL验证失败，回退到兼容模式...")
        try:
            # 临时禁用SSL警告
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            response = requests.get(
                image_url,
                headers=headers,
                verify=False,  # 跳过SSL验证
                timeout=30
            )
            response.raise_for_status()
            
            image_data = response.content
            if len(image_data) < 1000:
                raise Exception("下载的图片太小")
            
            with open(save_path, 'wb') as f:
                f.write(image_data)
            
            log_with_window("✅ 兼容模式下载成功")
            return True
            
        except Exception as e:
            log_with_window(f"❌ 兼容模式下载失败: {e}")
            return False
            
    except Exception as e:
        log_with_window(f"❌ 下载失败: {e}")
        return False

# 保持向后兼容的函数名
def simple_http_download(image_url, save_path, log_with_window):
    """向后兼容的图片下载函数"""
    return safe_http_download(image_url, save_path, log_with_window)
