import requests
import json
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# 官方文档地址
# https://doc2.bitbrowser.cn/jiekou/ben-di-fu-wu-zhi-nan.html

# 此demo仅作为参考使用，以下使用的指纹参数仅是部分参数，完整参数请参考文档

url = "http://127.0.0.1:54345"
headers = {'Content-Type': 'application/json'}


def createBrowser():  # 创建或者更新窗口，指纹参数 browserFingerPrint 如没有特定需求，只需要指定下内核即可，如果需要更详细的参数，请参考文档
    json_data = {
        'name': 'google',  # 窗口名称
        'remark': '',  # 备注
        'proxyMethod': 2,  # 代理方式 2自定义 3 提取IP
        # 代理类型  ['noproxy', 'http', 'https', 'socks5', 'ssh']
        'proxyType': 'noproxy',
        'host': '',  # 代理主机
        'port': '',  # 代理端口
        'proxyUserName': '',  # 代理账号
        "browserFingerPrint": {  # 指纹对象
            'coreVersion': '124'  # 内核版本，注意，win7/win8/winserver 2012 已经不支持112及以上内核了，无法打开
        }
    }

    res = requests.post(f"{url}/browser/update",
                        data=json.dumps(json_data), headers=headers).json()
    browserId = res['data']['id']
    print(browserId)
    return browserId


def updateBrowser():  # 更新窗口，支持批量更新和按需更新，ids 传入数组，单独更新只传一个id即可，只传入需要修改的字段即可，比如修改备注，具体字段请参考文档，browserFingerPrint指纹对象不修改，则无需传入
    json_data = {'ids': ['93672cf112a044f08b653cab691216f0'],
                 'remark': '我是一个备注', 'browserFingerPrint': {}}
    res = requests.post(f"{url}/browser/update/partial",
                        data=json.dumps(json_data), headers=headers).json()
    print(res)


def openBrowser(id):  # 直接指定ID打开窗口，也可以使用 createBrowser 方法返回的ID
    json_data = {
        "id": f'{id}',
        "args": ["--enable-automation"]  # 尝试添加启动参数以确保自动化接口可用
    }
    print(f"发送到 /browser/open 的请求数据: {json.dumps(json_data)}") # 记录请求数据
    res = requests.post(f"{url}/browser/open",
                        data=json.dumps(json_data), headers=headers).json()
    return res


def closeBrowser(id):  # 关闭窗口
    json_data = {'id': f'{id}'}
    requests.post(f"{url}/browser/close",
                  data=json.dumps(json_data), headers=headers).json()


def deleteBrowser(id):  # 删除窗口
    json_data = {'id': f'{id}'}
    print(requests.post(f"{url}/browser/delete",
          data=json.dumps(json_data), headers=headers).json())

def launch_and_get_debug_address():
    config_file_path = 'user_config.json'
    browser_id_from_config = None
    cdp_http_endpoint = None

    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # 从新的配置结构中获取第一个浏览器ID
            browser_ids = config.get('browser_settings', {}).get('browser_ids', [])
            if browser_ids:
                browser_id_from_config = browser_ids[0]
            else:
                browser_id_from_config = None

        if not browser_id_from_config:
            print(f"错误：请在 {config_file_path} 文件的 browser_settings.browser_ids 中提供一个有效的浏览器ID。")
            return None

    except FileNotFoundError:
        print(f"错误：配置文件 {config_file_path} 未找到。")
        return None
    except json.JSONDecodeError:
        print(f"错误：配置文件 {config_file_path} 格式无效，请确保它是有效的JSON。")
        return None
    except Exception as e:
        print(f"读取配置文件时发生错误: {e}")
        return None
    
    print(f"从配置文件读取到的浏览器ID: {browser_id_from_config}")

    open_response = openBrowser(browser_id_from_config)
    print(f"打开浏览器 {browser_id_from_config} 的响应: {open_response}")

    if open_response and open_response.get('success'):
        data = open_response.get('data', {})
        raw_http_address = None # 用于存储原始的 http 地址 (ip:port)
        raw_ws_address = data.get('ws') # 直接获取原始的 ws 地址

        # 优先尝试从 'http' 字段获取调试地址
        if 'http' in data and isinstance(data['http'], str):
            raw_http_address = data['http']
            print(f"成功从 'http' 字段获取原始调试地址: {raw_http_address}")
        
        # 如果 'http' 字段没有，再尝试 'webDriver' (可能也是 ip:port)
        if not raw_http_address and 'webDriver' in data and isinstance(data['webDriver'], str):
            raw_http_address = data['webDriver']
            print(f"成功从 'webDriver' 字段获取原始调试地址: {raw_http_address}")

        # 如果上述都没有，并且 'ws' 存在且是字符串，则尝试从 'ws' 字符串解析出 ip:port 作为备用的 raw_http_address
        if not raw_http_address and raw_ws_address and isinstance(raw_ws_address, str):
            print("未能从 'http' 或 'webDriver' 字段获取原始调试地址，尝试从 'ws' 字符串解析...")
            try:
                ws_url_parts = raw_ws_address.split('/')
                if len(ws_url_parts) > 2 and ":" in ws_url_parts[2]:
                    raw_http_address = ws_url_parts[2] 
                    print(f"成功从 'ws' 字符串解析出备用原始调试地址: {raw_http_address}")
                else:
                    print(f"解析 'ws' 字符串 ({raw_ws_address}) 失败，格式不符合预期。")
            except Exception as e:
                print(f"从 'ws' 字符串解析备用原始调试地址时发生错误: {e}")
        
        # 确保返回三个值，即使某些值可能是 None
        # main_controller 会根据这些原始值来构造 Playwright 需要的 cdp_http_endpoint
        if raw_http_address or raw_ws_address: # 只要有一个地址存在，就认为可以继续
            print(f"将返回 browser_id: {browser_id_from_config}, http_address: {raw_http_address}, ws_address: {raw_ws_address}")
            return browser_id_from_config, raw_http_address, raw_ws_address
        else:
            print("错误: 最终未能从打开浏览器的响应中获取到任何有效的原始调试连接信息 (http, webDriver, 或 ws)。")
            print(f"从 /browser/open 接口收到的 'data' 对象: {data}")
            print(f"完整的 'open_response' 对象是: {open_response}")
            return browser_id_from_config, None, None # 至少返回ID和None，让main_controller判断
    else:
        print(f"未能成功打开浏览器 {browser_id_from_config}。响应: {open_response}")
        return browser_id_from_config, None, None # 至少返回ID和None

