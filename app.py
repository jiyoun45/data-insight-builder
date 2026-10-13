import csv
import io
import json
import os
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from google import genai
from google.genai import types
import pandas as pd
import tools

load_dotenv()

app = Flask(__name__)

# 업로드 최대 용량 설정 (기본값 10MB)
max_mb = int(os.getenv("MAX_UPLOAD_MB", 10))
app.config["MAX_CONTENT_LENGTH"] = max_mb * 1024 * 1024

# 인메모리 단일 데이터셋 및 최근 분석 결과 관리 (디스크 영구 저장 안 함)
CURRENT_DATASET = None
CURRENT_FILENAME = None
LAST_RUN_RESULT = None

# Gemini 클라이언트 초기화
gemini_api_key = os.getenv("GEMINI_API_KEY")
gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
gemini_client = genai.Client(api_key=gemini_api_key) if gemini_api_key else None

# World Bank의 표준 집계(지역·소득군) 코드 목록
KNOWN_AGGREGATE_CODES = {
    "AFE", "AFW", "ARB", "CEB", "CSS", "EAP", "EAR", "EAS", "ECA", "ECS",
    "EMU", "EUU", "FCS", "HIC", "HPC", "IBD", "IBT", "IDA", "IDB", "IDX",
    "INX", "LAC", "LCN", "LDC", "LIC", "LMC", "LMY", "MEA", "MIC", "MNA",
    "NAC", "OED", "OSS", "PRE", "PSS", "PST", "SAS", "SSA", "SSF", "SST",
    "TEA", "TEC", "TLA", "TMN", "TSA", "TSS", "UMC", "WLD"
}

# 도구 카탈로그 12개 메타데이터 요약 (Gemini 안내용)
TOOL_CATALOG_SUMMARY = [
    {"name": "reshape_wide_to_long", "desc": "연도 열을 행으로 접기(Unpivot)", "required_params": []},
    {"name": "quality_report", "desc": "결측치·중복·타입 진단 리포트", "required_params": []},
    {"name": "year_coverage", "desc": "연도별 충실도와 권장 기준연도 탐색", "required_params": []},
    {"name": "detect_aggregates", "desc": "World, 소득군 등 집계 행 감지", "required_params": []},
    {"name": "describe_numeric", "desc": "개수·평균·중앙값·최소·최대·표준편차 기술통계", "required_params": ["reference_period"]},
    {"name": "trend_line", "desc": "주요 국가들의 연도별 시계열 추이 (선 차트)", "required_params": ["entities"]},
    {"name": "top_bottom_n", "desc": "기준연도 기준 상위·하위 N개 국가 (수평 막대)", "required_params": ["reference_period", "n"]},
    {"name": "group_summary", "desc": "대륙(Region) 또는 소득군별 평균 비교 (막대)", "required_params": ["reference_period", "group_column"]},
    {"name": "change_rate", "desc": "두 시점 사이 증가폭·변화율 (막대)", "required_params": ["reference_period", "base_period"]},
    {"name": "distribution", "desc": "기준연도 값들의 구간별 빈도 분포 (히스토그램)", "required_params": ["reference_period", "bins"]},
    {"name": "correlation_scatter", "desc": "두 시점 간 피어슨 상관계수 (산점도)", "required_params": ["reference_period", "compare_period"]},
    {"name": "compare_one_vs_all", "desc": "특정 국가 vs 전체 평균·중앙값 및 순위 (강조 막대)", "required_params": ["reference_period", "target_entity"]}
]


def detect_encoding_and_read(file_bytes):
    """여러 인코딩을 순차적으로 시도하여 텍스트를 디코딩합니다."""
    encodings = ["utf-8-sig", "utf-8", "cp949", "euc-kr", "latin1"]
    for enc in encodings:
        try:
            text = file_bytes.decode(enc)
            return text, enc
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError("지원하는 인코딩으로 파일을 읽을 수 없습니다.")


