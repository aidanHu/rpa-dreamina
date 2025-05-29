# 🎨 Dreamina 自动化工具

一个功能强大的 Dreamina 图片生成自动化工具，支持批量处理、多窗口并行、账号管理等功能。

## ✨ 主要功能

- 🖼️ **批量图片生成** - 从Excel文件读取提示词，自动生成图片
- 📏 **图片尺寸选择** - 支持多种尺寸比例（9:16, 1:1, 16:9等），可配置默认尺寸
- 🚀 **智能多窗口** - 根据配置的浏览器ID数量自动选择单窗口或多窗口模式
- 📝 **账号管理** - 自动注册和注销Dreamina账号
- 🔄 **智能断点续传** - 自动跳过已处理的提示词
- 📁 **项目独立管理** - 每个项目的文件独立存储
- ⚙️ **灵活配置** - 可自定义状态列、保存路径等

## 📁 文件结构

### 推荐的项目组织方式
```
Projects/
├── 项目A_风景/
│   ├── 项目A_风景_提示词.xlsx
│   ├── 1_美丽的山水风景_img1.jpg
│   └── 1_美丽的山水风景_img2.jpg
├── 项目B_动物/
│   ├── 项目B_动物_提示词.xlsx
│   ├── 1_可爱的小猫咪_img1.jpg
│   └── 2_奔跑的马匹_img1.jpg
└── 项目C_建筑/
    ├── 项目C_建筑_提示词.xlsx
    └── (生成的图片)
```

### Excel文件格式
- **第1行**: 标题行（会被跳过）
- **第1列**: 可选的其他信息
- **第2列**: 提示词文本（可配置）
- **第3列**: 状态标记（可配置）
- **从第2行开始**: 实际数据（可配置）

### 文件命名规则
**格式**: `{数据行号}_{清理后的提示词}_img{序号}.jpg`

**命名逻辑**:
- Excel第1行：标题行（跳过）
- Excel第2行：数据第1行 → 文件名以 `1_` 开头
- Excel第3行：数据第2行 → 文件名以 `2_` 开头
- 以此类推...

**示例**:
- `1_美丽的山水风景_img1.jpg` （来自Excel第2行的第1张图）
- `1_美丽的山水风景_img2.jpg` （来自Excel第2行的第2张图）
- `2_夕阳下的湖泊_img1.jpg` （来自Excel第3行的第1张图）

### 智能延时配置
程序使用智能延时来模拟人类操作节奏，避免被检测为机器行为：

- **延时范围**: 可在配置文件中设置最小值和最大值
- **随机性**: 每次延时时间在设置范围内随机生成
- **自适应**: 系统会根据不同操作场景自动应用合适的延时
- **可配置**: 用户可根据网络状况和偏好调整延时范围

**建议配置**:
- 网络较快: `min: 1, max: 3`
- 网络一般: `min: 2, max: 5`（默认）
- 网络较慢: `min: 3, max: 8`

## ⚙️ 配置文件

### 主配置文件

编辑 `user_config.json` 进行基本配置：

```json
{
  "browser_settings": {
    "browser_ids": [
      "your_browser_id_here"
    ]
  },
  "file_paths": {
    "root_directory": "/path/to/your/Projects"
  },
  "excel_settings": {
    "prompt_column": 2,
    "status_column": 3,
    "status_text": "已生成图片",
    "start_row": 2
  },
  "image_settings": {
    "default_aspect_ratio": "9:16"
  },
  "multi_window_settings": {
    "task_interval_seconds": 3,
    "startup_delay_seconds": 5,
    "error_retry_attempts": 2
  },
  "points_monitoring": {
    "enabled": true,
    "min_points_threshold": 4,
    "check_interval_seconds": 30
  },
  "smart_delays": {
    "min": 2,
    "max": 5,
    "description": "统一智能延时范围（秒）"
  }
}
```

### 多窗口专用配置文件

编辑 `multi_window_config.json` 进行多窗口优化配置：

```json
{
  "multi_window_settings": {
    "max_concurrent_windows": 3,
    "task_interval_seconds": 5,
    "startup_delay_seconds": 8,
    "error_retry_attempts": 3,
    "thread_timeout_seconds": 300,
    "window_restart_delay_seconds": 10
  },
  "thread_safety": {
    "enable_independent_playwright": true,
    "enable_thread_isolation": true,
    "max_thread_wait_time": 30
  },
  "error_handling": {
    "max_consecutive_errors": 5,
    "error_cooldown_seconds": 30,
    "auto_restart_on_error": true
  }
}
```

### 配置说明

| 配置项 | 说明 |
|--------|------|
| `root_directory` | 项目根目录路径 |
| `prompt_column` | Excel中提示词的列号（1基，默认第2列） |
| `status_column` | Excel中状态标记的列号（1基，默认第3列） |
| `status_text` | 状态标记文本 |
| `start_row` | 开始处理的行号（1基，默认第2行，跳过标题行） |
| `default_aspect_ratio` | 默认图片尺寸比例（如9:16, 1:1, 16:9等） |
| `browser_ids` | Bit Browser的浏览器ID列表（多个ID启用多窗口） |
| `min_points_threshold` | 最低积分阈值 |
| `smart_delays.min` | 智能延时最小值（秒） |
| `smart_delays.max` | 智能延时最大值（秒） |

