# -*- coding: utf-8 -*-
import os

# 1. 修改为你的网卡实际名称
# 虽然显示"无线局域网适配器 WLAN"，但系统内部名通常就是 "WLAN"
interface_name = "WLAN"

# 2. 修改为你的 IPv6 前缀 (根据你的 ipconfig)
# 原理：2001:250:4000:5113 是你的段
# 后面加上 "::" 是为了缩写中间的 0，直接拼上最后的数字
prefix = "2001:250:4000:5113::"

# 打开文件准备写入 (用 gbk 编码因为 Windows CMD 默认是 gbk)
with open("add_ips.bat", "w", encoding="gbk") as bat_file:
    
    bat_file.write("@echo off\n")
    bat_file.write(f"echo 正在为网卡 [{interface_name}] 添加 IP...\n")
    
    # 3. 循环生成 IP
    # 建议先生成 20 个测试 (range(1, 21))。
    # 如果没问题，再改成 range(1, 500)。一下子加太多校园网可能会断网。
    for i in range(1, 21):
        # 生成 16 进制后缀 (1 -> 1, 10 -> a)
        suffix = hex(i)[2:]
        
        # 拼凑命令
        # 结果类似于: netsh interface ipv6 add address "WLAN" 2001:250:4000:5113::1/64
        cmd = f'netsh interface ipv6 add address "{interface_name}" {prefix}{suffix}/64'
        
        bat_file.write(cmd + "\n")
        bat_file.write(f'echo 已添加: {prefix}{suffix}\n')

    bat_file.write("echo all done\n")
    bat_file.write("pause\n")

print("脚本生成完毕！请在目录下找到 add_ips.bat 并【右键-以管理员身份运行】")