def detect_header_row(text, max_rows_to_check=20):
    """
    World Bank 등의 CSV는 상단에 메타데이터 행이 존재할 수 있으므로,
    상위 행들을 검사하여 컬럼 수가 가장 많은 행을 실제 헤더 위치로 자동 감지합니다.
    """
    reader = csv.reader(io.StringIO(text))
    lines = [row for _, row in zip(range(max_rows_to_check), reader)]

    max_cols = 0
    header_idx = 0
    for i, row in enumerate(lines):
        non_empty = [c for c in row if c.strip()]
        if len(non_empty) > max_cols:
            max_cols = len(non_empty)
            header_idx = i

    return header_idx


def analyze_dataset(df):
    """
    데이터 품질, 연도별 데이터 충실도(Coverage),
    World Bank 집계 행 감지 및 상위 5개 행 미리보기 추출
    """
    total_rows = len(df)
    total_cells = int(df.size)
    null_cells = int(df.isna().sum().sum())
    null_ratio = round((null_cells / total_cells) * 100, 2) if total_cells > 0 else 0.0

    # 1. 연도 컬럼 식별 및 연도별 충실도(Coverage) 분석
    year_cols = [c for c in df.columns if str(c).strip().isdigit()]
    year_coverage = {}
    for y in year_cols:
        non_null_cnt = int(df[y].notna().sum())
        cov_pct = round((non_null_cnt / total_rows) * 100, 1) if total_rows > 0 else 0.0
        year_coverage[str(y)] = {
            "valid_count": non_null_cnt,
            "coverage_pct": cov_pct
        }

    # 최근 연도 중 충실도가 50% 이상인 최신 기준 추천 연도 감지
    recommended_year = None
    for y in sorted(year_cols, key=lambda x: int(x), reverse=True):
        if year_coverage[str(y)]["coverage_pct"] >= 50.0:
            recommended_year = str(y)
            break
    if not recommended_year and year_cols:
        recommended_year = str(year_cols[-1])

    # 2. 집계 행(Region, Income group 등) 감지
    aggregate_rows = []
    if "Country Code" in df.columns:
        matched_agg = df[df["Country Code"].isin(KNOWN_AGGREGATE_CODES)]
        for _, row in matched_agg.iterrows():
            code = str(row["Country Code"])
            name = str(row["Country Name"]) if "Country Name" in df.columns else code
            aggregate_rows.append({"code": code, "name": name})

    individual_count = total_rows - len(aggregate_rows)

    # 3. 상위 5개 행 미리보기
    preview_df = df.head(5).copy()
    preview = json.loads(preview_df.to_json(orient="records"))

    return {
        "quality": {
            "total_cells": total_cells,
            "null_cells": null_cells,
            "null_percentage": null_ratio
        },
        "year_analysis": {
            "year_columns_count": len(year_cols),
            "start_year": year_cols[0] if year_cols else None,
            "end_year": year_cols[-1] if year_cols else None,
            "recommended_year": recommended_year,
            "coverage_sample": {
                y: year_coverage[y]
                for y in sorted(year_cols, key=lambda x: int(x), reverse=True)[:10]
            }
        },
        "aggregates": {
            "aggregate_row_count": len(aggregate_rows),
            "individual_country_count": individual_count,
            "detected_aggregates": aggregate_rows[:10]
        },
        "preview": preview
    }


@app.route("/", methods=["GET"])
def index():
    """메인 HTML 대시보드 페이지 렌더링"""
    return render_template("index.html")


@app.route("/health", methods=["GET"])
def health_check():
    """서버 상태 및 API 키 설정 여부 반환 (키 원문 노출 금지)"""
    return jsonify({
        "status": "ok",
        "gemini_api_configured": bool(gemini_api_key),
        "gemini_model": gemini_model,
        "has_dataset_loaded": CURRENT_DATASET is not None
    })


