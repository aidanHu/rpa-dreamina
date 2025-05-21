# Dreamina 图像生成自动化脚本

本项目是一个 Python 自动化脚本，旨在使用 Bit Browser 和 Playwright 控制 Dreamina 网页 (`https://dreamina.capcut.com/ai-tool/image/generate`) 进行批量图片生成。脚本能够从 Excel 文件中读取提示词，自动输入到网页，等待图片生成完毕，并将生成的图片保存到本地。

## 功能特性

*   通过 Bit Browser API 控制指定的浏览器窗口。
*   使用 Playwright 自动化网页操作。
*   从指定文件夹内的多个 Excel 文件中读取图片生成提示词。
*   为每个提示词自动在 Dreamina 页面上执行图片生成操作。
*   智能等待图片生成完成，并保存与当前提示词对应的最新图片。
*   支持多浏览器窗口并行处理不同的 Excel 文件（或提示词）。
*   保存的图片文件名包含原始提示词、来源 Excel 文件名、行号和时间戳，方便追溯。

## 环境要求

*   Python 3.7+
*   Bit Browser 客户端已安装并正在运行。
*   Bit Browser API 服务已开启（通常在 Bit Browser 设置中可以找到）。
*   操作系统：Windows, macOS, 或 Linux。

## 安装与配置

1.  **获取项目文件**:
    *   如果您是通过版本控制系统（如 Git）获取的，请克隆仓库。
    *   如果直接获得文件，请确保所有脚本文件 (`main_controller.py`, `bit_api.py`, `dreamina_operator.py`, `excel_reader.py`) 和配置文件 (`browser_config.json`, `requirements.txt`) 都在同一个项目根目录下。

2.  **创建并激活虚拟环境** (推荐):
    ```bash
    python -m venv venv
    # Windows
    .\venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate
    ```

3.  **安装依赖**:
    在项目根目录下，运行以下命令安装所需的 Python 包：
    ```bash
    pip install -r requirements.txt
    ```
    这将安装 `playwright`, `requests`, 和 `openpyxl` 等必要的库。
    Playwright 在首次安装时可能会下载浏览器驱动，请耐心等待。如果下载速度慢或失败，可能需要配置网络代理或手动安装 (参考 Playwright 官方文档: `playwright install`)。

4.  **配置 Bit Browser 窗口 (`browser_config.json`)**:
    *   在项目根目录下，创建或修改 `browser_config.json` 文件。
    *   此文件用于指定脚本将要控制的 Bit Browser 窗口。
    *   格式为一个 JSON 数组，每个对象代表一个浏览器配置：
        ```json
        [
          {
            "id": "需要控制的第一个Bit Browser窗口ID",
            "name": "浏览器A" // 可选，用于日志输出，便于区分
          },
          {
            "id": "需要控制的第二个Bit Browser窗口ID",
            "name": "浏览器B"
          }
          // 可以添加更多浏览器配置
        ]
        ```
    *   `id`: **必需**，Bit Browser 中浏览器窗口的唯一ID。
    *   `name`: 可选，为浏览器指定一个易于识别的名称，会显示在日志中。
    *   确保填写的浏览器窗口 ID 在您的 Bit Browser 中是真实存在的。脚本运行时，这些浏览器窗口应该是关闭状态，脚本会自动尝试打开它们。

5.  **准备提示词 Excel 文件**:
    *   在项目根目录下创建一个名为 `excel_prompts` 的文件夹。
    *   将包含提示词的 Excel 文件（`.xlsx` 或 `.xls` 格式）放入此文件夹中。
    *   脚本会读取该文件夹下所有 Excel 文件的**第一个工作表 (Sheet)** 的**第一列 (Column A)** 作为提示词来源。
    *   每个单元格包含一个提示词。表头（如果有）也会被视为提示词，除非您在 `excel_reader.py` 中修改逻辑来跳过。
    *   确保 Excel 文件没有密码保护。

6.  **创建图片保存目录**:
    *   脚本会自动在项目根目录下创建一个名为 `generated_images` 的文件夹，用于存放生成的图片。如果此文件夹已存在，则直接使用。

