#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import time
from datetime import datetime
from typing import Optional, Dict
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from element_config import get_element_list

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
        检查当前页面的积分余额
        
        Args:
            page: Playwright页面对象
            timeout: 超时时间（毫秒）
            
        Returns:
            int: 积分余额，如果无法获取则返回None
        """
        try:
            print("[PointsMonitor] 开始检查积分余额...")
            
            # 方法1: 尝试从页面元素中提取积分信息
            points = self._extract_points_from_elements(page, timeout)
            if points is not None:
                print(f"[PointsMonitor] ✅ 从页面元素获取积分: {points}")
                return points
                
            # 方法2: 检查是否有积分不足的提示
            if self._check_insufficient_points_warning(page):
                print("[PointsMonitor] ⚠️ 检测到积分不足提示，返回积分为0")
                return 0
                
            # 方法3: 尝试从页面文本中提取积分
            points = self._extract_points_from_page_text(page)
            if points is not None:
                print(f"[PointsMonitor] ✅ 从页面文本获取积分: {points}")
                return points
                
            print("[PointsMonitor] ⚠️ 无法获取积分信息")
            return None
            
        except Exception as e:
            print(f"[PointsMonitor] ❌ 检查积分时出错: {e}")
            return None
            
    def _extract_points_from_elements(self, page: Page, timeout: int) -> Optional[int]:
        """从页面元素中提取积分"""
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
        """从整个页面文本中提取积分"""
        try:
            # 获取页面的所有文本内容
            page_text = page.text_content()
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
        """检查是否有积分不足的警告"""
        try:
            page_text = page.text_content()
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
        等待积分刷新
        
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
                # 刷新页面
                page.reload(wait_until="domcontentloaded")
                time.sleep(2)
                
                # 检查积分
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
        在图片生成过程中监控积分变化
        
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