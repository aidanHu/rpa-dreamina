import time
import threading # 引入 threading 模块
import math # For ceiling division in file distribution
import os #  确保导入os模块，用于os.path.basename
import shutil # 导入 shutil 模块用于文件移动
# from playwright.sync_api import sync_playwright, PlaywrightTimeoutError # Old import
from playwright.sync_api import sync_playwright
from playwright.sync_api import Error as PlaywrightError # General Playwright error
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError # Try this specific import path or rely on the general one

# Import functions from other modules
from bit_api import load_browser_configs, launch_and_get_debug_address, closeBrowser, BitAPIError
from dreamina_operator import navigate_and_setup_dreamina_page, generate_image_on_page
from excel_reader import get_excel_file_paths, get_prompts_from_single_excel, update_excel_remark 

# --- Configuration --- 
# EXCEL_FOLDER_PATH = "/Users/aidan/Documents/rpa-dreamina/" # Replaced by EXCEL_PROMPTS_FOLDER
DREAMINA_URL = "https://dreamina.capcut.com/ai-tool/image/generate"
# WAIT_AFTER_GENERATION_SECONDS = 15 # This seems to be handled within generate_image_on_page or a general wait
EXCEL_PROMPTS_FOLDER = "excel_prompts"  # Folder to read Excel files from
BROWSER_CONFIG_FILE = "browser_config.json"
PROCESSED_EXCEL_SUBFOLDER = "已处理" # 定义已处理文件夹的名称

