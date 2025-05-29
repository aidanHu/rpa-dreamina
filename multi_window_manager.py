#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import threading
import queue
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except ImportError:
    # 兼容不同版本的 Playwright
    PlaywrightError = Exception
    PlaywrightTimeoutError = Exception

# 导入现有模块
from bit_api import openBrowser, closeBrowser
from dreamina_operator import navigate_and_setup_dreamina_page, generate_image_on_page, check_page_connection
from excel_processor import get_unprocessed_prompts_from_excel_folder, get_unprocessed_prompts_from_subfolders, mark_prompt_as_processed
from points_monitor import PointsMonitor
from element_config import get_url

class WindowInstance:
    """单个窗口实例"""
    
    def __init__(self, browser_id: str, name: str, priority: int, account_info: Dict):
        self.browser_id = browser_id
        self.name = name
        self.priority = priority
        self.account_info = account_info
        self.enabled = True
        self.status = "idle"  # idle, working, error, paused
        self.current_task = None
        self.browser = None
        self.context = None
        self.page = None
        self.debug_address = None
        self.last_activity = datetime.now()
        self.error_count = 0
        self.completed_tasks = 0
        self.failed_tasks = 0
        # 每个窗口都有自己的Playwright实例
        self.playwright_instance = None
        
    def __str__(self):
        return f"Window({self.name}, {self.status}, tasks: {self.completed_tasks}/{self.failed_tasks})"

class TaskQueue:
    """任务队列管理器"""
    
    def __init__(self):
        self.queue = queue.Queue()
        self.completed_tasks = []
        self.failed_tasks = []
        self.lock = threading.Lock()
        
    def add_task(self, task):
        """添加任务到队列"""
        self.queue.put(task)
        
    def get_task(self, timeout=1):
        """从队列获取任务"""
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None
            
    def mark_completed(self, task, result):
        """标记任务完成"""
        with self.lock:
            self.completed_tasks.append({
                'task': task,
                'result': result,
                'completed_at': datetime.now()
            })
            
    def mark_failed(self, task, error):
        """标记任务失败"""
        with self.lock:
            self.failed_tasks.append({
                'task': task,
                'error': str(error),
                'failed_at': datetime.now()
            })
            
    def get_stats(self):
        """获取统计信息"""
        with self.lock:
            return {
                'pending': self.queue.qsize(),
                'completed': len(self.completed_tasks),
                'failed': len(self.failed_tasks),
                'total_processed': len(self.completed_tasks) + len(self.failed_tasks)
            }