@app.route("/inspect", methods=["POST"])
def inspect_file():
    """
    POST /inspect
    - 파일 수신 및 인코딩 순차 시도
    - 헤더 행 자동 감지
    - 인메모리에 1개 데이터셋 보관
    - 품질 검사, 연도별 충실도, 집계 행 감지, 미리보기 반환
    """
    global CURRENT_DATASET, CURRENT_FILENAME
    if "file" not in request.files:
        return jsonify({"error": "업로드할 파일('file')이 요청에 없습니다."}), 400

    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"error": "선택된 파일이 없습니다."}), 400

    file_bytes = file.read()
    if not file_bytes:
        return jsonify({"error": "업로드된 파일이 비어 있습니다."}), 400

    try:
        decoded_text, used_encoding = detect_encoding_and_read(file_bytes)
        header_idx = detect_header_row(decoded_text)

        # 헤더 행을 건너뛰고 DataFrame 생성
        df = pd.read_csv(io.StringIO(decoded_text), skiprows=header_idx)

        # 끝부분의 완전히 비어있는 Unnamed 열 정리
        df = df.loc[:, ~df.columns.str.contains(r"^Unnamed: \d+$", na=False) | df.notna().any()]

        # 인메모리에 데이터셋 적재
        CURRENT_DATASET = df
        CURRENT_FILENAME = file.filename

        columns_list = [str(c).strip() for c in df.columns]
        analysis_result = analyze_dataset(df)

        response_data = {
            "success": True,
            "filename": file.filename,
            "encoding": used_encoding,
            "header_row_index": header_idx,
            "row_count": len(df),
            "column_count": len(columns_list),
            "columns": columns_list,
            **analysis_result
        }

        return jsonify(response_data)

    except Exception as e:
        return jsonify({"error": f"파일 분석 중 오류가 발생했습니다: {str(e)}"}), 500


