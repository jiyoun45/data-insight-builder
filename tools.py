"""
tools.py - 데이터 분석 도구 카탈로그 (전체 12개 도구 완성)
모든 도구는 일관된 형식으로 결과를 반환합니다:
- reference_period: 기준 시점
- used_rows: 계산에 사용된 행 수
- excluded_rows: 제외된 행 수
- excluded_reason: 제외된 사유
- used_columns: 사용된 열 목록
- unit: 단위
- cautions: 주의사항 목록
- result: 실제 계산 결과 (JSON 안전 직렬화)

도구 공통 규칙:
- 7~12번 도구는 기준 시점(reference_period)을 필수 파라미터로 받습니다. 없으면 오류(ValueError)를 반환합니다.
- 집계 행 제외 여부(exclude_aggregates)는 기본값이 True(제외)입니다.
- 상관계수(도구 11)는 반드시 "상관관계는 인과관계가 아닙니다."를 주의사항에 포함합니다.
- NaN과 Infinity는 clean_for_json()을 통해 안전하게 처리됩니다.
"""

import glob
import json
import os
import numpy as np
import pandas as pd

# World Bank 표준 집계 코드
KNOWN_AGGREGATE_CODES = {
    "AFE", "AFW", "ARB", "CEB", "CSS", "EAP", "EAR", "EAS", "ECA", "ECS",
    "EMU", "EUU", "FCS", "HIC", "HPC", "IBD", "IBT", "IDA", "IDB", "IDX",
    "INX", "LAC", "LCN", "LDC", "LIC", "LMC", "LMY", "MEA", "MIC", "MNA",
    "NAC", "OED", "OSS", "PRE", "PSS", "PST", "SAS", "SSA", "SSF", "SST",
    "TEA", "TEC", "TLA", "TMN", "TSA", "TSS", "UMC", "WLD"
}

# 이름에 포함될 경우 집계 행으로 간주하는 키워드
AGGREGATE_KEYWORDS = [
    "world", "oecd", "euro area", "european union", "high income",
    "low income", "middle income", "income", "area", "dividend",
    "sub-saharan", "total", "states", "ida & ibrd", "fragile"
]


def clean_for_json(obj):
    """NaN, Inf, NumPy 타입을 순수 Python JSON 직렬화 가능 타입으로 변환"""
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return round(obj, 4)
    elif isinstance(obj, (np.integer, int)):
        return int(obj)
    elif isinstance(obj, (np.floating, float)):
        return round(float(obj), 4)
    elif isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_for_json(x) for x in obj]
    elif pd.isna(obj):
        return None
    return obj


def filter_aggregates_and_nulls(df, value_cols, exclude_aggregates=True):
    """
    집계 행 제외 및 지정된 열들의 결측치를 일관되게 필터링하는 공통 헬퍼
    반환값: (필터링된 df, 제외된 행 수, 제외 사유 문자열)
    """
    if isinstance(value_cols, str):
        value_cols = [value_cols]

    working_df = df.copy()
    initial_count = len(working_df)
    excluded_reasons = []

    # 1. 집계 행 제외
    if exclude_aggregates:
        code_col = "Country Code" if "Country Code" in working_df.columns else None
        name_col = "Country Name" if "Country Name" in working_df.columns else None

        is_agg_mask = pd.Series(False, index=working_df.index)
        if code_col:
            is_agg_mask |= working_df[code_col].astype(str).str.strip().isin(KNOWN_AGGREGATE_CODES)
        if name_col:
            name_lower = working_df[name_col].astype(str).str.lower()
            for kw in AGGREGATE_KEYWORDS:
                is_agg_mask |= name_lower.str.contains(kw, regex=False, na=False)

        agg_count = int(is_agg_mask.sum())
        if agg_count > 0:
            working_df = working_df[~is_agg_mask]
            excluded_reasons.append(f"집계 행 {agg_count}건 제외")

    # 2. 숫자 변환 및 결측치 제외
    for col in value_cols:
        if col in working_df.columns:
            working_df[col] = pd.to_numeric(working_df[col], errors="coerce")
            null_mask = working_df[col].isna()
            null_count = int(null_mask.sum())
            if null_count > 0:
                working_df = working_df[~null_mask]
                excluded_reasons.append(f"'{col}' 결측치 {null_count}건 제외")

    excluded_total = initial_count - len(working_df)
    reason_str = ", ".join(excluded_reasons) if excluded_reasons else "제외 항목 없음"
    return working_df, excluded_total, reason_str


