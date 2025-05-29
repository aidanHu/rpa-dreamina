#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
from pathlib import Path
from dreamina_operator import navigate_and_setup_dreamina_page, generate_image_on_page
from excel_processor import get_unprocessed_prompts_from_excel_folder, get_unprocessed_prompts_from_subfolders, mark_prompt_as_processed
from element_config import get_url
from playwright.sync_api import sync_playwright
try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except ImportError:
    # 兼容不同版本的 Playwright
    PlaywrightError = Exception
    PlaywrightTimeoutError = Exception
from account_manager import AccountManager
from account_logout import LogoutManager
from bit_api import launch_and_get_debug_address

# 配置文件路径
CONFIG_FILE = "user_config.json"

def load_config():
    """加载配置文件"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # 创建默认配置
            default_config = {
                "browser_settings": {
                    "browser_ids": []
                },
                "file_paths": {
                    "root_directory": "Projects"
                },
                "excel_settings": {
                    "prompt_column": 2,
                    "status_column": 3,
                    "status_text": "已生成图片",
                    "start_row": 2
                },
                "image_settings": {
                    "default_aspect_ratio": "9:16"
                },
                "multi_window_settings": {
                    "task_interval_seconds": 3,
                    "startup_delay_seconds": 5,
                    "error_retry_attempts": 2
                },
                "points_monitoring": {
                    "enabled": True,
                    "min_points_threshold": 4,
                    "check_interval_seconds": 30
                }
            }
            save_config(default_config)
            return default_config
    except Exception as e:
        print(f"❌ 加载配置文件失败: {e}")
        return {
            "file_paths": {
                "root_directory": "Projects"
            },
            "excel_settings": {
                "status_column": 3,
                "status_text": "已生成图片"
            }
        }

def save_config(config):
    """保存配置文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"❌ 保存配置失败: {e}")
        return False

def validate_excel_folder(path):
    """验证Excel文件夹路径（兼容性函数）"""
    if not path:
        return False, "路径为空"
    
    path_obj = Path(path)
    
    if not path_obj.exists():
        return False, f"路径不存在: {path}"
    
    if not path_obj.is_dir():
        return False, f"路径不是文件夹: {path}"
    
    # 检查是否包含Excel文件
    excel_files = list(path_obj.glob("*.xlsx")) + list(path_obj.glob("*.xls"))
    if not excel_files:
        return False, f"文件夹中没有Excel文件: {path}"
    
    return True, f"找到 {len(excel_files)} 个Excel文件"

def validate_root_directory(path):
    """验证根目录路径（新的子文件夹结构）"""
    if not path:
        return False, "路径为空"
    
    path_obj = Path(path)
    
    if not path_obj.exists():
        return False, f"路径不存在: {path}"
    
    if not path_obj.is_dir():
        return False, f"路径不是文件夹: {path}"
    
    # 检查子文件夹中是否包含Excel文件
    excel_count = 0
    subfolder_count = 0
    
    for item in path_obj.iterdir():
        if item.is_dir():
            subfolder_count += 1
            # 检查子文件夹中的Excel文件
            excel_files = list(item.glob("*.xlsx")) + list(item.glob("*.xls"))
            if excel_files:
                excel_count += len(excel_files)
    
    if subfolder_count == 0:
        return False, f"根目录中没有子文件夹: {path}"
    
    if excel_count == 0:
        return False, f"子文件夹中没有找到Excel文件: {path}"
    
    return True, f"找到 {subfolder_count} 个子文件夹，包含 {excel_count} 个Excel文件"

def display_menu():
    """显示主菜单"""
    print("\n" + "="*60)
    print("🎨 Dreamina 自动化图片生成工具 v2.0")
    print("="*60)
    print("📋 功能特点：")
    print("  • 🖼️  批量图片生成 - 从Excel读取提示词自动生成")
    print("  • 🚀  智能多窗口 - 根据配置的浏览器ID数量自动选择")
    print("  • 📁  项目独立管理 - 每个项目文件独立存储")
    print("  • 🔄  智能断点续传 - 自动跳过已处理项目")
    print("  • ⚙️  灵活配置 - 可自定义列位置和状态标记")
    print("-" * 60)
    print("请选择要执行的操作：")
    print("1. 📝 账号注册功能")
    print("2. 🚪 账号注销功能")
    print("3. 🖼️  批量图片生成")
    print("0. 👋 退出程序")
    print("="*60)

