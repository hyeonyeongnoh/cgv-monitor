import requests
import time
import json
import hmac
import hashlib
import base64
from datetime import datetime
from urllib.parse import urlparse

# ===== 설정 =====
KAKAO_TOKEN = "rDH3zp4Db9nVEJuBG7lEbO0iV19DK1KJAAAAAQoXFmIAAAGeAmaVBYh6dPOEuoNF"

# 쿠키 (만료시만 교체)
CGV_COOKIE = "_ga=GA1.1.602101579.1774355526; _cfuvid=j95ffyPk3kEsWe_mYmQL5SD7jmIOZOIX.KWhA90xec4-1778152989.0679383-1.0.1.1-bXGHw5uSldsZJlERtayOSGaSe.aS75JAo7dDGLETveM; refresh_token=mOlv4z/WKrseco4EVqIvnrfaap9cUIlZRMO/29QTyTqvIWA4dBvo7T4buZTmsHuSo4BfuND00qwuiASBBxp0JJHleYWipyyrHevWL/bLTheRRUAlR8lJ0pcMqa8GIdkPOmELgqp0P1lpFS1olagDqPp4uvXfqFwYLvubUIoV30w=; __cf_bm=Sf4uCzqjYeDtATTZi3uNU8jE.kt59sA4939lFb7baNQ-1778159426.4852343-1.0.1.1-3QpQECbLvC4jOSsSJaombX3xS_ttEH9SKjnU3q3F9kr6Kdw5j3rJGwL8djQgXI.ucos0JsWVWHsrStapZk3PU8ISSz_uZDm1pfXLSWXefg6NbKK30SUzFjlH0vaqLUpS; _ga_HV92ZRC3WF=GS2.1.s1778157165$o5$g1$t1778159798$j55$l0$h0"

# 서명 비밀키 (CGV JS에서 추출)
SIGNATURE_KEY = "ydqXY0ocnFLmJGHr_zNzFcpjwAsXq_8JcBNURAkRscg"

CGV_URL = "https://api.cgv.co.kr/sto/fstord/searchFstordStoDpProdPageingList"
CGV_PARAMS = {
    "coCd": "A420",
    "stoNo": "0013011",
    "dpctgNo": "8213",
    "orderBy": "01",
    "START_ROW": "1",
    "END_ROW": "20",
}

KEYWORD = "요시"
CHECK_INTERVAL = 300  # 5분마다
alert_sent = False

# ===== x-signature 자동 생성 =====
def generate_signature(url, timestamp, body=""):
    path = urlparse(url).path
    # JS 코드 기준: timestamp|pathname|body 순서
    message = f"{timestamp}|{path}|{body}"
    key = SIGNATURE_KEY.encode("utf-8")
    msg = message.encode("utf-8")
    sig = hmac.new(key, msg, hashlib.sha256).digest()
    return base64.b64encode(sig).decode("utf-8")

# ===== 카카오톡 알림 =====
def send_kakao(text, link="https://cgv.co.kr/sto/fastOrder"):
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {
        "Authorization": f"Bearer {KAKAO_TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    template = {
        "object_type": "text",
        "text": text,
        "link": {
            "web_url": link,
            "mobile_web_url": link
        }
    }
    res = requests.post(url, headers=headers, data={"template_object": json.dumps(template)})
    if res.status_code == 200:
        print("✅ 카카오톡 전송 성공!")
    else:
        print(f"❌ 카카오톡 전송 실패: {res.text}")

# ===== 재고 체크 =====
def check_stock():
    global alert_sent

    timestamp = str(int(time.time()))
    signature = generate_signature(CGV_URL, timestamp)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Whale/4.37.378.6 Safari/537.36",
        "x-signature": signature,
        "x-timestamp": timestamp,
        "Cookie": CGV_COOKIE,
        "Referer": "https://cgv.co.kr/",
        "Origin": "https://cgv.co.kr",
        "accept": "application/json",
        "accept-language": "ko-KR",
    }

    try:
        res = requests.get(CGV_URL, params=CGV_PARAMS, headers=headers, timeout=10)
        now = datetime.now().strftime('%H:%M:%S')
        print(f"[{now}] 상태코드: {res.status_code}")

        data = res.json()

        if data.get("statusCode") != 0:
            msg = data.get("statusMessage", "")
            print(f"[{now}] ❌ API 오류: {msg}")
            if not alert_sent:
                send_kakao("⚠️ CGV 인증 만료!\n쿠키 교체 필요!")
                alert_sent = True
            return

        alert_sent = False
        products = data.get("data", [])

        if not products:
            print(f"[{now}] ❌ 상품 없음 (품절 or 미판매 중)")
            return

        for product in products:
            name = product.get("prodNm", "이름없음")
            price = product.get("salAmt", "가격미상")
            stock = product.get("invntStusCd", "0")  # 1=재고있음, 0=품절

            print(f"[{now}] {name} | {price}원 | 재고상태:{stock}")

            if KEYWORD in name:
                if stock == "1":
                    print(f"[{now}] 🎉 {name} 구매 가능!")
                    send_kakao(f"🟢 {name} 재고 떴다!\n💰 가격: {price}원\n👉 지금 바로 구매!")
                    try:
                        import winsound
                        for _ in range(5):
                            winsound.Beep(1000, 500)
                    except:
                        pass
                else:
                    print(f"[{now}] ❌ {name} 품절")

    except Exception as e:
        print(f"[오류] {e}")

# ===== 실행 =====
print("=" * 50)
print("🔍 CGV 요시 팝콘통 재고 모니터링 시작!")
print(f"⏱ 체크 주기: {CHECK_INTERVAL // 60}분마다")
print("완전 자동화 버전 - 쿠키만 가끔 교체!")
print("=" * 50 + "\n")

while True:
    check_stock()
    time.sleep(CHECK_INTERVAL)
