#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import random
from typing import Optional, Tuple, Union
from playwright.sync_api import Page, Locator

class HumanBehavior:
    """模拟人类行为的工具类"""
    
    @staticmethod
    def random_delay(min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        """随机等待一段时间"""
        time.sleep(random.uniform(min_seconds, max_seconds))
    
    @staticmethod
    def simulate_mouse_movement(page: Page, target_x: Optional[int] = None, target_y: Optional[int] = None) -> None:
        """模拟鼠标移动
        
        Args:
            page: Playwright页面对象
            target_x: 目标X坐标，如果为None则随机生成
            target_y: 目标Y坐标，如果为None则随机生成
        """
        if target_x is None:
            target_x = random.randint(0, page.viewport_size['width'])
        if target_y is None:
            target_y = random.randint(0, page.viewport_size['height'])
            
        # 获取当前鼠标位置
        current_pos = page.mouse.position()
        
        # 计算移动步数
        steps = random.randint(5, 10)
        
        # 计算每步的移动距离
        step_x = (target_x - current_pos['x']) / steps
        step_y = (target_y - current_pos['y']) / steps
        
        # 逐步移动鼠标
        for i in range(steps):
            current_x = current_pos['x'] + step_x * (i + 1)
            current_y = current_pos['y'] + step_y * (i + 1)
            page.mouse.move(current_x, current_y)
            time.sleep(random.uniform(0.01, 0.03))
    
    @staticmethod
    def simulate_scroll(page: Page, direction: str = 'random', distance: Optional[int] = None) -> None:
        """模拟页面滚动
        
        Args:
            page: Playwright页面对象
            direction: 滚动方向，'up'/'down'/'random'
            distance: 滚动距离，如果为None则随机生成
        """
        if distance is None:
            distance = random.randint(100, 300)
            
        if direction == 'random':
            direction = random.choice(['up', 'down'])
            
        if direction == 'up':
            distance = -distance
            
        page.mouse.wheel(0, distance)
        time.sleep(random.uniform(0.3, 0.8))
    
    @staticmethod
    def human_like_click(page: Page, element: Locator) -> bool:
        """更真实地模拟人类点击行为：鼠标移动、悬停、随机偏移后点击，box为None时降级为.click()"""
        try:
            element.wait_for(state="visible", timeout=10000)
            box = element.bounding_box()
            if box:
                # 随机偏移，模拟手抖
                x = box['x'] + box['width'] * random.uniform(0.2, 0.8)
                y = box['y'] + box['height'] * random.uniform(0.2, 0.8)
                # 鼠标移动到目标
                page.mouse.move(x, y, steps=random.randint(8, 20))
                # 悬停一会
                time.sleep(random.uniform(0.2, 0.7))
                # 点击
                page.mouse.click(x, y)
                print("[HumanBehavior] 鼠标移动+悬停+随机偏移点击成功")
                return True
            else:
                # 降级为直接点击
                element.click(timeout=5000)
                print("[HumanBehavior] box为None，降级为locator.click()成功")
                return True
        except Exception as e:
            print(f"[HumanBehavior] 模拟点击失败: {e}")
            return False
    
    @staticmethod
    def human_like_type(page: Page, element: Locator, text: str) -> bool:
        """自动适配 input/textarea 和 contenteditable 输入框，并恢复输入验证"""
        try:
            element.wait_for(state="visible", timeout=10000)
            for _ in range(20):
                if element.is_enabled():
                    break
                time.sleep(0.2)
            else:
                print("[HumanBehavior] 输入框长时间不可交互")
                return False

            element.scroll_into_view_if_needed()
            time.sleep(random.uniform(0.5, 1.0))
            element.click()
            time.sleep(random.uniform(0.3, 0.5))

            # 判断是否为contenteditable
            if element.get_attribute('contenteditable') == 'true':
                element.evaluate("(el, value) => el.innerText = value", text)
                time.sleep(random.uniform(0.2, 0.4))
                actual_text = element.evaluate("el => el.innerText")
            else:
                element.fill("")
                time.sleep(random.uniform(0.2, 0.4))
                element.fill(text)
                time.sleep(random.uniform(0.2, 0.4))
                actual_text = element.input_value()

            if actual_text.strip() == text.strip():
                return True
            else:
                print(f"[HumanBehavior] 输入验证失败: 期望 '{text}', 实际 '{actual_text}'")
                return False

        except Exception as e:
            print(f"[HumanBehavior] 模拟输入失败: {e}")
            return False
    
    @staticmethod
    def prepare_for_generation(page: Page, generate_button: Locator) -> bool:
        """准备生成图片前的行为模拟（仅直接点击按钮）"""
        try:
            generate_button.wait_for(state="visible", timeout=10000)
            generate_button.click(timeout=5000)
            print("[HumanBehavior] 直接点击生成按钮成功")
            return True
        except Exception as e:
            print(f"[HumanBehavior] 直接点击生成按钮失败: {e}")
            return False 