# -------------------------------------------------------------
# 1. reshape_wide_to_long (연도 열을 행으로 접기)
# -------------------------------------------------------------
def reshape_wide_to_long(df, params=None):
    params = params or {}
    id_vars = [c for c in ["Country Name", "Country Code", "Indicator Name", "Indicator Code"] if c in df.columns]
    year_cols = [c for c in df.columns if str(c).strip().isdigit()]

    if not year_cols:
        raise ValueError("데이터셋에 변환할 숫자 연도 열이 없습니다.")

    melted = pd.melt(
        df,
        id_vars=id_vars,
        value_vars=year_cols,
        var_name="Year",
        value_name="Value"
    )
    melted["Value"] = pd.to_numeric(melted["Value"], errors="coerce")
    valid_melted = melted.dropna(subset=["Value"])

    return {
        "tool": "reshape_wide_to_long",
        "reference_period": f"{year_cols[0]}~{year_cols[-1]}",
        "used_rows": len(valid_melted),
        "excluded_rows": len(melted) - len(valid_melted),
        "excluded_reason": "연도별 지표 값이 누락(NaN)된 행",
        "used_columns": id_vars + ["Year", "Value"],
        "unit": "행 (롱 포맷 레코드)",
        "cautions": ["결측치는 제외되었으며, 변환 후 데이터 행 수가 크게 증가합니다."],
        "result": {
            "total_records": len(valid_melted),
            "preview": clean_for_json(valid_melted.head(10).to_dict(orient="records"))
        }
    }


# -------------------------------------------------------------
# 2. quality_report (결측·중복·타입·이상한 열 이름)
# -------------------------------------------------------------
def quality_report(df, params=None):
    params = params or {}
    total_rows = len(df)
    total_cells = int(df.size)
    null_cells = int(df.isna().sum().sum())
    null_ratio = round((null_cells / total_cells) * 100, 2) if total_cells > 0 else 0.0
    duplicate_rows = int(df.duplicated().sum())
    suspicious_cols = [c for c in df.columns if "unnamed" in str(c).lower() or not str(c).strip()]

    col_nulls = df.isna().sum()
    top_null_cols = [
        {"column": str(col), "missing_count": int(col_nulls[col]), "missing_pct": round((col_nulls[col] / total_rows) * 100, 1)}
        for col in col_nulls.nlargest(10).index
    ]

    return {
        "tool": "quality_report",
        "reference_period": "전체 데이터셋",
        "used_rows": total_rows,
        "excluded_rows": 0,
        "excluded_reason": "전체 행 대상 품질 검사",
        "used_columns": list(df.columns),
        "unit": "건 / 비율(%)",
        "cautions": [f"전체 데이터 결측률이 {null_ratio}%입니다. 과거 연도 데이터 누락에 주의하세요."] if null_ratio > 30 else [],
        "result": {
            "total_rows": total_rows,
            "null_ratio_pct": null_ratio,
            "duplicate_rows": duplicate_rows,
            "suspicious_columns": suspicious_cols,
            "top_missing_columns": top_null_cols
        }
    }


# -------------------------------------------------------------
# 3. year_coverage (연도별 값 개수와 권장 기준연도)
# -------------------------------------------------------------
def year_coverage(df, params=None):
    year_cols = [c for c in df.columns if str(c).strip().isdigit()]
    coverage_list = [
        {
            "year": str(y),
            "valid_count": int(df[y].notna().sum()),
            "coverage_pct": round((int(df[y].notna().sum()) / len(df)) * 100, 1)
        }
        for y in sorted(year_cols, key=lambda x: int(x))
    ]

    recommended = next((item["year"] for item in reversed(coverage_list) if item["coverage_pct"] >= 50.0), coverage_list[-1]["year"])

    return {
        "tool": "year_coverage",
        "reference_period": f"{coverage_list[0]['year']}~{coverage_list[-1]['year']}",
        "used_rows": len(df),
        "excluded_rows": 0,
        "excluded_reason": "전체 행 대상 연도별 충실도 검사",
        "used_columns": year_cols,
        "unit": "개수 / 충실도(%)",
        "cautions": [f"권장 기준연도는 {recommended}년입니다. 최신 연도는 보고 지연으로 결측치가 많을 수 있습니다."],
        "result": {
            "start_year": coverage_list[0]["year"],
            "end_year": coverage_list[-1]["year"],
            "recommended_year": recommended,
            "coverage": coverage_list
        }
    }


