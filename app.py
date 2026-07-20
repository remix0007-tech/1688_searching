import streamlit as st
import pandas as pd
import deepl
from apify_client import ApifyClient
import io

# ==========================================
# 1. 웹 페이지 기본 레이아웃 및 스타일 설정
# ==========================================
st.set_page_config(
    page_title="타오바오-쿠팡 10배 마진 소싱 분석기",
    page_icon="🚀",
    layout="wide"
)

st.title("🚀 타오바오-쿠팡 10배 마진 소싱 분석기")
st.markdown("""
이 도구는 **한국어 키워드**를 입력하면 자동으로 **DeepL**을 통해 중국어로 번역하여 **타오바오(Taobao)**에서 상품 정보를 수집합니다.
무료 플랜에서도 차단 없이 부드럽게 작동하며, 수집된 단가에 물류비와 수수료를 가산해 **10배 마진 상품**을 발굴합니다.
""")

# ==========================================
# 2. 사이드바 - API 인증 정보 및 설정 값 입력
# ==========================================
st.sidebar.header("🔑 API 설정 및 매개변수")

# API Key 입력 폼
deepl_api_key = st.sidebar.text_input("DeepL API Key 입력", type="password", help="DeepL Developer Console에서 발급받은 키를 입력하세요.")
apify_token = st.sidebar.text_input("Apify API Token 입력", type="password", help="Apify Console에서 발급받은 API 토큰을 입력하세요.")

st.sidebar.markdown("---")
st.sidebar.header("⚙️ 비용 및 환율 세부 설정")

exchange_rate = st.sidebar.number_input("현재 적용 환율 (원/위안)", min_value=100.0, max_value=300.0, value=192.0, step=0.5)
import_overhead = st.sidebar.number_input("개당 수입 부대비용 (원)", min_value=0, value=4500, step=100, help="중국 내 배송비, 해운비, 통관 수수료, 국내 배송비 등을 감안한 예상 비용입니다.")
coupang_fee_rate = st.sidebar.slider("쿠팡 판매 수수료율 (%)", min_value=5, max_value=20, value=12, step=1)
vat_rate = st.sidebar.slider("부가세율 (%)", min_value=0, max_value=20, value=10, step=1)

# ==========================================
# 3. 데이터 처리 핵심 로직 정의
# ==========================================
def translate_ko_to_zh(text, api_key):
    try:
        translator = deepl.Translator(api_key)
        result = translator.translate_text(text, source_lang="KO", target_lang="ZH")
        return result.text
    except Exception as e:
        st.error(f"DeepL 번역 중 오류가 발생했습니다: {e}")
        return None

def fetch_taobao_data(zh_keyword, token, limit=30):
    try:
        client = ApifyClient(token)
        # 뭏료 플랜에서 가장 잘 작동하는 타오바오 스크래퍼 양식 지정
        run_input = {
            "keywords": [zh_keyword],
            "maxItems": limit
        }
        # Apify 대중적인 타오바오 스크래퍼 액터 호출
        run = client.actor("janne/taobao-scraper").call(run_input=run_input)
        
        dataset_id = run.get("defaultDatasetId") if isinstance(run, dict) else run.default_dataset_id
        raw_items = list(client.dataset(dataset_id).iterate_items())
        return raw_items
    except Exception as e:
        st.error(f"타오바오 데이터 스크래핑 중 오류가 발생했습니다: {e}")
        return []

def analyze_margins(raw_items, target_price, exchange_rate, import_overhead, fee_rate, vat):
    analyzed_list = []
    for item in raw_items:
        # 타오바오 스크래퍼 변수 명칭 매핑 (title, price)
        title = item.get("title") or item.get("name") or "Unknown Title"
        price_raw = item.get("price") or item.get("view_price")
        
        if not price_raw:
            continue
        try:
            # "¥ 15.50" 형태로 긁어오는 경우를 대비해 특수문자 제거 후 숫자로 변환
            price_cny = float(str(price_raw).replace("¥", "").strip())
        except ValueError:
            continue
            
        # 1) 원화 환산 순수 물품가
        pure_product_cost = price_cny * exchange_rate
        # 2) 총 예상 수입 원가 (물품가 + 개당 부대비용)
        landed_cost_krw = pure_product_cost + import_overhead
        # 3) 쿠팡 정산액 계산 (판매가 - 수수료 - 부가세)
        deduction_rate = (fee_rate + vat) / 100.0
        real_revenue = target_price * (1 - deduction_rate)
        # 4) 마진 배수 및 순수익 계산
        net_profit_krw = real_revenue - landed_cost_krw
        margin_multiple = target_price / landed_cost_krw if landed_cost_krw > 0 else 0
        
        analyzed_list.append({
            "상품명": title,
            "타오바오 가격 (위안)": price_cny,
            "예상 수입원가 (원)": int(landed_cost_krw),
            "쿠팡 목표가 (원)": target_price,
            "예상 순익 (원)": int(net_profit_krw),
            "마진 배수 (배)": round(margin_multiple, 2),
            "타오바오 링크": item.get("item_url") or item.get("url") or "https://www.taobao.com"
        })
    return analyzed_list

