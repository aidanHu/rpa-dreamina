#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import time
import threading
from datetime import datetime
from typing import Optional, Dict
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from element_config import get_element_list
import queue
import json

# 全局积分检测锁，防止多线程同时检测积分
_points_check_lock = threading.Lock()

# 线程安全的积分缓存（避免频繁跨线程调用）
_points_cache = {}
_points_cache_lock = threading.Lock()
_cache_expiry_seconds = 10  # 缓存10秒

class PointsMonitor:
    """积分监控器"""
    
    def __init__(self, custom_points_selector=None):
        # 积分相关的XPath选择器 - 从配置文件获取
        if custom_points_selector:
            # 如果提供了自定义选择器，优先使用
            self.points_selectors = [custom_points_selector]
            # 添加配置文件中的备用选择器
            fallback_selectors = get_element_list("points_monitoring", "fallback_selectors")
            self.points_selectors.extend(fallback_selectors)
        else:
            # 从配置文件获取所有选择器
            primary_selector = get_element_list("points_monitoring", "primary_selector")
            fallback_selectors = get_element_list("points_monitoring", "fallback_selectors")
            self.points_selectors = primary_selector + fallback_selectors
        
        # 积分不足的提示信息
        self.insufficient_points_indicators = [
            "积分不足",
            "余额不足", 
            "insufficient points",
            "not enough points",
            "insufficient balance",
            "余额为0",
            "积分为0"
        ]
        
    def check_points(self, page: Page, timeout: int = 10000) -> Optional[int]:
        """
        检查当前页面的积分余额 - 最终线程安全版本
        
        Args:
            page: Playwright页面对象
            timeout: 超时时间（毫秒）
            
        Returns:
            int: 积分余额，如果无法获取则返回None
        """
        page_id = id(page)
        current_time = time.time()
        current_thread_id = threading.current_thread().ident
        
        # 🚀 首先检查缓存
        with _points_cache_lock:
            if page_id in _points_cache:
                cache_entry = _points_cache[page_id]
                if current_time - cache_entry['timestamp'] < _cache_expiry_seconds:
                    print(f"[PointsMonitor] 📱 使用缓存积分: {cache_entry['points']}")
                    return cache_entry['points']
                else:
                    # 缓存过期，删除
                    del _points_cache[page_id]
        
        # 🧵 检测跨线程调用，如果是跨线程则直接返回None，避免greenlet错误
        try:
            # 🔍 尝试一次非常简单的测试操作来检测线程兼容性
            page.url  # 这是一个简单的属性访问，通常安全
        except Exception as thread_error:
            if "Cannot switch to a different thread" in str(thread_error) or "greenlet" in str(thread_error).lower():
                print(f"[PointsMonitor] 🚫 检测到跨线程访问，返回None避免greenlet错误")
                return None
            # 其他错误继续处理
        
        # 🔒 使用锁保护积分检测，避免多线程冲突
        with _points_check_lock:
            try:
                print("[PointsMonitor] 开始检查积分余额...")
                
                # 🔧 尝试简单安全的方法
                result = self._safe_extract_points(page, timeout)
                
                # 🗃️ 更新缓存
                if result is not None:
                    with _points_cache_lock:
                        _points_cache[page_id] = {
                            'points': result,
                            'timestamp': current_time
                        }
                
                return result
                
            except Exception as e:
                # 🚫 如果遇到greenlet错误，直接返回None
                if "Cannot switch to a different thread" in str(e) or "greenlet" in str(e).lower():
                    print(f"[PointsMonitor] 🚫 检测到greenlet错误，跳过积分检测")
                    return None
                    
                print(f"[PointsMonitor] ❌ 检查积分时出错: {e}")
                return None

    def _safe_extract_points(self, page: Page, timeout: int) -> Optional[int]:
        """安全的积分提取方法 - 最小化页面操作，增强greenlet错误处理"""
        try:
            # 🔧 方法1：尝试最简单的页面文本提取
            try:
                print("[PointsMonitor] 🔍 尝试页面文本提取...")
                
                # 使用try-catch包装每个页面操作
                page_text = None
                try:
                    page_text = page.text_content("body")
                except Exception as pe:
                    # 🚫 检查是否是greenlet错误
                    if "Cannot switch to a different thread" in str(pe) or "greenlet" in str(pe).lower():
                        print(f"[PointsMonitor] 🚫 text_content遇到greenlet错误，跳过")
                        return None
                    
                    # 如果直接text_content失败，尝试其他方法
                    print(f"[PointsMonitor] ⚠️ text_content失败: {pe}")
                    try:
                        # 尝试通过evaluate获取文本
                        page_text = page.evaluate("() => document.body.innerText")
                    except Exception as ee:
                        if "Cannot switch to a different thread" in str(ee) or "greenlet" in str(ee).lower():
                            print(f"[PointsMonitor] 🚫 evaluate遇到greenlet错误，跳过")
                            return None
                        print(f"[PointsMonitor] ⚠️ evaluate也失败: {ee}")
                        page_text = None
                
                if page_text:
                    points = self._parse_points_from_page_text(page_text)
                    if points is not None:
                        print(f"[PointsMonitor] ✅ 从页面文本获取积分: {points}")
                        return points
                        
            except Exception as e:
                if "Cannot switch to a different thread" in str(e) or "greenlet" in str(e).lower():
                    print(f"[PointsMonitor] 🚫 页面文本提取遇到greenlet错误，跳过")
                    return None
                print(f"[PointsMonitor] ⚠️ 页面文本提取失败: {e}")
            
            # 🔧 方法2：尝试特定元素提取（更安全的方式）
            try:
                print("[PointsMonitor] 🔍 尝试元素提取...")
                
                # 只尝试最可靠的选择器
                reliable_selectors = [
                    "//span[contains(@class, 'creditText')]",
                    "//span[contains(text(), '积分')]",
                ]
                
                for selector in reliable_selectors:
                    try:
                        elements = page.locator(f"xpath={selector}")
                        count = elements.count()
                        if count > 0:
                            for i in range(min(count, 3)):  # 最多检查3个元素
                                try:
                                    element = elements.nth(i)
                                    if element.is_visible(timeout=1000):  # 短超时
                                        text = element.text_content()
                                        if text:
                                            points = self._parse_points_from_text(text)
                                            if points is not None:
                                                print(f"[PointsMonitor] ✅ 从元素获取积分: {points}")
                                                return points
                                except Exception as elem_e:
                                    # 🚫 检查greenlet错误
                                    if "Cannot switch to a different thread" in str(elem_e) or "greenlet" in str(elem_e).lower():
                                        print(f"[PointsMonitor] 🚫 元素操作遇到greenlet错误，跳过此元素")
                                        continue
                                    # 单个元素失败不影响其他元素
                                    continue
                    except Exception as sel_e:
                        # 🚫 检查greenlet错误
                        if "Cannot switch to a different thread" in str(sel_e) or "greenlet" in str(sel_e).lower():
                            print(f"[PointsMonitor] 🚫 选择器操作遇到greenlet错误，跳过此选择器")
                            continue
                        # 单个选择器失败不影响其他选择器
                        continue
                        
            except Exception as e:
                if "Cannot switch to a different thread" in str(e) or "greenlet" in str(e).lower():
                    print(f"[PointsMonitor] 🚫 元素提取遇到greenlet错误，跳过")
                    return None
                print(f"[PointsMonitor] ⚠️ 元素提取失败: {e}")
                
            # 🔧 方法3：检查积分不足提示
            try:
                print("[PointsMonitor] 🔍 检查积分不足提示...")
                
                insufficient_indicators = [
                    "积分不足", "余额不足", "insufficient points"
                ]
                
                for indicator in insufficient_indicators:
                    try:
                        locator = page.locator(f"text={indicator}")
                        if locator.count() > 0:
                            print("[PointsMonitor] ⚠️ 检测到积分不足提示，返回积分为0")
                            return 0
                    except Exception as ind_e:
                        # 🚫 检查greenlet错误
                        if "Cannot switch to a different thread" in str(ind_e) or "greenlet" in str(ind_e).lower():
                            print(f"[PointsMonitor] 🚫 积分不足检查遇到greenlet错误，跳过")
                            continue
                        continue
                        
            except Exception as e:
                if "Cannot switch to a different thread" in str(e) or "greenlet" in str(e).lower():
                    print(f"[PointsMonitor] 🚫 积分不足提示检查遇到greenlet错误，跳过")
                    return None
                print(f"[PointsMonitor] ⚠️ 检查积分不足提示失败: {e}")
            
            print("[PointsMonitor] ⚠️ 所有方法都失败，无法获取积分信息")
            return None
            
        except Exception as e:
            if "Cannot switch to a different thread" in str(e) or "greenlet" in str(e).lower():
                print(f"[PointsMonitor] 🚫 安全积分提取遇到greenlet错误，完全跳过")
                return None
            print(f"[PointsMonitor] ❌ 安全积分提取失败: {e}")
            return None

    def _parse_points_from_page_text(self, page_text: str) -> Optional[int]:
        """从页面文本中解析积分（纯文本处理，无DOM操作）"""
        if not page_text:
            return None
            
        # 使用正则表达式查找积分相关信息
        patterns = [
            r'积分[：:]\s*(\d+)',
            r'剩余积分[：:]\s*(\d+)', 
            r'余额[：:]\s*(\d+)',
            r'points[：:]\s*(\d+)',
            r'remaining\s+points[：:]\s*(\d+)',
            r'balance[：:]\s*(\d+)',
            # 查找数字后跟"积分"的模式
            r'(\d+)\s*积分',
            r'(\d+)\s*points'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, page_text, re.IGNORECASE)
            if matches:
                try:
                    points = int(matches[0])
                    # 验证积分数值的合理性（0-10000之间）
                    if 0 <= points <= 10000:
                        return points
                except ValueError:
                    continue
                    
        return None
            
    def _extract_points_from_elements(self, page: Page, timeout: int) -> Optional[int]:
        """从页面元素中提取积分 - 已在check_points中加锁保护"""
        for selector in self.points_selectors:
            try:
                # 等待元素出现
                elements = page.locator(f"xpath={selector}")
                if elements.count() > 0:
                    for i in range(elements.count()):
                        element = elements.nth(i)
                        if element.is_visible(timeout=2000):
                            text = element.text_content()
                            if text:
                                points = self._parse_points_from_text(text)
                                if points is not None:
                                    return points
            except PlaywrightTimeoutError:
                continue
            except Exception as e:
                print(f"[PointsMonitor] 检查选择器 {selector} 时出错: {e}")
                continue
                
        return None
        
    def _extract_points_from_page_text(self, page: Page) -> Optional[int]:
        """从整个页面文本中提取积分 - 已在check_points中加锁保护"""
        try:
            # 获取页面的所有文本内容
            page_text = page.text_content("body")
            if not page_text:
                return None
                
            # 使用正则表达式查找积分相关信息
            patterns = [
                r'积分[：:]\s*(\d+)',
                r'剩余积分[：:]\s*(\d+)',
                r'余额[：:]\s*(\d+)',
                r'points[：:]\s*(\d+)',
                r'remaining\s+points[：:]\s*(\d+)',
                r'balance[：:]\s*(\d+)',
                # 查找数字后跟"积分"的模式
                r'(\d+)\s*积分',
                r'(\d+)\s*points'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, page_text, re.IGNORECASE)
                if matches:
                    try:
                        points = int(matches[0])
                        # 验证积分数值的合理性（0-10000之间）
                        if 0 <= points <= 10000:
                            return points
                    except ValueError:
                        continue
                        
        except Exception as e:
            print(f"[PointsMonitor] 从页面文本提取积分时出错: {e}")
            
        return None
        
    def _parse_points_from_text(self, text: str) -> Optional[int]:
        """从文本中解析积分数值"""
        if not text:
            return None
            
        # 清理文本
        text = text.strip()
        
        # 直接是数字的情况
        if text.isdigit():
            points = int(text)
            # 验证合理性
            if 0 <= points <= 10000:
                return points
                
        # 包含积分关键词的情况
        patterns = [
            r'(\d+)\s*积分',
            r'积分[：:]\s*(\d+)',
            r'(\d+)\s*points',
            r'points[：:]\s*(\d+)',
            r'余额[：:]\s*(\d+)',
            r'balance[：:]\s*(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    points = int(match.group(1))
                    if 0 <= points <= 10000:
                        return points
                except ValueError:
                    continue
                    
        return None
        
    def _check_insufficient_points_warning(self, page: Page) -> bool:
        """检查是否有积分不足的警告 - 已在check_points中加锁保护"""
        try:
            page_text = page.text_content("body")
            if not page_text:
                return False
                
            for indicator in self.insufficient_points_indicators:
                if indicator in page_text:
                    return True
                    
            return False
            
        except Exception as e:
            print(f"[PointsMonitor] 检查积分不足警告时出错: {e}")
            return False
            
    def wait_for_points_refresh(self, page: Page, expected_points: int = None, max_wait_seconds: int = 60) -> bool:
        """
        等待积分刷新 - 线程安全版本
        
        Args:
            page: Playwright页面对象
            expected_points: 期望的积分数量
            max_wait_seconds: 最大等待时间（秒）
            
        Returns:
            bool: 是否成功刷新
        """
        print(f"[PointsMonitor] 等待积分刷新...")
        
        start_time = time.time()
        while time.time() - start_time < max_wait_seconds:
            try:
                # 🔒 使用锁保护页面刷新操作
                with _points_check_lock:
                    # 刷新页面
                    page.reload(wait_until="domcontentloaded")
                    time.sleep(2)
                
                # 检查积分（check_points内部已有锁保护）
                current_points = self.check_points(page)
                if current_points is not None:
                    if expected_points is None or current_points >= expected_points:
                        print(f"[PointsMonitor] ✅ 积分刷新成功: {current_points}")
                        return True
                        
                print(f"[PointsMonitor] 当前积分: {current_points}，继续等待...")
                time.sleep(5)
                
            except Exception as e:
                print(f"[PointsMonitor] 等待积分刷新时出错: {e}")
                time.sleep(5)
                
        print(f"[PointsMonitor] ⏰ 积分刷新等待超时")
        return False
        
    def monitor_points_during_generation(self, page: Page, initial_points: int, callback=None) -> Dict:
        """
        在图片生成过程中监控积分变化 - 线程安全版本
        
        Args:
            page: Playwright页面对象
            initial_points: 初始积分
            callback: 积分变化时的回调函数
            
        Returns:
            Dict: 监控结果
        """
        print(f"[PointsMonitor] 开始监控积分变化，初始积分: {initial_points}")
        
        monitoring_result = {
            'initial_points': initial_points,
            'final_points': None,
            'points_consumed': 0,
            'monitoring_duration': 0,
            'points_history': []
        }
        
        start_time = time.time()
        last_check_time = start_time
        
        try:
            while True:
                current_time = time.time()
                
                # 每10秒检查一次积分
                if current_time - last_check_time >= 10:
                    current_points = self.check_points(page)
                    
                    if current_points is not None:
                        monitoring_result['points_history'].append({
                            'timestamp': datetime.now().isoformat(),
                            'points': current_points
                        })
                        
                        # 检查积分是否发生变化
                        if current_points != initial_points:
                            points_consumed = initial_points - current_points
                            monitoring_result['points_consumed'] = points_consumed
                            monitoring_result['final_points'] = current_points
                            
                            print(f"[PointsMonitor] 积分变化: {initial_points} -> {current_points} (消耗: {points_consumed})")
                            
                            if callback:
                                callback(current_points, points_consumed)
                                
                            # 如果积分不足，停止监控
                            if current_points <= 0:
                                print("[PointsMonitor] ⚠️ 积分已耗尽")
                                break
                                
                    last_check_time = current_time
                    
                # 检查是否应该停止监控（例如，生成完成）
                # 这里可以添加更多的停止条件
                
                time.sleep(2)
                
        except KeyboardInterrupt:
            print("[PointsMonitor] 积分监控被用户中断")
        except Exception as e:
            print(f"[PointsMonitor] 积分监控过程中出错: {e}")
        finally:
            monitoring_result['monitoring_duration'] = time.time() - start_time
            
        return monitoring_result
        
    def estimate_remaining_generations(self, current_points: int, points_per_generation: int = 4) -> int:
        """
        估算剩余可生成次数
        
        Args:
            current_points: 当前积分
            points_per_generation: 每次生成消耗的积分
            
        Returns:
            int: 估算的剩余生成次数
        """
        if current_points <= 0 or points_per_generation <= 0:
            return 0
            
        return current_points // points_per_generation

# 使用示例
if __name__ == "__main__":
    # 这里可以添加测试代码
    pass 