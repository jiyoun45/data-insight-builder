import json
from app import app

client = app.test_client()

print("=" * 55)
print(" Step 19: POST /explain (모드 A vs 모드 B) 테스트")
print("=" * 55)

# 1. 파일 업로드 (/inspect)
with open("data/API_IT.NET.USER.ZS_DS2_en_csv_v2_468465.csv", "rb") as f:
    client.post("/inspect", data={"file": (f, "sample.csv")}, content_type="multipart/form-data")

# 2. 도구 7번 (top_bottom_n) 실행 (/run)
run_body = {
    "tool": "top_bottom_n",
    "params": {"reference_period": "2024", "n": 3, "exclude_aggregates": True}
}
client.post("/run", json=run_body)

# 3. 모드 A (비교용, 허술함) 요청 테스트
print("\n[1] 모드 A 테스트 (Pandas 결과 없이 진단 요약만 전달)")
res_a = client.post("/explain", json={"mode": "A"})
data_a = res_a.get_json()
print("--- 모드 A 응답 샘플 (앞 200자) ---")
print(data_a.get("explanation", "")[:200] + "...")

# 4. 모드 B (정식, 8대 규칙) 요청 테스트
print("\n[2] 모드 B 테스트 (Pandas 계산 결과 기반 7대 섹션 정밀 리포트)")
res_b = client.post("/explain", json={"mode": "B"})
data_b = res_b.get_json()
print("--- 모드 B 응답 결과 ---")
print(data_b.get("explanation", ""))
print("=" * 55)
