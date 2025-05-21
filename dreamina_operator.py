import time
import os
import re # For sanitizing filenames
import requests # For downloading image from URL
import base64 # For decoding base64 image data
from urllib.parse import urlparse
# from playwright.sync_api import Playwright, sync_playwright, TimeoutError as PlaywrightTimeoutError # Old import
from playwright.sync_api import Playwright, sync_playwright
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
import json # 导入json模块
# import argparse # argparse 不再需要，因为脚本将通过函数调用接收参数

# --- 全局选择器配置 --- #
SELECTORS_CONFIG_PATH = "selectors_config.json"
SELECTORS = None

def load_selectors_config():
    global SELECTORS
    try:
        with open(SELECTORS_CONFIG_PATH, 'r', encoding='utf-8') as f:
            SELECTORS = json.load(f)
        if not SELECTORS or 'dreamina_page' not in SELECTORS:
            print(f"[DreaminaOperator] 错误: 选择器配置文件 '{SELECTORS_CONFIG_PATH}' 格式不正确或缺少 'dreamina_page' 部分。将使用内部默认值。")
            SELECTORS = None # 强制使用默认值
        else:
            print(f"[DreaminaOperator] 已成功加载选择器配置: {SELECTORS_CONFIG_PATH}")
    except FileNotFoundError:
        print(f"[DreaminaOperator] 警告: 选择器配置文件 '{SELECTORS_CONFIG_PATH}' 未找到。将使用内部默认值。")
        SELECTORS = None
    except json.JSONDecodeError:
        print(f"[DreaminaOperator] 错误: 解析选择器配置文件 '{SELECTORS_CONFIG_PATH}' 失败。将使用内部默认值。")
        SELECTORS = None
    except Exception as e:
        print(f"[DreaminaOperator] 加载选择器配置时发生未知错误: {e}。将使用内部默认值。")
        SELECTORS = None

# 定义默认选择器，以防配置文件加载失败或缺少键
DEFAULT_SELECTORS = {
    "dreamina_page": {
        "file_size_button_xpath": "//*[@id=\\\"lv-tabs-0-panel-0\\\"]/div/div/div/div/div[1]/div[5]/div[2]/div/div[1]/div[2]/div[8]/div[1]/div",
        "prompt_input_xpath": "//*[@id=\\\"promptRickInput\\\"]/div",
        "generate_button_css_selector": "div.generateContent-RiLRrb",
        "generated_image_css_selector": "div.imageContainer-JMoE9v img.image-G36sd1",
        "general_record_block_xpath": "//div[starts-with(@id, 'item_') and contains(@id, '_record-') and not(contains(@id, '_record-mock_history_record_id__')) and .//div[contains(@class, 'result-uEEwco')]]",
        "server_busy_error_xpath": ".//div[@class='warningText-BwoChT' and contains(text(), 'The server is busy at the moment. Try again later.')]",
        "community_guidelines_violation_xpath": ".//div[@class='text-nIol2d' and contains(text(), 'The prompt may contain content that violates our Community Guidelines. Change it and try again.')]",
        "credit_text_xpath": "//div[contains(@class, 'creditWrapper-iTl7Wc')]//span[@class='creditText-OocMai']"
    }
}

load_selectors_config() # 程序启动时加载一次配置

def get_selector(key_path):
    """ Helper function to get a selector string using a dot-separated key path from the loaded SELECTORS or DEFAULT_SELECTORS. """
    global SELECTORS, DEFAULT_SELECTORS
    keys = key_path.split('.')
    current_level_selectors = SELECTORS
    if current_level_selectors:
        try:
            for key in keys:
                current_level_selectors = current_level_selectors[key]
            if isinstance(current_level_selectors, str):
                # print(f"[SelectorDebug] Using selector from config for '{key_path}': {current_level_selectors}")
                return current_level_selectors
        except KeyError:
            # print(f"[SelectorDebug] Key '{key_path}' not found in loaded config. Falling back to default.")
            pass # Fall through to default if key not found
        except TypeError: # If a level is not a dict
            # print(f"[SelectorDebug] Config structure error for '{key_path}'. Falling back to default.")
            pass 
    
    # Fallback to default selectors
    current_level_default = DEFAULT_SELECTORS
    try:
        for key in keys:
            current_level_default = current_level_default[key]
        if isinstance(current_level_default, str):
            # print(f"[SelectorDebug] Using DEFAULT selector for '{key_path}': {current_level_default}")
            return current_level_default
    except KeyError:
        print(f"[DreaminaOperator] 严重错误: 选择器键 '{key_path}' 在默认配置中也未找到！")
    except Exception as e_def:
        print(f"[DreaminaOperator] 严重错误: 获取默认选择器 '{key_path}' 时出错: {e_def}")
    return None # Should not happen if defaults are correct

