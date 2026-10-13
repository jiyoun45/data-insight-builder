import json
from app import app

client = app.test_client()

print("=" * 50)
print(" Step 17: POST /suggest 엔드투엔드 테스트")
print("=" * 50)

# 1. /inspect 먼저 실행하여 실제 데이터셋 진단 정보 획득
print("[1] CSV 파일 진단 (/inspect) 수행 중...")
with open("data/API_IT.NET.USER.ZS_DS2_en_csv_v2_468465.csv", "rb") as f:
    inspect_res = client.post("/inspect", data={"file": (f, "worldbank_test.csv")}, content_type="multipart/form-data")

inspect_data = inspect_res.get_json()
print(f"    - 진단 완료: {inspect_data['filename']}, 행={inspect_data['row_count']}, 추천연도={inspect_data['year_analysis']['recommended_year']}")

# 2. 진단 결과를 /suggest 에 전송하여 Gemini의 분석 제안 수신
print("\n[2] Gemini AI에게 분석 제안 요청 (/suggest) 전송 중...")
suggest_res = client.post("/suggest", json=inspect_data)

print(f"    - 응답 상태 코드: {suggest_res.status_code}")
suggest_data = suggest_res.get_json()

if suggest_res.status_code == 200 and suggest_data.get("success"):
    suggestions = suggest_data.get("suggestions", [])
    print(f"    - Gemini가 추천한 분석 개수: {len(suggestions)}개")
    print("-" * 50)
    for i, s in enumerate(suggestions, 1):
        print(f"[{i}] 도구명: {s['tool']}")
        print(f"    기준시점: {s.get('reference_period')}")
        print(f"    이유: {s.get('why')}")
        print(f"    주의점: {s.get('caution')}")
        print(f"    파라미터: {s.get('params')}")
        print("-" * 50)
else:
    print("    - 오류 발생:", suggest_data)

print("=" * 50)