def get_user_choice():
    """获取用户选择"""
    while True:
        try:
            choice = input("\n请输入选项编号 (0-3): ").strip()
            if choice in ['0', '1', '2', '3']:
                return choice
            else:
                print("❌ 无效的选项，请输入 0-3 之间的数字")
        except KeyboardInterrupt:
            print("\n\n👋 用户中断，退出程序")
            sys.exit(0)

def handle_account_registration():
    """处理账号注册功能"""
    print("\n📝 账号注册功能")
    print("-" * 30)
    
    while True:
        try:
            count = input("请输入要注册的账号数量: ").strip()
            count = int(count)
            if count > 0:
                break
            else:
                print("❌ 请输入大于0的数字")
        except ValueError:
            print("❌ 请输入有效的数字")
        except KeyboardInterrupt:
            print("\n\n👋 用户取消操作")
            return
    
    print(f"\n✅ 准备注册 {count} 个账号...")
    
    # 启动浏览器
    print("\n🌐 启动浏览器...")
    browser_id, http_address, ws_address = launch_and_get_debug_address()
    
    if not http_address and not ws_address:
        print("❌ 错误：未能获取浏览器调试地址")
        return
    
    # 创建账号管理器并执行注册
    account_manager = AccountManager()
    success = account_manager.register_accounts(count, browser_id, http_address, ws_address)
    
    if success:
        print(f"\n✅ 成功完成账号注册任务")
    else:
        print(f"\n❌ 账号注册过程中出现错误")

def handle_account_logout():
    """处理账号注销功能"""
    print("\n🚪 账号注销功能")
    print("-" * 30)
    
    # 启动浏览器
    print("\n🌐 启动浏览器...")
    browser_id, http_address, ws_address = launch_and_get_debug_address()
    
    if not http_address and not ws_address:
        print("❌ 错误：未能获取浏览器调试地址")
        return
    
    # 构建Playwright需要的调试地址
    if http_address and not http_address.startswith(("http://", "https://")):
        debug_address = f"http://{http_address}"
    else:
        debug_address = http_address
    
    print(f"连接到浏览器: {debug_address}")
    
    # 使用注销管理器
    logout_manager = LogoutManager()
    
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(debug_address)
            
            if not browser.contexts:
                print("❌ 错误: 浏览器中没有任何上下文")
                return
            
            context = browser.contexts[0]
            
            if not context.pages:
                print("❌ 错误: 浏览器中没有打开的页面")
                return
            
            page = context.pages[0]
            
            # 检查当前登录状态
            status = logout_manager.check_login_status(page)
            print(f"\n当前登录状态: {status}")
            
            if status == "logged_out":
                print("✅ 当前已经是未登录状态，无需注销")
                return
            elif status == "unknown":
                print("⚠️ 无法确定当前登录状态，将尝试执行注销操作")
            else:
                print("🔍 检测到已登录状态，准备执行注销...")
            
            # 执行注销
            success = logout_manager.logout_account(page)
            
            if success:
                print("\n✅ 账号注销成功！")
            else:
                print("\n❌ 账号注销失败")
                
    except Exception as e:
        print(f"❌ 注销过程中发生错误: {e}")

