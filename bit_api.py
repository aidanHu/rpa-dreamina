import requests
import json
import time
# from selenium import webdriver
# from selenium.webdriver.chrome.options import Options as ChromeOptions
# from selenium.webdriver.chrome.service import Service
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import asyncio # 虽然使用 sync_api，但有时某些环境或未来扩展可能需要

# 官方文档地址
# https://doc2.bitbrowser.cn/jiekou/ben-di-fu-wu-zhi-nan.html

# 此demo仅作为参考使用，以下使用的指纹参数仅是部分参数，完整参数请参考文档

url = "http://127.0.0.1:54345"
headers = {'Content-Type': 'application/json'}

# --- BitBrowser API Error --- #
class BitAPIError(Exception):
    """自定义Bit API相关操作的异常。"""
    pass

# --- Configuration Loading --- #
def load_browser_configs(config_file_path='browser_config.json'):
    """
    从指定的JSON配置文件中加载浏览器配置列表。
    期望的JSON结构: {"browsers": ["id1", "id2", ...]} 或 {"browsers": [{"id": "id1", "name": "name1"}, ...]}.
    内部会统一转换成 {"id": browser_id, "name": optional_name} 的格式供后续使用。
    返回: 浏览器配置字典的列表，如果文件不存在或格式错误则返回空列表。
    """
    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        raw_browser_list = config.get('browsers')
        processed_browser_list = []

        if isinstance(raw_browser_list, list):
            if not raw_browser_list: # 空列表
                print(f"[BitAPI] 配置文件 '{config_file_path}' 中的 'browsers' 列表为空。")
                return []

            # 检查列表的第一个元素来判断格式
            first_element = raw_browser_list[0]
            if isinstance(first_element, str): # 格式: ["id1", "id2", ...]
                if all(isinstance(item, str) and item.strip() for item in raw_browser_list):
                    for browser_id_str in raw_browser_list:
                        processed_browser_list.append({'id': browser_id_str.strip()})
                    print(f"[BitAPI] 从 '{config_file_path}' 加载了 {len(processed_browser_list)} 个浏览器ID (字符串列表格式)。")
                else:
                    print(f"[BitAPI] 错误：配置文件 '{config_file_path}' 的 'browsers' 列表应为非空字符串列表，但包含无效项。")
                    return []
            elif isinstance(first_element, dict): # 格式: [{"id": "id1", "name": "name1"}, ...]
                if all(isinstance(item, dict) and item.get('id') and isinstance(item.get('id'), str) and item.get('id').strip() for item in raw_browser_list):
                    # 可选地验证 name (如果存在)
                    for item_dict in raw_browser_list:
                        clean_item = {'id': item_dict['id'].strip()}
                        if 'name' in item_dict and isinstance(item_dict['name'], str) and item_dict['name'].strip():
                            clean_item['name'] = item_dict['name'].strip()
                        processed_browser_list.append(clean_item)
                    print(f"[BitAPI] 从 '{config_file_path}' 加载了 {len(processed_browser_list)} 个浏览器配置 (字典列表格式)。")
                else:
                    print(f"[BitAPI] 错误：配置文件 '{config_file_path}' 的 'browsers' 列表（字典格式）中，部分项目缺少有效的 'id' 字符串。")
                    return []
            else:
                print(f"[BitAPI] 错误：配置文件 '{config_file_path}' 的 'browsers' 列表包含未知类型的元素。应为字符串列表或字典列表。")
                return []
            
            return processed_browser_list
        else:
            print(f"[BitAPI] 错误：配置文件 '{config_file_path}' 缺少 'browsers' 字段，或者该字段不是一个列表。")
            return []
            
    except FileNotFoundError:
        print(f"[BitAPI] 错误：配置文件 '{config_file_path}' 未找到。")
        return []
    except json.JSONDecodeError:
        print(f"[BitAPI] 错误：配置文件 '{config_file_path}' 格式无效，请确保它是有效的JSON。")
        return []
    except Exception as e:
        print(f"[BitAPI] 读取配置文件 '{config_file_path}' 时发生未知错误: {e}")
        return []

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
    try:
        res = requests.post(f"{url}/browser/update", data=json.dumps(json_data), headers=headers, timeout=10).json()
        if res.get('success') and res.get('data') and res['data'].get('id'):
            browserId = res['data']['id']
            print(f"[BitAPI] 浏览器创建/更新成功，ID: {browserId}")
            return browserId
        else:
            raise BitAPIError(f"创建/更新浏览器失败: {res.get('msg', '未知错误')}")
    except requests.RequestException as e:
        raise BitAPIError(f"请求Bit API /browser/update 失败: {e}")
    except Exception as e:
        raise BitAPIError(f"处理创建/更新浏览器响应时出错: {e}")


def updateBrowser():  # 更新窗口，支持批量更新和按需更新，ids 传入数组，单独更新只传一个id即可，只传入需要修改的字段即可，比如修改备注，具体字段请参考文档，browserFingerPrint指纹对象不修改，则无需传入
    json_data = {'ids': ['93672cf112a044f08b653cab691216f0'],
                 'remark': '我是一个备注', 'browserFingerPrint': {}}
    res = requests.post(f"{url}/browser/update/partial",
                        data=json.dumps(json_data), headers=headers).json()
    print(res)


