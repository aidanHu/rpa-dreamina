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

# 尝试导入PIL用于图片格式转换
try:
    from PIL import Image
    PIL_AVAILABLE = True
    print("[DreaminaOperator] PIL 可用，将支持图片格式转换")
except ImportError:
    PIL_AVAILABLE = False
    print("[DreaminaOperator] PIL 不可用，将直接保存原始图片格式")

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

def navigate_and_setup_dreamina_page(context, target_url):
    """
    导航到Dreamina页面并进行基本设置
    """
    try:
        # 获取所有页面
        pages = context.pages
        
        if not pages:
            print("[DreaminaOperator] 没有找到任何页面，创建新页面")
            page = context.new_page()
        else:
            page = pages[0]
            print(f"[DreaminaOperator] 使用现有页面: {page.url}")
        
        # 导航到目标URL
        if page.url != target_url:
            print(f"[DreaminaOperator] 导航到: {target_url}")
            try:
                # 先尝试等待页面加载完成
                page.goto(target_url, wait_until="networkidle", timeout=60000)
            except Exception as e:
                print(f"[DreaminaOperator] ⚠️ 等待网络空闲超时，尝试使用domcontentloaded: {e}")
                page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        
        # 等待页面完全加载
        print("[DreaminaOperator] ⏳ 等待页面完全加载...")
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception as e:
            print(f"[DreaminaOperator] ⚠️ 等待网络空闲超时: {e}")
        
        # 确保页面稳定
        time.sleep(5)
        
        # 检查页面是否正常加载
        try:
            page_title = page.title()
            print(f"[DreaminaOperator] 📄 页面标题: {page_title}")
            if not page_title or "Dreamina" not in page_title:
                print("[DreaminaOperator] ⚠️ 页面可能未正确加载，尝试刷新...")
                page.reload(wait_until="networkidle", timeout=60000)
                time.sleep(5)
        except Exception as e:
            print(f"[DreaminaOperator] ⚠️ 检查页面标题时出错: {e}")
        
        return page
        
    except Exception as e:
        print(f"[DreaminaOperator] ❌ 导航到页面时出错: {e}")
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
        print(f"[DreaminaOperator] 页面连接检查失败: {e}")
        return False

def simple_scroll_down(page, description="简单向下滚动"):
    """
    简单的向下滚动功能，鼠标移动到网页右边进行滚动
    """
    try:
        print(f"[DreaminaOperator] 🖱️ 开始{description}...")
        
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
        
        print(f"[DreaminaOperator] 📍 移动鼠标到页面右边 ({right_x}, {center_y})")
        page.mouse.move(right_x, center_y)
        time.sleep(0.5)

        # 使用鼠标滚轮向下滚动几次
        print("[DreaminaOperator] 🔽 在页面右边向下滚动...")
        for i in range(3):
            page.mouse.wheel(0, 800)  # 向下滚动800像素
            time.sleep(1)
            print(f"[DreaminaOperator] 滚动第 {i+1}/3 次")
        
        print("[DreaminaOperator] ✅ 简单滚动完成")
        return True
        
    except Exception as e:
        print(f"[DreaminaOperator] ❌ 简单滚动失败: {e}")
        return False

def wait_for_content_and_scroll(page, content_selector, max_wait_seconds=10):
    """
    等待内容出现后再简单滚动
    """
    try:
        print(f"[DreaminaOperator] ⏳ 等待内容出现 (最多{max_wait_seconds}秒)...")
        
        start_time = time.time()
        content_appeared = False
        
        while time.time() - start_time < max_wait_seconds:
            # 检查内容是否出现
            content_count = page.locator(f"xpath={content_selector}").count()
            
            if content_count > 0:
                print("[DreaminaOperator] ✅ 检测到内容出现，准备滚动")
                content_appeared = True
                break
            
            time.sleep(1)
        
        if content_appeared:
            # 等待一点时间让内容稳定
            time.sleep(2)
            
            # 执行简单滚动
            scroll_success = simple_scroll_down(page, "等待内容后滚动")
            return scroll_success
        else:
            print("[DreaminaOperator] ⚠️ 内容未出现，执行备用滚动")
            return simple_scroll_down(page, "备用滚动")
            
    except Exception as e:
        print(f"[DreaminaOperator] 等待内容并滚动时出错: {e}")
        return False