def handle_image_generation():
    """处理批量图片生成功能（智能选择单窗口或多窗口）"""
    print("\n🖼️ 批量图片生成功能")
    print("-" * 30)
    
    # 加载配置
    config = load_config()
    root_directory = config.get("file_paths", {}).get("root_directory", "Projects")
    browser_ids = config.get('browser_settings', {}).get('browser_ids', [])
    
    print(f"📂 根目录: {root_directory}")
    print(f"📁 图片保存: 各项目子文件夹中")
    print(f"🌐 配置的浏览器数量: {len(browser_ids)}")
    
    # 根据浏览器ID数量决定模式
    if len(browser_ids) == 0:
        print("❌ 未配置浏览器ID，请在配置文件中添加浏览器ID")
        return
    elif len(browser_ids) == 1:
        print("🖼️  模式: 单窗口处理")
        mode = "single"
    else:
        print(f"🚀 模式: 多窗口并行处理 ({len(browser_ids)} 个窗口)")
        mode = "multi"
    
    # 验证根目录
    is_valid, message = validate_root_directory(root_directory)
    print(f"📋 Excel文件夹状态: {'✅' if is_valid else '❌'} {message}")
    
    if not is_valid:
        print("\n❌ 配置验证失败！")
        print(f"请在配置文件 '{CONFIG_FILE}' 中修改 'root_directory' 为正确的路径")
        print(f"当前配置的路径: {root_directory}")
        print(f"问题: {message}")
        
        # 提供修改配置的选项
        fix_choice = input("\n是否要修改配置？(y/n): ").strip().lower()
        if fix_choice == 'y':
            new_path = input("请输入正确的Excel文件夹路径: ").strip()
            if new_path:
                if "file_paths" not in config:
                    config["file_paths"] = {}
                config["file_paths"]["root_directory"] = new_path
                if save_config(config):
                    print("✅ 配置已更新")
                    # 重新验证
                    is_valid, message = validate_root_directory(new_path)
                    if is_valid:
                        print(f"✅ 新路径验证通过！{message}")
                    else:
                        print(f"❌ 新路径仍然无效: {message}")
                        return
                else:
                    print("❌ 配置更新失败")
                    return
        else:
            return
    
    print(f"\n✅ 配置验证通过！{message}")
    
    # 询问是否开始生成
    confirm = input(f"\n确定要开始{mode}模式图片生成吗？(y/n): ").strip().lower()
    if confirm != 'y':
        print("已取消生成")
        return
    
    # 根据模式执行相应的处理流程
    if mode == "single":
        print("\n" + "="*50)
        print("🖼️  开始单窗口图片生成")
        print("="*50)
        _execute_text_to_image_process(root_directory)
        print("\n" + "="*50)
        print("🖼️  单窗口图片生成完成")
        print("="*50)
    else:
        print("\n" + "="*80)
        print("🚀 开始多窗口并行图片生成")
        print("="*80)
        try:
            from multi_window_manager import MultiWindowManager
            manager = MultiWindowManager()
            success = manager.start_multi_window_processing(root_directory)
            if success:
                print("\n✅ 多窗口处理完成！")
            else:
                print("\n❌ 多窗口处理失败")
        except ImportError as e:
            print(f"❌ 导入多窗口管理器失败: {e}")
        except Exception as e:
            print(f"❌ 多窗口处理过程中发生错误: {e}")
        print("="*80)