class MultiWindowManager:
    """多窗口管理器"""
    
    def __init__(self, config_file="user_config.json", multi_window_config_file="multi_window_config.json"):
        self.config_file = config_file
        self.multi_window_config_file = multi_window_config_file
        self.config = self._load_config()
        self.multi_window_config = self._load_multi_window_config()
        self.windows = []
        self.task_queue = TaskQueue()
        
        # 从元素配置文件获取积分选择器
        from element_config import get_element
        points_selector = get_element("points_monitoring", "primary_selector")
        self.points_monitor = PointsMonitor(custom_points_selector=points_selector)
        
        self.running = False
        # 移除共享的playwright_instance，每个窗口将有自己的实例
        
        # 统计信息
        self.start_time = None
        self.total_tasks = 0
        
        # 初始化窗口实例
        self._initialize_windows()
        
    def _load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ 配置文件 {self.config_file} 未找到")
            return {}
        except json.JSONDecodeError as e:
            print(f"❌ 配置文件格式错误: {e}")
            return {}
            
    def _load_multi_window_config(self):
        """加载多窗口配置文件"""
        try:
            with open(self.multi_window_config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️ 多窗口配置文件 {self.multi_window_config_file} 未找到，使用默认配置")
            return {
                "multi_window_settings": {
                    "max_concurrent_windows": 3,
                    "task_interval_seconds": 5,
                    "startup_delay_seconds": 8,
                    "error_retry_attempts": 3,
                    "thread_timeout_seconds": 300,
                    "window_restart_delay_seconds": 10
                },
                "thread_safety": {
                    "enable_independent_playwright": True,
                    "enable_thread_isolation": True,
                    "max_thread_wait_time": 30
                },
                "error_handling": {
                    "max_consecutive_errors": 5,
                    "error_cooldown_seconds": 30,
                    "auto_restart_on_error": True
                }
            }
        except json.JSONDecodeError as e:
            print(f"❌ 多窗口配置文件格式错误: {e}")
            return {}
            
    def _save_config(self):
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ 保存配置文件失败: {e}")
            
    def _initialize_windows(self):
        """初始化窗口实例"""
        browser_ids = self.config.get('browser_settings', {}).get('browser_ids', [])
        
        for i, browser_id in enumerate(browser_ids):
            window_name = f"窗口{i+1}" if i > 0 else "主窗口"
            window = WindowInstance(
                browser_id=browser_id,
                name=window_name,
                priority=i+1,
                account_info={}
            )
            self.windows.append(window)
                
        print(f"[MultiWindowManager] 初始化了 {len(self.windows)} 个窗口实例")
        
    def _setup_window(self, window: WindowInstance) -> bool:
        """设置单个窗口"""
        max_retries = self.multi_window_config.get('error_handling', {}).get('max_retry_attempts', 5)
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                print(f"[{window.name}] 正在启动浏览器... (尝试 {retry_count + 1}/{max_retries})")
                
                # 为每个窗口创建独立的Playwright实例
                if not window.playwright_instance:
                    window.playwright_instance = sync_playwright().start()
                    print(f"[{window.name}] ✅ 创建独立的Playwright实例")
                
                # 打开浏览器
                response = openBrowser(window.browser_id)
                if not response or not response.get('success'):
                    print(f"[{window.name}] ❌ 启动浏览器失败: {response}")
                    retry_count += 1
                    time.sleep(5)
                    continue
                    
                # 获取调试地址
                data = response.get('data', {})
                http_address = data.get('http')
                
                if not http_address:
                    print(f"[{window.name}] ❌ 未获取到调试地址")
                    retry_count += 1
                    time.sleep(5)
                    continue
                    
                if not http_address.startswith(("http://", "https://")):
                    window.debug_address = f"http://{http_address}"
                else:
                    window.debug_address = http_address
                    
                print(f"[{window.name}] ✅ 浏览器启动成功，调试地址: {window.debug_address}")
                
                # 使用窗口自己的Playwright实例连接到浏览器
                try:
                    window.browser = window.playwright_instance.chromium.connect_over_cdp(window.debug_address)
                except Exception as e:
                    print(f"[{window.name}] ❌ 连接到浏览器失败: {e}")
                    retry_count += 1
                    time.sleep(5)
                    continue
                
                if not window.browser.contexts:
                    print(f"[{window.name}] ❌ 浏览器中没有上下文")
                    retry_count += 1
                    time.sleep(5)
                    continue
                    
                window.context = window.browser.contexts[0]
                
                # 关闭所有其他标签页
                pages = window.context.pages
                if len(pages) > 1:
                    print(f"[{window.name}] 正在关闭其他标签页...")
                    for page in pages[1:]:  # 保留第一个标签页
                        try:
                            page.close()
                        except Exception as e:
                            print(f"[{window.name}] 关闭标签页时出错: {e}")
                
                # 设置Dreamina页面
                dreamina_url = get_url("image_generate")
                window.page = navigate_and_setup_dreamina_page(window.context, dreamina_url)
                
                if not window.page or window.page.is_closed():
                    print(f"[{window.name}] ❌ 设置Dreamina页面失败")
                    retry_count += 1
                    time.sleep(5)
                    continue
                    
                # 等待页面完全加载
                try:
                    window.page.wait_for_load_state("networkidle", timeout=60000)
                except Exception as e:
                    print(f"[{window.name}] ⚠️ 等待网络空闲超时: {e}")
                    # 继续执行，因为页面可能已经部分加载
                
                # 延迟检测积分
                startup_delay = self.multi_window_config.get('multi_window_settings', {}).get('startup_delay_seconds', 25)
                print(f"[{window.name}] 等待 {startup_delay} 秒后检测积分...")
                time.sleep(startup_delay)
                
                # 验证页面是否真正可用
                try:
                    page_title = window.page.title()
                    if not page_title or "Dreamina" not in page_title:
                        print(f"[{window.name}] ⚠️ 页面标题异常: {page_title}")
                        retry_count += 1
                        time.sleep(5)
                        continue
                except Exception as e:
                    print(f"[{window.name}] ❌ 验证页面时出错: {e}")
                    retry_count += 1
                    time.sleep(5)
                    continue
                
                window.status = "idle"
                window.last_activity = datetime.now()
                print(f"[{window.name}] ✅ 窗口设置完成")
                return True
                
            except Exception as e:
                print(f"[{window.name}] ❌ 设置窗口时发生错误: {e}")
                retry_count += 1
                if retry_count < max_retries:
                    print(f"[{window.name}] 🔄 将在5秒后进行第{retry_count + 1}次尝试...")
                    time.sleep(5)
                else:
                    window.status = "error"
                    window.error_count += 1
                    return False
        
        window.status = "error"
        window.error_count += 1
        return False
            
    def _cleanup_window(self, window: WindowInstance):
        """清理窗口资源"""
        try:
            if window.page and not window.page.is_closed():
                window.page.close()
            if window.browser:
                window.browser.close()
            if window.playwright_instance:
                window.playwright_instance.stop()
                window.playwright_instance = None
            closeBrowser(window.browser_id)
            print(f"[{window.name}] 窗口资源已清理")
        except Exception as e:
            print(f"[{window.name}] 清理窗口时出错: {e}")
            
    def _worker_thread(self, window: WindowInstance):
        """工作线程函数"""
        print(f"[{window.name}] 工作线程启动")
        
        # 在线程开始时设置窗口
        if not self._setup_window(window):
            print(f"[{window.name}] ❌ 初始窗口设置失败，线程退出")
            return
        
        while self.running:
            try:
                # 检查窗口状态
                if window.status == "error":
                    print(f"[{window.name}] 窗口处于错误状态，尝试重启...")
                    if self._restart_window(window):
                        continue
                    else:
                        time.sleep(10)  # 重启失败，等待后重试
                        continue
                        
                if window.status == "paused":
                    time.sleep(5)
                    continue
                    
                # 获取任务
                task = self.task_queue.get_task(timeout=2)
                if not task:
                    continue
                    
                window.status = "working"
                window.current_task = task
                window.last_activity = datetime.now()
                
                print(f"[{window.name}] 开始处理任务: {task['prompt'][:30]}...")
                
                # 检查页面连接
                if not check_page_connection(window.page):
                    print(f"[{window.name}] 页面连接断开，尝试重新设置...")
                    if not self._restart_window(window):
                        self.task_queue.mark_failed(task, "页面连接失败")
                        continue
                        
                # 检查积分
                if self.config.get('points_monitoring', {}).get('enabled', True):
                    points_balance = self.points_monitor.check_points(window.page)
                    if points_balance is not None:
                        window.account_info['points_balance'] = points_balance
                        window.account_info['last_points_check'] = datetime.now().isoformat()
                        
                        min_threshold = self.config.get('points_monitoring', {}).get('min_points_threshold', 4)
                        if points_balance < min_threshold:
                            print(f"[{window.name}] ⚠️ 积分不足 ({points_balance} < {min_threshold})，暂停窗口")
                            window.status = "paused"
                            self.task_queue.add_task(task)  # 将任务放回队列
                            continue
                            
                # 执行图片生成任务
                result = generate_image_on_page(window.page, task)
                
                if result and len(result) > 0:
                    # 任务成功
                    window.completed_tasks += 1
                    self.task_queue.mark_completed(task, result)
                    
                    # 标记Excel中的状态
                    from excel_processor import get_excel_settings
                    excel_settings = get_excel_settings()
                    mark_prompt_as_processed(task['excel_file_path'], task['row_number'], 
                                           excel_settings["status_column"], excel_settings["status_text"])
                    
                    print(f"[{window.name}] ✅ 任务完成: {task['prompt'][:30]}... (生成 {len(result)} 张图片)")
                else:
                    # 任务失败
                    window.failed_tasks += 1
                    self.task_queue.mark_failed(task, "图片生成失败")
                    print(f"[{window.name}] ❌ 任务失败: {task['prompt'][:30]}...")
                    
                window.status = "idle"
                window.current_task = None
                
                # 任务间隔
                interval = self.multi_window_config.get('multi_window_settings', {}).get('task_interval_seconds', 5)
                time.sleep(interval)
                
            except Exception as e:
                print(f"[{window.name}] 工作线程出错: {e}")
                window.status = "error"
                window.error_count += 1
                if window.current_task:
                    self.task_queue.mark_failed(window.current_task, str(e))
                    window.current_task = None
                
                # 检查是否超过最大连续错误次数
                max_errors = self.multi_window_config.get('error_handling', {}).get('max_consecutive_errors', 5)
                if window.error_count >= max_errors:
                    print(f"[{window.name}] ❌ 连续错误次数过多 ({window.error_count})，停止此窗口")
                    break
                
                # 错误冷却时间
                cooldown = self.multi_window_config.get('error_handling', {}).get('error_cooldown_seconds', 30)
                time.sleep(cooldown)
                
        # 线程结束时清理资源
        self._cleanup_window(window)
        print(f"[{window.name}] 工作线程结束")
        
    def _restart_window(self, window: WindowInstance) -> bool:
        """重启窗口"""
        try:
            print(f"[{window.name}] 正在重启窗口...")
            
            # 清理旧资源（但不关闭playwright实例）
            if window.page and not window.page.is_closed():
                window.page.close()
            if window.browser:
                window.browser.close()
            closeBrowser(window.browser_id)
            
            # 使用配置的重启延时
            restart_delay = self.multi_window_config.get('multi_window_settings', {}).get('window_restart_delay_seconds', 10)
            time.sleep(restart_delay)
            
            if self._setup_window(window):
                window.error_count = 0
                print(f"[{window.name}] ✅ 窗口重启成功")
                return True
            else:
                print(f"[{window.name}] ❌ 窗口重启失败")
                return False
                
        except Exception as e:
            print(f"[{window.name}] 重启窗口时出错: {e}")
            return False
            
    def start_multi_window_processing(self, root_directory="Projects"):
        """启动多窗口处理"""
        print("\n" + "="*80)
        print("🚀 启动多窗口并行图片生成系统")
        print("="*80)
        
        # 检查配置
        browser_ids = self.config.get('browser_settings', {}).get('browser_ids', [])
        if len(browser_ids) <= 1:
            print("❌ 多窗口功能需要配置多个浏览器ID，当前只有一个或没有配置")
            return False
            
        if not self.windows:
            print("❌ 没有可用的窗口实例")
            return False
            
        # 加载任务
        print("\n📋 加载未处理的提示词...")
        prompts_data = get_unprocessed_prompts_from_subfolders(root_directory)
        
        if not prompts_data:
            print("✅ 所有提示词都已处理完成")
            return True
            
        # 将任务添加到队列
        for prompt_data in prompts_data:
            self.task_queue.add_task(prompt_data)
            
        self.total_tasks = len(prompts_data)
        print(f"📝 已加载 {self.total_tasks} 个待处理任务")
        
        try:
            # 启动工作线程（每个线程会自己设置窗口）
            self.running = True
            self.start_time = datetime.now()
            threads = []
            
            print(f"\n🎯 启动 {len(self.windows)} 个工作线程...")
            for i, window in enumerate(self.windows):
                # 增加线程启动间隔
                thread_startup_delay = self.multi_window_config.get('thread_safety', {}).get('thread_startup_delay', 5)
                if i > 0:  # 第一个线程不需要延迟
                    print(f"⏳ 等待 {thread_startup_delay} 秒后启动下一个线程...")
                    time.sleep(thread_startup_delay)
                
                thread = threading.Thread(target=self._worker_thread, args=(window,))
                thread.daemon = True
                thread.start()
                threads.append(thread)
                print(f"✅ {window.name} 工作线程已启动")
                
                # 等待线程初始化完成
                startup_delay = self.multi_window_config.get('multi_window_settings', {}).get('startup_delay_seconds', 15)
                print(f"⏳ 等待 {startup_delay} 秒确保窗口初始化完成...")
                time.sleep(startup_delay)
                
            # 验证所有窗口是否成功启动
            active_windows = [w for w in self.windows if w.status in ["idle", "working"]]
            if len(active_windows) < len(self.windows):
                print(f"⚠️ 警告：只有 {len(active_windows)}/{len(self.windows)} 个窗口成功启动")
                for window in self.windows:
                    if window.status not in ["idle", "working"]:
                        print(f"❌ {window.name} 启动失败，状态：{window.status}")
            
            # 监控进度
            self._monitor_progress()
            
            # 等待所有任务完成
            print("\n⏳ 等待所有任务完成...")
            while self.running:
                stats = self.task_queue.get_stats()
                active_windows = [w for w in self.windows if w.status in ["idle", "working"]]
                
                if stats['pending'] == 0 and all(w.status == "idle" for w in active_windows):
                    print("✅ 所有任务已完成")
                    break
                    
                # 检查是否所有窗口都出错了
                if not active_windows:
                    print("❌ 所有窗口都出错了，停止处理")
                    break
                    
                time.sleep(5)
                
        finally:
            # 停止所有线程
            print("\n🧹 停止所有线程...")
            self.running = False
            
            # 等待线程结束（资源清理在线程内部完成）
            for thread in threads:
                thread.join(timeout=10)
                
        # 显示最终统计
        self._show_final_stats()
        return True
        
    def _monitor_progress(self):
        """监控进度"""
        def monitor():
            while self.running:
                time.sleep(30)  # 每30秒显示一次进度
                self._show_progress()
                
        monitor_thread = threading.Thread(target=monitor)
        monitor_thread.daemon = True
        monitor_thread.start()
        
    def _show_progress(self):
        """显示进度信息"""
        stats = self.task_queue.get_stats()
        elapsed = datetime.now() - self.start_time if self.start_time else 0
        
        print(f"\n📊 进度报告 (运行时间: {elapsed})")
        print(f"  总任务: {self.total_tasks}")
        print(f"  待处理: {stats['pending']}")
        print(f"  已完成: {stats['completed']}")
        print(f"  失败: {stats['failed']}")
        print(f"  完成率: {stats['completed']/self.total_tasks*100:.1f}%" if self.total_tasks > 0 else "  完成率: 0%")
        
        print(f"\n窗口状态:")
        for window in self.windows:
            points = window.account_info.get('points_balance', 'N/A')
            print(f"  {window.name}: {window.status} (完成: {window.completed_tasks}, 失败: {window.failed_tasks}, 积分: {points})")
            
    def _show_final_stats(self):
        """显示最终统计"""
        stats = self.task_queue.get_stats()
        elapsed = datetime.now() - self.start_time if self.start_time else 0
        
        print("\n" + "="*80)
        print("📊 最终统计报告")
        print("="*80)
        print(f"总运行时间: {elapsed}")
        print(f"总任务数: {self.total_tasks}")
        print(f"成功完成: {stats['completed']}")
        print(f"失败任务: {stats['failed']}")
        print(f"成功率: {stats['completed']/self.total_tasks*100:.1f}%" if self.total_tasks > 0 else "成功率: 0%")
        
        print(f"\n各窗口表现:")
        for window in self.windows:
            total_tasks = window.completed_tasks + window.failed_tasks
            success_rate = window.completed_tasks / total_tasks * 100 if total_tasks > 0 else 0
            print(f"  {window.name}: 完成 {window.completed_tasks}, 失败 {window.failed_tasks}, 成功率 {success_rate:.1f}%")
            
        print("="*80)

# 使用示例
if __name__ == "__main__":
    manager = MultiWindowManager()
    manager.start_multi_window_processing() 