@app.route("/suggest", methods=["POST"])
def suggest_analyses():
    """
    POST /suggest (Step 17)
    - 진단 결과 요약을 Gemini에 전달
    - 도구 카탈로그(12개) 중에서만 분석 제안을 선택하도록 제한
    - 3~5개의 유의미한 분석 제안을 JSON 형식으로 반환
    """
    if not gemini_client:
        return jsonify({"error": "GEMINI_API_KEY가 서버에 설정되어 있지 않습니다."}), 500

    inspect_data = request.get_json()
    if not inspect_data:
        return jsonify({"error": "진단 결과(JSON) 데이터가 필요합니다."}), 400

    summary_for_ai = {
        "filename": inspect_data.get("filename", CURRENT_FILENAME or "dataset.csv"),
        "row_count": inspect_data.get("row_count"),
        "column_count": inspect_data.get("column_count"),
        "recommended_year": inspect_data.get("year_analysis", {}).get("recommended_year") or inspect_data.get("recommended_year", "2024"),
        "start_year": inspect_data.get("year_analysis", {}).get("start_year"),
        "end_year": inspect_data.get("year_analysis", {}).get("end_year"),
        "null_percentage": inspect_data.get("quality", {}).get("null_percentage"),
        "aggregate_row_count": inspect_data.get("aggregates", {}).get("aggregate_row_count", 0),
        "sample_columns": inspect_data.get("columns", [])[:10]
    }

    allowed_tool_names = list(tools.TOOL_REGISTRY.keys())

    prompt = f"""당신은 전문 데이터 분석가이자 통계 컨설턴트입니다.
업로드된 데이터셋의 진단 결과와 12개 도구 카탈로그를 확인하고, 이 데이터에서 가장 통찰력 있는 분석 3~5개를 선택해 제안해주세요.

[데이터셋 진단 결과 요약]
{json.dumps(summary_for_ai, ensure_ascii=False, indent=2)}

[도구 카탈로그 (오직 이 12개 도구만 제안할 수 있습니다)]
{json.dumps(TOOL_CATALOG_SUMMARY, ensure_ascii=False, indent=2)}

[엄격한 제약 규칙]
1. 제안할 도구(`tool`)는 반드시 위 카탈로그에 명시된 12개 이름 중 하나여야 합니다:
   {json.dumps(allowed_tool_names)}
2. 데이터셋에 존재하지 않는 도구나 열은 절대 제안하지 마십시오.
3. 7~12번 도구는 reference_period(기준시점)가 필수입니다. 권장 기준연도('{summary_for_ai["recommended_year"]}')를 적극 활용하십시오.
4. 총 3개에서 5개의 제안을 생성하십시오.
5. 반드시 아래 JSON 형식으로만 응답해야 합니다 (마크다운 백틱 없이 순수 JSON).

{{
  "suggestions": [
    {{
      "tool": "카탈로그에 있는 도구명",
      "params": {{
        "reference_period": "{summary_for_ai['recommended_year']}",
        "exclude_aggregates": true
      }},
      "reference_period": "{summary_for_ai['recommended_year']}",
      "why": "이 분석이 이 데이터에서 의미 있는 이유 (중학생도 이해하기 쉽게)",
      "caution": "분석 결과를 해석할 때 주의할 점"
    }}
  ]
}}
"""

    try:
        response = gemini_client.models.generate_content(
            model=gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        res_json = json.loads(response.text)
        raw_suggestions = res_json.get("suggestions", [])

        valid_suggestions = []
        for item in raw_suggestions:
            tool_name = item.get("tool")
            if tool_name in tools.TOOL_REGISTRY:
                if "params" not in item:
                    item["params"] = {}
                if tool_name in ["describe_numeric", "top_bottom_n", "group_summary", "change_rate", "distribution", "correlation_scatter", "compare_one_vs_all"]:
                    if not item["params"].get("reference_period"):
                        item["params"]["reference_period"] = summary_for_ai["recommended_year"]
                    if not item.get("reference_period"):
                        item["reference_period"] = summary_for_ai["recommended_year"]
                valid_suggestions.append(item)

        return jsonify({
            "success": True,
            "count": len(valid_suggestions),
            "suggestions": valid_suggestions
        })

    except Exception as e:
        return jsonify({"error": f"Gemini 분석 제안 생성 중 오류가 발생했습니다: {str(e)}"}), 500


@app.route("/run", methods=["POST"])
def run_tool():
    """
    POST /run (Step 18)
    - 선택된 도구를 인메모리 데이터셋에 대해 Pandas로 실행
    - 기준 시점 검증, 사용 행 수 및 제외 행 수/사유 반환
    - 계산 결과 및 차트 데이터 JSON 반환
    """
    global LAST_RUN_RESULT
    if CURRENT_DATASET is None:
        return jsonify({"error": "분석할 데이터셋이 메모리에 없습니다. 먼저 CSV 파일을 업로드(/inspect)해주세요."}), 400

    data = request.get_json() or {}
    tool_name = data.get("tool")
    params = data.get("params", {})

    if not tool_name or tool_name not in tools.TOOL_REGISTRY:
        return jsonify({
            "error": f"유효하지 않은 도구입니다: '{tool_name}'. 등록된 도구: {list(tools.TOOL_REGISTRY.keys())}"
        }), 400

    try:
        tool_func = tools.TOOL_REGISTRY[tool_name]
        output = tool_func(CURRENT_DATASET, params)

        # Step 19의 /explain 모드 B에서 사용할 수 있도록 최근 분석 결과 보관
        LAST_RUN_RESULT = output

        return jsonify({
            "success": True,
            **output
        })

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"도구 실행 중 오류가 발생했습니다: {str(e)}"}), 500


