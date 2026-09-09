import logging

import time
import base64
import hmac
import hashlib
import random
from urllib.parse import quote,urlencode,parse_qs
from pymongo import errors

def query_string_to_dict(query_string):
    """
    将查询字符串转换为字典

    参数:
    query_string (str): 查询字符串

    返回:
    dict: 包含键值对的字典
    """
    params_dict = parse_qs(query_string)
    for key, value in params_dict.items():
        if len(value) == 1:
            params_dict[key] = value[0]
    return params_dict

def merge_and_sort_params(params1, params2):
    """
    合并两个字典并根据键值对进行排序，然后转换为查询字符串

    参数:
    params1 (dict): 第一个字典
    params2 (dict): 第二个字典

    返回:
    str: 排序后的查询字符串
    """
    merged_params = {**params1, **params2}
    sorted_params = sorted(merged_params.items())
    sorted_query_string = urlencode(sorted_params)
    return sorted_query_string

def hmac_sha1(key, message):
    hmac_obj = hmac.new(key, message, hashlib.sha1)
    encrypted_message = hmac_obj.digest()
    base64_encoded = base64.b64encode(encrypted_message)
    return base64_encoded.decode('utf-8')

def create_params(params,url):
    page = 45
    # params参数，如果没有则设置为{}
    # 示例用法
    oauth_timestamp = str(int(time.time()))
    oauth_nonce = random.randint(10**18, 10**19 -10**16 - 1) # 随机数
    key = 'fea29b6a-c20c-4c4f-8c9a-d5957dc6f437&qwJe9zxnm3HA3aM1dPquYlzDrTr29tje'.encode('utf-8') # 密钥固定
    oauth_consumer_key = '59fe8fc0-4447-43ed-b7e3-bf026bb8d1e5' # 用户固定
    oauth_token = 'ie2J7oorRt86zmpHPPEHGwhXZMCTgPBd' # 用户固定
    # oauth_token = 'VXKAaQtF5M0zD3qoGxQwA4ceLVZFMo8T'
    oauth_version = '1.0'
    query_string = ('OAuth oauth_consumer_key="'+oauth_consumer_key+'", oauth_nonce="-'+str(oauth_nonce)+', oauth_signature_method="HMAC-SHA1", oauth_timestamp="'+oauth_timestamp+'", oauth_token="'+oauth_token+'", oauth_version="'+oauth_version+'"').replace(', ','&').replace('OAuth ','').replace('"','')
    params_dict = query_string_to_dict(query_string)
    sorted_query_string = merge_and_sort_params(params, params_dict)
    # print(query_string)
    # print(params_dict)
    # print(params)
    # print(sorted_query_string)
    # input()
    # url = 'https://api.starmakerstudios.com/api/v17/android/sm/zh-CN/phone/xxhdpi/library/recommend/songs'

    # 待加密信息
    # message = f'GET&https%3A%2F%2Fstarmakerapp-hrd.appspot.com%2Fapi%2Fv16%2F{quote(url.split("api/v17/")[1],safe="")}&is_select_music%3D0%26oauth_consumer_key%3D{oauth_consumer_key}%26oauth_nonce%3D-{oauth_nonce}%26oauth_signature_method%3DHMAC-SHA1%26oauth_timestamp%3D{oauth_timestamp}%26oauth_token%3D{oauth_token}%26oauth_version%3D1.0%26page%3D{page}%26source%3Dlibrary'.encode('utf-8')
    message = f'GET&https%3A%2F%2Fstarmakerapp-hrd.appspot.com%2Fapi%2Fv16%2F{quote(url.split("api/v17/")[1],safe="")}&{quote(sorted_query_string,safe="")}'.encode('utf-8')
    encrypted_message = hmac_sha1(key, message)
    oauth_signature = (encrypted_message)
    headers = {
        'User-Agent': 'sm/8.52.6/Android/10/google play/E5770DC3E50FDEBD818A04025C43D8FB/WIFI',
        'authorization': 'OAuth oauth_consumer_key="'+oauth_consumer_key+'", oauth_nonce="-'+str(oauth_nonce)+'", oauth_signature="'+oauth_signature+'", oauth_signature_method="HMAC-SHA1", oauth_timestamp="'+oauth_timestamp+'", oauth_token="'+oauth_token+'", oauth_version="'+oauth_version+'"',
        'content-type': 'application/json',
    }
    return headers
    # response = requests.get(
    #     url,
    #     params=params,
    #     headers=headers,
    # )
    #
    # print(headers['authorization'].replace(', ','&').replace('OAuth ','').replace('"',''))
    # print(response.json())

