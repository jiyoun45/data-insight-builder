import pandas as pd
import tools

# 데이터 로드 (헤더 감지 행 반영)
df = pd.read_csv('data/API_IT.NET.USER.ZS_DS2_en_csv_v2_468465.csv', skiprows=4)
df = df.loc[:, ~df.columns.str.contains(r'^Unnamed: \d+$', na=False) | df.notna().any()]

print("=" * 40)
print(" 도구 1~4 동작 검증 결과")
print("=" * 40)

# 도구 1: reshape_wide_to_long
t1 = tools.reshape_wide_to_long(df)
print(f"[도구 1] 롱 포맷 변환 행 수: {t1['used_rows']:,}건 (제외 {t1['excluded_rows']:,}건)")

# 도구 2: quality_report
t2 = tools.quality_report(df)
print(f"[도구 2] 전체 결측률: {t2['result']['null_ratio_pct']}% (중복 행 {t2['result']['duplicate_rows']}건)")

# 도구 3: year_coverage
t3 = tools.year_coverage(df)
print(f"[도구 3] 연도 범위: {t3['result']['start_year']}~{t3['result']['end_year']}년 (권장 기준연도: {t3['result']['recommended_year']}년)")

# 도구 4: detect_aggregates
t4 = tools.detect_aggregates(df)
print(f"[도구 4] 집계 행: {t4['result']['aggregate_count']}건 감지, 순수 국가 수: {t4['result']['individual_country_count']}건")
print("=" * 40)
