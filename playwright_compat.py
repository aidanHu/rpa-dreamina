#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Playwright 版本兼容性辅助模块
处理不同版本 Playwright 之间的API差异
"""

def safe_title(page, timeout=None):
    """
    安全地获取页面标题，兼容不同版本的Playwright
    """
    try:
        if timeout is not None:
            try:
                return page.title(timeout=timeout)
            except TypeError:
                # 如果timeout参数不支持，使用不带参数的版本
                return page.title()
        else:
            return page.title()
    except Exception as e:
        print(f"[PlaywrightCompat] 获取页面标题失败: {e}")
        return None

def safe_is_visible(element, timeout=None):
    """
    安全地检查元素是否可见，兼容不同版本的Playwright
    """
    try:
        if timeout is not None:
            try:
                return element.is_visible(timeout=timeout)
            except TypeError:
                # 如果timeout参数不支持，使用不带参数的版本
                return element.is_visible()
        else:
            return element.is_visible()
    except Exception as e:
        print(f"[PlaywrightCompat] 检查元素可见性失败: {e}")
        return False

def safe_wait_for_selector(page, selector, timeout=None):
    """
    安全地等待选择器，兼容不同版本的Playwright
    """
    try:
        if timeout is not None:
            return page.wait_for_selector(selector, timeout=timeout)
        else:
            return page.wait_for_selector(selector)
    except Exception as e:
        print(f"[PlaywrightCompat] 等待选择器失败: {e}")
        return None

def safe_wait_for(element, state="visible", timeout=None):
    """
    安全地等待元素状态，兼容不同版本的Playwright
    """
    try:
        if timeout is not None:
            return element.wait_for(state=state, timeout=timeout)
        else:
            return element.wait_for(state=state)
    except Exception as e:
        print(f"[PlaywrightCompat] 等待元素状态失败: {e}")
        return None 