@app.route("/explain", methods=["POST"])
def explain_analysis():
    """
    POST /explain (Step 19)
    - 모드 A (비교용, 의도적으로 허술하게): 진단 요약만 전달하고 일반 보고서 요청
    - 모드 B (정식, 8대 엄격 규칙): Pandas 계산 결과(표, 기준시점, 제외 행 수)만 전달하고 7개 마크다운 섹션으로 정확한 해석 생성
    """
    if not gemini_client:
        return jsonify({"error": "GEMINI_API_KEY가 서버에 설정되어 있지 않습니다."}), 500

    req_data = request.get_json() or {}
    mode = str(req_data.get("mode", "B")).upper()

    # 최근 계산 결과 또는 요청 body에 동봉된 계산 결과
    run_result = req_data.get("run_result") or LAST_RUN_RESULT

    if mode == "A":
        # 모드 A (비교용, 허술함): Pandas 계산 결과를 전혀 주지 않고 진단 요약만 전달
        summary_text = f"파일명: {CURRENT_FILENAME or 'data.csv'}, 데이터셋 행 수: {len(CURRENT_DATASET) if CURRENT_DATASET is not None else '알 수 없음'}"
        prompt = f"""이 데이터를 분석해서 보고서를 써줘.
{summary_text}
"""
    else:
        # 모드 B (정식): Pandas 계산 결과만 엄격한 8대 규칙과 7대 제목으로 분석
        if not run_result:
            return jsonify({"error": "해석할 도구 계산 결과가 없습니다. 먼저 도구를 실행(/run)해주세요."}), 400

        indicator_name = "인터넷 보급률 (% of population)"
        if CURRENT_DATASET is not None and "Indicator Name" in CURRENT_DATASET:
            valid_inds = CURRENT_DATASET["Indicator Name"].dropna()
            if len(valid_inds) > 0:
                indicator_name = str(valid_inds.iloc[0])

        prompt = f"""당신은 정밀한 데이터 사이언티스트이자 통계 해설가입니다.
아래 제공된 [Pandas 계산 결과]만을 바탕으로 정직하고 명확한 해석 보고서를 작성해주세요.

[엄격한 작성 규칙 - 반드시 준수]
1. 제공된 계산 결과에 있는 숫자만 사용한다.
2. 직접 계산하거나 추정하지 않는다.
3. 데이터에 없는 국가·연도·열을 언급하지 않는다.
4. 기준 시점과 제외된 행 수, 사유를 반드시 본문에 명시한다.
5. 상관관계를 인과관계로 표현하지 않는다.
6. 지표의 정의(지표명: {indicator_name})와 출처(World Bank World Development Indicators)를 보고서 앞부분에 표기한다.
7. 확인할 수 없는 것은 "이 데이터로는 확인할 수 없다"라고 쓴다.
8. 중학생도 이해할 수 있게 쓰되 정확성을 희생하지 않는다.

[출력 형식 - 아래 마크다운 제목 7개를 반드시 그대로 사용할 것]
## 무엇을 봤는가
## 데이터 출처와 정의
## 기준 시점과 제외된 항목
## 계산 결과
## 읽어낼 수 있는 것
## 이 데이터로는 알 수 없는 것
## 다음에 확인해볼 것

[Pandas 계산 결과]
{json.dumps(run_result, ensure_ascii=False, indent=2)}
"""

    try:
        response = gemini_client.models.generate_content(
            model=gemini_model,
            contents=prompt
        )

        return jsonify({
            "success": True,
            "mode": mode,
            "explanation": response.text.strip()
        })
    except Exception as e:
        return jsonify({"error": f"Gemini 해석 생성 중 오류가 발생했습니다: {str(e)}"}), 500


