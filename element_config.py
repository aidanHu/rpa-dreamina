#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
元素配置管理器
统一管理所有网页元素选择器和配置
"""

import json
import os
from typing import Dict, List, Optional, Any

class ElementConfig:
    """元素配置管理器"""
    
    def __init__(self, config_file="dreamina_elements.json"):
        self.config_file = config_file
        self.config = self._load_config()
        
    def _load_config(self) -> Dict:
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                print(f"❌ 元素配置文件 {self.config_file} 不存在")
                return {}
        except Exception as e:
            print(f"❌ 加载元素配置文件失败: {e}")
            return {}
    
    def get_url(self, url_key: str) -> str:
        """获取URL"""
        return self.config.get('urls', {}).get(url_key, '')
    
    def get_element(self, category: str, element_key: str) -> str:
        """获取元素选择器"""
        return self.config.get('elements', {}).get(category, {}).get(element_key, '')
    
    def get_element_list(self, category: str, element_key: str) -> List[str]:
        """获取元素选择器列表"""
        element = self.config.get('elements', {}).get(category, {}).get(element_key, [])
        if isinstance(element, list):
            return element
        elif isinstance(element, str):
            return [element]
        else:
            return []
    
    def get_wait_time(self, time_key: str) -> int:
        """获取等待时间"""
        return self.config.get('wait_times', {}).get(time_key, 10)
    
    def get_months(self) -> List[str]:
        """获取月份列表"""
        return self.config.get('months', [])
    
    def format_element(self, category: str, element_key: str, **kwargs) -> str:
        """格式化元素选择器（支持参数替换）"""
        element = self.get_element(category, element_key)
        if element and kwargs:
            try:
                return element.format(**kwargs)
            except KeyError as e:
                print(f"❌ 格式化元素选择器时缺少参数: {e}")
                return element
        return element
    
    def format_element_list(self, category: str, element_key: str, **kwargs) -> List[str]:
        """格式化元素选择器列表（支持参数替换）"""
        elements = self.get_element_list(category, element_key)
        formatted_elements = []
        for element in elements:
            if kwargs:
                try:
                    formatted_elements.append(element.format(**kwargs))
                except KeyError:
                    formatted_elements.append(element)
            else:
                formatted_elements.append(element)
        return formatted_elements

# 全局实例
element_config = ElementConfig()

# 便捷函数
def get_url(url_key: str) -> str:
    """获取URL"""
    return element_config.get_url(url_key)

def get_element(category: str, element_key: str) -> str:
    """获取元素选择器"""
    return element_config.get_element(category, element_key)

def get_element_list(category: str, element_key: str) -> List[str]:
    """获取元素选择器列表"""
    return element_config.get_element_list(category, element_key)

def get_wait_time(time_key: str) -> int:
    """获取等待时间"""
    return element_config.get_wait_time(time_key)

def format_element(category: str, element_key: str, **kwargs) -> str:
    """格式化元素选择器"""
    return element_config.format_element(category, element_key, **kwargs)

def format_element_list(category: str, element_key: str, **kwargs) -> List[str]:
    """格式化元素选择器列表"""
    return element_config.format_element_list(category, element_key, **kwargs) 