# -------------------------------------------------------------
# 4. detect_aggregates (집계 행 후보 탐지)
# -------------------------------------------------------------
def detect_aggregates(df, params=None):
    code_col = "Country Code" if "Country Code" in df.columns else None
    name_col = "Country Name" if "Country Name" in df.columns else None
    aggregates = []

    for idx, row in df.iterrows():
        is_agg = False
        reasons = []
        if code_col and str(row[code_col]).strip() in KNOWN_AGGREGATE_CODES:
            is_agg = True
            reasons.append("World Bank 지역/소득군 코드")
        if name_col:
            matched_kws = [kw for kw in AGGREGATE_KEYWORDS if kw in str(row[name_col]).lower()]
            if matched_kws:
                is_agg = True
                reasons.append(f"키워드 감지: {matched_kws}")
        if is_agg:
            aggregates.append({
                "row_index": int(idx),
                "code": str(row[code_col]) if code_col else None,
                "name": str(row[name_col]) if name_col else f"Row {idx}",
                "reason": ", ".join(reasons)
            })

    return {
        "tool": "detect_aggregates",
        "reference_period": "전체 데이터셋",
        "used_rows": len(df),
        "excluded_rows": 0,
        "excluded_reason": "전체 행 대상 집계 후보 탐지",
        "used_columns": [c for c in [code_col, name_col] if c],
        "unit": "개수(건)",
        "cautions": ["국가 순위나 분포 분석 시 집계 행을 반드시 제외해야 통계 왜곡(이중 계산)을 방지할 수 있습니다."],
        "result": {
            "total_rows": len(df),
            "aggregate_count": len(aggregates),
            "individual_country_count": len(df) - len(aggregates),
            "aggregates": aggregates
        }
    }


# -------------------------------------------------------------
# 5. describe_numeric (개수·평균·중앙값·최소·최대·표준편차)
# -------------------------------------------------------------
def describe_numeric(df, params=None):
    params = params or {}
    year_cols = [c for c in df.columns if str(c).strip().isdigit()]
    col = str(params.get("column") or params.get("reference_period") or (year_cols[-2] if len(year_cols) >= 2 else year_cols[-1]))

    exclude_agg = params.get("exclude_aggregates", True)
    clean_df, excluded_cnt, excluded_reason = filter_aggregates_and_nulls(df, col, exclude_aggregates=exclude_agg)
    series = clean_df[col]

    return {
        "tool": "describe_numeric",
        "reference_period": col,
        "used_rows": len(series),
        "excluded_rows": excluded_cnt,
        "excluded_reason": excluded_reason,
        "used_columns": [col],
        "unit": "수치 단위 (예: %)",
        "cautions": ["통계 왜곡 방지를 위해 지역 및 소득군 집계 행을 제외한 개별 국가 기준 통계입니다."],
        "result": clean_for_json({
            "column": col,
            "count": len(series),
            "mean": float(series.mean()),
            "median": float(series.median()),
            "std": float(series.std()),
            "min": float(series.min()),
            "max": float(series.max()),
            "q25": float(series.quantile(0.25)),
            "q75": float(series.quantile(0.75))
        })
    }