#### 多窗口配置说明

| 配置项 | 说明 |
|--------|------|
| `max_concurrent_windows` | 最大并发窗口数 |
| `task_interval_seconds` | 任务间隔时间（秒） |
| `startup_delay_seconds` | 窗口启动延时（秒） |
| `max_consecutive_errors` | 最大连续错误次数 |
| `error_cooldown_seconds` | 错误冷却时间（秒） |
| `window_restart_delay_seconds` | 窗口重启延时（秒） |
| `enable_independent_playwright` | 启用独立Playwright实例 |
| `enable_thread_isolation` | 启用线程隔离 |

## 🚀 使用方法

### 1. 环境准备

```bash
# 安装依赖
pip install -r requirements.txt

# 确保Bit Browser已安装并配置
```

### 2. 配置设置

1. 修改 `user_config.json` 中的 `root_directory` 为您的项目根目录
2. 配置浏览器ID（从Bit Browser获取）
3. 根据需要调整其他设置

### 3. 准备项目文件

1. 在根目录下创建项目子文件夹
2. 在每个子文件夹中放置Excel文件
3. Excel第二列填写提示词（可在配置中修改列号）

### 4. 运行程序

```bash
python main.py
```

选择相应功能：
- `1` - 账号注册功能
- `2` - 账号注销功能  
- `3` - 批量图片生成（智能选择单窗口或多窗口）

### 5. 验证多窗口修复（可选）

如果之前遇到过多窗口线程错误，可以运行测试验证修复效果：

```bash
python test_multi_window_fix.py
```

测试将验证：
- ✅ 配置文件正确加载
- ✅ 窗口独立Playwright实例
- ✅ 线程安全性

## 🎯 功能特点

### 📊 智能处理
- **断点续传**: 自动检测已生成的图片，跳过已处理项目
- **状态追踪**: 在Excel中标记处理状态
- **错误重试**: 自动重试失败的任务
- **智能延时**: 可配置的随机延时模拟人类操作节奏
- **简单滚动**: 在页面右边进行向下滚动，简单有效

### 🚀 高效并行
- **多窗口支持**: 同时运行多个浏览器实例
- **智能分配**: 自动分配任务到空闲窗口
- **积分监控**: 实时监控账号积分余额

### 📁 项目管理
- **独立存储**: 每个项目的图片独立保存
- **便于分发**: 项目文件夹可直接打包分享
- **灵活组织**: 支持任意的项目文件夹结构

## 🔧 故障排除

### 常见问题

1. **找不到Excel文件**
   - 检查根目录路径是否正确
   - 确保子文件夹中包含Excel文件

2. **图片保存失败**
   - 检查文件夹写入权限
   - 确保磁盘空间充足

3. **浏览器连接失败**
   - 确认Bit Browser正在运行
   - 检查浏览器ID是否正确

4. **积分不足**
   - 检查账号积分余额
   - 程序会自动暂停积分不足的窗口

5. **多窗口线程错误** ✅ **已修复**
   - ~~问题：`greenlet.error: Cannot switch to a different thread`~~
   - ✅ **解决方案**：每个窗口使用独立的Playwright实例
   - 运行 `python test_multi_window_fix.py` 验证修复效果

6. **页面滚动问题**
   - 程序会在页面右边进行简单滚动
   - 等待生成内容出现后再滚动
   - 避免复杂的滚动逻辑导致定位错误

### 配置验证

程序启动时会自动验证：
- ✅ 根目录是否存在
- ✅ 子文件夹和Excel文件统计
- ✅ 配置文件格式检查

## 📋 依赖要求

- Python 3.8+
- Playwright
- Pandas
- Requests
- PIL/Pillow
- Bit Browser

## 🔄 更新日志

### v2.2 - 多窗口线程安全修复版本
- 🔧 **重大修复**: 解决多窗口模式下的Playwright线程切换错误
- ✨ 为每个窗口创建独立的Playwright实例，确保线程安全
- ✨ 新增专门的多窗口配置文件 `multi_window_config.json`
- ✨ 改进的错误处理机制：连续错误限制、错误冷却、智能重启
- ✨ 增强的资源管理：线程内初始化和清理
- ✨ 新增多窗口修复验证测试脚本
- 📊 详细的窗口状态监控和统计报告

### v2.1 - 滚动优化版本
- ✨ 新增简单有效的滚动功能
- ✨ 在页面右边进行向下滚动
- ✨ 等待内容出现后再滚动
- ✨ 智能延时系统统一配置
- 🔧 修复所有语法错误和缩进问题
- 🐛 避免复杂滚动逻辑导致的定位问题

### v2.0 - 项目独立管理
- ✨ 新增子文件夹结构支持
- ✨ 图片保存到Excel所在文件夹
- ✨ 可配置状态列和标记文本
- 🔧 移除不必要的输出文件夹配置
- 🐛 修复Playwright版本兼容性问题

### v1.0 - 基础功能
- ✨ 基础图片生成功能
- ✨ 账号注册和管理
- ✨ 多窗口并行处理
- ✨ 积分监控

## 📞 技术支持

如遇到问题，请检查：
1. 配置文件格式是否正确
2. 文件路径是否存在
3. 权限设置是否正确
4. 控制台错误信息

## 📄 许可证

本项目仅供学习和研究使用。 