# --- Configuration for generate_image_on_page ---
IMAGE_SAVE_PATH = "generated_images" # Folder to save images
# Ensure this folder exists, create if not
if not os.path.exists(IMAGE_SAVE_PATH):
    os.makedirs(IMAGE_SAVE_PATH)
    print(f"[DreaminaOperator] Created folder for generated images: {IMAGE_SAVE_PATH}")

MAX_GENERATION_WAIT_SECONDS = 300 # 增加到5分钟
POLL_INTERVAL_SECONDS = 3
MIN_EXPECTED_IMAGES = 4 # 根据用户反馈，一次通常生成4张图片
OLD_SRC_SOAK_TIME_SECONDS = 15 # 新增：当结果块使用旧SRC时，需要保持稳定的"浸泡"观察时间

MIN_CREDIT_THRESHOLD = 10 # 低于此积分值则暂停生成

# Helper function to sanitize filename from prompt
def sanitize_filename(prompt, max_length=100):
    """Sanitizes a prompt to be a valid filename, supporting Chinese characters."""
    if not prompt or not prompt.strip(): # 检查原始prompt是否为空或只有空格
        return "untitled_image"
    
    sanitized = prompt.strip() # 先去除首尾空格
    # 步骤1: 将空格和常见非法文件名字符统一替换为下划线
    sanitized = re.sub(r'[\s/\\:*?"<>|]+', '_', sanitized) 
    # 步骤2: 移除非字母数字、下划线、连字符、中文字符之外的所有字符
    # 这个正则表达式允许中文 (\u4e00-\u9fa5)
    sanitized = re.sub(r'[^a-zA-Z0-9_\-\u4e00-\u9fa5]+', '', sanitized)
    # 步骤3: 将连续的下划线替换为单个下划线
    sanitized = re.sub(r'_+', '_', sanitized) 
    # 步骤4: 移除可能产生的前导或尾随下划线
    sanitized = sanitized.strip('_')

    # 步骤5: 如果经过所有清理，字符串变为空，则返回默认名
    if not sanitized:
        return "prompt_cleaned_empty" # 或者 "untitled_image_placeholder"
        
    return sanitized[:max_length]