# -------------------------------------------------------------
# 6. trend_line (선택 항목들의 연도별 추이 - 선 차트)
# -------------------------------------------------------------
def trend_line(df, params=None):
    params = params or {}
    name_col = "Country Name" if "Country Name" in df.columns else df.columns[0]
    year_cols = [c for c in df.columns if str(c).strip().isdigit()]
    entities = params.get("entities") or ["Korea, Rep.", "United States", "World"]
    sub_df = df[df[name_col].isin(entities)].copy()

    start_year = str(params.get("start_year") or "1990")
    end_year = str(params.get("end_year") or year_cols[-1])
    target_years = [y for y in year_cols if int(start_year) <= int(y) <= int(end_year)]

    datasets = [
        {
            "label": str(r[name_col]),
            "data": [clean_for_json(pd.to_numeric(r.get(y), errors="coerce")) for y in target_years]
        }
        for _, r in sub_df.iterrows()
    ]

    return {
        "tool": "trend_line",
        "reference_period": f"{target_years[0]}~{target_years[-1]}",
        "used_rows": len(sub_df),
        "excluded_rows": len(df) - len(sub_df),
        "excluded_reason": "선택된 대상 항목 이외의 행 제외",
        "used_columns": [name_col] + target_years,
        "unit": "연도별 지표 값",
        "cautions": ["결측치(null)인 연도는 차트 상에서 공백으로 연결될 수 있습니다."],
        "result": {
            "chart_type": "line",
            "labels": target_years,
            "datasets": datasets
        }
    }


# -------------------------------------------------------------
# 7. top_bottom_n (기준연도 기준 상위·하위 N - 수평 막대)
# -------------------------------------------------------------
def top_bottom_n(df, params=None):
    params = params or {}
    ref_period = params.get("reference_period")
    if not ref_period:
        raise ValueError("7번 도구(top_bottom_n)는 기준 시점(reference_period)이 필수 파라미터입니다.")

    ref_period = str(ref_period).strip()
    n = int(params.get("n", 10))
    name_col = params.get("label_column") or "Country Name"
    exclude_agg = params.get("exclude_aggregates", True)

    clean_df, excluded_cnt, excluded_reason = filter_aggregates_and_nulls(
        df, ref_period, exclude_aggregates=exclude_agg
    )
    sorted_df = clean_df.sort_values(by=ref_period, ascending=False)

    return {
        "tool": "top_bottom_n",
        "reference_period": ref_period,
        "used_rows": len(clean_df),
        "excluded_rows": excluded_cnt,
        "excluded_reason": excluded_reason,
        "used_columns": [name_col, ref_period],
        "unit": "지표 값",
        "cautions": [
            f"기준 시점은 {ref_period}년입니다. 해당 시점에 값이 없는 국가는 순위 집계에서 제외되었습니다."
        ],
        "result": {
            "chart_type": "horizontalBar",
            "top_n": [
                {"label": str(r[name_col]), "value": clean_for_json(float(r[ref_period]))}
                for _, r in sorted_df.head(n).iterrows()
            ],
            "bottom_n": [
                {"label": str(r[name_col]), "value": clean_for_json(float(r[ref_period]))}
                for _, r in sorted_df.tail(n).iloc[::-1].iterrows()
            ]
        }
    }


# -------------------------------------------------------------
# 8. group_summary (그룹별 평균·합계·개수 - 막대)
# -------------------------------------------------------------
def group_summary(df, params=None):
    params = params or {}
    ref_period = params.get("reference_period")
    if not ref_period:
        raise ValueError("8번 도구(group_summary)는 기준 시점(reference_period)이 필수 파라미터입니다.")

    ref_period = str(ref_period).strip()
    group_col = params.get("group_column", "Region")
    exclude_agg = params.get("exclude_aggregates", True)

    working_df = df.copy()
    if group_col not in working_df.columns and "Country Code" in working_df.columns:
        meta_candidates = glob.glob("data/Metadata_Country*.csv")
        if meta_candidates:
            df_meta = pd.read_csv(meta_candidates[0])
            working_df = pd.merge(working_df, df_meta[["Country Code", group_col]], on="Country Code", how="left")

    clean_df, excluded_cnt, excluded_reason = filter_aggregates_and_nulls(
        working_df, ref_period, exclude_aggregates=exclude_agg
    )
    final_df = clean_df[clean_df[group_col].notna() & (clean_df[group_col].astype(str).str.strip() != "")]
    grouped = final_df.groupby(group_col)[ref_period].agg(["mean", "median", "count"]).reset_index().sort_values(by="mean", ascending=False)

    return {
        "tool": "group_summary",
        "reference_period": ref_period,
        "used_rows": len(final_df),
        "excluded_rows": excluded_cnt + (len(clean_df) - len(final_df)),
        "excluded_reason": excluded_reason,
        "used_columns": [group_col, ref_period],
        "unit": "그룹별 평균 지표 값",
        "cautions": [
            f"기준 시점은 {ref_period}년입니다. 국가별 단순 평균치이며 인구 가중 평균이 아닙니다."
        ],
        "result": {
            "chart_type": "bar",
            "labels": grouped[group_col].tolist(),
            "datasets": [{
                "label": f"{group_col}별 평균 ({ref_period})",
                "data": [clean_for_json(float(v)) for v in grouped["mean"]]
            }]
        }
    }


