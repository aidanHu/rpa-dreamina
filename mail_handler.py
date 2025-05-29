#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import time
import re
import json

# Maildrop.cc API配置
GRAPHQL_API_URL = "https://api.maildrop.cc/graphql"

DEFAULT_TIMEOUT_SECONDS = 180  # 3分钟
DEFAULT_POLL_INTERVAL = 10  # 轮询间隔（秒）- 符合官方建议的每10秒检查一次

# 速率限制参数
MAX_GRAPHQL_RETRIES = 3
RETRY_DELAY_SECONDS = 15  # 429错误或其他可重试错误后的延迟

# 用于识别相关验证邮件的关键词
SUBJECT_KEYWORDS = ["dreamina", "capcut", "verification", "code", "verify", "验证", "代码", "激活", "confirm", "activation"]
SENDER_KEYWORDS = ["dreamina", "capcut", "bytedance", "noreply", "support", "account", "no-reply", "team", "service"]

def extract_verification_code(content: str) -> str | None:
    """从内容（HTML或纯文本）中提取验证码
    
    支持多种验证码格式：
    - 6位数字
    - 6位字母数字混合（如 AT2U3J）
    """
    if not content:
        return None
    
    plain_text = content
    # 如果是HTML内容，进行简单的标签剥离
    if "<" in content and ">" in content:
        print("[MailHandler] 检测到HTML内容，正在剥离标签...")
        # 先移除style和script块
        plain_text = re.sub(r'<style[^>]*?>.*?</style>', '', plain_text, flags=re.IGNORECASE | re.DOTALL)
        plain_text = re.sub(r'<script[^>]*?>.*?</script>', '', plain_text, flags=re.IGNORECASE | re.DOTALL)
        # 移除所有其他标签
        plain_text = re.sub(r'<[^>]+?>', ' ', plain_text)
        # 规范化空白字符
        plain_text = re.sub(r'\s+', ' ', plain_text).strip()
    
    # 查找验证码的多种模式
    # 模式1: "Your verification code: XXXXXX" 格式
    patterns = [
        r'Your verification code:\s*([A-Z0-9]{6})',  # 匹配 "Your verification code: AT2U3J"
        r'verification code:\s*([A-Z0-9]{6})',        # 更宽松的匹配
        r'code:\s*([A-Z0-9]{6})',                     # 更宽松的匹配
        r'(?<!\w)([A-Z0-9]{6})(?!\w)',                # 独立的6位字母数字组合
        r'(?<!\d)\d{6}(?!\d)',                        # 6位纯数字（原有模式）
    ]
    
    for pattern in patterns:
        match = re.search(pattern, plain_text, re.IGNORECASE)
    if match:
            code = match.group(1) if match.lastindex else match.group(0)
            log_text_preview = plain_text[:200].replace('\n', ' ')
            print(f"[MailHandler] 提取到验证码: {code}")
            print(f"[MailHandler] 使用的模式: {pattern}")
            return code.upper()  # 统一转为大写
    
    # 如果都没找到，打印部分内容用于调试
    print(f"[MailHandler] 未找到验证码")
    print(f"[MailHandler] 内容预览: {plain_text[:300]}")
    return None

def _send_graphql_request(query: str, variables: dict) -> dict | None:
    """发送GraphQL请求到Maildrop"""
    headers = {'Content-Type': 'application/json'}
    payload = {'query': query, 'variables': variables}
    
    for attempt in range(MAX_GRAPHQL_RETRIES):
        try:
            log_query = query.strip().replace('\n', ' ')
            if len(log_query) > 100:
                log_query = log_query[:100] + "..."
            print(f"[MailHandler] 发送GraphQL请求 (尝试 {attempt + 1}/{MAX_GRAPHQL_RETRIES})...")
            
            response = requests.post(GRAPHQL_API_URL, headers=headers, json=payload, timeout=20)
            
            if response.status_code == 429:  # 请求过多
                print(f"[MailHandler] 收到429错误，等待 {RETRY_DELAY_SECONDS} 秒后重试...")
                if attempt < MAX_GRAPHQL_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue
                else:
                    print(f"[MailHandler] 达到最大重试次数")
                    return None

            response.raise_for_status()
            
            response_json = response.json()
            if 'errors' in response_json:
                print(f"[MailHandler] GraphQL API返回错误: {response_json['errors']}")
                return None
            if 'data' not in response_json:
                print(f"[MailHandler] GraphQL响应缺少'data'字段")
                return None
            return response_json['data']

        except requests.exceptions.Timeout:
            print(f"[MailHandler] 请求超时 (尝试 {attempt + 1})")
            if attempt < MAX_GRAPHQL_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                return None
        except Exception as e:
            print(f"[MailHandler] 请求出错: {e}")
            return None
    
    return None

def get_mailbox_listing_graphql(mailbox: str) -> list[dict] | None:
    """使用GraphQL获取邮箱列表"""
    query = """
        query GetInbox($mailbox: String!) {
            inbox(mailbox: $mailbox) {
                id
                headerfrom
                subject
                date
            }
        }
    """
    variables = {"mailbox": mailbox}
    data = _send_graphql_request(query, variables)
    
    if data and 'inbox' in data:
        # inbox可能是None（查询失败）或者空数组（邮箱为空）
        if data['inbox'] is None:
            print(f"[MailHandler] 邮箱查询失败")
            return None
        # 返回邮件列表（可能为空数组）
        return data['inbox']
    return None