def openBrowser(browser_id):
    json_data = {
        "id": browser_id,
        "args": ["--enable-automation"]
    }
    print(f"[BitAPI] 发送到 /browser/open 的请求数据: {json.dumps(json_data)}")
    try:
        response = requests.post(f"{url}/browser/open", data=json.dumps(json_data), headers=headers, timeout=10)
        response.raise_for_status() # 如果HTTP请求返回了错误状态码，则抛出HTTPError
        res_json = response.json()
        print(f"[BitAPI] 打开浏览器 {browser_id} 的响应: {res_json}")
        return res_json
    except requests.HTTPError as e:
        raise BitAPIError(f"打开浏览器 {browser_id} 的HTTP请求失败: {e}. 响应内容: {response.text if response else 'N/A'}")
    except requests.RequestException as e:
        raise BitAPIError(f"打开浏览器 {browser_id} 的请求失败: {e}")
    except json.JSONDecodeError as e:
        raise BitAPIError(f"解析打开浏览器 {browser_id} 的响应JSON失败: {e}. 响应文本: {response.text if response else 'N/A'}")


def closeBrowser(browser_id):  # 关闭窗口
    json_data = {'id': browser_id}
    try:
        response = requests.post(f"{url}/browser/close", data=json.dumps(json_data), headers=headers, timeout=10)
        response.raise_for_status()
        print(f"[BitAPI] 关闭浏览器 {browser_id} 的响应: {response.json()}")
    except Exception as e:
        print(f"[BitAPI] 关闭浏览器 {browser_id} 时出错: {e}") # 出错时仅打印，不中断主流程


def deleteBrowser(browser_id):  # 删除窗口
    json_data = {'id': browser_id}
    print(requests.post(f"{url}/browser/delete",
          data=json.dumps(json_data), headers=headers).json())

def launch_and_get_debug_address(browser_id_to_open): # 修改：接受 browser_id 作为参数
    """
    使用给定的 browser_id 打开浏览器并获取调试地址。
    返回: (browser_id, raw_http_address, raw_ws_address) 的元组。
          失败时，地址部分可能为 None。
    """
    if not browser_id_to_open:
        print("[BitAPI] 错误: launch_and_get_debug_address 需要一个 browser_id。")
        # 为了保持返回三个值，即使browser_id_to_open是None，也返回None, None, None
        # 或者可以抛出异常，但main_controller目前期望接收一个元组
        return None, None, None 

    print(f"[BitAPI] 尝试为浏览器ID '{browser_id_to_open}' 打开并获取调试地址...")
    try:
        open_response = openBrowser(browser_id_to_open)
    except BitAPIError as e:
        print(f"[BitAPI] 调用 openBrowser API 失败 for ID '{browser_id_to_open}': {e}")
        return browser_id_to_open, None, None

    if open_response and open_response.get('success'):
        data = open_response.get('data', {})
        raw_http_address = None
        raw_ws_address = data.get('ws')

        if 'http' in data and isinstance(data['http'], str):
            raw_http_address = data['http']
            print(f"[BitAPI] 成功从 'http' 字段获取原始调试地址: {raw_http_address} for ID '{browser_id_to_open}'")
        elif 'webDriver' in data and isinstance(data['webDriver'], str): # webDriver通常也是ip:port
            raw_http_address = data['webDriver']
            print(f"[BitAPI] 成功从 'webDriver' 字段获取原始调试地址: {raw_http_address} for ID '{browser_id_to_open}'")
        elif raw_ws_address and isinstance(raw_ws_address, str):
            print(f"[BitAPI] 未能从 'http'/'webDriver' 获取地址，尝试从 'ws': {raw_ws_address} 解析 for ID '{browser_id_to_open}'")
            try:
                ws_url_parts = raw_ws_address.split('/')
                if len(ws_url_parts) > 2 and ":" in ws_url_parts[2]:
                    raw_http_address = ws_url_parts[2]
                    print(f"[BitAPI] 成功从 'ws' 字符串解析出备用原始调试地址: {raw_http_address} for ID '{browser_id_to_open}'")
            except Exception as e_parse:
                print(f"[BitAPI] 从 'ws' 字符串解析备用原始调试地址时发生错误: {e_parse}")
        
        if raw_http_address or raw_ws_address:
            print(f"[BitAPI] 将为ID '{browser_id_to_open}' 返回: http_addr={raw_http_address}, ws_addr={raw_ws_address}")
            return browser_id_to_open, raw_http_address, raw_ws_address
        else:
            print(f"[BitAPI] 错误: 未能为ID '{browser_id_to_open}' 获取到任何有效的原始调试连接信息。Data: {data}")
            return browser_id_to_open, None, None
    else:
        print(f"[BitAPI] 未能成功打开浏览器ID '{browser_id_to_open}'。响应: {open_response}")
        return browser_id_to_open, None, None

# 原来的 if __name__ == '__main__': 块被移除或注释掉
# if __name__ == '__main__':
    # cdp_endpoint = launch_and_get_debug_address()
    # if cdp_endpoint:
    #     print(f"获取到的 CDP Endpoint: {cdp_endpoint}")
    #     print("浏览器窗口应保持打开状态。后续操作可由其他脚本使用此 Endpoint。")
    #     # 例如，等待一段时间，然后可以调用 closeBrowser 如果需要
    #     # time.sleep(60) 
    #     # print("准备关闭浏览器...")
    #     # browser_id = ... # 需要从 launch_and_get_debug_address 或其内部获取
    #     # closeBrowser(browser_id_from_config) # 需要传递正确的 browser_id
    # else:
    #     print("未能成功启动浏览器或获取调试地址。")
