import pandas as pd
import os
import glob

EXCEL_FOLDER_PATH = "excel_prompts"  # 定义包含Excel文件的文件夹路径

def get_excel_file_paths(folder_path=EXCEL_FOLDER_PATH):
    """
    获取指定文件夹下所有Excel文件 (.xlsx, .xls) 的路径列表。
    """
    if not os.path.isdir(folder_path):
        print(f"[ExcelReader] 错误：文件夹 '{folder_path}' 不存在。")
        return []
    
    excel_files = glob.glob(os.path.join(folder_path, "*.xlsx")) + \
                  glob.glob(os.path.join(folder_path, "*.xls"))
    
    if not excel_files:
        print(f"[ExcelReader] 警告：在文件夹 '{folder_path}' 中未找到Excel文件。")
    return excel_files

def get_prompts_from_single_excel(file_path):
    """
    读取单个指定的Excel文件第一列的提示词。
    返回一个列表，其中每个元素是一个字典，包含 'prompt', 'source_excel_name', 'row_number', 和 'original_file_path'。
    'source_excel_name' 是不含扩展名的Excel文件名。
    'row_number' 是提示词在原Excel文件中的1基行号。
    'original_file_path' 是原始文件的完整路径。
    """
    prompts_data = []
    if not os.path.isfile(file_path):
        print(f"[ExcelReader] 错误：文件 '{file_path}' 不是一个有效的文件路径。")
        return prompts_data

    try:
        source_excel_name = os.path.splitext(os.path.basename(file_path))[0]
        # 读取时不指定usecols，以便后续写入时保留其他列数据
        df = pd.read_excel(file_path, header=None, dtype=str, sheet_name=0)
        
        if df.empty:
            print(f"[ExcelReader] 文件 '{os.path.basename(file_path)}' 的第一张工作表为空或仅包含头部。")
            return prompts_data

        prompts_added_from_file = 0
        for index, row in df.iterrows():
            # 提示词仍然从第一列 (iloc[0]) 读取
            prompt_text = row.iloc[0] if len(row) > 0 and pd.notna(row.iloc[0]) else None 
            if prompt_text and str(prompt_text).strip(): # 确保 prompt_text 不为 None 且 strip 后不为空
                current_prompt_clean = str(prompt_text).strip()
                excel_row_number = index + 1 # pandas的索引是0基，转换为1基行号
                
                prompts_data.append({
                    'prompt': current_prompt_clean,
                    'source_excel_name': source_excel_name,
                    'row_number': excel_row_number,
                    'original_file_path': file_path  # 添加原始文件路径
                })
                prompts_added_from_file += 1
        
        if prompts_added_from_file > 0:
            print(f"[ExcelReader] 从 '{os.path.basename(file_path)}' 提取了 {prompts_added_from_file} 个提示词。")
        else:
            print(f"[ExcelReader] 文件 '{os.path.basename(file_path)}' 未提取到有效提示词。")

    except FileNotFoundError:
        print(f"[ExcelReader] 错误：文件 '{file_path}' 未找到。")
    except pd.errors.EmptyDataError:
        print(f"[ExcelReader] 错误：文件 '{os.path.basename(file_path)}' 是空的。")
    except IndexError:
        print(f"[ExcelReader] 错误：无法从文件 '{os.path.basename(file_path)}' 的第一列读取数据。检查文件格式。")
    except Exception as e:
        if "xlrd" in str(e).lower():
             print(f"[ExcelReader] 读取Excel文件 '{os.path.basename(file_path)}' 时可能存在问题 (例如 .xls 文件需要 'xlrd' 库，或版本不兼容): {e}")
        else:
            print(f"[ExcelReader] 读取Excel文件 '{os.path.basename(file_path)}' 时发生未知错误: {e}")
    
    return prompts_data

