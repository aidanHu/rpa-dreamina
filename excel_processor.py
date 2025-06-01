#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import os
import glob
from pathlib import Path
import json

def load_config():
    """加载用户配置"""
    try:
        with open('user_config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[ExcelProcessor] 加载配置文件失败: {e}")
        return {}

def get_excel_settings():
    """获取Excel相关设置"""
    config = load_config()
    excel_settings = config.get("excel_settings", {})
    return {
        "prompt_column": excel_settings.get("prompt_column", 2),
        "status_column": excel_settings.get("status_column", 3),
        "status_text": excel_settings.get("status_text", "已生成图片"),
        "start_row": excel_settings.get("start_row", 2)
    }

def find_excel_files_in_subfolders(root_directory):
    """
    在根目录下的所有子文件夹中查找Excel文件
    
    Args:
        root_directory: 根目录路径
        
    Returns:
        list: 包含Excel文件信息的列表，每个元素包含文件路径和所在文件夹
    """
    if not os.path.exists(root_directory):
        print(f"[ExcelProcessor] 错误：根目录 '{root_directory}' 不存在。")
        return []
    
    excel_files = []
    
    # 遍历根目录下的所有子文件夹
    for item in os.listdir(root_directory):
        subfolder_path = os.path.join(root_directory, item)
        
        # 只处理文件夹
        if not os.path.isdir(subfolder_path):
            continue
            
        # 在子文件夹中查找Excel文件
        excel_patterns = [
            os.path.join(subfolder_path, "*.xlsx"),
            os.path.join(subfolder_path, "*.xls")
        ]
        
        subfolder_excel_files = []
        for pattern in excel_patterns:
            subfolder_excel_files.extend(glob.glob(pattern))
        
        if subfolder_excel_files:
            # 如果有多个Excel文件，只取第一个并警告
            if len(subfolder_excel_files) > 1:
                print(f"[ExcelProcessor] 警告：子文件夹 '{item}' 中有多个Excel文件，只处理第一个: {os.path.basename(subfolder_excel_files[0])}")
            
            excel_files.append({
                'file_path': subfolder_excel_files[0],
                'subfolder_name': item,
                'subfolder_path': subfolder_path
            })
        else:
            print(f"[ExcelProcessor] 信息：子文件夹 '{item}' 中未找到Excel文件，跳过。")
    
    return excel_files

def check_if_prompt_generated_in_subfolder(prompt_text, subfolder_path):
    """
    检查指定提示词是否已经在子文件夹中生成过图片
    
    Args:
        prompt_text: 提示词文本
        subfolder_path: 子文件夹路径
        
    Returns:
        bool: 是否已生成
    """
    try:
        # 简单的文件名清理函数，避免导入问题
        def simple_sanitize_filename(text):
            import re
            sanitized = re.sub(r'[<>:"/\\|?*]', '_', text)
            sanitized = re.sub(r'[\r\n\t]', ' ', sanitized)
            sanitized = re.sub(r'\s+', '_', sanitized.strip())
            return sanitized[:50] if len(sanitized) > 50 else sanitized
        
        if not os.path.exists(subfolder_path):
            return False
        
        # 构建文件名前缀
        file_prefix = simple_sanitize_filename(prompt_text)
        
        # 检查是否存在以该前缀开头的图片文件
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
            pattern = os.path.join(subfolder_path, f"*{file_prefix}*{ext}")
            if glob.glob(pattern):
                return True
                
        return False
        
    except Exception as e:
        print(f"[ExcelProcessor] 检查提示词生成状态时出错: {e}")
        return False

def mark_prompt_as_processed(excel_file_path, row_number, status_column=3, status_text="已生成图片"):
    """
    在Excel文件中标记提示词为已处理
    
    Args:
        excel_file_path: Excel文件路径
        row_number: 行号（1基）
        status_column: 状态列号（1基）
        status_text: 状态标记文本
    """
    try:
        # 读取Excel文件
        df = pd.read_excel(excel_file_path, header=None)
        
        # 确保有足够的列
        max_col = max(status_column, df.shape[1])
        if df.shape[1] < max_col:
            df = df.reindex(columns=range(max_col))
        
        # 标记状态（转换为0基索引）
        df.iloc[row_number - 1, status_column - 1] = status_text
        
        # 保存回Excel文件
        df.to_excel(excel_file_path, index=False, header=False, engine='openpyxl')
        print(f"[ExcelProcessor] 已标记行 {row_number} 为: {status_text}")
        
    except Exception as e:
        print(f"[ExcelProcessor] 标记Excel文件时出错: {e}")

def get_unprocessed_prompts(root_directory):
    """
    从Excel文件中获取未处理的提示词列表
    
    Args:
        root_directory: Excel文件所在的根目录
        
    Returns:
        list: 未处理的提示词信息列表
    """
    unprocessed_prompts = []
    seen_prompts_globally = set()  # 用于全局去重
    
    # 获取Excel设置
    excel_settings = get_excel_settings()
    prompt_column = excel_settings["prompt_column"]
    status_column = excel_settings["status_column"]
    status_text = excel_settings["status_text"]
    start_row = excel_settings["start_row"]
    
    # 获取所有子文件夹中的Excel文件
    excel_files = find_excel_files_in_subfolders(root_directory)
    
    # 遍历每个Excel文件
    for excel_info in excel_files:
        file_path = excel_info['file_path']
        subfolder_name = excel_info['subfolder_name']
        subfolder_path = excel_info['subfolder_path']
        
        try:
            print(f"\n[ExcelProcessor] 处理文件: {os.path.basename(file_path)}")
            
            # 读取Excel文件
            df = pd.read_excel(file_path, header=None)
            
            file_unprocessed_count = 0
            file_already_processed_count = 0
            
            # 遍历每一行
            for index, row in df.iterrows():
                excel_row_number = index + 1  # pandas的索引是0基，转换为1基行号
                
                # 跳过标题行，从指定行开始处理
                if excel_row_number < start_row:
                    continue
                
                prompt_text = row.iloc[prompt_column - 1] if len(row) >= prompt_column else None  # 提示词列（可配置）
                status_cell = row.iloc[status_column - 1] if len(row) >= status_column else None  # 状态列
                
                # 检查是否为有效提示词
                if pd.notna(prompt_text) and str(prompt_text).strip():
                    current_prompt_clean = str(prompt_text).strip()
                    
                    # 跳过重复的提示词
                    if current_prompt_clean in seen_prompts_globally:
                        continue
                    
                    # 检查Excel中的状态标记
                    if pd.notna(status_cell) and str(status_cell).strip() in [status_text, "提示词有问题，需修改"]:
                        file_already_processed_count += 1
                        seen_prompts_globally.add(current_prompt_clean)
                        continue
                    
                    # 检查是否已经生成过图片
                    if check_if_prompt_generated_in_subfolder(current_prompt_clean, subfolder_path):
                        print(f"[ExcelProcessor] 发现已生成图片的提示词，自动标记: 行{excel_row_number} - {current_prompt_clean[:30]}...")
                        mark_prompt_as_processed(file_path, excel_row_number, status_column, status_text)
                        file_already_processed_count += 1
                        seen_prompts_globally.add(current_prompt_clean)
                        continue
                    
                    # 添加到未处理列表
                    unprocessed_prompts.append({
                        'prompt': current_prompt_clean,
                        'source_excel_name': os.path.splitext(os.path.basename(file_path))[0],
                        'row_number': excel_row_number,
                        'excel_file_path': file_path,
                        'subfolder_name': subfolder_name,
                        'subfolder_path': subfolder_path,
                        'image_save_path': subfolder_path  # 图片保存到Excel所在的子文件夹
                    })
                    seen_prompts_globally.add(current_prompt_clean)
                    file_unprocessed_count += 1
            
            print(f"[ExcelProcessor] 子文件夹 '{subfolder_name}': 未处理 {file_unprocessed_count} 个，已处理 {file_already_processed_count} 个")

        except FileNotFoundError:
            print(f"[ExcelProcessor] 错误：文件 '{file_path}' 未找到。")
        except pd.errors.EmptyDataError:
            print(f"[ExcelProcessor] 错误：文件 '{os.path.basename(file_path)}' 是空的或无法解析。")
        except Exception as e:
            print(f"[ExcelProcessor] 读取Excel文件 '{os.path.basename(file_path)}' 时发生错误: {e}")

    if not unprocessed_prompts:
        print("[ExcelProcessor] ✅ 所有提示词都已处理完成！")
    else:
        print(f"[ExcelProcessor] 找到 {len(unprocessed_prompts)} 个未处理的提示词，将继续处理。")
        
    return unprocessed_prompts

# 兼容性函数，保持与原有代码的兼容性
def get_unprocessed_prompts_from_excel_folder(folder_path, image_save_path="generated_images"):
    """
    兼容性函数：如果传入的是旧的excel_folder_path，则作为根目录处理
    """
    return get_unprocessed_prompts(folder_path)

# 添加新的兼容性函数
def get_unprocessed_prompts_from_subfolders(root_directory):
    """
    兼容性函数：从子文件夹中获取未处理的提示词
    """
    return get_unprocessed_prompts(root_directory)

def get_prompts_from_excel_folder(folder_path):
    """
    兼容性函数：读取所有提示词（包括已处理的）
    保持与原有代码的兼容性
    """
    return get_unprocessed_prompts(folder_path)

# 测试代码
if __name__ == '__main__':
    # 创建测试数据结构
    test_root = "test_projects"
    if not os.path.exists(test_root):
        os.makedirs(test_root)

    # 创建测试子文件夹和Excel文件
    for i, project_name in enumerate(["项目A", "项目B"], 1):
        project_path = os.path.join(test_root, project_name)
        os.makedirs(project_path, exist_ok=True)
        
        # 创建测试Excel文件
        test_data = {
            'prompts': [f'{project_name}的可爱小猫', f'{project_name}的美丽风景', f'{project_name}的红色汽车'],
            'status': [None, None, None],
            'other': [None, None, None]
        }
        df_test = pd.DataFrame(test_data)
        test_file = os.path.join(project_path, f"{project_name}_提示词.xlsx")
        df_test.to_excel(test_file, index=False, header=False)
        print(f"创建测试文件: {test_file}")

    print("\n测试新的子文件夹结构...")
    unprocessed = get_unprocessed_prompts(test_root)
    
    if unprocessed:
        print(f"\n找到 {len(unprocessed)} 个未处理的提示词:")
        for item in unprocessed:
            print(f"  子文件夹: {item['subfolder_name']}")
            print(f"  行号: {item['row_number']}")
            print(f"  提示词: '{item['prompt']}'")
            print(f"  图片保存路径: {item['image_save_path']}")
            print("  ---")
    else:
        print("\n没有找到未处理的提示词。") 