def process_browser_task(browser_config, assigned_excel_files, dreamina_url):
    """处理单个浏览器所有任务的函数，将在单独的线程中运行。"""
    current_browser_id = browser_config['id']
    browser_name = browser_config.get('name', current_browser_id) # 使用我们之前确认的命名逻辑

    print(f"\n=== [线程: {browser_name}] 开始处理浏览器 (ID: {current_browser_id}) ===")

    if not assigned_excel_files:
        print(f"[线程: {browser_name}] 没有分配到Excel文件，将跳过提示词处理。")
        # 线程仍会尝试启动和关闭浏览器（如果配置如此），或直接退出
        # 为保持一致性，即使没有任务，也尝试一次完整的浏览器启动/关闭周期
        # 如果希望无任务时不启动浏览器，可以在这里提前返回或调整逻辑

    returned_id, http_address, ws_address = None, None, None
    # files_to_move 在 try 块外部定义，以确保 finally 中可访问
    # 只有当一个Excel文件中的所有提示词都被迭代过（无论成功与否），该文件才会被加入此列表
    files_considered_processed_by_thread = [] 

    try:
        returned_id, http_address, ws_address = launch_and_get_debug_address(current_browser_id)
    except BitAPIError as bae:
        print(f"[线程: {browser_name}] 启动 Bit Browser 时发生API错误: {bae}。线程中止。")
        return
    except Exception as e_launch:
        print(f"[线程: {browser_name}] 启动 Bit Browser 时发生未知错误: {e_launch}。线程中止。")
        return

    if returned_id != current_browser_id or not (http_address or ws_address):
        print(f"[线程: {browser_name}] 错误: 未能为浏览器 (ID: {current_browser_id}) 获取有效的调试地址。线程中止。")
        if returned_id: 
            print(f"[线程: {browser_name}] 尝试关闭可能已打开的浏览器 (ID: {returned_id})...")
            try:
                closeBrowser(returned_id)
            except Exception as e_close_early:
                print(f"[线程: {browser_name}] 尝试关闭浏览器时出错: {e_close_early}")
        return

    debug_address_for_playwright = None
    if http_address and not http_address.startswith(("http://", "https://")):
        debug_address_for_playwright = f"http://{http_address}"
    elif http_address:
        debug_address_for_playwright = http_address
    elif ws_address:
        if ws_address.startswith("ws://"):
            parts = ws_address.split("/")
            if len(parts) >= 3:
                debug_address_for_playwright = f"http://{parts[2]}"
                print(f"[线程: {browser_name}] 从WebSocket调试地址派生出HTTP CDP地址: {debug_address_for_playwright}")
        if not debug_address_for_playwright:        
            print(f"[线程: {browser_name}] WebSocket调试地址 '{ws_address}' 格式不符合预期或无法派生HTTP地址。线程中止。")
            try: closeBrowser(current_browser_id) 
            except Exception: pass
            return 
    else:
        print(f"[线程: {browser_name}] 严重内部错误: HTTP 和 WS 调试地址均无效。线程中止。")
        try: closeBrowser(current_browser_id)
        except Exception: pass
        return

    print(f"[线程: {browser_name}] 使用调试地址: {debug_address_for_playwright} 连接 Playwright。")

    try:
        with sync_playwright() as p: # 每个线程独立的Playwright实例
            browser_instance = None
            try:
                print(f"[线程: {browser_name}] 连接到已打开的浏览器实例...")
                browser_instance = p.chromium.connect_over_cdp(debug_address_for_playwright, timeout=60000)
                
                if not browser_instance.contexts:
                    print(f"[线程: {browser_name}] 错误: 浏览器中没有任何上下文。")
                    if browser_instance: browser_instance.close()
                    return 
                
                context = browser_instance.contexts[0]
                print(f"[线程: {browser_name}] 已连接到浏览器上下文。页面数量: {len(context.pages)}")

                print(f"\n[线程: {browser_name}] 导航并设置 Dreamina 页面...")
                dreamina_page = navigate_and_setup_dreamina_page(context, dreamina_url)

                if not dreamina_page or dreamina_page.is_closed():
                    print(f"[线程: {browser_name}] 错误: 未能成功设置 Dreamina 页面。")
                    if browser_instance: browser_instance.close()
                    return
                
                print(f"[线程: {browser_name}] Dreamina 页面准备就绪。开始处理该浏览器分配的任务...")
                
                if not assigned_excel_files:
                    print(f"[线程: {browser_name}] 再次确认：没有分配Excel文件，不处理提示词。")
                else:
                    total_prompts_for_this_browser = 0
                    prompts_processed_for_this_browser = 0
                    for excel_file_index, excel_file_path in enumerate(assigned_excel_files):
                        print(f"\n-- [线程: {browser_name}] 开始处理Excel文件 ({excel_file_index + 1}/{len(assigned_excel_files)}): {os.path.basename(excel_file_path)} --")
                        prompts_data_list_for_file = get_prompts_from_single_excel(excel_file_path)
                        if not prompts_data_list_for_file:
                            print(f"[线程: {browser_name}] Excel文件 '{os.path.basename(excel_file_path)}' 未提取到提示词。该文件仍将被视为已处理。")
                            # 即使文件无提示词，也认为它已被"处理"过
                            files_considered_processed_by_thread.append(excel_file_path)
                            continue
                        total_prompts_for_this_browser += len(prompts_data_list_for_file)
                        for i, prompt_info_item in enumerate(prompts_data_list_for_file):
                            prompts_processed_for_this_browser +=1
                            prompt_text = prompt_info_item['prompt']
                            source_excel_name_for_log = prompt_info_item['source_excel_name']
                            row_num_for_log = prompt_info_item['row_number']
                            original_excel_file_path = prompt_info_item['original_file_path'] # 获取原始文件路径

                            print(f"\n--- [线程: {browser_name}] 文件 '{source_excel_name_for_log}' ({excel_file_index+1}/{len(assigned_excel_files)}), "
                                  f"提示词 ({i+1}/{len(prompts_data_list_for_file)}): "
                                  f"行 {row_num_for_log}, 内容: '{prompt_text}' ---")
                            
                            success = generate_image_on_page(dreamina_page, prompt_info_item)
                            
                            if success:
                                print(f"[线程: {browser_name}] 提示词 (源: {source_excel_name_for_log}, 行: {row_num_for_log}) 生成和保存成功。")
                                remark_to_add = "已生成并保存图片"
                                # 第二列的0基索引是1
                                update_status = update_excel_remark(original_excel_file_path, 
                                                                    row_num_for_log, 
                                                                    1, 
                                                                    remark_to_add)
                                if update_status:
                                    print(f"[线程: {browser_name}] 已在Excel文件 '{os.path.basename(original_excel_file_path)}' 的第 {row_num_for_log} 行第二列添加备注。")
                                else:
                                    print(f"[线程: {browser_name}] 未能更新Excel文件 '{os.path.basename(original_excel_file_path)}' 的备注。")
                            else:
                                print(f"[线程: {browser_name}] 提示词 (源: {source_excel_name_for_log}, 行: {row_num_for_log}) 生成或保存失败。Excel备注将留空。")
                            
                            is_last_prompt_overall_for_browser = (excel_file_index == len(assigned_excel_files) - 1 and
                                                               i == len(prompts_data_list_for_file) - 1)
                            if not is_last_prompt_overall_for_browser:
                                wait_time = 5 
                                print(f"[线程: {browser_name}] 等待 {wait_time} 秒后处理下一个提示词或文件...")
                                time.sleep(wait_time)
                        print(f"-- [线程: {browser_name}] 完成处理Excel文件: {os.path.basename(excel_file_path)} --")
                        files_considered_processed_by_thread.append(excel_file_path)
                    if total_prompts_for_this_browser == 0 and assigned_excel_files:
                         print(f"[线程: {browser_name}] 分配的Excel文件均未提取到有效提示词。")
                    elif prompts_processed_for_this_browser > 0 :
                         print(f"[线程: {browser_name}] 此浏览器共处理了 {prompts_processed_for_this_browser} 个提示词。")

            except PlaywrightTimeoutError as pte:
                print(f"[线程: {browser_name}] Playwright 操作超时: {pte}")
            except BitAPIError as bae: 
                print(f"[线程: {browser_name}] Bit API 操作时发生错误: {bae}")
            except Exception as e:
                print(f"[线程: {browser_name}] 在 Playwright/提示词处理中发生错误: {e} (行号: {e.__traceback__.tb_lineno if e.__traceback__ else 'N/A'})")
            finally:
                print(f"[线程: {browser_name}] Playwright 部分执行完毕。")
                if browser_instance and browser_instance.is_connected():
                    print(f"[线程: {browser_name}] Playwright断开与浏览器的连接...")
                    browser_instance.close()
    
    except Exception as e_outer: 
         print(f"[线程: {browser_name}] 处理浏览器时发生外部错误: {e_outer}")
    finally:
        # --- 文件移动逻辑 ---
        if files_considered_processed_by_thread:
            target_processed_folder = os.path.join(EXCEL_PROMPTS_FOLDER, PROCESSED_EXCEL_SUBFOLDER)
            try:
                os.makedirs(target_processed_folder, exist_ok=True)
                print(f"[线程: {browser_name}] 确保已处理文件夹存在: {target_processed_folder}")
                for file_path_to_move in files_considered_processed_by_thread:
                    if not os.path.exists(file_path_to_move):
                        print(f"[线程: {browser_name}] 警告: 尝试移动的文件 '{os.path.basename(file_path_to_move)}' 不再存在于原始位置。")
                        continue
                    
                    file_name_to_move = os.path.basename(file_path_to_move)
                    destination_file_path = os.path.join(target_processed_folder, file_name_to_move)
                    
                    if os.path.exists(destination_file_path):
                        print(f"[线程: {browser_name}] 警告: 文件 '{file_name_to_move}' 已存在于目标文件夹 '{target_processed_folder}'。将不会移动以避免覆盖。")
                    else:
                        try:
                            shutil.move(file_path_to_move, destination_file_path)
                            print(f"[线程: {browser_name}] 已将文件 '{file_name_to_move}' 移动到 '{target_processed_folder}'")
                        except FileNotFoundError:
                             print(f"[线程: {browser_name}] 移动文件 '{file_name_to_move}' 时源文件未找到 (可能已被并发移动)。")
                        except Exception as e_move_file:
                            print(f"[线程: {browser_name}] 移动文件 '{file_name_to_move}' 时发生错误: {e_move_file}")
            except Exception as e_create_processed_dir:
                print(f"[线程: {browser_name}] 创建已处理文件夹或准备移动文件时出错: {e_create_processed_dir}")
        elif assigned_excel_files: # 有分配文件，但 files_considered_processed_by_thread 为空，说明处理未开始或未完成任何一个文件
            print(f"[线程: {browser_name}] 没有Excel文件被标记为已完全处理，不执行移动操作。")

        if returned_id: 
            print(f"[线程: {browser_name}] 浏览器处理流程结束。尝试通过BitAPI关闭浏览器窗口 {returned_id}...")
            try:
                closeBrowser(returned_id)
                print(f"[线程: {browser_name}] 成功请求关闭浏览器 {returned_id}.")
            except BitAPIError as bae_close:
                print(f"[线程: {browser_name}] BitAPI 关闭浏览器 {returned_id} 时发生错误: {bae_close}")
            except Exception as e_close_final:
                print(f"[线程: {browser_name}] 关闭浏览器 {returned_id} 时发生未知错误: {e_close_final}")
        else:
            print(f"[线程: {browser_name}] 浏览器未成功启动或ID未知，无需通过BitAPI关闭。")
        
        print(f"=== [线程: {browser_name}] 浏览器 (ID: {current_browser_id}) 处理完毕 ===") # Removed scorers=

