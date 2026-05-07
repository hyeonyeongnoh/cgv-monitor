import requests
import time
import json
import hmac
import hashlib
import base64
import os
from datetime import datetime
from urllib.parse import urlparse

# ===== 설정 =====
KAKAO_TOKEN = os.environ.get("KAKAO_TOKEN", "")
CGV_COOKIE = os.environ.get("CGV_COOKIE", "")
SIGNATURE_KEY = "ydqXY0ocnFLmJGHr_zNzFcpjwAsXq_8JcBNURAkRscg"

KEYWORD = "요시"

# ===== x-signature 자동 생성 =====
def generate_signature(url, timestamp, body=""):
    path = urlparse(url).path
    message = f"{timestamp}|{path}|{body}"
    key = SIGNATURE_KEY.encode("utf-8")
    msg = message.encode("utf-8")
    sig = hmac.new(key, msg, hashlib.sha256).digest()
    return base64.b64encode(sig).decode("utf-8")

def get_headers(url):
    timestamp = str(int(time.time()))
    signature = generate_signature(url, timestamp)
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Whale/4.37.378.6 Safari/537.36",
        "x-signature": signature,
        "x-timestamp": timestamp,
        "Cookie": CGV_COOKIE,
        "Referer": "https://cgv.co.kr/",
        "Origin": "https://cgv.co.kr",
        "accept": "application/json",
        "accept-language": "ko-KR",
    }

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
        "link": {"web_url": link, "mobile_web_url": link}
    }
    res = requests.post(url, headers=headers, data={"template_object": json.dumps(template)})
    if res.status_code == 200:
        print("✅ 카카오톡 전송 성공!")
    else:
        print(f"❌ 카카오톡 전송 실패: {res.text}")

# ===== 전국 지점 siteNo 수집 =====
def get_all_sites():
    sites = []
    url = "https://api.cgv.co.kr/sto/fstord/searchFstordRegnSiteList"
    
    for regnGrpCd in range(1, 10):  # 01~09 전국 지역
        params = {
            "coCd": "A420",
            "regnGrpCd": f"{regnGrpCd:02d}",
            "lntd": "126.870978",
            "lttd": "37.553751"
        }
        try:
            res = requests.get(url, params=params, headers=get_headers(url), timeout=10)
            data = res.json()
            if data.get("statusCode") == 0:
                region_sites = data.get("data", [])
                sites.extend(region_sites)
                print(f"지역 {regnGrpCd:02d}: {len(region_sites)}개 지점 수집")
            time.sleep(0.5)  # 과도한 요청 방지
        except Exception as e:
            print(f"지역 {regnGrpCd:02d} 오류: {e}")
    
    print(f"\n✅ 전국 총 {len(sites)}개 지점 수집 완료!\n")
    return sites

# ===== 지점별 재고 체크 =====
def check_site(site_no, site_nm):
    url = "https://api.cgv.co.kr/sto/fstord/searchFstordMain"
    params = {
        "coCd": "A420",
        "siteNo": site_no,
    }
    
    try:
        res = requests.get(url, params=params, headers=get_headers(url), timeout=10)
        data = res.json()
        
        if data.get("statusCode") != 0:
            return
        
        hotdl_list = data.get("data", {}).get("hotdlList", []) or []
        
        for product in hotdl_list:
            name = product.get("prodNm", "")
            price = product.get("salAmt", "")
            stock = product.get("salPsblCnt", 0)  # 구매 가능 수량
            
            if KEYWORD in name:
                now = datetime.now().strftime('%H:%M:%S')
                print(f"[{now}] 🎯 {site_nm} | {name} | {price}원 | 재고:{stock}개")
                
                if stock and int(stock) > 0:
                    print(f"[{now}] 🎉 {site_nm}에서 {name} 구매 가능!")
                    send_kakao(
                        f"🟢 {name} 재고 떴다!\n📍 지점: {site_nm}\n💰 가격: {price}원\n🛒 남은 수량: {stock}개\n👉 지금 바로 구매!",
                        f"https://cgv.co.kr/sto/fastOrder"
                    )
                else:
                    print(f"[{now}] ❌ {site_nm} 품절")
                    
    except Exception as e:
        print(f"[{site_nm}] 오류: {e}")

# ===== 메인 실행 =====
def main():
    print("=" * 50)
    print("🔍 CGV 요시 팝콘통 전국 재고 모니터링!")
    print("=" * 50 + "\n")

    # 전국 지점 수집
    sites = get_all_sites()
    
    if not sites:
        print("❌ 지점 목록 수집 실패")
        send_kakao("⚠️ CGV 쿠키 만료!\nGitHub Secrets에서 CGV_COOKIE 교체 필요!")
        return

    # 전국 지점 순회하며 재고 체크
    print("전국 지점 재고 체크 시작...\n")
    found = False
    
    for site in sites:
        site_no = site.get("siteNo")
        site_nm = site.get("siteNm")
        check_site(site_no, site_nm)
        time.sleep(0.3)  # 과도한 요청 방지
    
    print("\n✅ 전국 재고 체크 완료!")

main()