def select_aspect_ratio(page, aspect_ratio="9:16"):
    """
    选择图片尺寸比例
    """
    try:
        print(f"[DreaminaOperator] 🖼️ 选择图片尺寸: {aspect_ratio}")
        
        # 从元素配置获取对应的选择器
        aspect_ratio_selector = get_element("aspect_ratio_selection", aspect_ratio)
        
        if not aspect_ratio_selector:
            print(f"[DreaminaOperator] ⚠️ 未找到尺寸 {aspect_ratio} 的选择器，跳过尺寸选择")
            return False
        
        # 查找并点击对应的尺寸选项
        aspect_ratio_element = page.locator(f"xpath={aspect_ratio_selector}")
        
        # 等待元素可见
        aspect_ratio_element.wait_for(state="visible", timeout=10000)
        
        # 点击尺寸选项
        aspect_ratio_element.click(timeout=10000)
        
        print(f"[DreaminaOperator] ✅ 成功选择图片尺寸: {aspect_ratio}")
        
        # 等待选择生效
        time.sleep(2)
        
        return True
        
    except Exception as e:
        print(f"[DreaminaOperator] ❌ 选择图片尺寸失败: {e}")
        return False

def generate_image_on_page(page, prompt_info):
    """
    输入提示词，选择尺寸，点击生成，等待图片加载完成，并保存所有生成的图片。
    """
    final_image_elements = []

    current_prompt_text = prompt_info['prompt']
    source_folder_name = prompt_info['source_excel_name']
    excel_row_num = prompt_info['row_number']

    # 检查页面连接
    if not check_page_connection(page):
        print(f"[DreaminaOperator] 页面连接已断开，无法处理提示词: {current_prompt_text}")
        return final_image_elements

    # 使用新的保存路径（Excel所在的子文件夹）
    current_image_save_path = prompt_info.get('image_save_path', IMAGE_SAVE_PATH)
    
    # 确保保存目录存在
    if not os.path.exists(current_image_save_path):
        try:
            os.makedirs(current_image_save_path)
            print(f"[DreaminaOperator] 已创建保存目录: {current_image_save_path}")
        except OSError as e:
            print(f"[DreaminaOperator] 错误：创建保存目录 '{current_image_save_path}' 失败: {e}。将尝试保存到默认图片文件夹。")
            current_image_save_path = IMAGE_SAVE_PATH

    try:
        print(f"[DreaminaOperator] 处理提示词: '{current_prompt_text}' (源: '{source_folder_name}')")
        print(f"[DreaminaOperator] 图片保存路径: {current_image_save_path}")
        
        # 生成前检测积分余额
        print(f"\n[DreaminaOperator] 💰 生成前积分检测...")
        try:
            points_selector = get_element("points_monitoring", "primary_selector")
            points_monitor = PointsMonitor(custom_points_selector=points_selector)
            initial_points = points_monitor.check_points(page, timeout=10000)
            
            if initial_points is not None:
                print(f"[DreaminaOperator] 💰 生成前积分余额: {initial_points} 分")
                
                if initial_points < 2:
                    print(f"[DreaminaOperator] 🚨 积分不足，无法进行生成！当前积分: {initial_points}")
                    return final_image_elements
                elif initial_points < 6:
                    print(f"[DreaminaOperator] ⚠️ 积分余额较低: {initial_points} 分")
                else:
                    print(f"[DreaminaOperator] ✅ 积分充足，开始生成")
            else:
                print(f"[DreaminaOperator] ⚠️ 无法获取积分信息，继续尝试生成")
                initial_points = None
                
        except Exception as e:
            print(f"[DreaminaOperator] ❌ 生成前积分检测失败: {e}")
            initial_points = None
        
        # 输入提示词
        prompt_input_xpath = get_element("image_generation", "prompt_input")
        prompt_input = page.locator(prompt_input_xpath)
        prompt_input.wait_for(state="visible", timeout=30000) 
        prompt_input.click() 
        prompt_input.fill("") 
        prompt_input.fill(current_prompt_text)
        print("[DreaminaOperator] 提示词已输入.")
        
        # 智能延时：模拟人类思考时间
        smart_delay("输入提示词")
        
        # 选择图片尺寸
        try:
            import json
            with open('user_config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            default_aspect_ratio = config.get("image_settings", {}).get("default_aspect_ratio", "9:16")
            
            select_aspect_ratio(page, default_aspect_ratio)
            
        except Exception as e:
            print(f"[DreaminaOperator] ❌ 选择图片尺寸失败: {e}，继续生成流程")

        # 生成前准备
        smart_delay("点击生成按钮前准备")

        # 点击生成按钮（简化版）
        print("[DreaminaOperator] 等待 2 秒后点击生成按钮...")
        time.sleep(2)
        generate_button_selector = get_element("image_generation", "generate_button")
        generate_button = page.locator(generate_button_selector)
        generate_button.wait_for(state="visible", timeout=30000)
        generate_button.click(timeout=30000)
        print("[DreaminaOperator] '生成' 按钮已点击.")
        print("[DreaminaOperator] 点击生成后，等待2秒以便结果块初步加载...")
        time.sleep(2)

        # === 检测排队状态并等待消失 ===
        queueing_xpath = get_element("image_generation", "queueing_status")
        
        print("[DreaminaOperator] 🔍 检测是否有排队状态...")
        
        try:
            page.wait_for_selector(f"xpath={queueing_xpath}", timeout=10000)
            print("[DreaminaOperator] ⏳ 检测到排队状态，开始等待...")
            
            QUEUE_WAIT_TIMEOUT = get_wait_time("queue_timeout")
            queue_start_time = time.time()

            while time.time() - queue_start_time < QUEUE_WAIT_TIMEOUT:
                queueing_count = page.locator(f"xpath={queueing_xpath}").count()
                
                if queueing_count == 0:
                    print("[DreaminaOperator] ✅ 排队状态已消失")
                    break
                
                time.sleep(3)
            else:
                print(f"[DreaminaOperator] ⚠️ 排队等待超时，继续检测生成状态")
                
        except PlaywrightTimeoutError:
            print("[DreaminaOperator] ✅ 未检测到排队状态")
        except Exception as e:
            print(f"[DreaminaOperator] ⚠️ 检测排队状态时出错: {e}")

        smart_delay("排队检测完成")

        # === 检测生成中状态并等待内容出现后滚动 ===
        generating_xpath = get_element("image_generation", "generating_status")

        print("[DreaminaOperator] 🔍 开始检测生成中状态...")
        
        try:
            page.wait_for_selector(f"xpath={generating_xpath}", timeout=60000)
            print("[DreaminaOperator] ✅ 检测到生成中状态（4张loading图片）")
            
            # 关键优化：等待生成内容真正出现后再滚动
            print("[DreaminaOperator] 🔄 等待生成内容出现后执行智能滚动...")
            wait_for_content_and_scroll(page, generating_xpath, max_wait_seconds=10)
                
        except PlaywrightTimeoutError:
            print("[DreaminaOperator] ⚠️ 未检测到生成中状态，执行备用滚动")
            simple_scroll_down(page, "备用滚动")
        
        # 等待生成中状态完全消失
        MAX_GENERATION_WAIT_SECONDS = get_wait_time("generation_timeout")
        POLL_INTERVAL_SECONDS = get_wait_time("poll_interval")
        
        print(f"[DreaminaOperator] ⏳ 等待生成完成（最多{MAX_GENERATION_WAIT_SECONDS//60}分钟）...")
        
        generation_start_time = time.time()
        
        while time.time() - generation_start_time < MAX_GENERATION_WAIT_SECONDS:
            generating_count = page.locator(f"xpath={generating_xpath}").count()
            
            if generating_count == 0:
                print("[DreaminaOperator] ✅ 生成中状态已完全消失！")
                break
            
            print(f"[DreaminaOperator] 🔄 仍在生成中，继续等待...")
            time.sleep(POLL_INTERVAL_SECONDS)
        else:
            print(f"[DreaminaOperator] ⏰ 生成超时，尝试检测部分完成的图片")
        
        smart_delay("生成状态检测完成")
        
        # === 检测完成状态容器 ===
        completed_xpath = get_element("image_generation", "completed_container")
        
        print("[DreaminaOperator] 🔍 开始检测完成状态容器...")
        
        # 最终确保页面位置正确
        try:
            print("[DreaminaOperator] 🎯 最终定位：确保页面滚动到结果区域...")
            simple_scroll_down(page, "最终定位滚动")
        except Exception as scroll_error:
            print(f"[DreaminaOperator] 最终滚动时出现问题: {scroll_error}")
        
        try:
            page.wait_for_selector(f"xpath={completed_xpath}", timeout=30000)
            completed_container = page.locator(f"xpath={completed_xpath}")
            
            if completed_container.count() > 0:
                print("[DreaminaOperator] ✅ 找到完成状态容器")
                
                # 等待容器内的图片加载完成
                image_selector = get_element("image_generation", "generated_images")
                
                print("[DreaminaOperator] 🖼️ 等待图片加载完成...")
                MAX_IMAGE_LOAD_WAIT = get_wait_time("image_load_timeout")
                image_load_start = time.time()
                final_image_elements = []
                
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
                    print(f"[DreaminaOperator] 图片加载进度: {loaded_count}/4")
                    
                    if loaded_count >= 4:
                        print("[DreaminaOperator] ✅ 所有4张图片加载完成")
                        final_image_elements = loaded_images
                        break
                    elif loaded_count >= 1:
                        print(f"[DreaminaOperator] 已加载{loaded_count}张图片，继续等待...")
                        time.sleep(5)
                    else: 
                        time.sleep(3)
                
                if not final_image_elements:
                    print("[DreaminaOperator] ⚠️ 图片加载超时，尝试使用已加载的图片")
                    if loaded_count >= 1:
                        final_image_elements = loaded_images
                    else:
                        print("[DreaminaOperator] ❌ 未加载到任何图片")
                        return []
            else:
                print("[DreaminaOperator] ❌ 完成状态容器不可见")
                return []
        except PlaywrightTimeoutError:
            print("[DreaminaOperator] ❌ 未找到完成状态容器")
            return []
        except Exception as e:
            print(f"[DreaminaOperator] ❌ 检测完成状态时出错: {e}")
            return []
        
        # 如果成功获得图片元素，直接进行保存
        if not final_image_elements:
            print("[DreaminaOperator] ❌ 未获得任何图片元素")
            return []
        
        print(f"[DreaminaOperator] ✅ 成功获得 {len(final_image_elements)} 张图片，开始保存...")
        
        smart_delay("准备保存图片")
        
        # 直接进入保存流程
        saved_count = 0
        save_errors = []
        total_images = len(final_image_elements)
        
        for i, img_element in enumerate(final_image_elements):
            try:
                print(f"[DreaminaOperator] 正在保存第 {i+1}/{total_images} 张图片...")
                
                image_src = img_element.get_attribute("src") 
                if not image_src: 
                    error_msg = f"第 {i+1} 张图片的 src 意外为空"
                    print(f"[DreaminaOperator] 警告: (Row {excel_row_num}) {error_msg}，跳过。")
                    save_errors.append(error_msg)
                    continue
                
                # 计算数据行号
                import json
                with open('user_config.json', 'r', encoding='utf-8') as f:
                    config = json.load(f)
                start_row = config.get("excel_settings", {}).get("start_row", 2)
                data_row_num = excel_row_num - start_row + 1
            
                filename_prompt_part = "default"
                image_filename = f"{data_row_num}_{filename_prompt_part}_img{i+1}.jpg"
                full_save_path = os.path.join(current_image_save_path, image_filename) 

                # 确保目录存在
                os.makedirs(os.path.dirname(full_save_path), exist_ok=True)
                
                save_success = False

                if image_src.startswith('data:image'):
                    print(f"[DreaminaOperator] 检测到 base64 图片数据，正在解码并转换为JPG...")
                    try:
                        header, encoded = image_src.split(',', 1)
                        image_data = base64.b64decode(encoded)
                        
                        if PIL_AVAILABLE:
                            img = Image.open(io.BytesIO(image_data))
                            
                            if img.mode in ('RGBA', 'LA'):
                                background = Image.new('RGB', img.size, (255, 255, 255))
                                if img.mode == 'RGBA':
                                    background.paste(img, mask=img.split()[-1])
                                else:
                                    background.paste(img)
                                img = background
                            elif img.mode != 'RGB':
                                img = img.convert('RGB')
                            
                            img.save(full_save_path, 'JPEG', quality=95, optimize=True)
                        else:
                            with open(full_save_path, 'wb') as f:
                                f.write(image_data)
                        
                        save_success = True
                        print(f"[DreaminaOperator] ✅ 第 {i+1} 张图片保存成功: {image_filename}")
                    except Exception as e:
                        error_msg = f"解码/保存 base64 图片为JPG失败: {e}"
                        print(f"[DreaminaOperator] ❌ (Row {excel_row_num}) {error_msg}")
                        save_errors.append(error_msg)
                        
                elif image_src.startswith('http'):
                    print(f"[DreaminaOperator] 检测到图片 URL，正在下载并转换为JPG...")
                    try:
                        img_response = requests.get(image_src, timeout=60)
                        img_response.raise_for_status()
                        
                        if PIL_AVAILABLE:
                            img = Image.open(io.BytesIO(img_response.content))
                            
                            if img.mode in ('RGBA', 'LA'):
                                background = Image.new('RGB', img.size, (255, 255, 255))
                                if img.mode == 'RGBA':
                                    background.paste(img, mask=img.split()[-1])
                                else:
                                    background.paste(img)
                                img = background
                            elif img.mode != 'RGB':
                                img = img.convert('RGB')
                            
                            img.save(full_save_path, 'JPEG', quality=95, optimize=True)
                        else:
                            with open(full_save_path, 'wb') as f:
                                f.write(img_response.content)
                        
                        save_success = True
                        print(f"[DreaminaOperator] ✅ 第 {i+1} 张图片下载并转换为JPG成功: {image_filename}")
                    except requests.RequestException as e:
                        error_msg = f"下载图片 URL 失败: {e}"
                        print(f"[DreaminaOperator] ❌ (Row {excel_row_num}) {error_msg}")
                        save_errors.append(error_msg)
                elif image_src.startswith('blob:'):
                    print(f"[DreaminaOperator] 检测到 blob URL，尝试截图并转换为JPG...")
                    try:
                        if PIL_AVAILABLE:
                            temp_png_path = full_save_path.replace('.jpg', '_temp.png')
                            img_element.screenshot(path=temp_png_path)
                            
                            img = Image.open(temp_png_path)
                            
                            if img.mode in ('RGBA', 'LA'):
                                background = Image.new('RGB', img.size, (255, 255, 255))
                                if img.mode == 'RGBA':
                                    background.paste(img, mask=img.split()[-1])
                                else:
                                    background.paste(img)
                                img = background
                            elif img.mode != 'RGB':
                                img = img.convert('RGB')
                            
                            img.save(full_save_path, 'JPEG', quality=95, optimize=True)
                            
                            try:
                                os.remove(temp_png_path)
                            except:
                                pass
                        else:
                            img_element.screenshot(path=full_save_path)
                        
                        save_success = True
                        print(f"[DreaminaOperator] ✅ 第 {i+1} 张图片截图并转换为JPG成功: {image_filename}")
                    except Exception as e_screenshot:
                        error_msg = f"blob 图片元素截图转JPG失败: {e_screenshot}"
                        print(f"[DreaminaOperator] ❌ (Row {excel_row_num}) {error_msg}")
                        save_errors.append(error_msg)
                else:
                    error_msg = f"未识别的图片源格式: {image_src[:60]}..."
                    print(f"[DreaminaOperator] ❌ (Row {excel_row_num}) {error_msg}")
                    save_errors.append(error_msg)
                    
                if save_success:
                    saved_count += 1
                    # 验证文件确实保存成功
                    if os.path.exists(full_save_path) and os.path.getsize(full_save_path) > 0:
                        print(f"[DreaminaOperator] 📁 文件验证成功: {full_save_path} ({os.path.getsize(full_save_path)} bytes)")
                    else:
                        print(f"[DreaminaOperator] ⚠️ 文件验证失败: {full_save_path}")
                        saved_count -= 1
                        save_errors.append(f"文件验证失败: {image_filename}")
                
                # 在保存图片之间添加智能延时（最后一张图片除外）
                if i < total_images - 1:
                    smart_delay("图片保存间隔")
                        
            except Exception as e:
                error_msg = f"保存第 {i+1} 张图片时发生意外错误: {e}"
                print(f"[DreaminaOperator] ❌ (Row {excel_row_num}) {error_msg}")
                save_errors.append(error_msg)
                continue
        
        # 保存完成后的详细报告
        print(f"\n[DreaminaOperator] 📊 图片保存完成报告 (Row {excel_row_num}):")
        print(f"  总计图片数: {total_images}")
        print(f"  成功保存: {saved_count}")
        print(f"  保存失败: {len(save_errors)}")
        print(f"  成功率: {saved_count/total_images*100:.1f}%" if total_images > 0 else "  成功率: 0%")
        
        if save_errors:
            print(f"  错误详情:")
            for i, error in enumerate(save_errors[:3], 1):
                print(f"    {i}. {error}")
            if len(save_errors) > 3:
                print(f"    ... 还有 {len(save_errors) - 3} 个错误")
        
        # 判断成功标准
        min_success_threshold = max(1, min(2, total_images // 2))
        is_success = saved_count >= min_success_threshold
        
        if is_success:
            print(f"[DreaminaOperator] ✅ 图片保存任务被认为成功 (保存了 {saved_count}/{total_images} 张)")
        else:
            print(f"[DreaminaOperator] ❌ 图片保存任务失败 (仅保存了 {saved_count}/{total_images} 张)")
            
        # 检测并显示当前积分余额
        print(f"\n[DreaminaOperator] 💰 生成后积分检测...")
        try:
            points_selector = get_element("points_monitoring", "primary_selector")
            points_monitor = PointsMonitor(custom_points_selector=points_selector)
            current_points = points_monitor.check_points(page, timeout=10000)
            
            if current_points is not None:
                print(f"[DreaminaOperator] 💰 生成后积分余额: {current_points} 分")
                
                if initial_points is not None:
                    points_consumed = initial_points - current_points
                    if points_consumed > 0:
                        print(f"[DreaminaOperator] 📉 本次消耗积分: {points_consumed} 分")
                    elif points_consumed < 0:
                        print(f"[DreaminaOperator] 📈 积分增加了: {abs(points_consumed)} 分")
                    else:
                        print(f"[DreaminaOperator] ➡️ 积分无变化")
                
                remaining_generations = points_monitor.estimate_remaining_generations(current_points, 2)
                print(f"[DreaminaOperator] 📊 预计还可生成: {remaining_generations} 次")
                
                if current_points < 2:
                    print(f"[DreaminaOperator] 🚨 积分不足，无法进行下次生成！")
                elif current_points < 6:
                    print(f"[DreaminaOperator] ⚠️ 积分余额较低，建议及时充值！")
                else:
                    print(f"[DreaminaOperator] ✅ 积分充足，可继续生成")
            else:
                print(f"[DreaminaOperator] ⚠️ 无法获取积分信息，请检查页面状态")
                
        except Exception as e:
            print(f"[DreaminaOperator] ❌ 积分检测失败: {e}")
        
        smart_delay("任务完成")
        
        # 返回保存成功的图片信息列表
        if is_success:
            saved_images = []
            import json
            with open('user_config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            start_row = config.get("excel_settings", {}).get("start_row", 2)
            data_row_num = excel_row_num - start_row + 1
            
            for i in range(saved_count):
                filename_prompt_part = "default"
                image_filename = f"{data_row_num}_{filename_prompt_part}_img{i+1}.jpg"
                full_save_path = os.path.join(current_image_save_path, image_filename)
                if os.path.exists(full_save_path):
                    saved_images.append({
                        'filename': image_filename,
                        'path': full_save_path,
                        'size': os.path.getsize(full_save_path)
                    })
            return saved_images
        else:
            return []
            
    except PlaywrightTimeoutError as pte:
        print(f"[DreaminaOperator] 在为提示词 (Row {excel_row_num}) '{current_prompt_text}' 生成图片过程中发生 Playwright 超时: {pte}")
        return []
    except PlaywrightError as pe:
        print(f"[DreaminaOperator] 在为提示词 (Row {excel_row_num}) '{current_prompt_text}' 生成图片过程中发生 Playwright 错误: {pe}")
        return []
    except Exception as e:
        print(f"[DreaminaOperator] 在为提示词 (Row {excel_row_num}) '{current_prompt_text}' 生成图片过程中发生一般错误: {e}")
        return [] 