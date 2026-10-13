import json
from app import app

client = app.test_client()

print("=" * 55)
print(" Step 18: POST /run 엔드투엔드 테스트")
print("=" * 55)

# 1. 파일 업로드 (/inspect) 수행하여 메모리에 데이터셋 적재
print("[1] CSV 업로드 (/inspect) 로 메모리에 데이터셋 적재...")
with open("data/API_IT.NET.USER.ZS_DS2_en_csv_v2_468465.csv", "rb") as f:
    res_inspect = client.post("/inspect", data={"file": (f, "sample.csv")}, content_type="multipart/form-data")

print(f"    - 업로드 완료: 행 수 = {res_inspect.get_json()['row_count']}")

# 2. POST /run 정상 실행: 도구 7번 (top_bottom_n)
print("\n[2] POST /run 정상 실행 테스트 (도구: top_bottom_n, 기준시점: 2024)")
req_body = {
    "tool": "top_bottom_n",
    "params": {
        "reference_period": "2024",
        "n": 5,
        "exclude_aggregates": True
    }
}
res_run = client.post("/run", json=req_body)
data_run = res_run.get_json()

print(f"    - 상태 코드: {res_run.status_code}")
print(f"    - 기준 시점: {data_run.get('reference_period')}")
print(f"    - 사용 행 수: {data_run.get('used_rows')}건")
print(f"    - 제외 행 수: {data_run.get('excluded_rows')}건 (사유: {data_run.get('excluded_reason')})")
print(f"    - 차트 종류: {data_run.get('result', {}).get('chart_type')}")
print(f"    - 1위 국가: {data_run.get('result', {}).get('top_n', [{}])[0]}")

# 3. 기준 시점 누락 시 필수 에러 검증
print("\n[3] 기준 시점 누락 시 유효성 검증 테스트 (오류 반환 여부)")
bad_body = {
    "tool": "top_bottom_n",
    "params": {"n": 5}  # reference_period 누락!
}
res_bad = client.post("/run", json=bad_body)
print(f"    - 상태 코드: {res_bad.status_code} (예상: 400)")
print(f"    - 에러 메시지: {res_bad.get_json().get('error')}")

# 4. 도구 8번 (group_summary) 실행
print("\n[4] POST /run 실행 테스트 (도구: group_summary, 기준시점: 2024)")
group_body = {
    "tool": "group_summary",
    "params": {
        "reference_period": "2024",
        "group_column": "Region"
    }
}
res_group = client.post("/run", json=group_body)
data_group = res_group.get_json()
print(f"    - 상태 코드: {res_group.status_code}")
print(f"    - 대륙별 평균 상위: {data_group.get('result', {}).get('labels', [])[:3]}")

print("=" * 55)