@app.route("/chat", methods=["POST"])
def follow_up_chat():
    """
    POST /chat
    - 최종 분석 리포트 및 계산 결과를 바탕으로 사용자의 후속 질문에 실시간 답변
    - '중학생도 이해할 수 있게 쉽게 설명해줘' 등 다양한 맞춤형 질문 지원
    """
    if not gemini_client:
        return jsonify({"error": "GEMINI_API_KEY가 서버에 설정되어 있지 않습니다."}), 500

    req_data = request.get_json() or {}
    user_message = req_data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "질문 내용이 없습니다."}), 400

    chat_history = req_data.get("chat_history", [])
    report_context = req_data.get("report_context", "")
    run_result = req_data.get("run_result") or LAST_RUN_RESULT

    system_instruction = f"""당신은 친절하고 전문적인 AI 데이터 멘토입니다.
사용자는 앞서 생성된 World Bank 데이터 분석 보고서와 Pandas 계산 결과를 보고 후속 질문을 하고 있습니다.

[이전 분석 보고서 내용]
{report_context}

[실제 Pandas 계산 결과]
{json.dumps(run_result, ensure_ascii=False, indent=2) if run_result else "계산 결과 없음"}

[답변 가이드라인]
1. 사용자가 '중학생도 이해할 수 있게 쉽게 설명해줘'라고 하거나 쉬운 설명을 요청하면, 전문 통계 용어를 일상적인 비유(학교, 친구, 100명 중 몇 명 등)로 풀어서 아주 쉽고 친근하게 설명하세요.
2. 사실에 기반하여 답변하되, 실제 데이터에 없는 내용은 함부로 지어내지 말고 "이 데이터셋에는 해당 정보가 없어 추정하기 어렵습니다"라고 솔직하게 안내하세요.
3. 상관관계와 인과관계를 절대 혼동하지 않도록 주의하세요.
4. 마크다운(볼드체, 목록 등)을 적절히 활용하여 가독성 높게 작성하세요.
"""

    conversation_prompt = f"{system_instruction}\n\n[대화 기록]\n"
    for msg in chat_history[-6:]:
        role = "사용자" if msg.get("role") == "user" else "AI 멘토"
        conversation_prompt += f"{role}: {msg.get('content')}\n"

    conversation_prompt += f"사용자: {user_message}\nAI 멘토:"

    try:
        response = gemini_client.models.generate_content(
            model=gemini_model,
            contents=conversation_prompt
        )
        return jsonify({
            "success": True,
            "answer": response.text.strip()
        })
    except Exception as e:
        return jsonify({"error": f"AI 답변 생성 중 오류가 발생했습니다: {str(e)}"}), 500


