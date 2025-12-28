import base64, httpx

url = "https://wx3.sinaimg.cn/orj360/0078YzJegy1i8mwzrc7jej30xx5vt7wh.jpg"
headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://m.weibo.cn/",
    # 如果 403/302，再加 Cookie（从你 Playwright 登录拿到的 cookie_str）
    # "Cookie": cookie_str,
}

with httpx.Client(follow_redirects=True, timeout=10) as client:
    r = client.get(url, headers=headers)
    r.raise_for_status()
    img_bytes = r.content

img_b64 = base64.b64encode(img_bytes).decode("utf-8")

# 然后把 img_b64 作为 image 输入传给你使用的大模型 SDK