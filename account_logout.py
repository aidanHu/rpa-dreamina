#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Dreamina账号注销管理器
提供安全的账号注销功能，支持重试机制和状态验证
"""

import time
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from element_helper import ElementHelper
from element_config import get_url

class LogoutManager:
    """Dreamina账号注销管理器"""
    
    def __init__(self):
        self.element_helper = ElementHelper()
        
    def logout_account(self, page):
        """注销当前登录的账号
        
        Args:
            page: Playwright页面对象
            
        Returns:
            bool: 是否注销成功
        """
        print("\n" + "="*50)
        print("🚪 开始注销当前账号")
        print("="*50)
        
        try:
            # 检查是否已经是未登录状态
            if self._is_already_logged_out(page):
                print("✅ 当前已经是未登录状态")
                return True
            
            # 1. 点击用户头像
            print("[1/3] 点击用户头像...")
            if not self._safe_click_user_avatar(page):
                print("❌ 点击用户头像失败")
                return False
            
            # 2. 等待下拉菜单出现并点击Sign out
            print("[2/3] 点击Sign out按钮...")
            if not self._safe_click_sign_out(page):
                print("❌ 点击Sign out失败")
                return False
            
            # 3. 验证注销是否成功
            print("[3/3] 验证注销状态...")
            if not self._verify_logout_success(page):
                print("❌ 注销验证失败")
                return False
            
            print("✅ 账号注销成功！")
            return True
            
        except Exception as e:
            print(f"❌ 注销过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _retry_operation(self, operation_func, max_retries=3, delay=2, description="操作"):
        """重试操作机制
        
        Args:
            operation_func: 要执行的操作函数
            max_retries: 最大重试次数
            delay: 重试间隔秒数
            description: 操作描述
            
        Returns:
            bool: 是否成功
        """
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"[重试 {attempt}/{max_retries-1}] {description}...")
                    time.sleep(delay)  # 重试前等待
                
                result = operation_func()
                if result:
                    if attempt > 0:
                        print(f"✅ {description} 重试成功")
                    return True
                    
            except Exception as e:
                print(f"❌ {description} 执行异常: {e}")
                
            if attempt < max_retries - 1:
                print(f"⚠️ {description} 失败，准备重试...")
        
        print(f"❌ {description} 经过 {max_retries} 次尝试后仍然失败")
        return False
    
    def _is_already_logged_out(self, page):
        """检查是否已经是未登录状态
        
        Args:
            page: Playwright页面对象
            
        Returns:
            bool: 是否已经未登录
        """
        try:
            # 检查是否存在登录按钮（说明未登录）
            sign_in_button = self.element_helper.find_element(page, "home_page", "sign_in_button", timeout=3000)
            if sign_in_button and sign_in_button.is_visible():
                return True
                
            # 检查是否不存在用户头像（说明未登录）
            user_avatar = self.element_helper.find_element(page, "logout", "user_avatar", timeout=3000)
            if not user_avatar:
                return True
                
            return False
        except:
            return False
    
    def _safe_click_user_avatar(self, page):
        """安全点击用户头像
        
        Args:
            page: Playwright页面对象
            
        Returns:
            bool: 是否点击成功
        """
        def click_avatar():
            # 查找用户头像
            avatar = self.element_helper.find_element(page, "logout", "user_avatar", timeout=10000)
            if not avatar:
                print("❌ 未找到用户头像")
                return False
            
            if not avatar.is_visible():
                print("❌ 用户头像不可见")
                return False
            
            # 点击头像
            avatar.click()
            time.sleep(2)  # 等待下拉菜单出现
            
            # 验证下拉菜单是否出现
            dropdown = self.element_helper.find_element(page, "logout", "dropdown_menu", timeout=5000)
            if dropdown and dropdown.is_visible():
                print("✅ 用户菜单已展开")
                return True
            else:
                print("❌ 用户菜单未展开")
                return False
        
        return self._retry_operation(click_avatar, max_retries=3, delay=2, description="点击用户头像")
    
    def _safe_click_sign_out(self, page):
        """安全点击Sign out按钮
        
        Args:
            page: Playwright页面对象
            
        Returns:
            bool: 是否点击成功
        """
        def click_sign_out():
            # 确保下拉菜单仍然可见
            dropdown = self.element_helper.find_element(page, "logout", "dropdown_menu", timeout=5000)
            if not dropdown or not dropdown.is_visible():
                print("❌ 下拉菜单不可见，重新点击头像")
                # 重新点击头像
                avatar = self.element_helper.find_element(page, "logout", "user_avatar", timeout=5000)
                if avatar:
                    avatar.click()
                    time.sleep(2)
            
            # 查找Sign out按钮
            sign_out_btn = self.element_helper.find_element(page, "logout", "sign_out_button", timeout=5000)
            if not sign_out_btn:
                print("❌ 未找到Sign out按钮")
                return False
            
            if not sign_out_btn.is_visible():
                print("❌ Sign out按钮不可见")
                return False
            
            # 点击Sign out
            sign_out_btn.click()
            print("✅ 已点击Sign out按钮")
            time.sleep(3)  # 等待注销处理
            
            return True
        
        return self._retry_operation(click_sign_out, max_retries=3, delay=2, description="点击Sign out")
    
    def _verify_logout_success(self, page, timeout=15):
        """验证注销是否成功
        
        Args:
            page: Playwright页面对象
            timeout: 验证超时时间（秒）
            
        Returns:
            bool: 是否注销成功
        """
        print(f"[验证] 等待注销完成（最多{timeout}秒）...")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # 方法1: 检查是否出现了登录按钮
                sign_in_button = self.element_helper.find_element(page, "home_page", "sign_in_button", timeout=2000)
                if sign_in_button and sign_in_button.is_visible():
                    print("✅ 检测到登录按钮，注销成功")
                    return True
                
                # 方法2: 检查用户头像是否消失
                user_avatar = self.element_helper.find_element(page, "logout", "user_avatar", timeout=1000)
                if not user_avatar or not user_avatar.is_visible():
                    print("✅ 用户头像已消失，注销成功")
                    return True
                
                # 方法3: 检查URL是否回到主页
                current_url = page.url
                home_url = get_url("home")
                if current_url == home_url or current_url.endswith('/'):
                    # 再次确认是否有登录按钮
                    time.sleep(1)
                    sign_in_check = self.element_helper.find_element(page, "home_page", "sign_in_button", timeout=2000)
                    if sign_in_check and sign_in_check.is_visible():
                        print("✅ 页面已回到主页且显示登录按钮，注销成功")
                        return True
                
                print(f"⏳ 仍在验证注销状态... (已等待{int(time.time() - start_time)}秒)")
                time.sleep(2)
                
            except Exception as e:
                print(f"⚠️ 验证过程中出现异常: {e}")
                time.sleep(2)
        
        print(f"❌ 等待{timeout}秒后仍无法确认注销状态")
        return False
    
    def force_navigate_to_home(self, page):
        """强制导航到主页（注销后的清理操作）
        
        Args:
            page: Playwright页面对象
            
        Returns:
            bool: 是否成功导航到主页
        """
        def navigate_home():
            print("🏠 导航到主页...")
            home_url = get_url("home")
            page.goto(home_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            
            # 验证是否成功加载主页
            sign_in_button = self.element_helper.find_element(page, "home_page", "sign_in_button", timeout=10000)
            if sign_in_button and sign_in_button.is_visible():
                print("✅ 已成功导航到主页")
                return True
            return False
        
        return self._retry_operation(navigate_home, max_retries=3, delay=3, description="导航到主页")
    
    def check_login_status(self, page):
        """检查当前登录状态
        
        Args:
            page: Playwright页面对象
            
        Returns:
            str: "logged_in", "logged_out", "unknown"
        """
        try:
            # 检查是否有用户头像（已登录）
            user_avatar = self.element_helper.find_element(page, "logout", "user_avatar", timeout=3000)
            if user_avatar and user_avatar.is_visible():
                return "logged_in"
            
            # 检查是否有登录按钮（未登录）
            sign_in_button = self.element_helper.find_element(page, "home_page", "sign_in_button", timeout=3000)
            if sign_in_button and sign_in_button.is_visible():
                return "logged_out"
            
            return "unknown"
            
        except Exception as e:
            print(f"检查登录状态时出错: {e}")
            return "unknown"

# 便捷函数
def logout_current_account(page):
    """便捷函数：注销当前账号
    
    Args:
        page: Playwright页面对象
        
    Returns:
        bool: 是否注销成功
    """
    logout_manager = LogoutManager()
    return logout_manager.logout_account(page)

def check_user_login_status(page):
    """便捷函数：检查用户登录状态
    
    Args:
        page: Playwright页面对象
        
    Returns:
        str: 登录状态
    """
    logout_manager = LogoutManager()
    return logout_manager.check_login_status(page) 