# -------------------------------------------------------------
# 9. change_rate (두 시점 사이 변화량·변화율 - 막대)
# -------------------------------------------------------------
def change_rate(df, params=None):
    """기준 시점 필수! 두 시점 사이의 증가량(포인트 차이) 및 변화율(%)을 계산합니다."""
    params = params or {}
    ref_period = params.get("reference_period")
    if not ref_period:
        raise ValueError("9번 도구(change_rate)는 기준 시점(reference_period)이 필수 파라미터입니다.")

    ref_period = str(ref_period).strip()
    year_cols = [c for c in df.columns if str(c).strip().isdigit()]

    # 비교 기준 연도 (기본값: 10년 전 또는 가능한 이전 연도)
    base_period = str(params.get("base_period") or (str(int(ref_period) - 10) if str(int(ref_period) - 10) in year_cols else year_cols[0]))
    if base_period not in df.columns or ref_period not in df.columns:
        raise ValueError(f"시점 '{base_period}' 또는 '{ref_period}'이(가) 데이터셋 열에 없습니다.")

    name_col = params.get("label_column") or "Country Name"
    exclude_agg = params.get("exclude_aggregates", True)
    n = int(params.get("n", 10))

    clean_df, excluded_cnt, excluded_reason = filter_aggregates_and_nulls(
        df, [base_period, ref_period], exclude_aggregates=exclude_agg
    )

    clean_df["diff"] = clean_df[ref_period] - clean_df[base_period]
    # base가 0인 경우 대비 0 나누기 처리
    clean_df["pct_change"] = np.where(clean_df[base_period] > 0, (clean_df["diff"] / clean_df[base_period]) * 100, np.nan)

    # 변화량 기준 상위 N개국
    sorted_df = clean_df.sort_values(by="diff", ascending=False)
    top_diff = sorted_df.head(n)

    labels = top_diff[name_col].astype(str).tolist()
    diffs = [clean_for_json(float(v)) for v in top_diff["diff"]]

    return {
        "tool": "change_rate",
        "reference_period": f"{base_period} vs {ref_period}",
        "used_rows": len(clean_df),
        "excluded_rows": excluded_cnt,
        "excluded_reason": excluded_reason,
        "used_columns": [name_col, base_period, ref_period],
        "unit": "포인트 증가량 (%p)",
        "cautions": [
            f"비교 기간: {base_period}년 대비 {ref_period}년입니다. 두 시점 모두 데이터가 있는 항목만 계산되었습니다."
        ],
        "result": {
            "chart_type": "bar",
            "base_period": base_period,
            "reference_period": ref_period,
            "labels": labels,
            "datasets": [{
                "label": f"증가폭 ({base_period}→{ref_period})",
                "data": diffs
            }],
            "top_increasers": [
                {
                    "country": str(r[name_col]),
                    "base_value": clean_for_json(float(r[base_period])),
                    "ref_value": clean_for_json(float(r[ref_period])),
                    "diff": clean_for_json(float(r["diff"])),
                    "pct_change": clean_for_json(float(r["pct_change"])) if pd.notna(r["pct_change"]) else None
                }
                for _, r in top_diff.iterrows()
            ]
        }
    }