def navigate_and_setup_dreamina_page(context, target_url):
    """
    Ensures the Dreamina page is open in the given browser context, performs initial setup (like clicking size button),
    closes other tabs, and returns the Playwright page object for Dreamina.
    Args:
        context: Playwright browser context.
        target_url (str): The URL for the Dreamina page.
    Returns:
        Page object for Dreamina, or None if setup fails.
    """
    print(f"[DreaminaOperator] Setting up Dreamina page: {target_url}")
    dreamina_page = None
    page_opened_successfully = False

    # Check if Dreamina page is already open
    for page_iter in context.pages:
        if target_url in page_iter.url: # Simple check
            print(f"[DreaminaOperator] Found existing Dreamina page: {page_iter.url}")
            dreamina_page = page_iter
            dreamina_page.bring_to_front()
            page_opened_successfully = True # Assume already set up if page exists
            break
    
    if not dreamina_page:
        print(f"[DreaminaOperator] Dreamina page not found. Opening new page and navigating to: {target_url}")
        dreamina_page = context.new_page()
        try:
            dreamina_page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            print(f"[DreaminaOperator] Successfully navigated to: {dreamina_page.url}")
            dreamina_page.bring_to_front()
            page_opened_successfully = True

            # Click file size button ONLY on new page load/setup
            # file_size_button_xpath = "//*[@id=\"lv-tabs-0-panel-0\"]/div/div/div/div/div[1]/div[5]/div[2]/div/div[1]/div[2]/div[8]/div[1]/div"
            # print(f"[DreaminaOperator] Attempting to click file size button (only on new page setup): {file_size_button_xpath}")
            # file_size_button = dreamina_page.locator(file_size_button_xpath)
            # file_size_button.wait_for(state="visible", timeout=30000) 
            # file_size_button.click()
            # print("[DreaminaOperator] File size button clicked.")
            # time.sleep(1) 
        except PlaywrightTimeoutError as pte:
            print(f"[DreaminaOperator] Timeout navigating to Dreamina page: {pte}")
            if dreamina_page and not dreamina_page.is_closed(): dreamina_page.close()
            return None
        except PlaywrightError as pe:
            print(f"[DreaminaOperator] Playwright error during navigation: {pe}")
            if dreamina_page and not dreamina_page.is_closed(): dreamina_page.close()
            return None
        except Exception as e:
            print(f"[DreaminaOperator] Error navigating to Dreamina page: {e}")
            if dreamina_page and not dreamina_page.is_closed(): dreamina_page.close()
            return None

    if not (page_opened_successfully and dreamina_page and not dreamina_page.is_closed()):
        print("[DreaminaOperator] Failed to open or maintain Dreamina page for setup.")
        return None

    # Always attempt to click the file size button once the page is confirmed to be open and valid.
    try:
        file_size_button_xpath = get_selector("dreamina_page.file_size_button_xpath")
        if file_size_button_xpath:
            print(f"[DreaminaOperator] Attempting to click file size button: {file_size_button_xpath}")
            file_size_button = dreamina_page.locator(file_size_button_xpath)
            file_size_button.wait_for(state="visible", timeout=10000) 
            file_size_button.click(timeout=5000) 
            print("[DreaminaOperator] File size button click attempted.")
            time.sleep(1) 
    except PlaywrightTimeoutError:
        print("[DreaminaOperator] Timeout waiting for or clicking file size button (this might be okay if already configured or button not always present).")
    except Exception as e_size_button:
        print(f"[DreaminaOperator] Error clicking file size button: {e_size_button} (this might be okay).")

    # Close other tabs
    print("[DreaminaOperator] Closing other tabs...")
    pages_snapshot = list(context.pages)
    closed_count = 0
    for p_iter in pages_snapshot:
        if p_iter.is_closed() or p_iter == dreamina_page:
            continue
        print(f"[DreaminaOperator] Closing tab: {p_iter.url}")
        try:
            p_iter.close()
            closed_count +=1
        except Exception as e:
            print(f"[DreaminaOperator] Error closing tab {p_iter.url}: {e}")
    print(f"[DreaminaOperator] Closed {closed_count} other tabs.")
    
    if dreamina_page and not dreamina_page.is_closed():
        dreamina_page.bring_to_front()
        print("[DreaminaOperator] 页面已置顶。等待5秒以便历史图片框充分加载...")
        time.sleep(5) # 增加延时确保历史图片加载
        
        # 在页面设置完成后，立即检查并打印一次积分
        print("[DreaminaOperator] 页面设置完成，首次检查积分...")
        check_credits(dreamina_page) # 调用积分检查函数，它会自行打印积分
    else:
        print("[DreaminaOperator] Dreamina page became invalid after tab closing.")
        return None
        
    return dreamina_page

def check_credits(page) -> bool:
    """检查用户积分是否足够。"""
    print("[DreaminaOperator] 正在检查用户积分...")
    credit_selector = get_selector("dreamina_page.credit_text_xpath")
    if not credit_selector:
        print("[DreaminaOperator] 错误: 未能加载积分元素选择器! 无法检查积分。")
        return False # 无法检查，默认失败

    try:
        credit_element = page.locator(credit_selector)
        credit_element.wait_for(state="visible", timeout=10000) # 等待元素可见
        credit_text = credit_element.inner_text()
        current_credits = int(credit_text.strip())
        print(f"[DreaminaOperator] 当前积分为: {current_credits}")
        if current_credits < MIN_CREDIT_THRESHOLD:
            print(f"[DreaminaOperator] 警告: 积分 ({current_credits}) 低于阈值 ({MIN_CREDIT_THRESHOLD})!")
            return False
        return True
    except PlaywrightTimeoutError:
        print("[DreaminaOperator] 错误: 检查积分时未能找到积分元素或元素不可见。")
        return False
    except ValueError:
        print(f"[DreaminaOperator] 错误: 无法将积分文本 '{credit_text}' 解析为数字。")
        return False
    except Exception as e:
        print(f"[DreaminaOperator] 检查积分时发生未知错误: {e}")
        return False

