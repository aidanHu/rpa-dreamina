#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from playwright.sync_api import Page, Locator, TimeoutError as PlaywrightTimeoutError
from element_config import get_element_list, format_element_list

class ElementHelper:
    """元素定位辅助类，从JSON配置文件读取XPath定位信息"""
    
    def __init__(self, config_file="dreamina_elements.json"):
        """初始化元素辅助类
        
        Args:
            config_file: 元素配置文件路径
        """
        self.config_file = config_file
        self.config = self._load_config()
        
    def _load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"[ElementHelper] 错误: 配置文件 {self.config_file} 未找到")
            return {}
        except json.JSONDecodeError as e:
            print(f"[ElementHelper] 错误: 配置文件格式错误 - {e}")
            return {}
    
    def get_xpath(self, page_name: str, element_name: str) -> str:
        """获取元素的XPath
        
        Args:
            page_name: 页面名称
            element_name: 元素名称
            
        Returns:
            str: XPath字符串
        """
        try:
            return self.config['elements'][page_name][element_name]
        except KeyError:
            print(f"[ElementHelper] 警告: 未找到元素配置 {page_name}.{element_name}")
            return None
    
    def find_element(self, page: Page, page_name: str, element_name: str, timeout: int = None) -> Locator:
        """查找元素
        
        Args:
            page: Playwright页面对象
            page_name: 页面名称
            element_name: 元素名称
            timeout: 超时时间（毫秒）
            
        Returns:
            Locator: 找到的元素定位器
        """
        xpath = self.get_xpath(page_name, element_name)
        if not xpath:
            return None
        
        if timeout is None:
            timeout = self.config.get('wait_times', {}).get('element_wait', 10) * 1000
        
        try:
            locator = page.locator(f"xpath={xpath}")
            
            # 检查元素是否存在且可见
            if locator.is_visible(timeout=timeout):
                print(f"[ElementHelper] 成功找到元素 {element_name}")
                return locator
            else:
                print(f"[ElementHelper] 元素 {element_name} 不可见")
                return None
                
        except Exception as e:
            print(f"[ElementHelper] 查找元素 {element_name} 时出错: {e}")
            return None
    
    def click_element(self, page: Page, page_name: str, element_name: str, timeout: int = None) -> bool:
        """点击元素
        
        Args:
            page: Playwright页面对象
            page_name: 页面名称
            element_name: 元素名称
            timeout: 超时时间（毫秒）
            
        Returns:
            bool: 是否成功点击
        """
        locator = self.find_element(page, page_name, element_name, timeout)
        if locator:
            try:
                locator.click(timeout=5000)
                print(f"[ElementHelper] 成功点击元素 {element_name}")
                return True
            except Exception as e:
                print(f"[ElementHelper] 点击元素 {element_name} 失败: {e}")
                return False
        return False
    
    def fill_element(self, page: Page, page_name: str, element_name: str, value: str, timeout: int = None) -> bool:
        """填充输入框
        
        Args:
            page: Playwright页面对象
            page_name: 页面名称
            element_name: 元素名称
            value: 要填充的值
            timeout: 超时时间（毫秒）
            
        Returns:
            bool: 是否成功填充
        """
        locator = self.find_element(page, page_name, element_name, timeout)
        if locator:
            try:
                locator.fill(value)
                print(f"[ElementHelper] 成功填充元素 {element_name}")
                return True
            except Exception as e:
                print(f"[ElementHelper] 填充元素 {element_name} 失败: {e}")
                return False
        return False
    
    def select_dropdown_option(self, page: Page, dropdown_page: str, dropdown_element: str, 
                              option_page: str, option_element: str, option_value: str) -> bool:
        """选择下拉框选项（原始方法）
        
        Args:
            page: Playwright页面对象
            dropdown_page: 下拉框所在页面
            dropdown_element: 下拉框元素名
            option_page: 选项所在页面
            option_element: 选项元素名
            option_value: 选项值
            
        Returns:
            bool: 是否成功选择
        """
        # 先点击下拉框
        if not self.click_element(page, dropdown_page, dropdown_element):
            return False
        
        # 等待下拉选项出现
        wait_time = self.config.get('wait_times', {}).get('after_click', 2)
        page.wait_for_timeout(wait_time * 1000)
        
        # 等待popup容器出现（针对lv-select组件）
        try:
            # 从下拉框元素中获取aria-controls属性来找到对应的popup
            dropdown_xpath = self.get_xpath(dropdown_page, dropdown_element)
            if dropdown_xpath and 'aria-controls' in dropdown_xpath:
                # 提取popup ID
                import re
                popup_match = re.search(r"aria-controls='([^']+)'", dropdown_xpath)
                if popup_match:
                    popup_id = popup_match.group(1)
                    # 等待popup出现并且可见
                    page.wait_for_selector(f"#{popup_id}", state="visible", timeout=5000)
                    print(f"[ElementHelper] Popup容器 {popup_id} 已出现")
        except Exception as e:
            print(f"[ElementHelper] 等待popup时出错: {e}")
        
        # 获取选项XPath并替换占位符
        option_xpath = self.get_xpath(option_page, option_element)
        if not option_xpath:
            return False
        
        # 替换占位符
        option_xpath = option_xpath.format(month=option_value, day=option_value)
        
        try:
            # 等待选项出现
            page.wait_for_selector(f"xpath={option_xpath}", state="visible", timeout=5000)
            
            option_locator = page.locator(f"xpath={option_xpath}")
            if option_locator.is_visible(timeout=3000):
                option_locator.click()
                print(f"[ElementHelper] 成功选择选项: {option_value}")
                return True
            else:
                print(f"[ElementHelper] 选项不可见: {option_value}")
                return False
        except Exception as e:
            print(f"[ElementHelper] 选择选项失败: {e}")
            return False
    
    def select_dropdown_option_enhanced(self, page: Page, dropdown_page: str, dropdown_element: str, 
                                       option_value: str, option_type: str = "month") -> bool:
        """增强的下拉框选择方法，支持多种选择策略
        
        Args:
            page: Playwright页面对象
            dropdown_page: 下拉框所在页面
            dropdown_element: 下拉框元素名
            option_value: 选项值（月份名称或日期数字）
            option_type: 选项类型 ("month" 或 "day")
            
        Returns:
            bool: 是否成功选择
        """
        print(f"[ElementHelper] 使用增强方法选择{option_type}: {option_value}")
        
        # 先点击下拉框
        dropdown_xpath = self.get_xpath(dropdown_page, dropdown_element)
        if not dropdown_xpath:
            print(f"[ElementHelper] 未找到下拉框配置")
            return False
            
        try:
            dropdown = page.locator(f"xpath={dropdown_xpath}")
            dropdown.click(timeout=5000)
            print(f"[ElementHelper] 已点击下拉框")
            
            # 等待下拉选项出现
            page.wait_for_timeout(1000)
            
            # 策略1: 尝试通过文本内容点击
            try:
                # 从配置文件获取下拉选项选择器
                option_selectors = format_element_list("common", "dropdown_options", option_value=option_value)
                
                for selector in option_selectors:
                    try:
                        option = page.locator(f"xpath={selector}")
                        if option.is_visible(timeout=1000):
                            option.click()
                            print(f"[ElementHelper] 策略1成功: 通过选择器 {selector} 选择了 {option_value}")
                            return True
                    except:
                        continue
                        
            except Exception as e:
                print(f"[ElementHelper] 策略1失败: {e}")
            
            # 策略2: 通过键盘操作选择
            try:
                print(f"[ElementHelper] 尝试策略2: 键盘操作")
                
                # 先尝试直接输入
                dropdown_input = dropdown.locator("input").first
                if dropdown_input.is_visible(timeout=1000):
                    dropdown_input.fill(option_value)
                    page.wait_for_timeout(500)
                    page.keyboard.press("Enter")
                    print(f"[ElementHelper] 策略2成功: 通过输入并回车选择了 {option_value}")
                    return True
                    
            except Exception as e:
                print(f"[ElementHelper] 策略2失败: {e}")
            
            # 策略3: 通过方向键选择（适用于月份和日期）
            try:
                print(f"[ElementHelper] 尝试策略3: 方向键导航")
                
                if option_type == "month":
                    # 月份映射到索引
                    months = self.config.get('months', [])
                    if option_value in months:
                        target_index = months.index(option_value)
                        # 先按Home键到第一个选项
                        page.keyboard.press("Home")
                        page.wait_for_timeout(100)
                        # 然后按向下键到目标位置
                        for _ in range(target_index):
                            page.keyboard.press("ArrowDown")
                            page.wait_for_timeout(50)
                        page.keyboard.press("Enter")
                        print(f"[ElementHelper] 策略3成功: 通过方向键选择了月份 {option_value}")
                        return True
                        
                elif option_type == "day":
                    # 日期直接使用数字
                    try:
                        day_num = int(option_value)
                        # 先按Home键到第一个选项
                        page.keyboard.press("Home")
                        page.wait_for_timeout(100)
                        # 然后按向下键到目标位置
                        for _ in range(day_num - 1):
                            page.keyboard.press("ArrowDown")
                            page.wait_for_timeout(50)
                        page.keyboard.press("Enter")
                        print(f"[ElementHelper] 策略3成功: 通过方向键选择了日期 {option_value}")
                        return True
                    except ValueError:
                        print(f"[ElementHelper] 无效的日期值: {option_value}")
                        
            except Exception as e:
                print(f"[ElementHelper] 策略3失败: {e}")
            
            # 策略4: 点击可见的包含文本的元素
            try:
                print(f"[ElementHelper] 尝试策略4: 模糊匹配")
                # 从配置文件获取文本搜索选择器
                fuzzy_selectors = format_element_list("common", "text_search_selectors", option_value=option_value)
                
                for selector in fuzzy_selectors:
                    elements = page.locator(f"xpath={selector}").all()
                    for element in elements:
                        try:
                            if element.is_visible():
                                # 检查元素是否在下拉框容器内
                                element.click()
                                print(f"[ElementHelper] 策略4成功: 通过模糊匹配选择了 {option_value}")
                                return True
                        except:
                            continue
                            
            except Exception as e:
                print(f"[ElementHelper] 策略4失败: {e}")
                
            print(f"[ElementHelper] 所有策略都失败了，无法选择 {option_value}")
            return False
            
        except Exception as e:
            print(f"[ElementHelper] 增强选择方法出错: {e}")
            return False
    
    def wait_for_element(self, page: Page, page_name: str, element_name: str, timeout: int = None) -> bool:
        """等待元素出现
        
        Args:
            page: Playwright页面对象
            page_name: 页面名称
            element_name: 元素名称
            timeout: 超时时间（毫秒）
            
        Returns:
            bool: 元素是否出现
        """
        if timeout is None:
            timeout = self.config.get('wait_times', {}).get('element_wait', 10) * 1000
            
        locator = self.find_element(page, page_name, element_name, timeout)
        return locator is not None
    
    def get_url(self, url_name: str) -> str:
        """获取URL配置
        
        Args:
            url_name: URL名称
            
        Returns:
            str: URL地址
        """
        return self.config.get('urls', {}).get(url_name, '')
    
    def get_wait_time(self, wait_type: str) -> int:
        """获取等待时间配置（秒）
        
        Args:
            wait_type: 等待类型
            
        Returns:
            int: 等待时间（秒）
        """
        return self.config.get('wait_times', {}).get(wait_type, 3)
    
    def print_xpath_list(self):
        """打印所有XPath配置，便于调试验证"""
        print("\n=== 所有XPath配置 ===")
        elements = self.config.get('elements', {})
        for page_name, page_elements in elements.items():
            print(f"\n[{page_name}]")
            for element_name, xpath in page_elements.items():
                print(f"  {element_name}: {xpath}") 