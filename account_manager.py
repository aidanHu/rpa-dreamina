#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import os
import pandas as pd
import random
import string
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from element_helper import ElementHelper
from element_config import get_element, get_url, get_element_list
from mail_handler import get_verification_code_from_maildrop
from account_logout import LogoutManager

# 账号生成工具函数
def generate_random_username(index=None):
    """生成随机用户名"""
    prefixes = [
        "User", "Dream", "Art", "Creative", "Design", "Visual", 
        "Magic", "Studio", "Pixel", "Digital", "Media", "Vision"
    ]
    prefix = random.choice(prefixes)
    suffix_length = random.randint(4, 6)
    suffix = ''.join(random.choices(string.digits, k=suffix_length))
    
    if index:
        username = f"{prefix}_{index}_{suffix}"
    else:
        username = f"{prefix}_{suffix}"
    
    return username

def generate_random_password(length=12):
    """生成随机密码"""
    lowercase = string.ascii_lowercase
    uppercase = string.ascii_uppercase
    digits = string.digits
    special_chars = "!@#$%^&*"
    
    # 确保每种类型至少有一个字符
    password = [
        random.choice(lowercase),
        random.choice(uppercase),
        random.choice(digits),
        random.choice(special_chars)
    ]
    
    # 填充剩余长度
    all_chars = lowercase + uppercase + digits + special_chars
    for _ in range(length - 4):
        password.append(random.choice(all_chars))
    
    # 打乱顺序
    random.shuffle(password)
    
    return ''.join(password)

def generate_random_email(username=None):
    """生成随机邮箱地址（使用maildrop.cc）"""
    if username:
        clean_username = ''.join(c for c in username.lower() if c.isalnum() or c in ['_'])
        random_suffix = ''.join(random.choices(string.digits, k=4))
        mailbox_name = f"{clean_username}_{random_suffix}"
    else:
        length = random.randint(8, 12)
        mailbox_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
    
    email = f"{mailbox_name}@maildrop.cc"
    return email, mailbox_name

# URLs从配置文件获取
DREAMINA_URL = get_url("home")
LOGIN_URL = get_url("login")

