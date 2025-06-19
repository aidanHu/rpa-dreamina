#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
简化版 Dreamina 管理器
解决现有架构的混乱问题，提供稳定可靠的图片生成功能
"""

import time
import json
import threading
from datetime import datetime
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from bit_api import openBrowser, closeBrowser
from dreamina_operator import navigate_and_setup_dreamina_page, generate_image_on_page
from excel_processor import get_unprocessed_prompts_from_subfolders, mark_prompt_as_processed, get_excel_settings
from points_monitor import PointsMonitor
from element_config import get_url, get_element

class SimpleDreaminaManager:
    """简化版 Dreamina 管理器 - 专注稳定性和可靠性"""
    
    def __init__(self, config_file="gui_config.json", gui_mode=False, progress_callback=None):
        self.config_file = config_file
        self.config = self._load_config()
        self.running = False
        self.gui_mode = gui_mode  # 添加GUI模式标识
        self.progress_callback = progress_callback  # 进度回调函数
        
        # 获取浏览器配置
        self.browser_ids = self.config.get('browser_settings', {}).get('browser_ids', [])
        
        # 积分监控
        points_selector = get_element("points_monitoring", "primary_selector")
        self.points_monitor = PointsMonitor(custom_points_selector=points_selector)
        
        # 多窗口管理
        self.window_lock = threading.Lock()
        self.task_queue = []
        self.task_queue_lock = threading.Lock()
        self.results = {"success": 0, "failed": 0}
        self.results_lock = threading.Lock()
        
        # 进度追踪
        self.total_tasks = 0
        self.completed_tasks = 0
        self.failed_tasks = 0
        self.progress_lock = threading.Lock()
        
        # 保持窗口不关闭
        self.browsers = {}  # 存储浏览器实例
        self.keep_browsers_open = True  # 固定设置为不关闭窗口
        
        print(f"[SimpleDreaminaManager] 初始化完成，配置了 {len(self.browser_ids)} 个浏览器")
    
    def _update_progress(self, completed_delta=0, failed_delta=0):
        """更新进度并通知GUI"""
        with self.progress_lock:
            self.completed_tasks += completed_delta
            self.failed_tasks += failed_delta
            
            # 通知GUI更新进度
            if self.progress_callback:
                self.progress_callback(self.total_tasks, self.completed_tasks, self.failed_tasks)
    
    def _load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[SimpleDreaminaManager] 加载配置失败: {e}")
            return {}
    
    def start_processing(self, root_directory="Projects"):
        """开始处理任务 - 简化版本"""
        print("\n" + "="*80)
        print("🚀 启动简化版 Dreamina 图片生成")
        print("="*80)
        
        self.running = True
        
        try:
            # 获取所有待处理任务
            prompts_data_list = get_unprocessed_prompts_from_subfolders(root_directory, self.config)
            if not prompts_data_list:
                print("✅ 所有任务都已完成，或没有找到待处理任务")
                return True
            
            total_tasks = len(prompts_data_list)
            print(f"📋 找到 {total_tasks} 个待处理任务")
            
            # 初始化进度追踪
            with self.progress_lock:
                self.total_tasks = total_tasks
                self.completed_tasks = 0
                self.failed_tasks = 0
            
            # 初始化进度显示
            if self.progress_callback:
                self.progress_callback(self.total_tasks, 0, 0)
            
            # 根据浏览器数量决定处理方式
            if len(self.browser_ids) == 1:
                print("🖼️ 单窗口模式")
                return self._single_window_processing(prompts_data_list)
            else:
                print(f"🚀 多窗口并行模式 ({len(self.browser_ids)} 个窗口)")
                return self._parallel_multi_window_processing(prompts_data_list)
                
        except Exception as e:
            print(f"❌ 处理过程中发生错误: {e}")
            return False
        finally:
            self.running = False
    
    def _single_window_processing(self, prompts_data_list):
        """单窗口处理模式 - 最稳定的方式"""
        print("\n🖼️ 开始单窗口处理...")
        
        browser_id = self.browser_ids[0]
        
        try:
            # 启动浏览器
            print(f"🚀 启动浏览器: {browser_id}")
            browser_result = openBrowser(browser_id)
            
            if not browser_result or not browser_result.get('success'):
                print(f"❌ 浏览器启动失败: {browser_result}")
                return False
            
            data = browser_result.get('data', {})
            http_address = data.get('http', '')
            debug_address = f"http://{http_address}"
            
            print(f"✅ 浏览器启动成功: {debug_address}")
            
            with sync_playwright() as p:
                # 连接浏览器
                browser = p.chromium.connect_over_cdp(debug_address)
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                
                # 设置页面
                target_url = get_url("image_generate")
                page = navigate_and_setup_dreamina_page(context, target_url, "主窗口")
                
                if not page:
                    print("❌ 页面设置失败")
                    return False
                
                print("✅ 页面设置完成，开始处理任务")
                
                # 处理所有任务
                success_count = 0
                failed_count = 0
                first_generation = True  # 追踪是否是此窗口的首次生成
                
                for i, prompt_info in enumerate(prompts_data_list):
                    if not self.running:
                        print("⏹️ 处理被中断")
                        break
                    
                    print(f"\n[{i+1}/{len(prompts_data_list)}] 处理: {prompt_info['prompt'][:50]}...")
                    
                    try:
                        # 检查积分
                        points = self.points_monitor.check_points(page)
                        if points is not None and points < 2:
                            print(f"💰 积分不足 ({points})，停止单窗口任务处理")
                            print("🛑 单窗口模式已停止，如需继续请充值积分后重新启动")
                            break
                        
                        # 生成图片
                        result = generate_image_on_page(page, prompt_info, first_generation, "单窗口", self.config)
                        first_generation = False  # 首次生成后设置为False
                        
                        if result and len(result) > 0:
                            success_count += 1
                            print(f"✅ 成功生成 {len(result)} 张图片")
                            
                            # 更新进度
                            self._update_progress(completed_delta=1)
                            
                            # 标记为已处理
                            excel_settings = get_excel_settings(self.config)
                            mark_prompt_as_processed(
                                prompt_info['excel_file_path'], 
                                prompt_info['row_number'],
                                excel_settings["status_column"], 
                                excel_settings["status_text"]
                            )
                        else:
                            failed_count += 1
                            print("❌ 图片生成失败")
                            
                            # 更新进度
                            self._update_progress(failed_delta=1)
                        
                        # 任务间隔
                        time.sleep(5)
                        
                    except Exception as e:
                        failed_count += 1
                        print(f"❌ 处理任务时出错: {e}")
                        
                        # 更新进度
                        self._update_progress(failed_delta=1)
                
                # 统计结果
                print(f"\n📊 处理完成:")
                print(f"  成功: {success_count}")
                print(f"  失败: {failed_count}")
                print(f"  成功率: {success_count/(success_count+failed_count)*100:.1f}%")
                
                # 单窗口模式 - 保持窗口不关闭
                print("🖼️ 窗口将保持打开状态")
                print("👀 你可以在浏览器中查看处理结果")
                
                # 检查是否在GUI模式运行，避免input()阻塞
                if not self.gui_mode:
                    input("\n按回车键关闭窗口...")
                    
                return success_count > 0
                
        except Exception as e:
            print(f"❌ 单窗口处理失败: {e}")
            return False
        finally:
            # 不自动关闭浏览器，保持窗口打开
            pass
    
    def _parallel_multi_window_processing(self, prompts_data_list):
        """并行多窗口处理模式 - 真正的多窗口并行"""
        print("\n🚀 开始并行多窗口处理...")
        
        # 初始化任务队列
        with self.task_queue_lock:
            self.task_queue = prompts_data_list.copy()
        
        # 启动所有窗口
        threads = []
        for i, browser_id in enumerate(self.browser_ids):
            thread = threading.Thread(
                target=self._window_worker,
                args=(browser_id, i+1),
                name=f"窗口{i+1}"
            )
            threads.append(thread)
            thread.start()
            
            # 窗口启动间隔
            time.sleep(5)
        
        print(f"✅ 已启动 {len(threads)} 个窗口线程")
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        # 统计结果
        with self.results_lock:
            total_success = self.results["success"]
            total_failed = self.results["failed"]
        
        print(f"\n📊 并行多窗口处理完成:")
        print(f"  总成功: {total_success}")
        print(f"  总失败: {total_failed}")
        if total_success + total_failed > 0:
            print(f"  总成功率: {total_success/(total_success+total_failed)*100:.1f}%")
        
        # 保持窗口打开
        print("\n🖼️ 所有窗口将保持打开状态")
        print("👀 你可以在浏览器中查看处理结果")
        
        # 检查是否在GUI模式运行，避免input()阻塞
        if self.gui_mode:
            print("🖥️ GUI模式检测到，窗口将保持打开，程序继续运行")
        else:
            input("\n按回车键关闭所有窗口...")
            self._close_all_browsers()
        
        return total_success > 0
    
    def _window_worker(self, browser_id, window_num):
        """窗口工作线程"""
        print(f"🖼️ 窗口{window_num} 开始启动...")
        
        try:
            # 启动浏览器
            browser_result = openBrowser(browser_id)
            if not browser_result or not browser_result.get('success'):
                print(f"❌ 窗口{window_num} 浏览器启动失败: {browser_result}")
                # 更新失败统计
                with self.results_lock:
                    self.results["failed"] += 1
                return
            
            data = browser_result.get('data', {})
            http_address = data.get('http', '')
            debug_address = f"http://{http_address}"
            
            print(f"✅ 窗口{window_num} 浏览器启动成功: {debug_address}")
            
            # 存储浏览器信息
            self.browsers[browser_id] = {
                'window_num': window_num,
                'debug_address': debug_address
            }
            
            with sync_playwright() as p:
                # 连接浏览器
                browser = p.chromium.connect_over_cdp(debug_address)
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                
                # 设置页面
                target_url = get_url("image_generate")
                page = navigate_and_setup_dreamina_page(context, target_url, f"窗口{window_num}")
                
                if not page:
                    print(f"❌ 窗口{window_num} 页面设置失败")
                    # 更新失败统计
                    with self.results_lock:
                        self.results["failed"] += 1
                    return
                
                print(f"✅ 窗口{window_num} 页面设置完成，开始处理任务")
                
                # 处理任务
                task_count = 0
                success_count = 0
                failed_count = 0
                first_generation = True  # 追踪是否是此窗口的首次生成
                
                while self.running:
                    # 从队列获取任务
                    task = None
                    with self.task_queue_lock:
                        if self.task_queue:
                            task = self.task_queue.pop(0)
                    
                    if not task:
                        print(f"🏁 窗口{window_num} 没有更多任务，完成工作")
                        break
                    
                    task_count += 1
                    print(f"🖼️ 窗口{window_num} [{task_count}] 处理: {task['prompt'][:30]}...")
                    
                    try:
                        # 检查积分
                        points = self.points_monitor.check_points(page)
                        if points is not None and points < 2:
                            print(f"💰 窗口{window_num} 积分不足 ({points})，停止此窗口的任务处理")
                            # 将任务放回队列供其他窗口处理
                            with self.task_queue_lock:
                                self.task_queue.insert(0, task)
                            
                            # 直接退出此窗口的工作循环
                            print(f"🛑 窗口{window_num} 因积分不足已停止，等待重新启动任务时再检测积分")
                            break
                        
                        # 生成图片
                        result = generate_image_on_page(page, task, first_generation, f"窗口{window_num}", self.config)
                        first_generation = False  # 首次生成后设置为False
                        
                        if result and len(result) > 0:
                            success_count += 1
                            print(f"✅ 窗口{window_num} 成功生成 {len(result)} 张图片")
                            
                            # 更新进度
                            self._update_progress(completed_delta=1)
                            
                            # 标记为已处理
                            excel_settings = get_excel_settings(self.config)
                            mark_prompt_as_processed(
                                task['excel_file_path'], 
                                task['row_number'],
                                excel_settings["status_column"], 
                                excel_settings["status_text"]
                            )
                            
                            # 更新全局统计
                            with self.results_lock:
                                self.results["success"] += 1
                                
                        else:
                            failed_count += 1
                            print(f"❌ 窗口{window_num} 图片生成失败")
                            
                            # 更新进度
                            self._update_progress(failed_delta=1)
                            
                            # 更新全局统计
                            with self.results_lock:
                                self.results["failed"] += 1
                        
                        # 任务间隔
                        time.sleep(3)
                        
                    except Exception as e:
                        failed_count += 1
                        print(f"❌ 窗口{window_num} 处理任务时出错: {e}")
                        
                        # 更新进度
                        self._update_progress(failed_delta=1)
                        
                        # 更新全局统计
                        with self.results_lock:
                            self.results["failed"] += 1
                
                print(f"🏁 窗口{window_num} 完成所有任务: 成功 {success_count}, 失败 {failed_count}")
                
        except Exception as e:
            print(f"❌ 窗口{window_num} 工作线程失败: {e}")
        finally:
            # 不自动关闭浏览器，保持窗口打开
            pass
    
    def _close_all_browsers(self):
        """关闭所有浏览器"""
        print("🔒 正在关闭所有窗口...")
        for browser_id, info in self.browsers.items():
            try:
                closeBrowser(browser_id)
                print(f"🔒 窗口{info['window_num']} 已关闭")
            except Exception as e:
                print(f"⚠️ 关闭窗口{info['window_num']}失败: {e}")
    
    def stop(self):
        """停止处理"""
        self.running = False
        print("⏹️ 正在停止处理...")

# 便捷函数
def run_simple_dreamina(root_directory="Projects"):
    """运行简化版 Dreamina 处理器"""
    manager = SimpleDreaminaManager()
    return manager.start_processing(root_directory)

if __name__ == "__main__":
    # 测试运行
    run_simple_dreamina() 