def main():
    print("[MainController] 开始自动化流程...")

    print("\n[MainController] 步骤1: 加载浏览器配置...")
    browser_configs = load_browser_configs(BROWSER_CONFIG_FILE)
    if not browser_configs:
        print("[MainController] 未能加载任何浏览器配置，流程中止。")
        return
    active_browser_configs = [bc for bc in browser_configs if bc.get('id')]
    if not active_browser_configs:
        print("[MainController] 加载的浏览器配置均无效 (缺少 'id')，流程中止。")
        return
    
    print(f"[MainController] 加载了 {len(active_browser_configs)} 个有效的浏览器配置。")

    print("\n[MainController] 步骤2: 扫描Excel文件...")
    excel_file_paths = get_excel_file_paths(EXCEL_PROMPTS_FOLDER)
    if not excel_file_paths:
        print(f"[MainController] 在文件夹 '{EXCEL_PROMPTS_FOLDER}' 中未找到Excel文件，流程结束。")
        return
    print(f"[MainController] 找到 {len(excel_file_paths)} 个Excel文件: {[os.path.basename(p) for p in excel_file_paths]}") # Log only basenames

    # --- 步骤3: 将Excel文件分配给浏览器 ---
    num_browsers = len(active_browser_configs)
    num_excel_files = len(excel_file_paths)
    
    excel_distribution = {config['id']: [] for config in active_browser_configs}

    if num_excel_files == 0:
        print("[MainController] 没有Excel文件需要处理。")
    elif num_browsers == 0:
        print("[MainController] 没有可用的浏览器来处理Excel文件。流程结束。")
        return
    else:
        for i, file_path in enumerate(excel_file_paths):
            browser_config_for_file = active_browser_configs[i % num_browsers]
            excel_distribution[browser_config_for_file['id']].append(file_path)
        
        print("\n[MainController] Excel文件分配结果:")
        for browser_id, files in excel_distribution.items():
            browser_name_temp = next((bc.get('name', f"ID_{browser_id}") for bc in active_browser_configs if bc['id'] == browser_id), f"ID_{browser_id}")
            if files:
                print(f"  浏览器 {browser_name_temp} (ID: {browser_id}) 将处理: {[os.path.basename(file) for file in files]}")
            else:
                print(f"  浏览器 {browser_name_temp} (ID: {browser_id}) 没有分配到Excel文件。")
    
    # --- 步骤4: 并行启动浏览器并处理分配的任务 ---
    threads = []
    print("\n[MainController] 准备启动并行浏览器处理任务...")
    for browser_config in active_browser_configs:
        current_browser_id_for_thread = browser_config['id']
        assigned_files_for_thread = excel_distribution.get(current_browser_id_for_thread, [])
        
        thread = threading.Thread(target=process_browser_task, 
                                  args=(browser_config, assigned_files_for_thread, DREAMINA_URL))
        threads.append(thread)
        print(f"[MainController] 已为浏览器ID '{current_browser_id_for_thread}' 创建处理线程。")

    if threads:
        print(f"\n[MainController] 开始启动 {len(threads)} 个处理线程...")
        for thread in threads:
            thread.start()
            time.sleep(1) 

        print(f"\n[MainController] 所有线程已启动。等待所有浏览器任务完成...")
        for thread in threads:
            thread.join()
    else:
        print("[MainController] 没有有效的浏览器或任务来创建线程。")
            
    print("\n[MainController] 所有并行浏览器任务均已处理完毕（或尝试处理）。")
    print("[MainController] 自动化流程结束。")

if __name__ == "__main__":
    main() 