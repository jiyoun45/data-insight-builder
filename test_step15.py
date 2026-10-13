import pandas as pd
import tools

# 데이터 로드
df = pd.read_csv('data/API_IT.NET.USER.ZS_DS2_en_csv_v2_468465.csv', skiprows=4)
df = df.loc[:, ~df.columns.str.contains(r'^Unnamed: \d+$', na=False) | df.notna().any()]

print("=" * 45)
print(" 도구 5~8 동작 검증 결과")
print("=" * 45)

# 도구 5: describe_numeric
t5 = tools.describe_numeric(df, {"reference_period": "2024"})
print(f"[도구 5] 2024년 기술통계: 평균={t5['result']['mean']}%, 중앙값={t5['result']['median']}% (사용행: {t5['used_rows']}건)")

# 도구 6: trend_line
t6 = tools.trend_line(df, {"entities": ["Korea, Rep.", "United States", "World"], "start_year": "2000", "end_year": "2024"})
print(f"[도구 6] 시계열 추이: 연도 수={len(t6['result']['labels'])}개, 대상 수={len(t6['result']['datasets'])}개")

# 도구 7: top_bottom_n (기준시점 2024년 필수)
t7 = tools.top_bottom_n(df, {"reference_period": "2024", "n": 3})
top3_names = [item['label'] for item in t7['result']['top_n']]
print(f"[도구 7] 2024년 상위 3개국: {top3_names} (제외행: {t7['excluded_rows']}건)")

# 도구 8: group_summary (기준시점 2024년 필수, Region 그룹 분석)
t8 = tools.group_summary(df, {"reference_period": "2024", "group_column": "Region"})
print(f"[도구 8] 대륙(Region)별 그룹 수: {len(t8['result']['labels'])}개 (최고 평균: {t8['result']['labels'][0]} {t8['result']['table'][0]['mean']}%)")
print("=" * 45)