def _execute_text_to_image_process(root_directory):
    """执行文生图核心流程"""
    import time
    
    print("[TextToImage] 开始自动化流程...")
    
    debug_address = None
    try:
        print("[TextToImage] 步骤1: 启动浏览器并获取调试地址...")
        browser_id, http_debug_address, ws_debug_address = launch_and_get_debug_address()
        
        if not http_debug_address and not ws_debug_address:
            print("[TextToImage] 错误: 未能从 Bit API 获取有效的调试地址。请检查 Bit Browser 是否运行正常。")
            return

        # 构建调试地址
        if http_debug_address and not http_debug_address.startswith(("http://", "https://")):
            debug_address = f"http://{http_debug_address}"
        elif http_debug_address:
            debug_address = http_debug_address
        elif ws_debug_address:
            if ws_debug_address.startswith("ws://"):
                parts = ws_debug_address.split("/")
                if len(parts) >= 3:
                    debug_address = f"http://{parts[2]}"
                    print(f"[TextToImage] 从WebSocket调试地址派生出HTTP CDP地址: {debug_address}")
                else:
                    print(f"[TextToImage] 错误: WebSocket调试地址格式不符合预期。")
                    return    
            else:
                print(f"[TextToImage] 错误: WebSocket调试地址格式不标准。")
                return
        else:
            print("[TextToImage] 严重错误: HTTP 和 WS 调试地址均无效。")
            return

        print(f"[TextToImage] 使用调试地址: {debug_address}")

        print("\n[TextToImage] 步骤2: 从Excel文件加载未处理的提示词...")
        prompts_data_list = get_unprocessed_prompts_from_subfolders(root_directory)
        if not prompts_data_list:
            print("[TextToImage] ✅ 所有提示词都已处理完成，或未找到任何提示词。")
            return
        
        print(f"[TextToImage] 找到 {len(prompts_data_list)} 条未处理的提示词，开始处理。")

        with sync_playwright() as p:
            try:
                print("[TextToImage] 步骤3: 连接到已打开的浏览器...")
                browser = p.chromium.connect_over_cdp(debug_address)
                
                if not browser.contexts:
                    print("[TextToImage] 错误: 浏览器中没有任何上下文。")
                    return
                
                context = browser.contexts[0]
                print(f"[TextToImage] 已连接到浏览器上下文。页面数量: {len(context.pages)}")

                print("\n[TextToImage] 步骤4: 导航并设置 Dreamina 页面...")
                dreamina_url = get_url("image_generate")
                dreamina_page = navigate_and_setup_dreamina_page(context, dreamina_url)

                if not dreamina_page or dreamina_page.is_closed():
                    print("[TextToImage] 错误: 未能成功设置 Dreamina 页面，流程中止。")
                    return
                
                print("[TextToImage] Dreamina 页面准备就绪。")
                
                print("\n[TextToImage] 步骤5: 循环处理提示词并生成图片...")
                
                # 统计变量
                total_prompts = len(prompts_data_list)
                successful_count = 0
                failed_count = 0
                failed_prompts = []
                
                for i, prompt_info_item in enumerate(prompts_data_list):
                    prompt_text = prompt_info_item['prompt']
                    source_excel = prompt_info_item['source_excel_name']
                    row_number = prompt_info_item['row_number']
                    excel_file_path = prompt_info_item['excel_file_path']
                    
                    print(f"\n{'='*80}")
                    print(f"[TextToImage] 📝 处理第 {i+1}/{total_prompts} 个提示词")
                    print(f"  提示词: '{prompt_text}'")
                    print(f"  来源文件: {source_excel}")
                    print(f"  行号: {row_number}")
                    print(f"  进度: {(i+1)/total_prompts*100:.1f}%")
                    print(f"{'='*80}")
                    
                    try:
                        # 检查页面连接状态
                        if dreamina_page.is_closed():
                            print("[TextToImage] ❌ 页面已关闭，尝试重新设置...")
                            dreamina_url = get_url("image_generate")
                            dreamina_page = navigate_and_setup_dreamina_page(context, dreamina_url)
                            if not dreamina_page or dreamina_page.is_closed():
                                print("[TextToImage] ❌ 无法重新建立页面连接，流程中止")
                                break
                        
                        generated_images = generate_image_on_page(dreamina_page, prompt_info_item)
                        
                        if generated_images and len(generated_images) > 0:
                            successful_count += 1
                            print(f"[TextToImage] ✅ 提示词 '{prompt_text}' 处理成功！生成了 {len(generated_images)} 张图片")
                            
                            # 标记为已处理
                            from excel_processor import get_excel_settings
                            excel_settings = get_excel_settings()
                            mark_prompt_as_processed(excel_file_path, row_number, 
                                                   excel_settings["status_column"], 
                                                   excel_settings["status_text"])
                        else:
                            failed_count += 1
                            failed_prompts.append({
                                'prompt': prompt_text,
                                'source': source_excel,
                                'row': row_number,
                                'reason': '图片生成或保存失败'
                            })
                            print(f"[TextToImage] ❌ 提示词 '{prompt_text}' 处理失败")
                            
                    except PlaywrightTimeoutError as pte:
                        failed_count += 1
                        failed_prompts.append({
                            'prompt': prompt_text,
                            'source': source_excel,
                            'row': row_number,
                            'reason': f'Playwright 超时: {pte}'
                        })
                        print(f"[TextToImage] ❌ 在为提示词 (Row {row_number}) '{prompt_text}' 生成图片过程中发生 Playwright 超时: {pte}")
                        
                    except PlaywrightError as pe:
                        failed_count += 1
                        failed_prompts.append({
                            'prompt': prompt_text,
                            'source': source_excel,
                            'row': row_number,
                            'reason': f'Playwright 错误: {pe}'
                        })
                        print(f"[TextToImage] ❌ 在为提示词 (Row {row_number}) '{prompt_text}' 生成图片过程中发生 Playwright 错误: {pe}")
                        
                    except Exception as e:
                        failed_count += 1
                        failed_prompts.append({
                            'prompt': prompt_text,
                            'source': source_excel,
                            'row': row_number,
                            'reason': f'异常错误: {e}'
                        })
                        print(f"[TextToImage] ❌ 处理提示词 '{prompt_text}' 时发生异常: {e}")
                    
                    # 显示实时统计
                    print(f"\n[TextToImage] 📊 当前统计:")
                    print(f"  已处理: {i+1}/{total_prompts}")
                    print(f"  成功: {successful_count}")
                    print(f"  失败: {failed_count}")
                    print(f"  成功率: {successful_count/(i+1)*100:.1f}%")
                    
                    if i < len(prompts_data_list) - 1:
                        wait_time = 5
                        print(f"[TextToImage] ⏳ 等待 {wait_time} 秒后处理下一个提示词...")
                        time.sleep(wait_time)
                
                # 最终统计报告
                print(f"\n{'='*80}")
                print(f"[TextToImage] 📊 最终处理报告")
                print(f"{'='*80}")
                print(f"  总计提示词数量: {total_prompts}")
                print(f"  成功处理: {successful_count}")
                print(f"  失败处理: {failed_count}")
                print(f"  总体成功率: {successful_count/total_prompts*100:.1f}%" if total_prompts > 0 else "  总体成功率: 0%")
                
                if failed_prompts:
                    print(f"\n  失败详情:")
                    for i, failed in enumerate(failed_prompts[:5], 1):
                        print(f"    {i}. 行{failed['row']} - '{failed['prompt'][:30]}...' ({failed['source']})")
                        print(f"       原因: {failed['reason']}")
                    if len(failed_prompts) > 5:
                        print(f"    ... 还有 {len(failed_prompts) - 5} 个失败项目")
                
                if successful_count > 0:
                    print(f"\n✅ 任务完成！成功处理了 {successful_count} 个提示词的图片生成。")
                else:
                    print(f"\n❌ 任务失败！没有成功处理任何提示词。")
                    
                print(f"{'='*80}")

            except PlaywrightTimeoutError as pte:
                print(f"[TextToImage] Playwright 操作超时: {pte}")
            except Exception as e:
                print(f"[TextToImage] 在 Playwright 操作或图片生成循环中发生错误: {e}")
            finally:
                print("[TextToImage] Playwright 部分执行完毕。浏览器保持打开状态。")
    
    except Exception as e:
        print(f"[TextToImage] 发生未预料的错误: {e}")
    finally:
        print("[TextToImage] 自动化流程结束。")



def main():
    """主程序入口"""
    print("\n🚀 启动 Dreamina 自动化工具...")
    
    while True:
        display_menu()
        choice = get_user_choice()
        
        if choice == '0':
            print("\n👋 感谢使用，再见！")
            break
        elif choice == '1':
            handle_account_registration()
        elif choice == '2':
            handle_account_logout()
        elif choice == '3':
            handle_image_generation()
        
        # 操作完成后询问是否继续
        if choice != '0':
            continue_choice = input("\n是否返回主菜单？(y/n): ").strip().lower()
            if continue_choice != 'y':
                print("\n👋 感谢使用，再见！")
                break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 程序被中断，退出")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 程序运行出错: {e}")
        sys.exit(1) 