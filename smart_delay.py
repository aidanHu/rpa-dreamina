#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import random
from typing import Dict, Any, Optional

class SmartDelay:
    """智能延时管理器"""
    
    def __init__(self, config_path: str = "user_config.json"):
        """
        初始化智能延时管理器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.delay_settings = self._load_delay_settings()
        
    def _load_delay_settings(self) -> Dict[str, Any]:
        """
        从配置文件加载延时设置
        
        Returns:
            延时设置字典
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            smart_delays = config.get("smart_delays", {})
            
            # 如果没有配置，使用默认值
            if not smart_delays:
                print("[SmartDelay] 未找到智能延时配置，使用默认设置")
                smart_delays = self._get_default_delays()
            
            return smart_delays
            
        except FileNotFoundError:
            print(f"[SmartDelay] 配置文件 {self.config_path} 未找到，使用默认延时设置")
            return self._get_default_delays()
        except json.JSONDecodeError as e:
            print(f"[SmartDelay] 配置文件格式错误: {e}，使用默认延时设置")
            return self._get_default_delays()
        except Exception as e:
            print(f"[SmartDelay] 加载配置文件时出错: {e}，使用默认延时设置")
            return self._get_default_delays()
    
    def _get_default_delays(self) -> Dict[str, Any]:
        """
        获取默认延时设置
        
        Returns:
            默认延时设置字典
        """
        return {
            "min": 2,
            "max": 5,
            "description": "统一智能延时范围（秒）"
        }
    
    def get_delay_settings(self) -> Dict[str, Any]:
        """
        获取当前延时设置
        
        Returns:
            延时设置字典
        """
        return self.delay_settings
    
    def reload_settings(self):
        """重新加载延时设置"""
        self.delay_settings = self._load_delay_settings()
        print("[SmartDelay] 延时设置已重新加载")
    
    def smart_delay(self, custom_description: Optional[str] = None) -> float:
        """
        执行智能延时
        
        Args:
            custom_description: 自定义描述信息
            
        Returns:
            实际延时时间
        """
        min_delay = self.delay_settings.get("min", 2)
        max_delay = self.delay_settings.get("max", 5)
        description = custom_description or self.delay_settings.get("description", "智能延时")
        
        # 生成随机延时
        actual_delay = random.uniform(min_delay, max_delay)
        
        # 显示延时信息
        print(f"[SmartDelay] 🕒 {description} - 延时 {actual_delay:.1f} 秒 (范围: {min_delay}-{max_delay}秒)")
        
        # 执行延时
        time.sleep(actual_delay)
        
        return actual_delay
    
    def get_delay_info(self) -> Dict[str, Any]:
        """
        获取延时信息
        
        Returns:
            延时信息字典
        """
        return self.delay_settings.copy()
    
    def list_all_delays(self):
        """列出延时配置"""
        print("\n[SmartDelay] 📋 当前延时配置:")
        print("-" * 50)
        
        min_time = self.delay_settings.get("min", 0)
        max_time = self.delay_settings.get("max", 0)
        description = self.delay_settings.get("description", "无描述")
        
        print(f"  延时范围: {min_time}-{max_time} 秒")
        print(f"  说明: {description}")
        
        print("-" * 50)
    
    def validate_settings(self) -> bool:
        """
        验证延时设置的有效性
        
        Returns:
            设置是否有效
        """
        valid = True
        issues = []
        
        min_time = self.delay_settings.get("min")
        max_time = self.delay_settings.get("max")
        
        # 检查必需字段
        if min_time is None or max_time is None:
            issues.append("缺少 min 或 max 配置")
            valid = False
        else:
            # 检查类型
            if not isinstance(min_time, (int, float)) or not isinstance(max_time, (int, float)):
                issues.append("min 和 max 必须是数字")
                valid = False
            else:
                # 检查逻辑
                if min_time < 0 or max_time < 0:
                    issues.append("min 和 max 不能为负数")
                    valid = False
                
                if min_time > max_time:
                    issues.append(f"min ({min_time}) 不能大于 max ({max_time})")
                    valid = False
        
        if not valid:
            print("[SmartDelay] ❌ 延时设置验证失败:")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("[SmartDelay] ✅ 延时设置验证通过")
        
        return valid


# 全局智能延时实例
_smart_delay_instance = None

def get_smart_delay() -> SmartDelay:
    """
    获取全局智能延时实例
    
    Returns:
        SmartDelay实例
    """
    global _smart_delay_instance
    if _smart_delay_instance is None:
        _smart_delay_instance = SmartDelay()
    return _smart_delay_instance

def smart_delay(custom_description: Optional[str] = None) -> float:
    """
    便捷函数：执行智能延时
    
    Args:
        custom_description: 自定义描述
        
    Returns:
        实际延时时间
    """
    return get_smart_delay().smart_delay(custom_description)

def reload_delay_settings():
    """便捷函数：重新加载延时设置"""
    global _smart_delay_instance
    if _smart_delay_instance is not None:
        _smart_delay_instance.reload_settings()

def list_delay_settings():
    """便捷函数：列出所有延时配置"""
    get_smart_delay().list_all_delays()


if __name__ == "__main__":
    # 测试智能延时功能
    print("🧪 测试智能延时功能...")
    
    delay_manager = SmartDelay()
    
    # 验证设置
    delay_manager.validate_settings()
    
    # 列出延时配置
    delay_manager.list_all_delays()
    
    # 测试延时功能
    print("\n测试延时功能:")
    delay_manager.smart_delay("输入提示词")
    delay_manager.smart_delay("点击生成按钮")
    delay_manager.smart_delay()  # 使用默认描述
    
    print("✅ 智能延时测试完成！") 