# ==========================================
# 4. 사용자 입력 UI 및 비즈니스 실행 흐름
# ==========================================
st.subheader("🔍 검색 및 마진 분석 조건 설정")
col1, col2, col3 = st.columns(3)
with col1:
    search_keyword = st.text_input("수집할 한국어 키워드", value="스마트폰 거치대", help="찾고자 하는 상품군을 한국어로 적어주세요.")
with col2:
    target_price = st.number_input("쿠팡 판매 목표 가격 (원)", min_value=1000, value=35000, step=1000, help="쿠팡에 등록해 판매할 목표 소비자가격입니다.")
with col3:
    margin_threshold = st.number_input("필터링 기준 최소 마진 배수 (배)", min_value=1.0, value=10.0, step=0.5, help="입력한 수치 이상의 마진율을 확보한 상품만 걸러냅니다.")

st.markdown("---")

if st.button("🚀 타오바오 마진 분석 실행", type="primary"):
    if not deepl_api_key or not apify_token:
        st.warning("왼쪽 사이드바에서 DeepL API Key와 Apify API Token을 먼저 입력해 주세요!")
    elif not search_keyword:
        st.warning("분석할 키워드를 입력해 주세요.")
    else:
        with st.spinner("🔄 타오바오 시장 조사 중... 잠시만 기다려 주세요 (약 20초~40초 소요)"):
            # STEP 1: 번역
            zh_keyword = translate_ko_to_zh(search_keyword, deepl_api_key)
            if zh_keyword:
                st.info(f"🇨🇳 **중국어 번역 결과:** '{zh_keyword}' 키워드로 타오바오를 검색합니다.")
                
                # STEP 2: 타오바오 크롤러 가동
                raw_data = fetch_taobao_data(zh_keyword, apify_token, limit=30)
                if raw_data:
                    # STEP 3: 마진 분석
                    analyzed_results = analyze_margins(
                        raw_items=raw_data,
                        target_price=target_price,
                        exchange_rate=exchange_rate,
                        import_overhead=import_overhead,
                        fee_rate=coupang_fee_rate,
                        vat=vat_rate
                    )
                    df = pd.DataFrame(analyzed_results)
                    
                    # 마진 필터링
                    filtered_df = df[df["마진 배수 (배)"] >= margin_threshold]
                    filtered_df = filtered_df.sort_values(by="마진 배수 (배)", ascending=False)
                    
                    st.success(f"🎉 분석 완료! {len(df)}개 상품 중 {len(filtered_df)}개의 아이템이 최소 {margin_threshold}배 마진 조건을 충족합니다.")
                    
                    tab1, tab2 = st.tabs(["📊 분석 결과 리스트", "📈 핵심 지표 분석"])
                    with tab1:
                        if not filtered_df.empty:
                            styled_df = filtered_df.copy()
                            styled_df["타오바오 링크"] = styled_df["타오바오 링크"].apply(lambda x: f'<a href="{x}" target="_blank">상품 바로가기</a>' if x else "")
                            st.write(
                                styled_df.to_html(escape=False, index=False),
                                unsafe_allow_html=True
                            )
                            
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                filtered_df.to_excel(writer, index=False, sheet_name='타오바오_소싱_결과')
                            processed_data = output.getvalue()
                            
                            st.markdown("<br>", unsafe_allow_html=True)
                            st.download_button(
                                label="📥 분석 결과 엑셀(.xlsx) 파일 다운로드",
                                data=processed_data,
                                file_name=f"taobao_margin_analysis_{search_keyword}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        else:
                            st.warning(f"설정하신 최소 마진 배수({margin_threshold}배)를 확보할 수 있는 상품이 타오바오 검색 결과에 없습니다.")
                    with tab2:
                        if not filtered_df.empty:
                            st.metric("🔥 분석 대상 중 최고 마진 배수", f"{filtered_df['마진 배수 (배)'].max()} 배")
                            st.metric("💰 분석 대상 중 최대 예상 순익", f"{filtered_df['예상 순익 (원)'].max():,} 원")