## 如何运行

1.  **确保 Bit Browser 客户端正在运行**，并且其 API 服务已开启。
2.  **确保 `browser_config.json` 中配置的浏览器窗口在 Bit Browser 中是关闭状态**。脚本会尝试通过 API 打开它们。
3.  打开终端或命令提示符，导航到项目根目录。
4.  如果使用了虚拟环境，请确保已激活。
5.  运行主控制脚本：
    ```bash
    python main_controller.py
    ```
6.  脚本将开始执行：
    *   加载浏览器配置。
    *   扫描 `excel_prompts` 文件夹中的 Excel 文件。
    *   为每个配置的浏览器分配 Excel 文件任务。
    *   并行启动并控制每个浏览器窗口：
        *   打开 Dreamina 网页。
        *   依次处理分配到的 Excel 文件中的每个提示词。
        *   生成图片并保存到 `generated_images` 文件夹。
    *   日志信息会输出到控制台，显示当前操作进度、成功与失败信息。

## 输出说明

*   生成的图片将保存在项目根目录下的 `generated_images` 文件夹中。
*   每张图片（通常 Dreamina 一次会生成多张，脚本会尝试保存所有检测到的新图片）的文件名格式如下：
    `[提示词前30字符]_[来源Excel文件名]_[行号]_[时间戳YYYYMMDDHHMMSS]_[图片序号].png`
    例如：`A_beautiful_cat_sitting_on_a_sofa_prompts_v1_3_20231027153000_1.png`
    *   提示词部分会被截断并替换特殊字符，以确保文件名有效。
    *   图片序号用于区分同一提示词生成的不同图片。

## 项目文件结构

*   `main_controller.py`: 主执行脚本，负责整体流程控制、任务分配和多浏览器并行处理。
*   `bit_api.py`: 封装与 Bit Browser 本地 API 交互的函数，如打开和关闭浏览器窗口。
*   `dreamina_operator.py`: 使用 Playwright 控制 Dreamina 网页操作的模块，包括导航、输入提示词、点击生成按钮、等待图片加载和保存图片。
*   `excel_reader.py`: 负责从 Excel 文件中读取提示词。
*   `requirements.txt`: 项目的 Python 依赖库列表。
*   `browser_config.json`: Bit Browser 窗口配置文件。
*   `README.md`: 本说明文件。
*   `excel_prompts/`: (需用户创建) 存放包含提示词的 Excel 文件的文件夹。
*   `generated_images/`: (脚本自动创建) 保存生成的图片的文件夹。
*   `venv/`: (推荐创建) Python 虚拟环境文件夹。

## 注意事项与故障排查

*   **Bit Browser API**: 确保 Bit Browser 的 API 地址和端口（通常默认为 `127.0.0.1:54345`）可以被脚本访问。如果 Bit Browser 修改了 API 端口，您可能需要相应地修改 `bit_api.py` 中的 `BASE_URL`。
*   **网络问题**: 图片生成和下载依赖网络连接。如果网络不稳定，可能会导致超时或失败。
*   **Dreamina 页面结构变化**: 如果 Dreamina 网站的页面结构（HTML元素、CSS选择器）发生较大变化，`dreamina_operator.py` 中的元素定位逻辑可能需要更新。
*   **图片加载判断**: 当前图片加载完成的判断逻辑依赖于观察新图片元素的出现及其 `src` 属性的更新。在某些情况下，如果页面行为有细微变化，可能需要调整等待条件和超时设置。
*   **权限问题**: 确保脚本对 `excel_prompts` 文件夹有读取权限，对项目根目录有创建 `generated_images` 文件夹和写入文件的权限。
*   **Playwright Timeout**: 如果遇到 Playwright 操作超时 (`PlaywrightTimeoutError`)，可以尝试在 `dreamina_operator.py` 或 `main_controller.py` 中涉及 Playwright 调用的地方适当增加超时时间（例如 `page.wait_for_selector` 或 `browser.connect_over_cdp` 的 `timeout` 参数）。 