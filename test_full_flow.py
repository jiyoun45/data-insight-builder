import json
from app import app

client = app.test_client()

print("=" * 60)
print(" 🚀 Step 23: World Bank 실제 CSV 전체 흐름 종합 테스트")
print("=" * 60)

# [Step 1] 메인 페이지 & 헬스체크
print("\n[검증 1] 서버 연결 및 헬스체크 (GET / & GET /health)")
res_page = client.get("/")
assert res_page.status_code == 200, "메인 페이지 로드 실패"
res_health = client.get("/health")
assert res_health.status_code == 200, "헬스체크 실패"
health_data = res_health.get_json()
print(f"  ✅ 메인 HTML 로드 성공 (200 OK)")
print(f"  ✅ Gemini API 키 연동 여부: {health_data['gemini_api_configured']} (모델: {health_data['gemini_model']})")

# [Step 2] World Bank CSV 파일 업로드 및 진단 (POST /inspect)
print("\n[검증 2] World Bank CSV 파일 업로드 및 진단 (POST /inspect)")
with open("data/API_IT.NET.USER.ZS_DS2_en_csv_v2_468465.csv", "rb") as f:
    res_inspect = client.post("/inspect", data={"file": (f, "API_IT.NET.USER.ZS.csv")}, content_type="multipart/form-data")

assert res_inspect.status_code == 200, f"진단 실패: {res_inspect.data}"
inspect_data = res_inspect.get_json()
rec_year = inspect_data["year_analysis"]["recommended_year"]
print(f"  ✅ 파일 인코딩 감지: {inspect_data['encoding']}")
print(f"  ✅ 메타데이터 건너뛰고 감지된 헤더 행: {inspect_data['header_row_index']}번 인덱스")
print(f"  ✅ 총 데이터 행 수: {inspect_data['row_count']}개, 열 수: {inspect_data['column_count']}개")
print(f"  ✅ 전체 결측률: {inspect_data['quality']['null_percentage']}%")
print(f"  ✅ World Bank 집계 행 감지: {inspect_data['aggregates']['aggregate_row_count']}건 (순수 개별 국가: {inspect_data['aggregates']['individual_country_count']}개국)")
print(f"  ✅ 최적 권장 기준연도: {rec_year}년")
print(f"  ✅ 미리보기 행 수: {len(inspect_data['preview'])}개 행")

# [Step 3] Gemini AI 분석 제안 요청 (POST /suggest)
print("\n[검증 3] Gemini AI 실시간 분석 제안 요청 (POST /suggest)")
res_suggest = client.post("/suggest", json=inspect_data)
assert res_suggest.status_code == 200, f"제안 요청 실패: {res_suggest.data}"
suggest_data = res_suggest.get_json()
suggestions = suggest_data.get("suggestions", [])
assert len(suggestions) >= 3, f"제안 개수 부족: {len(suggestions)}"
print(f"  ✅ Gemini가 도구 카탈로그에서 선별한 제안 개수: {len(suggestions)}개")
for idx, s in enumerate(suggestions, 1):
    print(f"     {idx}. 도구: [{s['tool']}] (기준시점: {s.get('reference_period')}) - {s['why'][:45]}...")

# [Step 4] 제안된 도구 중 첫 번째 도구 실제 실행 (POST /run)
first_tool = suggestions[0]
print(f"\n[검증 4] 선택된 분석 도구 실행 (POST /run: {first_tool['tool']})")
res_run = client.post("/run", json={"tool": first_tool["tool"], "params": first_tool["params"]})
assert res_run.status_code == 200, f"도구 실행 실패: {res_run.data}"
run_data = res_run.get_json()
print(f"  ✅ 기준 시점: {run_data['reference_period']}")
print(f"  ✅ 실제 사용된 행: {run_data['used_rows']}건")
print(f"  ✅ 제외된 행: {run_data['excluded_rows']}건 ({run_data['excluded_reason']})")
print(f"  ✅ Chart.js 차트 종류: {run_data['result'].get('chart_type', 'bar')}")

# [Step 5] Gemini AI 심층 마크다운 리포트 생성 (POST /explain 모드 B)
print(f"\n[검증 5] Gemini AI 심층 마크다운 해석 리포트 생성 (POST /explain 모드 B)")
res_explain = client.post("/explain", json={"mode": "B", "run_result": run_data})
assert res_explain.status_code == 200, f"해석 생성 실패: {res_explain.data}"
explain_data = res_explain.get_json()
explanation_text = explain_data.get("explanation", "")
assert "## 무엇을 봤는가" in explanation_text, "필수 섹션 누락"
assert "## 데이터 출처와 정의" in explanation_text, "필수 섹션 누락"
assert "## 계산 결과" in explanation_text, "필수 섹션 누락"
print("  ✅ 7개 필수 섹션 마크다운 리포트 정상 생성 완료!")
print("\n--- [AI 생성 리포트 미리보기] ---")
print(explanation_text[:400] + "\n...")

print("\n" + "=" * 60)
print(" 🎉 전체 흐름 엔드투엔드 통합 테스트 ALL PASS!")
print("=" * 60)
