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
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("MY_REPO", "")  # ex) hyeonyeongnoh/cgv-monitor
SIGNATURE_KEY = "ydqXY0ocnFLmJGHr_zNzFcpjwAsXq_8JcBNURAkRscg"
STATE_FILE = "stock_state.json"
KEYWORD = "요시"
YOSHI_LINK = "https://cgv.co.kr/sto/fastOrder/0226070023076?coCd=A420&prodNo=0226070023076"

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

# ===== 이전 상태 불러오기 (GitHub API) =====
def load_previous_state():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{STATE_FILE}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        data = res.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return json.loads(content), data["sha"]
    return {}, None

# ===== 현재 상태 저장 (GitHub API) =====
def save_current_state(state, sha=None):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{STATE_FILE}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    content = base64.b64encode(json.dumps(state, ensure_ascii=False).encode()).decode()
    body = {
        "message": "Update stock state",
        "content": content,
    }
    if sha:
        body["sha"] = sha
    requests.put(url, headers=headers, json=body)

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

# ===== 전국 지점 수집 =====
def get_all_sites():
    sites = []
    url = "https://api.cgv.co.kr/sto/fstord/searchFstordRegnSiteList"
    for regnGrpCd in range(1, 10):
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
                sites.extend(data.get("data", []))
            time.sleep(0.5)
        except Exception as e:
            print(f"지역 {regnGrpCd:02d} 오류: {e}")
    print(f"✅ 전국 총 {len(sites)}개 지점 수집 완료!")
    return sites

# ===== 지점별 재고 체크 =====
def check_site_result(site_no, site_nm):
    url = "https://api.cgv.co.kr/sto/fstord/searchFstordMain"
    params = {"coCd": "A420", "siteNo": site_no}
    try:
        res = requests.get(url, params=params, headers=get_headers(url), timeout=10)
        data = res.json()
        if data.get("statusCode") != 0:
            return None
        hotdl_list = data.get("data", {}).get("hotdlList", []) or []
        for product in hotdl_list:
            name = product.get("prodNm", "")
            price = product.get("salAmt", "")
            stock = product.get("salPsblCnt", 0)
            if KEYWORD in name:
                return {
                    "site_nm": site_nm,
                    "name": name,
                    "price": price,
                    "stock": int(stock) if stock else 0
                }
    except Exception as e:
        print(f"[{site_nm}] 오류: {e}")
    return None

# ===== 메인 실행 =====
def main():
    print("=" * 50)
    print("🔍 CGV 요시 팝콘통 전국 재고 모니터링!")
    print("=" * 50 + "\n")

    # 이전 상태 불러오기
    prev_state, sha = load_previous_state()
    print(f"이전 상태: {len(prev_state)}개 지점 기록\n")

    # 전국 지점 수집
    sites = get_all_sites()
    if not sites:
        send_kakao("⚠️ CGV 쿠키 만료!\nGitHub Secrets에서 CGV_COOKIE 교체 필요!")
        return

    # 전국 재고 체크
    current_state = {}
    newly_available = []  # 새로 재고 생긴 곳
    newly_sold_out = []   # 새로 품절된 곳

    for site in sites:
        site_no = site.get("siteNo")
        site_nm = site.get("siteNm")
        result = check_site_result(site_no, site_nm)

        current_stock = result["stock"] if result else 0
        prev_stock = prev_state.get(site_no, {}).get("stock", 0)

        current_state[site_no] = {
            "site_nm": site_nm,
            "stock": current_stock,
            "price": result["price"] if result else ""
        }

        # 상태 변화 감지
        if prev_stock == 0 and current_stock > 0:
            newly_available.append(result)
            print(f"🆕 재고 생김! {site_nm} ({current_stock}개)")
        elif prev_stock > 0 and current_stock == 0:
            newly_sold_out.append(site_nm)
            print(f"💨 품절됨! {site_nm}")
        else:
            print(f"{'✅' if current_stock > 0 else '❌'} {site_nm} ({current_stock}개) - 변화없음")

        time.sleep(0.3)

    # 재고 생긴 곳 알림
    if newly_available:
        lines = ["🟢 요시 팝콘통 재고 떴다!\n"]
        for r in newly_available:
            lines.append(f"📍 {r['site_nm']} ({r['stock']}개)")
        lines.append(f"\n💰 가격: {newly_available[0]['price']}원")
        lines.append("👉 지금 바로 구매!")
        send_kakao("\n".join(lines), link=YOSHI_LINK)

    # 품절된 곳 알림
    if newly_sold_out:
        lines = ["💨 요시 팝콘통 품절 지점\n"]
        for nm in newly_sold_out:
            lines.append(f"📍 {nm}")
        send_kakao("\n".join(lines), link=YOSHI_LINK)

    if not newly_available and not newly_sold_out:
        print("\n변화 없음 - 알림 없음")

    # 현재 상태 저장
    save_current_state(current_state, sha)
    print("\n✅ 상태 저장 완료!")

main()