# -------------------------------------------------------------
# 10. distribution (구간별 분포 - 히스토그램)
# -------------------------------------------------------------
def distribution(df, params=None):
    """기준 시점 필수! 지정된 기준연도 값들의 구간별 빈도(히스토그램)를 산출합니다."""
    params = params or {}
    ref_period = params.get("reference_period")
    if not ref_period:
        raise ValueError("10번 도구(distribution)는 기준 시점(reference_period)이 필수 파라미터입니다.")

    ref_period = str(ref_period).strip()
    if ref_period not in df.columns:
        raise ValueError(f"기준 시점 '{ref_period}'이(가) 데이터셋 열에 없습니다.")

    bins_count = int(params.get("bins", 10))
    exclude_agg = params.get("exclude_aggregates", True)

    clean_df, excluded_cnt, excluded_reason = filter_aggregates_and_nulls(
        df, ref_period, exclude_aggregates=exclude_agg
    )
    series = clean_df[ref_period]

    counts, bin_edges = np.histogram(series, bins=bins_count)
    labels = [f"{round(bin_edges[i], 1)}~{round(bin_edges[i+1], 1)}" for i in range(len(counts))]

    histogram_data = [
        {
            "bin": labels[i],
            "count": int(counts[i]),
            "pct": round((int(counts[i]) / len(series)) * 100, 1)
        }
        for i in range(len(counts))
    ]

    return {
        "tool": "distribution",
        "reference_period": ref_period,
        "used_rows": len(series),
        "excluded_rows": excluded_cnt,
        "excluded_reason": excluded_reason,
        "used_columns": [ref_period],
        "unit": "빈도수(개국) / 비율(%)",
        "cautions": [
            f"기준 시점은 {ref_period}년입니다. 총 {len(series)}개 유효 국가 데이터를 {bins_count}개 구간으로 분류했습니다."
        ],
        "result": {
            "chart_type": "bar",
            "labels": labels,
            "datasets": [{
                "label": f"국가 수 분포 ({ref_period})",
                "data": [int(c) for c in counts]
            }],
            "table": histogram_data
        }
    }


# -------------------------------------------------------------
# 11. correlation_scatter (두 숫자 열 상관계수 - 산점도)
# -------------------------------------------------------------
def correlation_scatter(df, params=None):
    """기준 시점 필수! 두 시점(또는 열) 간의 피어슨 상관계수와 산점도 데이터를 산출합니다."""
    params = params or {}
    ref_period = params.get("reference_period")
    if not ref_period:
        raise ValueError("11번 도구(correlation_scatter)는 기준 시점(reference_period)이 필수 파라미터입니다.")

    ref_period = str(ref_period).strip()
    year_cols = [c for c in df.columns if str(c).strip().isdigit()]
    compare_period = str(params.get("compare_period") or (str(int(ref_period) - 10) if str(int(ref_period) - 10) in year_cols else year_cols[0]))

    if ref_period not in df.columns or compare_period not in df.columns:
        raise ValueError(f"열 '{ref_period}' 또는 '{compare_period}'이(가) 데이터셋에 없습니다.")

    name_col = params.get("label_column") or "Country Name"
    exclude_agg = params.get("exclude_aggregates", True)

    clean_df, excluded_cnt, excluded_reason = filter_aggregates_and_nulls(
        df, [compare_period, ref_period], exclude_aggregates=exclude_agg
    )

    corr_coef = float(clean_df[compare_period].corr(clean_df[ref_period]))

    scatter_points = [
        {
            "x": clean_for_json(float(r[compare_period])),
            "y": clean_for_json(float(r[ref_period])),
            "label": str(r[name_col])
        }
        for _, r in clean_df.iterrows()
    ]

    return {
        "tool": "correlation_scatter",
        "reference_period": f"{compare_period} vs {ref_period}",
        "used_rows": len(clean_df),
        "excluded_rows": excluded_cnt,
        "excluded_reason": excluded_reason,
        "used_columns": [name_col, compare_period, ref_period],
        "unit": "상관계수 (-1.0 ~ +1.0)",
        "cautions": [
            "⚠️ 상관관계는 인과관계가 아닙니다.",
            f"피어슨 상관계수 r = {round(corr_coef, 4)}입니다. 두 변수 간의 통계적 상관성만 나타냅니다."
        ],
        "result": {
            "chart_type": "scatter",
            "x_label": compare_period,
            "y_label": ref_period,
            "correlation_coefficient": round(corr_coef, 4),
            "points": scatter_points
        }
    }


