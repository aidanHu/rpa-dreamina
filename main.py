#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import time
from pathlib import Path

# 配置文件路径
CONFIG_FILE = "gui_config.json"

def load_config():
    """加载配置文件"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # 创建默认配置
            default_config = {
                "browser_settings": {
                    "browser_ids": []
                },
                "file_paths": {
                    "root_directory": "Projects"
                },
                "excel_settings": {
                    "prompt_column": 2,
                    "status_column": 3,
                    "status_text": "已生成图片",
                    "start_row": 2
                },
                "image_settings": {
                    "default_model": "Image 3.0",
                    "default_aspect_ratio": "9:16"
                },
                "points_monitoring": {
                    "enabled": True,
                    "min_points_threshold": 4,
                    "check_interval_seconds": 30
                }
            }
            save_config(default_config)
            return default_config
    except Exception as e:
        print(f"❌ 加载配置文件失败: {e}")
        return {
            "file_paths": {
                "root_directory": "Projects"
            },
            "excel_settings": {
                "status_column": 3,
                "status_text": "已生成图片"
            },
            "image_settings": {
                "default_model": "Image 3.0",
                "default_aspect_ratio": "9:16"
            }
        }

def save_config(config):
    """保存配置文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"❌ 保存配置失败: {e}")
        return False

def validate_root_directory(path):
    """验证根目录路径（新的子文件夹结构）"""
    if not path:
        return False, "路径为空"
    
    path_obj = Path(path)
    
    if not path_obj.exists():
        return False, f"路径不存在: {path}"
    
    if not path_obj.is_dir():
        return False, f"路径不是文件夹: {path}"
    
    # 检查子文件夹中是否包含Excel文件
    excel_count = 0
    subfolder_count = 0
    
    for item in path_obj.iterdir():
        if item.is_dir():
            subfolder_count += 1
            # 检查子文件夹中的Excel文件
            excel_files = list(item.glob("*.xlsx")) + list(item.glob("*.xls"))
            if excel_files:
                excel_count += len(excel_files)
    
    if subfolder_count == 0:
        return False, f"根目录中没有子文件夹: {path}"
    
    if excel_count == 0:
        return False, f"子文件夹中没有找到Excel文件: {path}"
    
    return True, f"找到 {subfolder_count} 个子文件夹，包含 {excel_count} 个Excel文件"

def run_gui():
    """启动GUI界面"""
    try:
        # 检查PyQt6依赖
        try:
            from PyQt6.QtWidgets import QApplication
            from dreamina_gui import run_gui as gui_main
        except ImportError as e:
            print(f"❌ 缺少PyQt6依赖: {e}")
            print("请运行: pip install PyQt6")
            return False
        
        # 启动GUI
        return gui_main()
        
    except Exception as e:
        print(f"❌ 启动GUI失败: {e}")
        return False

def main():
    """主程序入口 - 直接启动GUI"""
    success = run_gui()
    
    if not success:
        print("❌ 程序启动失败")

if __name__ == "__main__":
    main() 