def update_excel_remark(original_file_path, row_number, column_index_zero_based, remark_text):
    """
    更新指定Excel文件特定单元格的备注。
    row_number: 1基行号。
    column_index_zero_based: 0基列号 (例如，第二列是1)。
    remark_text: 要写入的备注文本。
    """
    try:
        # 读取整个工作表，不设置列名，保留原始数据
        # engine=None 尝试自动选择，可根据xls/xlsx改为'xlrd'或'openpyxl'
        df = pd.read_excel(original_file_path, header=None, sheet_name=0, engine=None)

        actual_row_index = row_number - 1

        if actual_row_index < 0 or actual_row_index >= len(df):
            print(f"[ExcelWriter] 错误: 行号 {row_number} (0基索引 {actual_row_index}) 超出文件 '{os.path.basename(original_file_path)}' 的范围 (总行数: {len(df)})。")
            return False
        
        # 确保DataFrame有足够的列，如果不够则扩展
        while column_index_zero_based >= df.shape[1]:
            df[df.shape[1]] = pd.NA # 添加新列并用 pd.NA 填充 (更通用的缺失值表示)
        
        df.iat[actual_row_index, column_index_zero_based] = remark_text
        
        # 根据文件扩展名选择合适的引擎写回
        engine_to_write = 'openpyxl' if original_file_path.endswith('.xlsx') else None # None 会让 pandas 尝试根据扩展名推断
        df.to_excel(original_file_path, index=False, header=False, sheet_name='Sheet1', engine=engine_to_write)
        print(f"[ExcelWriter] 已成功在文件 '{os.path.basename(original_file_path)}' 的第 {row_number} 行，第 {column_index_zero_based + 1} 列写入备注: '{remark_text}'")
        return True
    except FileNotFoundError:
        print(f"[ExcelWriter] 错误: 文件 '{original_file_path}' 未找到，无法更新备注。")
        return False
    except Exception as e:
        print(f"[ExcelWriter] 更新Excel文件 '{os.path.basename(original_file_path)}' 时发生错误: {e}")
        return False

def get_prompts_from_excel_folder(folder_path=EXCEL_FOLDER_PATH):
    """
    读取指定文件夹下所有Excel文件第一列的提示词。
    返回一个列表，其中每个元素是一个字典，包含 'prompt', 'source_excel_name', 'row_number', and 'original_file_path'。
    会自动去重提示词（基于提示词文本），保留首次出现的行号和来源。
    """
    excel_files = get_excel_file_paths(folder_path)

    if not excel_files:
        return []

    all_prompts_with_source_and_row = []
    seen_prompts_globally = set()

    print(f"[ExcelReader] 开始从以下Excel文件读取提示词 (共 {len(excel_files)} 个文件):")
    # 为了日志更清晰，可以逐个打印文件名
    # for f_path in excel_files: print(f"  - {os.path.basename(f_path)}") 

    for file_path in excel_files:
        # 调用修改后的 get_prompts_from_single_excel
        single_file_prompts = get_prompts_from_single_excel(file_path)
        
        file_specific_prompts_added_to_global = 0
        for prompt_item in single_file_prompts:
            # prompt_item 已经是包含 'prompt', 'source_excel_name', 'row_number', 'original_file_path' 的字典
            if prompt_item['prompt'] not in seen_prompts_globally:
                all_prompts_with_source_and_row.append(prompt_item)
                seen_prompts_globally.add(prompt_item['prompt'])
                file_specific_prompts_added_to_global +=1
        
        if file_specific_prompts_added_to_global > 0:
            print(f"[ExcelReader] 从 '{os.path.basename(file_path)}' 提取并向全局列表添加了 {file_specific_prompts_added_to_global} 个新提示词。")
        # elif single_file_prompts: # 如果文件中有提示词但都重复了
            # print(f"[ExcelReader] 文件 '{os.path.basename(file_path)}' 中的提示词已存在于全局列表。")

    if not all_prompts_with_source_and_row:
        print("[ExcelReader] 未能从任何Excel文件中提取到唯一的、有效的提示词。")
    else:
        print(f"[ExcelReader] 总共提取到 {len(all_prompts_with_source_and_row)} 个唯一的提示词（含来源和行号），将进行处理。")
        
    return all_prompts_with_source_and_row