def generate_image_on_page(page, prompt_info):
    """
    输入提示词，点击生成，等待图片加载完成，并保存所有生成的图片。
    图片会保存在以 prompt_info['source_excel_name'] 命名的子文件夹下。
    图片文件名基于 prompt_info['prompt']。
    如果服务器繁忙，会进行重试。
    """
    current_prompt_text = prompt_info['prompt']
    source_folder_name = prompt_info['source_excel_name']
    excel_row_num = prompt_info['row_number']

    current_image_save_path = os.path.join(IMAGE_SAVE_PATH, sanitize_filename(source_folder_name, max_length=50))
    if not os.path.exists(current_image_save_path):
        try:
            os.makedirs(current_image_save_path)
            print(f"[DreaminaOperator] 已创建子文件夹: {current_image_save_path}")
        except OSError as e:
            print(f"[DreaminaOperator] 错误：创建子文件夹 '{current_image_save_path}' 失败: {e}。将尝试保存到主图片文件夹。")
            current_image_save_path = IMAGE_SAVE_PATH

    prompt_input_xpath = get_selector("dreamina_page.prompt_input_xpath")
    existing_image_selector = get_selector("dreamina_page.generated_image_css_selector")
    general_record_block_xpath = get_selector("dreamina_page.general_record_block_xpath")
    generate_button_selector = get_selector("dreamina_page.generate_button_css_selector")
    server_busy_error_selector = get_selector("dreamina_page.server_busy_error_xpath")
    community_guidelines_violation_selector = get_selector("dreamina_page.community_guidelines_violation_xpath")

    if not all([prompt_input_xpath, existing_image_selector, general_record_block_xpath, generate_button_selector, server_busy_error_selector, community_guidelines_violation_selector]):
        print("[DreaminaOperator] 错误: 一个或多个核心选择器未能加载! 无法继续生成。")
        return False

    MAX_RETRY_ATTEMPTS = 2
    current_attempt = 0

    while current_attempt <= MAX_RETRY_ATTEMPTS:
        # 在每次尝试（包括重试）开始前检查积分
        if not check_credits(page):
            print(f"[DreaminaOperator] 积分不足 (低于 {MIN_CREDIT_THRESHOLD})。请充值后手动重新运行脚本。暂停当前图片生成任务。")
            # 此处返回 False 将导致此提示词处理失败，
            # 调用此函数的外部脚本需要根据此返回值决定是否完全停止或如何处理暂停逻辑。
            return False

        print(f"[DreaminaOperator] 开始生成尝试 {current_attempt + 1}/{MAX_RETRY_ATTEMPTS + 1} for prompt (Row {excel_row_num}) '{current_prompt_text}'")
        
        final_image_elements = []
        block_soak_start_time = {}

        try:
            prompt_input = page.locator(prompt_input_xpath)
            prompt_input.wait_for(state="visible", timeout=30000)
            prompt_input.click()
            prompt_input.fill("") 
            prompt_input.fill(current_prompt_text)
            print("[DreaminaOperator] 提示词已输入.")
            time.sleep(1)

            previous_image_srcs = set()
            try:
                all_img_locators_before_generation = page.locator(existing_image_selector).all()
                for img_loc in all_img_locators_before_generation:
                    if img_loc.is_visible(timeout=1000):
                        src = img_loc.get_attribute("src")
                        if src and (src.startswith("http") or src.startswith("data:image") or src.startswith("blob:")):
                            previous_image_srcs.add(src)
                print(f"[DreaminaOperator] 尝试 {current_attempt + 1}: 点击生成前，记录到 {len(previous_image_srcs)} 个可见图片srcs。")
            except Exception as e_old_src:
                print(f"[DreaminaOperator] 警告 (尝试 {current_attempt + 1}): 收集旧图片src时出错: {e_old_src}。")

            ids_before_generation = set()
            try:
                existing_blocks_locators = page.locator(general_record_block_xpath).all()
                for block_loc in existing_blocks_locators:
                    block_id = block_loc.get_attribute('id')
                    if block_id:
                        ids_before_generation.add(block_id)
                print(f"[DreaminaOperator] 尝试 {current_attempt + 1}: 点击生成前，记录到 {len(ids_before_generation)} 个结果块ID。")
            except Exception as e_old_blocks:
                print(f"[DreaminaOperator] 警告 (尝试 {current_attempt + 1}): 收集旧结果块ID时出错: {e_old_blocks}。")

            print("[DreaminaOperator] 等待 2 秒后点击生成按钮...")
            time.sleep(2)
            generate_button = page.locator(generate_button_selector)
            generate_button.wait_for(state="visible", timeout=30000)
            generate_button.click(timeout=30000)
            print("[DreaminaOperator] '生成' 按钮已点击.")
            print("[DreaminaOperator] 点击生成后，等待2秒以便结果块初步加载...")
            time.sleep(2)

            print(f"[DreaminaOperator] 尝试 {current_attempt + 1}: 开始识别新出现的结果块...")
            identified_new_block = None
            NEW_BLOCK_ACQUISITION_TIMEOUT_SECONDS = 60
            acquisition_loop_start_time = time.time()
            while time.time() - acquisition_loop_start_time < NEW_BLOCK_ACQUISITION_TIMEOUT_SECONDS:
                all_current_block_locators = page.locator(general_record_block_xpath).all()
                for current_block_loc in reversed(all_current_block_locators):
                    current_block_id = current_block_loc.get_attribute('id')
                    if current_block_id and current_block_id not in ids_before_generation:
                        print(f"[DreaminaOperator] 尝试 {current_attempt + 1}: 成功识别新结果块 (ID: {current_block_id})。")
                        identified_new_block = current_block_loc
                        break
                if identified_new_block:
                    break
                time.sleep(POLL_INTERVAL_SECONDS)
            
            if not identified_new_block:
                print(f"[DreaminaOperator] 尝试 {current_attempt + 1} 失败: 在 {NEW_BLOCK_ACQUISITION_TIMEOUT_SECONDS} 秒内未能识别出新结果块。")
                if current_attempt < MAX_RETRY_ATTEMPTS:
                    print("[DreaminaOperator] 等待10秒后将重试...")
                    time.sleep(10)
                    current_attempt += 1
                    continue
                else:
                    print("[DreaminaOperator] 已达到最大重试次数，放弃生成。")
                    return False

            target_record_block = identified_new_block
            target_block_id = target_record_block.get_attribute('id')

            # 给新块内容一点稳定时间
            page.wait_for_timeout(500) 

            # 首先检查是否违反社区准则 (这种错误不需要重试)
            try:
                guideline_violation_element = target_record_block.locator(community_guidelines_violation_selector)
                if guideline_violation_element.is_visible(timeout=5000): # 增加超时
                    print(f"[DreaminaOperator] 尝试 {current_attempt + 1}: 检测到提示词 (Row {excel_row_num}) '{current_prompt_text}' 违反社区准则 (块 ID: {target_block_id})。将跳过此提示词。")
                    return False # 直接返回失败，主循环应该跳过这个提示词
            except PlaywrightTimeoutError:
                # 未找到违反准则的提示，这是正常情况
                pass 
            except Exception as e_check_guideline:
                print(f"[DreaminaOperator] 尝试 {current_attempt + 1}: 检查社区准则消息时发生意外错误: {e_check_guideline}。假设无违规。")

            # 接着检查服务器繁忙错误 (这种错误可以重试)
            try:
                error_message_element = target_record_block.locator(server_busy_error_selector)
                if error_message_element.is_visible(timeout=5000): # 增加超时
                    print(f"[DreaminaOperator] 尝试 {current_attempt + 1}: 检测到服务器繁忙错误 (块 ID: {target_block_id})。")
                    if current_attempt < MAX_RETRY_ATTEMPTS:
                        print("[DreaminaOperator] 等待15秒后将重试...")
                        time.sleep(15)
                        current_attempt += 1
                        continue
                    else:
                        print("[DreaminaOperator] 服务器繁忙，已达到最大重试次数，放弃生成。")
                        return False
                else:
                    print(f"[DreaminaOperator] 尝试 {current_attempt + 1}: 未检测到服务器繁忙。继续图片加载检查。")
            except PlaywrightTimeoutError:
                print(f"[DreaminaOperator] 尝试 {current_attempt + 1}: 检查服务器繁忙消息时未找到(超时)。假设无错误。")
            except Exception as e_check_busy:
                print(f"[DreaminaOperator] 尝试 {current_attempt + 1}: 检查服务器繁忙消息时发生意外错误: {e_check_busy}。假设无错误。")

            print(f"[DreaminaOperator] 将针对新块 (ID: {target_block_id}) 开始智能等待图片生成 (最多 {MAX_GENERATION_WAIT_SECONDS} 秒)...")
            overall_image_wait_start_time = time.time()
            
            while time.time() - overall_image_wait_start_time < MAX_GENERATION_WAIT_SECONDS:
                if not target_record_block.is_visible():
                    print(f"[DreaminaOperator] 错误：目标新块 (ID: {target_block_id}) 已不再可见。此尝试的图片加载失败。")
                    break 

                images_in_this_block = target_record_block.locator(existing_image_selector).all()
                
                if not images_in_this_block or len(images_in_this_block) < MIN_EXPECTED_IMAGES:
                    block_soak_start_time.pop(target_block_id, None)
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue

                all_images_basically_loaded = True
                current_block_image_details = []
                for img_loc in images_in_this_block:
                    if not img_loc.is_visible(timeout=1000):
                        all_images_basically_loaded = False; break
                    img_src = img_loc.get_attribute("src")
                    if not (img_src and (img_src.startswith("http") or img_src.startswith("data:image") or img_src.startswith("blob:"))):
                        all_images_basically_loaded = False; break
                    current_block_image_details.append({"locator": img_loc, "src": img_src})
                
                if not all_images_basically_loaded:
                    block_soak_start_time.pop(target_block_id, None)
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue

                are_all_srcs_new = True
                temp_final_image_elements = []
                for img_detail in current_block_image_details:
                    temp_final_image_elements.append(img_detail["locator"])
                    if img_detail["src"] in previous_image_srcs:
                        are_all_srcs_new = False
                
                if are_all_srcs_new:
                    print(f"[DreaminaOperator] 目标块 (ID: {target_block_id}) 所有图片的 src 都是全新的！接受。")
                    final_image_elements = temp_final_image_elements
                    break 
                else:
                    if target_block_id not in block_soak_start_time:
                        print(f"[DreaminaOperator] 目标块 (ID: {target_block_id}) src 非全新。开始稳定观察期 ({OLD_SRC_SOAK_TIME_SECONDS}s)。")
                        block_soak_start_time[target_block_id] = time.time()
                    elif time.time() - block_soak_start_time[target_block_id] >= OLD_SRC_SOAK_TIME_SECONDS:
                        print(f"[DreaminaOperator] 目标块 (ID: {target_block_id}) src 非全新，已稳定观察。确认提示词...")
                        safe_current_prompt_text = current_prompt_text.replace("'", "\\'").replace("\"", "\\\"")
                        prompt_span_in_block_xpath = f".//span[@class='promptSpan-yzB1oU' and text()='{safe_current_prompt_text}']"
                        try:
                            if target_record_block.locator(prompt_span_in_block_xpath).is_visible(timeout=2000):
                                print(f"[DreaminaOperator] 确认：目标块 (ID: {target_block_id}) 内部仍包含当前提示词。接受此块。")
                                final_image_elements = temp_final_image_elements
                                break
                            else:
                                print(f"[DreaminaOperator] 警告：目标块 (ID: {target_block_id}) 稳定观察后不含提示词。重置观察。")
                                block_soak_start_time.pop(target_block_id, None)
                        except PlaywrightTimeoutError:
                            print(f"[DreaminaOperator] 警告：检查目标块 (ID: {target_block_id}) 提示词超时。重置观察。")
                            block_soak_start_time.pop(target_block_id, None)
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue

            if final_image_elements:
                print(f"[DreaminaOperator] 尝试 {current_attempt + 1}: 在最终确定的块 (ID: {target_block_id}) 中找到 {len(final_image_elements)} 张图片。开始保存...")
                saved_count = 0
                for i, img_element in enumerate(final_image_elements):
                    image_src = img_element.get_attribute("src")
                    if not image_src:
                        print(f"[DreaminaOperator] 警告: (Row {excel_row_num}) 第 {i+1} 张图片的 src 意外为空，跳过。")
                        continue
                    
                    filename_prompt_part = sanitize_filename(current_prompt_text)
                    image_filename = f"{excel_row_num}_{filename_prompt_part}_img{i+1}.jpg"
                    full_save_path = os.path.join(current_image_save_path, image_filename)

                    try:
                        if image_src.startswith('data:image'):
                            header, encoded = image_src.split(',', 1)
                            image_data = base64.b64decode(encoded)
                            with open(full_save_path, 'wb') as f: f.write(image_data)
                            saved_count += 1
                        elif image_src.startswith('http'):
                            img_response = requests.get(image_src, timeout=60)
                            img_response.raise_for_status()
                            with open(full_save_path, 'wb') as f: f.write(img_response.content)
                            saved_count += 1
                        elif image_src.startswith('blob:'):
                            img_element.screenshot(path=full_save_path, type='jpeg')
                            saved_count += 1
                        else:
                            print(f"[DreaminaOperator] (Row {excel_row_num}) 未识别的图片源格式: {image_src[:60]}...")
                    except Exception as e_save:
                        print(f"[DreaminaOperator] (Row {excel_row_num}) 保存图片 {full_save_path} 时出错: {e_save}")
                
                if saved_count >= MIN_EXPECTED_IMAGES:
                    print(f"[DreaminaOperator] 尝试 {current_attempt + 1}: 成功保存 {saved_count} 张图片。生成完成。")
                    return True
                else:
                    print(f"[DreaminaOperator] 尝试 {current_attempt + 1} 失败: 图片保存数量不足 ({saved_count}/{MIN_EXPECTED_IMAGES})。")
            else:
                print(f"[DreaminaOperator] 尝试 {current_attempt + 1} 失败: 未能最终确认图片加载 (块 ID: {target_block_id if identified_new_block else 'N/A'})。")

        except PlaywrightTimeoutError as pte:
            print(f"[DreaminaOperator] 尝试 {current_attempt + 1} 中发生 Playwright 超时: {pte}")
        except PlaywrightError as pe:
            print(f"[DreaminaOperator] 尝试 {current_attempt + 1} 中发生 Playwright 错误: {pe}")
        except Exception as e:
            print(f"[DreaminaOperator] 尝试 {current_attempt + 1} 中发生一般错误: {e} (行号: {e.__traceback__.tb_lineno if e.__traceback__ else 'N/A'})")

        if current_attempt < MAX_RETRY_ATTEMPTS:
            print(f"[DreaminaOperator] 等待10秒后将进行下一次尝试...")
            time.sleep(10)
            current_attempt += 1
        else:
            print(f"[DreaminaOperator] 所有尝试 ({MAX_RETRY_ATTEMPTS + 1}) 均失败。放弃为提示词 (Row {excel_row_num}) '{current_prompt_text}' 生成。")
            return False

    return False

# 原来的 if __name__ == '__main__': 块被移除或注释掉
# if __name__ == '__main__':
#     parser = argparse.ArgumentParser(description="控制已打开的浏览器标签页，打开 Dreamina 并关闭其他标签页。")
#     parser.add_argument("cdp_endpoint", help="Playwright 连接所需的 CDP Endpoint (例如: http://127.0.0.1:xxxxx)")
#     args = parser.parse_args()
# 
#     dreamina_url = "https://dreamina.capcut.com/ai-tool/image/generate"
#     
#     if not args.cdp_endpoint.startswith("http://") and not args.cdp_endpoint.startswith("https://"):
#         actual_cdp_endpoint = f"http://{args.cdp_endpoint}"
#         print(f"CDP Endpoint 未包含 http:// 或 https://, 自动添加 http:// 前缀: {actual_cdp_endpoint}")
#     else:
#         actual_cdp_endpoint = args.cdp_endpoint
# 
#     control_dreamina_tabs(cdp_endpoint=actual_cdp_endpoint, target_url=dreamina_url) 