@app.route("/ask", methods=["POST"])
def natural_language_ask():
    """
    POST /ask
    - 자연어 질문을 받아 도구(tool) 및 파라미터를 자동 매핑
    - Pandas로 실제 계산을 수행하고 계산 결과 기반의 팩트 자연어 답변 작성
    - 사용자가 즉시 차트를 볼 수 있도록 run_result를 동봉하여 반환
    """
    global LAST_RUN_RESULT
    if CURRENT_DATASET is None:
        return jsonify({"error": "분석할 데이터셋이 메모리에 없습니다. 먼저 CSV 파일을 업로드해주세요."}), 400
    if not gemini_client:
        return jsonify({"error": "GEMINI_API_KEY가 서버에 설정되어 있지 않습니다."}), 500

    req_data = request.get_json() or {}
    query = req_data.get("query", "").strip()
    if not query:
        return jsonify({"error": "질문 내용을 입력해주세요."}), 400

    year_cols = [c for c in CURRENT_DATASET.columns if str(c).strip().isdigit()]
    rec_year = year_cols[-2] if len(year_cols) >= 2 else (year_cols[-1] if year_cols else "2024")
    available_tools = list(tools.TOOL_REGISTRY.keys())

    mapping_prompt = f"""사용자가 데이터셋에 대해 자연어로 다음과 같이 질문했습니다:
질문: "{query}"

사용 가능한 12개 도구 목록:
{json.dumps(available_tools, ensure_ascii=False)}

데이터셋 정보:
- 숫자 연도 열: {year_cols[-5:] if len(year_cols) >= 5 else year_cols}
- 추천 기준연도: {rec_year}
- 주요 식별 열: Country Name, Country Code

이 질문에 답하기 위해 가장 적합한 도구 1개와 파라미터를 선택하세요.
만약 특정 국가(예: '대한민국', '한국', '미국')를 비교하고자 한다면 highlight_entity에 영문 국가명('Korea, Rep.', 'United States' 등)을 기재하세요.

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "tool": "도구명 (위 12개 중 하나)",
  "params": {{
    "reference_period": "{rec_year}",
    "n": 10,
    "exclude_aggregates": true
  }},
  "highlight_entity": "Korea, Rep."
}}
"""

    try:
        map_resp = gemini_client.models.generate_content(
            model=gemini_model,
            contents=mapping_prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        mapping_data = json.loads(map_resp.text)
        selected_tool = mapping_data.get("tool")
        if selected_tool not in tools.TOOL_REGISTRY:
            selected_tool = "top_bottom_n"

        params = mapping_data.get("params", {})
        if "reference_period" not in params:
            params["reference_period"] = rec_year

        highlight_entity = mapping_data.get("highlight_entity")

        # 도구 실행
        tool_func = tools.TOOL_REGISTRY[selected_tool]
        run_output = tool_func(CURRENT_DATASET, params)

        # highlight_entity(예: 한국)가 top_bottom_n에 누락되어 있다면 차트에 함께 추가
        ref_col = str(run_output.get("reference_period"))
        if highlight_entity and selected_tool == "top_bottom_n" and "Country Name" in CURRENT_DATASET and ref_col in CURRENT_DATASET:
            kr_match = CURRENT_DATASET[CURRENT_DATASET["Country Name"].astype(str).str.lower() == highlight_entity.lower()]
            if len(kr_match) > 0 and pd.notna(kr_match[ref_col].values[0]):
                kr_val = float(pd.to_numeric(kr_match[ref_col].values[0]))
                kr_name = str(kr_match["Country Name"].values[0])

                clean_s = pd.to_numeric(CURRENT_DATASET[~CURRENT_DATASET["Country Code"].isin(tools.KNOWN_AGGREGATE_CODES)][ref_col], errors="coerce").dropna()
                kr_rank = int((clean_s > kr_val).sum()) + 1

                top_list = run_output["result"].get("top_n", [])
                if not any(item["label"].lower() == kr_name.lower() for item in top_list):
                    top_list.append({
                        "label": f"{kr_name} ({kr_rank}위)",
                        "value": round(kr_val, 2),
                        "is_highlight": True
                    })
                    run_output["result"]["top_n"] = top_list

        LAST_RUN_RESULT = run_output

        # 실제 수치 결과 바탕으로 자연어 답변 생성
        answer_prompt = f"""사용자가 다음과 같이 질문했습니다: "{query}"

아래는 Pandas가 실제 데이터셋에서 계산한 검증된 결과입니다:
{json.dumps(run_output, ensure_ascii=False, indent=2)}

[답변 작성 가이드]
1. 위 계산 결과에 실제로 존재하는 숫자와 팩트만을 사용하여 질문에 명쾌하고 친절하게 답변하세요.
2. 수치(순위, 백분율, 차이 등)를 구체적으로 언급하며 비교 설명하세요.
3. 데이터에 없는 사실은 절대 지어내지 마세요.
4. 마크다운 목록과 볼드체를 적절히 활용하여 읽기 쉽게 2~3문단으로 답변하세요.
"""
        ans_resp = gemini_client.models.generate_content(
            model=gemini_model,
            contents=answer_prompt
        )

        return jsonify({
            "success": True,
            "query": query,
            "answer": ans_resp.text.strip(),
            "tool": selected_tool,
            "params": params,
            "run_result": run_output
        })

    except Exception as e:
        return jsonify({"error": f"자연어 질문 분석 중 오류가 발생했습니다: {str(e)}"}), 500


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    port = int(os.getenv("FLASK_PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=debug_mode)

