#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Dreamina GUI - PyQt6界面
提供直观的用户配置和启动界面
"""

import sys
import json
import os
import threading
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QGridLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QGroupBox,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QTabWidget,
    QSpinBox, QCheckBox, QProgressBar, QSplitter, QFrame, QInputDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QMetaObject
from PyQt6.QtGui import QIcon, QPixmap

from simple_dreamina_manager import SimpleDreaminaManager
import io
import sys

class GuiLogHandler:
    """将print输出重定向到GUI日志"""
    def __init__(self, log_callback):
        self.log_callback = log_callback
        self.buffer = ""
    
    def write(self, text):
        try:
            if text and text.strip() and self.log_callback:  # 只处理非空内容
                # 移除不需要的前缀
                clean_text = text.strip()
                if clean_text.startswith('[') and ']' in clean_text:
                    # 提取日志内容，移除模块前缀
                    try:
                        end_bracket = clean_text.index(']')
                        clean_text = clean_text[end_bracket + 1:].strip()
                    except:
                        pass
                if clean_text:
                    self.log_callback(clean_text)
        except Exception as e:
            # 如果GUI日志失败，回退到标准输出
            try:
                print(f"GUI日志错误: {e}", file=sys.__stderr__)
                print(text, file=sys.__stderr__)
            except:
                pass
    
    def flush(self):
        try:
            pass
        except:
            pass

class DreaminaWorkerThread(QThread):
    """工作线程 - 处理图片生成任务"""
    
    # 信号定义
    progress_update = pyqtSignal(str)
    progress_stats = pyqtSignal(int, int, int)  # 新增：总任务数，已完成，失败数
    task_completed = pyqtSignal(bool)
    
    def __init__(self, root_directory):
        super().__init__()
        self.root_directory = root_directory
        self.manager = None
        
    def run(self):
        """线程主函数"""
        try:
            self.progress_update.emit("🚀 正在启动 Dreamina 管理器...")
            
            # 创建管理器（GUI模式，传递进度回调）
            self.manager = SimpleDreaminaManager(
                gui_mode=True, 
                progress_callback=self.update_progress_stats
            )
            
            self.progress_update.emit("📋 正在加载任务...")
            
            # 开始处理
            success = self.manager.start_processing(self.root_directory)
            
            if success:
                self.progress_update.emit("✅ 所有任务处理完成！")
            else:
                self.progress_update.emit("❌ 任务处理失败")
                
            self.task_completed.emit(success)
            
        except Exception as e:
            self.progress_update.emit(f"❌ 处理过程中发生错误: {e}")
            self.task_completed.emit(False)
    
    def update_progress_stats(self, total_tasks, completed_tasks, failed_tasks):
        """更新进度统计"""
        self.progress_stats.emit(total_tasks, completed_tasks, failed_tasks)

class DreaminaGUI(QMainWindow):
    """Dreamina主界面"""
    
    # 添加日志信号
    log_signal = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.config_file = "gui_config.json"  # 使用独立的GUI配置文件
        self.config = self.load_config()
        self.worker_thread = None
        self.original_stdout = None
        
        self.init_ui()
        self.load_config_to_ui()
        
        # 启动时检查配置并提示
        self.check_initial_config()
        
        # 界面完全初始化后再设置日志重定向
        self.setup_log_redirection()
    
    def setup_log_redirection(self):
        """设置日志重定向"""
        try:
            # 连接日志信号到槽
            self.log_signal.connect(self._append_log_text)
            
            # 确保log_text组件已经初始化
            if hasattr(self, 'log_text') and self.log_text is not None:
                self.original_stdout = sys.stdout
                self.log_handler = GuiLogHandler(self._thread_safe_log)
                sys.stdout = self.log_handler
                print("✅ 日志重定向设置成功")
            else:
                print("⚠️ 日志组件未就绪，跳过日志重定向")
        except Exception as e:
            print(f"❌ 设置日志重定向失败: {e}")
    
    def _thread_safe_log(self, message):
        """线程安全的日志方法，通过信号发送"""
        self.log_signal.emit(message)
    
    def _append_log_text(self, message):
        """在主线程中添加日志文本"""
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_message = f"[{timestamp}] {message}"
            
            if hasattr(self, 'log_text') and self.log_text is not None:
                self.log_text.append(formatted_message)
                
                # 滚动到底部
                scrollbar = self.log_text.verticalScrollBar()
                if scrollbar:
                    scrollbar.setValue(scrollbar.maximum())
        except Exception as e:
            print(f"日志显示失败: {e}", file=sys.__stderr__)
    
    def restore_stdout(self):
        """恢复标准输出"""
        try:
            if self.original_stdout:
                sys.stdout = self.original_stdout
                print("✅ 标准输出已恢复")
        except Exception as e:
            print(f"⚠️ 恢复标准输出时出错: {e}")
    
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("🎨 Dreamina 自动化图片生成工具 v3.0")
        self.setGeometry(100, 100, 1000, 700)
        
        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # 左侧配置面板
        config_widget = self.create_config_panel()
        splitter.addWidget(config_widget)
        
        # 右侧控制面板
        control_widget = self.create_control_panel()
        splitter.addWidget(control_widget)
        
        # 设置分割器比例
        splitter.setSizes([400, 600])
        
        # 状态栏
        self.statusBar().showMessage("就绪")
        
    def create_config_panel(self):
        """创建配置面板"""
        config_frame = QFrame()
        config_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        config_layout = QVBoxLayout(config_frame)
        
        # 配置标题
        config_title = QLabel("⚙️ 配置设置")
        config_layout.addWidget(config_title)
        
        # 浏览器设置
        browser_group = QGroupBox("🌐 浏览器设置")
        browser_layout = QVBoxLayout(browser_group)
        
        self.browser_list = QListWidget()
        self.browser_list.setMaximumHeight(120)
        browser_layout.addWidget(self.browser_list)
        
        browser_buttons_layout = QHBoxLayout()
        self.add_browser_btn = QPushButton("➕ 添加浏览器ID")
        self.remove_browser_btn = QPushButton("➖ 删除选中")
        self.add_browser_btn.clicked.connect(self.add_browser_id)
        self.remove_browser_btn.clicked.connect(self.remove_browser_id)
        browser_buttons_layout.addWidget(self.add_browser_btn)
        browser_buttons_layout.addWidget(self.remove_browser_btn)
        browser_layout.addLayout(browser_buttons_layout)
        
        config_layout.addWidget(browser_group)
        
        # 文件路径设置
        path_group = QGroupBox("📁 路径设置")
        path_layout = QGridLayout(path_group)
        
        path_layout.addWidget(QLabel("根目录:"), 0, 0)
        self.root_dir_edit = QLineEdit()
        path_layout.addWidget(self.root_dir_edit, 0, 1)
        self.browse_dir_btn = QPushButton("📂 浏览")
        self.browse_dir_btn.clicked.connect(self.browse_root_directory)
        path_layout.addWidget(self.browse_dir_btn, 0, 2)
        
        config_layout.addWidget(path_group)
        
        # Excel设置
        excel_group = QGroupBox("📊 Excel设置")
        excel_layout = QGridLayout(excel_group)
        
        excel_layout.addWidget(QLabel("提示词列:"), 0, 0)
        self.prompt_column_spin = QSpinBox()
        self.prompt_column_spin.setMinimum(1)
        self.prompt_column_spin.setMaximum(100)
        excel_layout.addWidget(self.prompt_column_spin, 0, 1)
        
        excel_layout.addWidget(QLabel("状态列:"), 1, 0)
        self.status_column_spin = QSpinBox()
        self.status_column_spin.setMinimum(1)
        self.status_column_spin.setMaximum(100)
        excel_layout.addWidget(self.status_column_spin, 1, 1)
        
        excel_layout.addWidget(QLabel("开始行:"), 2, 0)
        self.start_row_spin = QSpinBox()
        self.start_row_spin.setMinimum(1)
        self.start_row_spin.setMaximum(1000)
        excel_layout.addWidget(self.start_row_spin, 2, 1)
        
        excel_layout.addWidget(QLabel("状态文本:"), 3, 0)
        self.status_text_edit = QLineEdit()
        excel_layout.addWidget(self.status_text_edit, 3, 1, 1, 2)
        
        config_layout.addWidget(excel_group)
        
        # 图片设置
        image_group = QGroupBox("🖼️ 图片设置")
        image_layout = QGridLayout(image_group)
        
        image_layout.addWidget(QLabel("默认模型:"), 0, 0)
        from PyQt6.QtWidgets import QComboBox
        self.model_combo = QComboBox()
        self.model_combo.addItems(["Image 3.0", "Image 2.1", "Image 2.0 Pro"])
        image_layout.addWidget(self.model_combo, 0, 1)
        
        image_layout.addWidget(QLabel("默认尺寸:"), 1, 0)
        self.aspect_ratio_combo = QComboBox()
        self.aspect_ratio_combo.addItems(["9:16", "16:9", "1:1", "3:4", "4:3"])
        image_layout.addWidget(self.aspect_ratio_combo, 1, 1)
        
        config_layout.addWidget(image_group)
        
        # 积分监控设置
        points_group = QGroupBox("💰 积分监控")
        points_layout = QGridLayout(points_group)
        
        self.points_enabled_cb = QCheckBox("启用积分监控")
        points_layout.addWidget(self.points_enabled_cb, 0, 0, 1, 2)
        
        points_layout.addWidget(QLabel("最小积分阈值:"), 1, 0)
        self.min_points_spin = QSpinBox()
        self.min_points_spin.setMinimum(1)
        self.min_points_spin.setMaximum(100)
        points_layout.addWidget(self.min_points_spin, 1, 1)
        
        config_layout.addWidget(points_group)
        
        # 保存配置按钮
        self.save_config_btn = QPushButton("💾 保存配置")
        self.save_config_btn.clicked.connect(self.save_config_from_ui)
        config_layout.addWidget(self.save_config_btn)
        
        return config_frame
        
    def create_control_panel(self):
        """创建控制面板"""
        control_frame = QFrame()
        control_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        control_layout = QVBoxLayout(control_frame)
        
        # 控制标题
        control_title = QLabel("🎮 操作控制")
        control_layout.addWidget(control_title)
        
        # 状态显示
        status_group = QGroupBox("📊 状态信息")
        status_layout = QVBoxLayout(status_group)
        
        # 配置状态
        config_status_layout = QGridLayout()
        config_status_layout.addWidget(QLabel("浏览器数量:"), 0, 0)
        self.browser_count_label = QLabel("0")
        config_status_layout.addWidget(self.browser_count_label, 0, 1)
        
        config_status_layout.addWidget(QLabel("根目录状态:"), 1, 0)
        self.root_dir_status_label = QLabel("未设置")
        config_status_layout.addWidget(self.root_dir_status_label, 1, 1)
        
        config_status_layout.addWidget(QLabel("积分监控:"), 2, 0)
        self.points_status_label = QLabel("关闭")
        config_status_layout.addWidget(self.points_status_label, 2, 1)
        
        status_layout.addLayout(config_status_layout)
        control_layout.addWidget(status_group)
        
        # 操作按钮
        actions_group = QGroupBox("🚀 操作")
        actions_layout = QVBoxLayout(actions_group)
        
        # 验证配置按钮
        self.validate_btn = QPushButton("🔍 验证配置")
        self.validate_btn.clicked.connect(self.validate_configuration)
        actions_layout.addWidget(self.validate_btn)
        
        # 开始生成按钮
        self.start_btn = QPushButton("🎨 开始图片生成")
        self.start_btn.clicked.connect(self.start_generation)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 10px;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        actions_layout.addWidget(self.start_btn)
        
        # 停止按钮
        self.stop_btn = QPushButton("⏹️ 停止处理")
        self.stop_btn.clicked.connect(self.stop_generation)
        self.stop_btn.setEnabled(False)
        actions_layout.addWidget(self.stop_btn)
        
        control_layout.addWidget(actions_group)
        
        # 进度显示
        progress_group = QGroupBox("📈 处理进度")
        progress_layout = QVBoxLayout(progress_group)
        
        # 任务进度标签
        self.task_progress_label = QLabel("等待任务开始...")
        self.task_progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_layout.addWidget(self.task_progress_label)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)
        
        control_layout.addWidget(progress_group)
        
        # 日志显示
        log_group = QGroupBox("📋 处理日志")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(250)
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        # 清除日志按钮
        self.clear_log_btn = QPushButton("🗑️ 清除日志")
        self.clear_log_btn.clicked.connect(self.clear_log)
        log_layout.addWidget(self.clear_log_btn)
        
        control_layout.addWidget(log_group)
        
        return control_frame
    
    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                return self.get_default_config()
        except Exception as e:
            self.show_error(f"加载配置失败: {e}")
            return self.get_default_config()
    
    def get_default_config(self):
        """获取默认配置"""
        return {
            "browser_settings": {
                "browser_ids": []
            },
            "file_paths": {
                "root_directory": "Projects"
            },
            "excel_settings": {
                "prompt_column": 2,
                "status_column": 4,
                "status_text": "已生成图片",
                "start_row": 2
            },
            "image_settings": {
                "default_model": "Image 3.0",
                "default_aspect_ratio": "9:16"
            },
            "points_monitoring": {
                "enabled": True,
                "min_points_threshold": 1
            }
        }
    
    def load_config_to_ui(self):
        """将配置加载到界面"""
        # 浏览器设置
        browser_ids = self.config.get("browser_settings", {}).get("browser_ids", [])
        self.browser_list.clear()
        for browser_id in browser_ids:
            self.browser_list.addItem(browser_id)
        
        # 路径设置
        root_dir = self.config.get("file_paths", {}).get("root_directory", "Projects")
        self.root_dir_edit.setText(root_dir)
        
        # Excel设置
        excel_settings = self.config.get("excel_settings", {})
        self.prompt_column_spin.setValue(excel_settings.get("prompt_column", 2))
        self.status_column_spin.setValue(excel_settings.get("status_column", 4))
        self.start_row_spin.setValue(excel_settings.get("start_row", 2))
        self.status_text_edit.setText(excel_settings.get("status_text", "已生成图片"))
        
        # 图片设置
        image_settings = self.config.get("image_settings", {})
        model = image_settings.get("default_model", "Image 3.0")
        aspect_ratio = image_settings.get("default_aspect_ratio", "9:16")
        
        # 设置模型下拉框
        model_index = self.model_combo.findText(model)
        if model_index >= 0:
            self.model_combo.setCurrentIndex(model_index)
        
        # 设置尺寸下拉框
        aspect_index = self.aspect_ratio_combo.findText(aspect_ratio)
        if aspect_index >= 0:
            self.aspect_ratio_combo.setCurrentIndex(aspect_index)
        
        # 积分监控设置
        points_settings = self.config.get("points_monitoring", {})
        self.points_enabled_cb.setChecked(points_settings.get("enabled", True))
        self.min_points_spin.setValue(points_settings.get("min_points_threshold", 1))
        
        # 更新状态显示
        self.update_status_display()
    
    def save_config_from_ui(self):
        """从界面保存配置"""
        try:
            # 收集浏览器ID
            browser_ids = []
            for i in range(self.browser_list.count()):
                browser_ids.append(self.browser_list.item(i).text())
            
            # 构建配置
            self.config = {
                "browser_settings": {
                    "browser_ids": browser_ids
                },
                "file_paths": {
                    "root_directory": self.root_dir_edit.text().strip()
                },
                "excel_settings": {
                    "prompt_column": self.prompt_column_spin.value(),
                    "status_column": self.status_column_spin.value(),
                    "status_text": self.status_text_edit.text().strip(),
                    "start_row": self.start_row_spin.value()
                },
                "image_settings": {
                    "default_model": self.model_combo.currentText(),
                    "default_aspect_ratio": self.aspect_ratio_combo.currentText()
                },
                "points_monitoring": {
                    "enabled": self.points_enabled_cb.isChecked(),
                    "min_points_threshold": self.min_points_spin.value()
                }
            }
            
            # 保存到GUI配置文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            
            self.update_status_display()
            self.log_message("✅ 配置保存成功")
            
        except Exception as e:
            self.show_error(f"保存配置失败: {e}")

    def check_initial_config(self):
        """检查初始配置状态"""
        QTimer.singleShot(500, self._check_config_status)  # 延迟500ms执行
    
    def _check_config_status(self):
        """检查配置状态并提示用户"""
        browser_count = self.browser_list.count()
        root_dir = self.root_dir_edit.text().strip()
        
        if browser_count == 0:
            self.log_message("⚠️ 请先添加浏览器ID")
            
        if not root_dir or not os.path.exists(root_dir):
            self.log_message("⚠️ 请设置有效的项目根目录")
        
        if browser_count == 0 or not root_dir or not os.path.exists(root_dir):
            self.log_message("💡 请完成基本配置后开始使用")
        else:
            self.log_message("🎉 配置看起来不错，可以开始使用了！")
    
    def add_browser_id(self):
        """添加浏览器ID"""
        browser_id, ok = QInputDialog.getText(
            self, '添加浏览器ID', '请输入浏览器ID:')
        
        if ok and browser_id.strip():
            self.browser_list.addItem(browser_id.strip())
            self.log_message(f"➕ 添加浏览器ID: {browser_id.strip()}")
    
    def remove_browser_id(self):
        """删除选中的浏览器ID"""
        current_row = self.browser_list.currentRow()
        if current_row >= 0:
            item = self.browser_list.takeItem(current_row)
            self.log_message(f"➖ 删除浏览器ID: {item.text()}")
        else:
            self.show_warning("请先选择要删除的浏览器ID")
    
    def browse_root_directory(self):
        """浏览根目录"""
        directory = QFileDialog.getExistingDirectory(
            self, "选择项目根目录", self.root_dir_edit.text())
        
        if directory:
            self.root_dir_edit.setText(directory)
            self.log_message(f"📂 设置根目录: {directory}")
    
    def validate_configuration(self):
        """验证配置"""
        self.log_message("🔍 正在验证配置...")
        
        errors = []
        warnings = []
        
        # 检查浏览器ID
        if self.browser_list.count() == 0:
            errors.append("至少需要配置一个浏览器ID")
        
        # 检查根目录
        root_dir = self.root_dir_edit.text().strip()
        if not root_dir:
            errors.append("必须设置项目根目录")
        elif not os.path.exists(root_dir):
            errors.append(f"根目录不存在: {root_dir}")
        elif not os.path.isdir(root_dir):
            errors.append(f"根目录不是文件夹: {root_dir}")
        else:
            # 检查子文件夹中的Excel文件
            excel_count = 0
            for item in Path(root_dir).iterdir():
                if item.is_dir():
                    excel_files = list(item.glob("*.xlsx")) + list(item.glob("*.xls"))
                    excel_count += len(excel_files)
            
            if excel_count == 0:
                warnings.append("根目录的子文件夹中没有找到Excel文件")
        
        # 显示验证结果
        if errors:
            self.log_message("❌ 配置验证失败:")
            for error in errors:
                self.log_message(f"  • {error}")
            self.show_error("配置验证失败，请修正错误后重试")
        else:
            self.log_message("✅ 配置验证通过")
            if warnings:
                self.log_message("⚠️ 警告:")
                for warning in warnings:
                    self.log_message(f"  • {warning}")
                self.show_warning("配置验证通过，但存在警告")
            else:
                self.show_info("配置验证通过，可以开始处理")
        
        self.update_status_display()
        return len(errors) == 0
    
    def start_generation(self):
        """开始图片生成"""
        # 先验证配置
        if not self.validate_configuration():
            return
        
        # 保存当前配置
        self.save_config_from_ui()
        
        # 获取根目录
        root_directory = self.root_dir_edit.text().strip()
        
        # 直接启动工作线程，无需确认对话框
        self.worker_thread = DreaminaWorkerThread(root_directory)
        self.worker_thread.progress_update.connect(self.log_message)
        self.worker_thread.progress_stats.connect(self.update_progress_stats)
        self.worker_thread.task_completed.connect(self.on_task_completed)
        
        # 更新界面状态
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)  # 百分比进度条
        self.progress_bar.setValue(0)
        
        # 显示开始信息
        self.log_message(f"🚀 开始图片生成处理...")
        self.log_message(f"📁 根目录: {root_directory}")
        self.log_message(f"🌐 浏览器数量: {self.browser_list.count()}")
        
        self.worker_thread.start()
    
    def stop_generation(self):
        """停止图片生成"""
        if self.worker_thread and self.worker_thread.isRunning():
            self.log_message("⏹️ 正在停止处理...")
            
            # 停止管理器
            if hasattr(self.worker_thread, 'manager') and self.worker_thread.manager:
                self.worker_thread.manager.stop()
            
            # 等待线程结束
            self.worker_thread.quit()
            self.worker_thread.wait(3000)  # 等待3秒
            
            self.on_task_completed(False)
            self.log_message("⏹️ 处理已停止")
    
    def update_progress_stats(self, total_tasks, completed_tasks, failed_tasks):
        """更新进度统计"""
        processed_tasks = completed_tasks + failed_tasks
        pending_tasks = total_tasks - processed_tasks
        
        # 更新进度条
        if total_tasks > 0:
            progress_percentage = int(processed_tasks / total_tasks * 100)
            self.progress_bar.setValue(progress_percentage)
            self.progress_bar.setFormat(f"{processed_tasks}/{total_tasks}")
        
        # 更新进度标签
        if total_tasks > 0:
            self.task_progress_label.setText(
                f"📊 任务进度: {processed_tasks}/{total_tasks} | 待处理: {pending_tasks}"
            )
        else:
            self.task_progress_label.setText("等待任务开始...")
    
    def on_task_completed(self, success):
        """任务完成回调"""
        # 更新界面状态
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        
        # 重置进度显示
        self.task_progress_label.setText("任务已完成")
        
        if success:
            self.show_info("图片生成任务完成！")
        else:
            self.show_warning("图片生成任务未完全成功")
        
        self.statusBar().showMessage("就绪")
    
    def update_status_display(self):
        """更新状态显示"""
        # 浏览器数量
        self.browser_count_label.setText(str(self.browser_list.count()))
        
        # 根目录状态
        root_dir = self.root_dir_edit.text().strip()
        if not root_dir:
            self.root_dir_status_label.setText("未设置")
        elif os.path.exists(root_dir) and os.path.isdir(root_dir):
            self.root_dir_status_label.setText("✅ 有效")
        else:
            self.root_dir_status_label.setText("❌ 无效")
        
        # 积分监控状态
        if self.points_enabled_cb.isChecked():
            self.points_status_label.setText("✅ 启用")
        else:
            self.points_status_label.setText("❌ 关闭")
    
    def log_message(self, message):
        """添加日志消息（线程安全）"""
        # 直接使用信号发送消息
        self.log_signal.emit(message)
    
    def _scroll_to_bottom(self):
        """滚动日志到底部（已合并到_append_log_text中，此方法可以删除）"""
        pass
    
    def clear_log(self):
        """清除日志"""
        self.log_text.clear()
        self.log_message("📋 日志已清除")
    
    def show_info(self, message):
        """显示信息消息"""
        QMessageBox.information(self, "信息", message)
    
    def show_warning(self, message):
        """显示警告消息"""
        QMessageBox.warning(self, "警告", message)
    
    def show_error(self, message):
        """显示错误消息"""
        QMessageBox.critical(self, "错误", message)
    
    def closeEvent(self, event):
        """关闭事件"""
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(
                self, '确认退出', 
                '当前有任务正在运行，确定要退出吗？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.stop_generation()
                self.restore_stdout()
                event.accept()
            else:
                event.ignore()
        else:
            self.restore_stdout()
            event.accept()

def run_gui():
    """运行GUI应用"""
    import os
    
    # 嵌入式资源处理
    try:
        from resource_helper import ensure_config_files
        # 确保配置文件可用
        ensure_config_files()
    except ImportError:
        # 开发环境，忽略
        pass
    
    # 抑制Qt相关的调试信息
    os.environ['QT_LOGGING_RULES'] = 'qt.qpa.fonts.debug=false'
    
    app = QApplication(sys.argv)
    app.setApplicationName("Dreamina图片生成工具")
    
    # 设置应用样式
    app.setStyleSheet("""
        QMainWindow {
            background-color: #f5f5f5;
        }
        QGroupBox {
            border: 2px solid #cccccc;
            border-radius: 5px;
            margin-top: 1ex;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
        }
        QPushButton {
            padding: 8px;
            border: 1px solid #ccc;
            border-radius: 4px;
            background-color: #ffffff;
        }
        QPushButton:hover {
            background-color: #e8e8e8;
        }
        QLineEdit, QSpinBox {
            padding: 5px;
            border: 1px solid #ccc;
            border-radius: 3px;
        }
        QTextEdit {
            border: 1px solid #ccc;
            border-radius: 3px;
        }
    """)
    
    window = DreaminaGUI()
    window.show()
    
    return app.exec()

if __name__ == "__main__":
    run_gui() 