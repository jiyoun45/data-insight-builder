import pandas as pd
import tools

df = pd.read_csv('data/API_IT.NET.USER.ZS_DS2_en_csv_v2_468465.csv', skiprows=4)
df = df.loc[:, ~df.columns.str.contains(r'^Unnamed: \d+$', na=False) | df.notna().any()]

print("=" * 48)
print(" 도구 9~12 동작 검증 결과")
print("=" * 48)

# 도구 9: change_rate
t9 = tools.change_rate(df, {"reference_period": "2024", "base_period": "2014", "n": 3})
print(f"[도구 9] 2014→2024 증가폭 1위: {t9['result']['top_increasers'][0]['country']} (+{t9['result']['top_increasers'][0]['diff']}%p)")

# 도구 10: distribution
t10 = tools.distribution(df, {"reference_period": "2024", "bins": 5})
print(f"[도구 10] 2024년 5개 구간 분포: 총 {t10['used_rows']}개국")

# 도구 11: correlation_scatter
t11 = tools.correlation_scatter(df, {"reference_period": "2024", "compare_period": "2014"})
print(f"[도구 11] 2014 vs 2024 상관계수: r={t11['result']['correlation_coefficient']} (주의사항: '{t11['cautions'][0]}')")

# 도구 12: compare_one_vs_all
t12 = tools.compare_one_vs_all(df, {"reference_period": "2024", "target_entity": "Korea, Rep."})
res12 = t12['result']
print(f"[도구 12] {res12['target_entity']} ({res12['target_value']}%) vs 전체평균 ({res12['all_mean']}%), 순위: {res12['rank']}/{res12['total_count']}위")

print(f"\n[레지스트리] 전체 등록된 도구 개수: {len(tools.TOOL_REGISTRY)}개")
print("=" * 48)