# -------------------------------------------------------------
# 12. compare_one_vs_all (특정 항목 vs 전체 평균·중앙값 - 강조 막대)
# -------------------------------------------------------------
def compare_one_vs_all(df, params=None):
    """기준 시점 필수! 특정 국가의 지표값을 전체 국가의 평균 및 중앙값과 직관적으로 비교합니다."""
    params = params or {}
    ref_period = params.get("reference_period")
    if not ref_period:
        raise ValueError("12번 도구(compare_one_vs_all)는 기준 시점(reference_period)이 필수 파라미터입니다.")

    ref_period = str(ref_period).strip()
    if ref_period not in df.columns:
        raise ValueError(f"기준 시점 '{ref_period}'이(가) 데이터셋 열에 없습니다.")

    name_col = params.get("label_column") or "Country Name"
    target_entity = params.get("target_entity") or "Korea, Rep."
    exclude_agg = params.get("exclude_aggregates", True)

    clean_df, excluded_cnt, excluded_reason = filter_aggregates_and_nulls(
        df, ref_period, exclude_aggregates=exclude_agg
    )

    # 타겟 항목 조회
    matched = clean_df[clean_df[name_col].astype(str).str.lower() == target_entity.lower()]
    if len(matched) == 0:
        # 혹시 원본(집계행 등)에 있는지 확인
        matched = df[df[name_col].astype(str).str.lower() == target_entity.lower()]
        if len(matched) == 0:
            target_entity = clean_df[name_col].iloc[0]
            matched = clean_df.iloc[[0]]

    target_val = float(pd.to_numeric(matched[ref_period].values[0]))
    actual_name = str(matched[name_col].values[0])

    mean_val = float(clean_df[ref_period].mean())
    median_val = float(clean_df[ref_period].median())

    # 백분위수 순위 계산 (낮은 값부터의 백분위수)
    percentile_rank = round(float((clean_df[ref_period] <= target_val).mean()) * 100, 1)
    rank = int((clean_df[ref_period] > target_val).sum()) + 1

    return {
        "tool": "compare_one_vs_all",
        "reference_period": ref_period,
        "used_rows": len(clean_df),
        "excluded_rows": excluded_cnt,
        "excluded_reason": excluded_reason,
        "used_columns": [name_col, ref_period],
        "unit": "지표 값 (예: %)",
        "cautions": [
            f"비교 대상: {actual_name} ({ref_period}년)",
            "전체 국가(집계 행 제외) 대비 상대적 위치를 분석한 결과입니다."
        ],
        "result": {
            "chart_type": "bar",
            "target_entity": actual_name,
            "target_value": round(target_val, 2),
            "all_mean": round(mean_val, 2),
            "all_median": round(median_val, 2),
            "rank": rank,
            "total_count": len(clean_df),
            "percentile": percentile_rank,
            "labels": [actual_name, "전체 평균 (Mean)", "전체 중앙값 (Median)"],
            "datasets": [{
                "label": f"{ref_period}년 지표 비교",
                "data": [round(target_val, 2), round(mean_val, 2), round(median_val, 2)]
            }]
        }
    }


# -------------------------------------------------------------
# 도구 전체 레지스트리 (Tools 1~12)
# -------------------------------------------------------------
TOOL_REGISTRY = {
    "reshape_wide_to_long": reshape_wide_to_long,
    "quality_report": quality_report,
    "year_coverage": year_coverage,
    "detect_aggregates": detect_aggregates,
    "describe_numeric": describe_numeric,
    "trend_line": trend_line,
    "top_bottom_n": top_bottom_n,
    "group_summary": group_summary,
    "change_rate": change_rate,
    "distribution": distribution,
    "correlation_scatter": correlation_scatter,
    "compare_one_vs_all": compare_one_vs_all,
}