def get_specific_message_graphql(mailbox: str, message_id: str) -> dict | None:
    """使用GraphQL获取特定邮件内容"""
    # 先获取基本信息
    query_minimal = """
        query GetMessageMinimal($mailbox: String!, $id: String!) {
            message(mailbox: $mailbox, id: $id) {
                id
                subject 
                headerfrom
                date
            }
        }
    """
    variables = {"mailbox": mailbox, "id": message_id}
    minimal_data = _send_graphql_request(query_minimal, variables)

    if not (minimal_data and 'message' in minimal_data and minimal_data['message']):
        print(f"[MailHandler] 获取邮件 {message_id} 基本信息失败")
        return None
    
    base_message_data = minimal_data['message']
    
    # 获取HTML内容
    query_html = """
        query GetMessageWithHTML($mailbox: String!, $id: String!) {
            message(mailbox: $mailbox, id: $id) {
                html 
            }
        }
    """
    html_data = _send_graphql_request(query_html, variables)

    if html_data and 'message' in html_data and html_data['message'] and 'html' in html_data['message']:
        base_message_data['html_content'] = html_data['message']['html']
        return base_message_data
    
        return None 

def get_verification_code_from_maildrop(mailbox: str, 
                                      timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS, 
                                      poll_interval: int = DEFAULT_POLL_INTERVAL) -> str | None:
    """
    轮询Maildrop.cc邮箱，获取验证码

    Args:
        mailbox: 邮箱名（例如 'username' 对应 'username@maildrop.cc'）
        timeout_seconds: 轮询超时时间
        poll_interval: 轮询间隔

    Returns:
        6位验证码字符串，如果未找到返回None
    """
    print(f"[MailHandler] 开始轮询邮箱: '{mailbox}@maildrop.cc'")
    start_time = time.time()
    checked_message_ids = set()  # 记录已检查过的邮件ID

    while time.time() - start_time < timeout_seconds:
        elapsed = time.time() - start_time
        print(f"[MailHandler] 轮询中... 已用时: {elapsed:.0f}秒 / {timeout_seconds}秒")
        
        messages = get_mailbox_listing_graphql(mailbox)

        if messages is None:
            print(f"[MailHandler] 获取邮箱列表失败，将重试")
        elif not messages:
            print(f"[MailHandler] 邮箱为空")
        else:
            print(f"[MailHandler] 发现 {len(messages)} 封邮件")
            # 检查所有邮件（不只是新邮件）
            for msg in messages:
                if not msg or not msg.get('id'):
                    continue
                
                message_id = msg.get('id')
                
                # 如果已经检查过这封邮件且没有验证码，跳过
                if message_id in checked_message_ids:
                    continue 

                print(f"[MailHandler] 检查邮件:")
                print(f"  ID: {message_id}")
                print(f"  主题: {msg.get('subject')}")
                print(f"  发件人: {msg.get('headerfrom')}")
                
                # 检查是否是相关邮件
                subject_str = (msg.get('subject') or '').lower()
                sender_str = (msg.get('headerfrom') or '').lower()
                
                # 检查是否包含关键词
                is_relevant = False
                for keyword in SUBJECT_KEYWORDS:
                    if keyword in subject_str or keyword in sender_str:
                        is_relevant = True
                        print(f"[MailHandler] 邮件匹配关键词: {keyword}")
                        break
                
                if not is_relevant:
                    # 再检查发件人关键词
                    for keyword in SENDER_KEYWORDS:
                        if keyword in sender_str:
                            is_relevant = True
                            print(f"[MailHandler] 发件人匹配关键词: {keyword}")
                            break

                if not is_relevant:
                    print(f"[MailHandler] 邮件不相关，跳过")
                    checked_message_ids.add(message_id)
                    continue

                print(f"[MailHandler] 邮件可能包含验证码，获取完整内容...")
                msg_detail = get_specific_message_graphql(mailbox, message_id)

                if msg_detail:
                    html_content = msg_detail.get('html_content')
                    if html_content:
                        code = extract_verification_code(html_content)
                        if code:
                            print(f"[MailHandler] ✅ 成功提取验证码: {code}")
                            return code
                        else:
                            print(f"[MailHandler] 未能从邮件中提取验证码")
                            # 如果没有提取到验证码，也要记录这个ID避免重复检查
                            checked_message_ids.add(message_id)
                    else:
                        print(f"[MailHandler] 邮件内容为空")
                        checked_message_ids.add(message_id)
                else:
                    print(f"[MailHandler] 获取邮件详情失败")
                    # 获取失败的邮件下次还可以尝试，不加入已检查列表
        
        time.sleep(poll_interval)

    print(f"[MailHandler] 超时：在 {timeout_seconds} 秒内未找到验证码邮件")
    return None

def create_maildrop_email():
    """
    创建一个随机的Maildrop邮箱地址
    
    Returns:
        tuple: (邮箱地址, 邮箱名)
    """
    import random
    import string
    
    # 生成随机邮箱名
    length = random.randint(8, 12)
    mailbox_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
    email = f"{mailbox_name}@maildrop.cc"
    
    print(f"[MailHandler] 创建Maildrop邮箱: {email}")
    return email, mailbox_name

# 测试代码
if __name__ == '__main__':
    print("=== Dreamina邮箱验证码处理测试 ===")
    
    # 创建测试邮箱
    test_email, test_mailbox = create_maildrop_email()
    print(f"测试邮箱: {test_email}")
    print(f"请发送包含6位验证码的邮件到此邮箱")
    print(f"邮件主题应包含: {SUBJECT_KEYWORDS}")
    print(f"等待时间: {DEFAULT_TIMEOUT_SECONDS} 秒...")

    code = get_verification_code_from_maildrop(test_mailbox)

    if code:
        print(f"\n✅ 成功获取验证码: {code}")
    else:
        print(f"\n❌ 未能获取验证码") 