if __name__ == '__main__':
    base_test_folder = "temp_excel_reader_tests"
    if os.path.exists(base_test_folder):
        import shutil
        shutil.rmtree(base_test_folder)
    os.makedirs(base_test_folder)

    folder_for_single_read = os.path.join(base_test_folder, "single_files_here")
    os.makedirs(folder_for_single_read)
    print(f"[TestSetup] Created base test folder: {base_test_folder}")

    # 测试文件1: 包含多列数据
    data1 = {
        'Prompts': ['Alpha', 'Beta', 'Gamma'], 
        'Remarks': ['OldRemark1', '', 'OldRemark3'],
        'OtherData': [100, 200, 300]
    }
    df1 = pd.DataFrame(data1)
    file1_path_single = os.path.join(folder_for_single_read, "file_multi_col.xlsx")
    df1.to_excel(file1_path_single, index=False, header=False)
    print(f"[TestSetup] Created: {file1_path_single}")

    # 测试 get_prompts_from_single_excel
    print("\n--- 测试 get_prompts_from_single_excel (多列文件) ---")
    prompts1 = get_prompts_from_single_excel(file1_path_single)
    print(f"从 '{os.path.basename(file1_path_single)}' 提取的提示词:")
    for item in prompts1: print(f"  {item}")
    expected_prompts1_texts = ['Alpha', 'Beta', 'Gamma']
    actual_prompts1_texts = [p['prompt'] for p in prompts1]
    if actual_prompts1_texts == expected_prompts1_texts and \
       all(p['original_file_path'] == file1_path_single for p in prompts1):
        print(f"get_prompts_from_single_excel ({os.path.basename(file1_path_single)}): PASS")
    else:
        print(f"get_prompts_from_single_excel ({os.path.basename(file1_path_single)}): FAIL")

    # --- 测试 update_excel_remark ---
    print("\n--- 测试 update_excel_remark ---")
    # 场景1: 更新现有备注列的单元格 (第2行，第2列，即B2)
    update_success = update_excel_remark(file1_path_single, row_number=2, column_index_zero_based=1, remark_text="Updated Beta Remark")
    # 场景2: 在新列写入备注 (第1行，第4列，即D1)
    update_success_new_col = update_excel_remark(file1_path_single, row_number=1, column_index_zero_based=3, remark_text="New Col Alpha")
    # 场景3: 更新第一列 (第3行，第1列，即A3) - 不推荐，因为这里存的是提示词
    # update_success_col_A = update_excel_remark(file1_path_single, row_number=3, column_index_zero_based=0, remark_text="Modified Gamma Prompt") 

    print(f"更新操作1状态: {update_success}, 操作2状态: {update_success_new_col}")

    # 验证更改
    if update_success and update_success_new_col:
        df_check = pd.read_excel(file1_path_single, header=None, sheet_name=0)
        print("更新后的Excel内容:")
        print(df_check)
        # 检查 B2 (0-indexed: 1,1)
        # 检查 D1 (0-indexed: 0,3)
        remark_b2 = df_check.iat[1, 1] if df_check.shape[1] > 1 else "[Col B not found]"
        remark_d1 = df_check.iat[0, 3] if df_check.shape[1] > 3 else "[Col D not found]"
        
        expected_b2 = "Updated Beta Remark"
        expected_d1 = "New Col Alpha"
        
        pass_b2 = str(remark_b2) == expected_b2
        pass_d1 = str(remark_d1) == expected_d1

        if pass_b2 and pass_d1:
            print("update_excel_remark: PASS")
        else:
            print("update_excel_remark: FAIL")
            if not pass_b2: print(f"  B2: Expected '{expected_b2}', Got '{remark_b2}'")
            if not pass_d1: print(f"  D1: Expected '{expected_d1}', Got '{remark_d1}'")
    else:
        print("update_excel_remark: FAIL (一个或多个更新操作返回False)")

    # 清理
    # shutil.rmtree(base_test_folder)
    # print(f"\n[TestCleanup] 已删除测试文件夹: {base_test_folder}")
    print("\n测试完成。如果不想保留测试文件夹和文件，请手动删除：", base_test_folder)