class AccountManager:
    """Dreamina账号管理器"""
    
    def __init__(self):
        self.accounts_data = []
        self.excel_file = "dreamina_accounts.xlsx"
        self.element_helper = ElementHelper()
        self.logout_manager = LogoutManager()
        
    def register_accounts(self, count, browser_id, http_address, ws_address):
        """批量注册账号
        
        Args:
            count: 要注册的账号数量
            browser_id: 浏览器ID
            http_address: HTTP调试地址
            ws_address: WebSocket调试地址
            
        Returns:
            bool: 是否成功完成所有注册
        """
        # 构建Playwright需要的调试地址
        if http_address and not http_address.startswith(("http://", "https://")):
            debug_address = f"http://{http_address}"
        else:
            debug_address = http_address
            
        print(f"[AccountManager] 使用调试地址: {debug_address}")
        
        registered_count = 0
        
        with sync_playwright() as p:
            try:
                print("[AccountManager] 连接到浏览器...")
                browser = p.chromium.connect_over_cdp(debug_address)
                
                if not browser.contexts:
                    print("[AccountManager] 错误: 浏览器中没有任何上下文")
                    return False
                
                context = browser.contexts[0]
                
                # 循环注册账号
                for i in range(count):
                    print(f"\n{'='*60}")
                    print(f"开始注册第 {i+1}/{count} 个账号")
                    print(f"{'='*60}")
                    
                    success = self._register_single_account(context, i+1)
                    
                    if success:
                        registered_count += 1
                        print(f"✅ 第 {i+1} 个账号注册成功")
                        
                        # 注册成功后自动注销（为下一个账号注册做准备）
                        if i < count - 1:  # 不是最后一个账号才注销
                            print(f"\n🔄 准备注销第 {i+1} 个账号...")
                            logout_success = self.logout_manager.logout_account(context.pages[0] if context.pages else None)
                            if logout_success:
                                print(f"✅ 第 {i+1} 个账号已成功注销")
                            else:
                                print(f"⚠️ 第 {i+1} 个账号注销失败，但不影响下一个账号注册")
                    else:
                        print(f"❌ 第 {i+1} 个账号注册失败")
                    
                    # 如果不是最后一个，等待一段时间再继续
                    if i < count - 1:
                        wait_time = 10
                        print(f"\n等待 {wait_time} 秒后继续...")
                        time.sleep(wait_time)
                
                # 保存所有账号信息到Excel
                if self.accounts_data:
                    self._save_all_accounts()
                    
            except Exception as e:
                print(f"[AccountManager] 注册过程中发生错误: {e}")
                return False
                
        print(f"\n[AccountManager] 注册完成: 成功 {registered_count}/{count} 个账号")
        return registered_count == count
    
    def _register_single_account(self, context, index):
        """注册单个账号
        
        Args:
            context: Playwright浏览器上下文
            index: 账号序号
            
        Returns:
            bool: 是否注册成功
        """
        page = None
        try:
            # 打开新页面或使用现有页面
            if context.pages:
                page = context.pages[0]
                # 关闭其他标签页
                for p in context.pages[1:]:
                    try:
                        p.close()
                    except:
                        pass
            else:
                page = context.new_page()
            
            # 生成账号信息
            username = generate_random_username(index)
            password = generate_random_password()
            email, mailbox_name = generate_random_email(username)  # 使用maildrop邮箱
            
            # 生成随机生日（确保在2000年之前，年龄24岁以上）
            current_year = datetime.now().year
            # 生成1970-1999年之间的年份（确保年龄在24-54岁之间）
            birth_year = str(random.randint(1970, 1999))
            birth_month = random.choice(self.element_helper.config.get('months', []))
            birth_day = str(random.randint(1, 28))  # 使用1-28避免月份日期问题
            
            print(f"\n[AccountManager] 生成的账号信息:")
            print(f"  邮箱: {email}")
            print(f"  密码: {password}")
            print(f"  生日: {birth_year}年 {birth_month} {birth_day}日")
            
            # 1. 导航到Dreamina主页
            print("\n[1/14] 导航到Dreamina网站...")
            if not self._safe_navigate_to_home(page):
                print("❌ 导航到主页失败")
                return False
            
            # 2. 点击Sign in按钮
            print("[2/14] 点击Sign in按钮...")
            if not self._safe_click_sign_in(page):
                print("❌ 点击Sign in按钮失败")
                return False
            
            # 3. 等待页面跳转完成 (已在_safe_click_sign_in中处理)
            print("[3/14] 页面跳转完成...")
            
            # 4. 勾选用户协议
            print("[4/14] 勾选用户协议...")
            if not self._safe_agree_terms(page):
                print("❌ 勾选用户协议失败")
                return False
            
            # 5. 点击Sign in按钮（模态框中）
            print("[5/14] 点击Sign in按钮打开登录框...")
            if not self._safe_open_sign_in_modal(page):
                print("❌ 打开登录模态框失败")
                return False
            
            # 6. 点击Continue with email
            print("[6/14] 选择邮箱注册方式...")
            if not self._safe_choose_email_method(page):
                print("❌ 选择邮箱登录方式失败")
                return False
            
            # 7. 点击Sign up链接
            print("[7/14] 切换到注册模式...")
            if not self._safe_switch_to_signup(page):
                print("❌ 切换到注册模式失败")
                return False
            
            # 8. 输入邮箱
            print("[8/14] 输入邮箱地址...")
            if not self._safe_fill_email(page, email):
                print("❌ 输入邮箱失败")
                return False
            
            # 9. 输入密码
            print("[9/14] 输入密码...")
            if not self._safe_fill_password(page, password):
                print("❌ 输入密码失败")
                return False
            
            # 10. 点击Continue按钮
            print("[10/14] 点击Continue按钮...")
            if not self._safe_submit_registration(page):
                print("❌ 提交注册表单失败")
                return False
            
            # 11. 处理验证码
            print("[11/14] 处理验证码...")
            verification_code = self._handle_verification_code(page, mailbox_name, email)
            
            # 12. 等待跳转到生日页面
            print("[12/14] 等待跳转到生日页面...")
            if not self._safe_wait_for_birthday_page(page):
                print("❌ 未能跳转到生日页面")
                return False
            
            # 13. 填写生日信息
            print("[13/14] 填写生日信息...")
            if not self._safe_fill_birthday(page, birth_year, birth_month, birth_day):
                print("❌ 填写生日信息失败")
                return False
            
            # 14. 提交生日信息并完成注册
            print("[14/14] 完成注册...")
            if not self._safe_complete_registration(page, index, email, password, username, birth_year, birth_month, birth_day, verification_code):
                print("❌ 完成注册失败")
                return False
            
            return True  # 注册成功
                
        except Exception as e:
            print(f"[AccountManager] 注册单个账号时发生错误: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _save_all_accounts(self):
        """保存所有账号信息到Excel文件"""
        try:
            # 检查是否已存在文件
            if os.path.exists(self.excel_file):
                # 读取现有数据
                existing_df = pd.read_excel(self.excel_file)
                # 创建新数据的DataFrame
                new_df = pd.DataFrame(self.accounts_data)
                # 合并数据
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                # 重新编号
                combined_df['序号'] = range(1, len(combined_df) + 1)
            else:
                # 创建新的DataFrame
                combined_df = pd.DataFrame(self.accounts_data)
            
            # 保存到Excel
            combined_df.to_excel(self.excel_file, index=False, engine='openpyxl')
            print(f"\n[AccountManager] 账号信息已保存到: {self.excel_file}")
            print(f"[AccountManager] 共保存 {len(self.accounts_data)} 个新账号")
            
        except Exception as e:
            print(f"[AccountManager] 保存账号信息时发生错误: {e}") 

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

    def _verify_page_state(self, page, expected_elements, description="页面状态"):
        """验证页面状态
        
        Args:
            page: Playwright页面对象
            expected_elements: 期望存在的元素列表 [(section, element_key), ...]
            description: 页面描述
            
        Returns:
            bool: 是否符合期望状态
        """
        print(f"[验证] 检查{description}...")
        
        for section, element_key in expected_elements:
            if not self.element_helper.find_element(page, section, element_key, timeout=3000):
                print(f"❌ {description}验证失败: 未找到 {section}.{element_key}")
                return False
        
        print(f"✅ {description}验证通过")
        return True

    def _safe_navigate_to_home(self, page):
        """安全导航到主页"""
        def navigate():
            home_url = self.element_helper.get_url('home')
            page.goto(home_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            # 验证是否成功加载主页
            return self.element_helper.find_element(page, "home_page", "sign_in_button", timeout=10000)
        
        return self._retry_operation(navigate, max_retries=3, delay=3, description="导航到主页")

    def _safe_click_sign_in(self, page):
        """安全点击Sign in按钮"""
        def click_sign_in():
            result = self.element_helper.click_element(page, "home_page", "sign_in_button")
            if result:
                time.sleep(3)
                # 验证是否成功跳转到登录页面
                page.wait_for_load_state("domcontentloaded")
                return self.element_helper.find_element(page, "login_page", "user_agreement_checkbox", timeout=10000)
            return False
        
        return self._retry_operation(click_sign_in, max_retries=3, delay=2, description="点击Sign in按钮")

    def _safe_agree_terms(self, page):
        """安全勾选用户协议"""
        def agree_terms():
            result = self.element_helper.click_element(page, "login_page", "user_agreement_checkbox")
            if result:
                time.sleep(1)
                # 验证复选框是否被选中
                checkbox = self.element_helper.find_element(page, "login_page", "user_agreement_checkbox")
                if checkbox:
                    # 检查是否有checked属性或相关类名
                    return True  # 假设点击成功就是选中了
            return False
        
        return self._retry_operation(agree_terms, max_retries=3, delay=1, description="勾选用户协议")

    def _safe_open_sign_in_modal(self, page):
        """安全打开登录模态框"""
        def open_modal():
            result = self.element_helper.click_element(page, "login_page", "sign_in_button_modal")
            if result:
                time.sleep(3)
                # 验证模态框是否打开
                return self.element_helper.find_element(page, "sign_in_modal", "continue_with_email", timeout=10000)
            return False
        
        return self._retry_operation(open_modal, max_retries=3, delay=2, description="打开登录模态框")

    def _safe_choose_email_method(self, page):
        """安全选择邮箱登录方式"""
        def choose_email():
            result = self.element_helper.click_element(page, "sign_in_modal", "continue_with_email")
            if result:
                time.sleep(2)
                # 验证是否出现Sign up链接
                return self.element_helper.find_element(page, "sign_in_modal", "sign_up_link", timeout=10000)
            return False
        
        return self._retry_operation(choose_email, max_retries=3, delay=2, description="选择邮箱登录方式")

    def _safe_switch_to_signup(self, page):
        """安全切换到注册模式"""
        def switch_signup():
            result = self.element_helper.click_element(page, "sign_in_modal", "sign_up_link")
            if result:
                time.sleep(2)
                # 验证是否出现注册表单
                return self.element_helper.find_element(page, "registration_form", "email_input", timeout=10000)
            return False
        
        return self._retry_operation(switch_signup, max_retries=3, delay=2, description="切换到注册模式")

    def _safe_fill_email(self, page, email):
        """安全填写邮箱"""
        def fill_email():
            result = self.element_helper.fill_element(page, "registration_form", "email_input", email)
            if result:
                time.sleep(1)
                # 验证邮箱是否正确填入
                email_input = self.element_helper.find_element(page, "registration_form", "email_input")
                if email_input:
                    current_value = email_input.input_value()
                    return current_value == email
            return False
        
        return self._retry_operation(fill_email, max_retries=3, delay=1, description="填写邮箱地址")

    def _safe_fill_password(self, page, password):
        """安全填写密码"""
        def fill_password():
            result = self.element_helper.fill_element(page, "registration_form", "password_input", password)
            if result:
                time.sleep(1)
                # 验证密码是否正确填入
                password_input = self.element_helper.find_element(page, "registration_form", "password_input")
                if password_input:
                    current_value = password_input.input_value()
                    return len(current_value) > 0  # 密码字段通常不显示实际内容
            return False
        
        return self._retry_operation(fill_password, max_retries=3, delay=1, description="填写密码")

    def _safe_submit_registration(self, page):
        """安全提交注册表单"""
        def submit_form():
            result = self.element_helper.click_element(page, "registration_form", "continue_button")
            if result:
                time.sleep(3)
                # 验证是否出现验证码输入框
                verification_selectors = [
                    ("registration_form", "verification_input"),  # 如果配置文件中有这个元素
                ]
                
                # 使用配置文件中的选择器查找验证码输入框
                code_input_found = False
                input_selectors = get_element_list("registration_form", "verification_code_inputs_fallback")
                
                for selector in input_selectors:
                    try:
                        temp_input = page.locator(selector).first
                        if temp_input.is_visible(timeout=3000):
                            code_input_found = True
                            break
                    except:
                        continue
                
                return code_input_found
            return False
        
        return self._retry_operation(submit_form, max_retries=3, delay=2, description="提交注册表单")

    def _safe_wait_for_birthday_page(self, page, timeout=90):
        """安全等待跳转到生日页面"""
        print(f"[验证] 等待跳转到生日页面（最多{timeout}秒）...")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            # 检查是否已经跳转到生日页面
            if self.element_helper.find_element(page, "birthday_form", "year_input", timeout=2000):
                print("✅ 已成功跳转到生日填写页面")
                return True
                
            # 检查是否有错误消息
            error_element = self.element_helper.find_element(page, "common", "error_message", timeout=1000)
            if error_element and error_element.is_visible():
                error_text = error_element.text_content()
                print(f"❌ 发现错误消息: {error_text}")
                return False
                
            # 检查验证码输入框是否还存在（说明验证码可能输入错误）
            code_input_still_exists = False
            input_selectors = get_element_list("registration_form", "verification_code_inputs_fallback")[:3]  # 只使用前3个选择器
            
            for selector in input_selectors:
                try:
                    temp_input = page.locator(selector).first
                    if temp_input.is_visible(timeout=1000):
                        code_input_still_exists = True
                        break
                except:
                    continue
            
            if code_input_still_exists:
                print("⚠️ 验证码输入框仍存在，可能需要重新输入验证码")
                
            time.sleep(3)
        
        print(f"❌ 等待{timeout}秒后仍未跳转到生日页面")
        return False

    def _handle_verification_code(self, page, mailbox_name, email):
        """处理验证码
        
        Args:
            page: Playwright页面对象
            mailbox_name: 邮箱名称
            email: 邮箱地址
            
        Returns:
            str: 验证码
        """
        print(f"[AccountManager] 正在自动获取验证码，请稍候...")
        print(f"[AccountManager] 监控邮箱: {email}")
        
        # 启动邮箱监控获取验证码
        verification_code = None
        try:
            # 等待90秒获取验证码（增加等待时间）
            # 使用10秒间隔，符合Maildrop官方建议（避免速率限制）
            verification_code = get_verification_code_from_maildrop(
                mailbox_name, 
                timeout_seconds=90,
                poll_interval=10  # 改为10秒，符合官方建议
            )
            
            if verification_code:
                print(f"[AccountManager] ✅ 自动获取到验证码: {verification_code}")
                
                # 多种方式查找验证码输入框
                code_input = None
                input_selectors = get_element_list("registration_form", "verification_code_inputs_fallback")
                
                for selector in input_selectors:
                    try:
                        temp_input = page.locator(selector).first
                        if temp_input.is_visible(timeout=1000):
                            code_input = temp_input
                            print(f"[AccountManager] 使用选择器找到验证码输入框: {selector}")
                            break
                    except:
                        continue
                
                if code_input:
                    # 清空输入框并输入验证码
                    code_input.clear()
                    code_input.fill(verification_code)
                    print("[AccountManager] 已自动填入验证码")
                    print("[AccountManager] 等待自动验证...")
                    time.sleep(3)  # 等待系统自动验证
                    
                else:
                    print("[AccountManager] ⚠️ 未找到验证码输入框，请手动输入")
            else:
                print("[AccountManager] ⚠️ 未能自动获取验证码")
            
        except Exception as e:
            print(f"[AccountManager] 自动获取验证码时出错: {e}")
            import traceback
            traceback.print_exc()
        
        return verification_code

    def _safe_fill_birthday(self, page, birth_year, birth_month, birth_day):
        """安全填写生日信息
        
        Args:
            page: Playwright页面对象
            birth_year: 出生年份
            birth_month: 出生月份
            birth_day: 出生日期
            
        Returns:
            bool: 是否填写成功
        """
        def fill_year():
            result = self.element_helper.fill_element(page, "birthday_form", "year_input", birth_year)
            if result:
                time.sleep(1)
                # 验证年份是否正确填入
                year_input = self.element_helper.find_element(page, "birthday_form", "year_input")
                if year_input:
                    current_value = year_input.input_value()
                    return current_value == birth_year
            return False
        
        def fill_month():
            print(f"  选择月份: {birth_month}")
            month_selected = self.element_helper.select_dropdown_option_enhanced(
                page, "birthday_form", "month_dropdown", birth_month, "month"
            )
            
            # 如果增强方法失败，尝试原始方法
            if not month_selected:
                print("[AccountManager] 增强方法失败，尝试原始方法选择月份...")
                month_selected = self.element_helper.select_dropdown_option(
                    page, "birthday_form", "month_dropdown",
                    "birthday_form", "month_option", birth_month
                )
            return month_selected
        
        def fill_day():
            print(f"  选择日期: {birth_day}")
            day_selected = self.element_helper.select_dropdown_option_enhanced(
                page, "birthday_form", "day_dropdown", birth_day, "day"
            )
            
            # 如果增强方法失败，尝试原始方法
            if not day_selected:
                print("[AccountManager] 增强方法失败，尝试原始方法选择日期...")
                day_selected = self.element_helper.select_dropdown_option(
                    page, "birthday_form", "day_dropdown",
                    "birthday_form", "day_option", birth_day
                )
            return day_selected
        
        # 分别重试每个步骤
        if not self._retry_operation(fill_year, max_retries=3, delay=1, description="输入年份"):
            return False
            
        if not self._retry_operation(fill_month, max_retries=3, delay=1, description="选择月份"):
            return False
            
        if not self._retry_operation(fill_day, max_retries=3, delay=1, description="选择日期"):
            return False
        
        # 点击Next按钮
        def click_next():
            result = self.element_helper.click_element(page, "birthday_form", "next_button")
            if result:
                time.sleep(3)
                # 验证是否出现成功模态框或下一个步骤
                return (self.element_helper.find_element(page, "success_modal", "ok_button", timeout=5000) or
                        self.element_helper.find_element(page, "registration_complete", "continue_button", timeout=5000))
            return False
        
        return self._retry_operation(click_next, max_retries=3, delay=2, description="点击Next按钮")

    def _safe_complete_registration(self, page, index, email, password, username, birth_year, birth_month, birth_day, verification_code):
        """安全完成注册
        
        Args:
            page: Playwright页面对象
            index: 账号序号
            email: 邮箱
            password: 密码
            username: 用户名
            birth_year: 出生年份
            birth_month: 出生月份
            birth_day: 出生日期
            verification_code: 验证码
            
        Returns:
            bool: 是否完成注册成功
        """
        def complete_registration():
            # 等待成功模态框出现
            ok_button_found = False
            for _ in range(10):  # 最多等待10秒
                if self.element_helper.find_element(page, "success_modal", "ok_button", timeout=1000):
                    ok_button_found = True
                    break
                time.sleep(1)
            
            if ok_button_found:
                if self.element_helper.click_element(page, "success_modal", "ok_button"):
                    print("✅ 注册成功！")
                    
                    # 保存账号信息
                    account_info = {
                        "序号": index,
                        "邮箱": email,
                        "密码": password,
                        "用户名": username,
                        "生日": f"{birth_year}-{birth_month}-{birth_day}",
                        "注册时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "状态": "成功",
                        "备注": "自动获取验证码" if verification_code else "手动输入验证码"
                    }
                    self.accounts_data.append(account_info)
                    return True
                else:
                    print("❌ 无法点击OK按钮")
                    return False
            else:
                print("❌ 未找到成功确认按钮")
                return False
        
        return self._retry_operation(complete_registration, max_retries=3, delay=2, description="完成注册确认") 