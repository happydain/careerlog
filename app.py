"""
보건스케줄 자동정리 및 구글 드라이브 연동 시스템 (메인 UI)
- 메뉴 1: 📥 보건스케줄 입력 (엑셀/카톡 공통 증빙 자동 분류 및 드라이브 배포)
- 메뉴 3: 📅 최종 스케줄 관리 (데이터 수정 시 실시간 이미지/텍스트 변동이력 핀포인트 기록)
"""

import streamlit as st
import pandas as pd
from datetime import datetime

# 💡 구글 드라이브 연동 모듈(gdrive.py)에서 필요한 함수 일괄 로드
from gdrive import (
    create_careerlog_structure,
    get_folder_url,
    save_common_request_evidence,
    append_change_log_with_evidence
)

# 임의의 구글 시트 마스터 컬럼 정의 (환경에 맞게 수정 가능)
COLUMNS = ["강의일시", "의뢰기관", "과정명", "강사명", "변경이력", "증빙폴더"]

st.set_page_config(page_title="보건스케줄 관리 시스템", layout="wide")
st.title("🏥 보건스케줄 자동정리 및 증빙 관리 시스템")

# ─────────────────────────────────────────────
# 사이드바 메뉴 구성
# ─────────────────────────────────────────────
menu = sidebar_menu = st.sidebar.selectbox(
    "메뉴를 선택하세요",
    ["📥 보건스케줄 입력", "📅 최종 스케줄(취소/변경 반영)"]
)

# 테스트용 세션 상태 및 마스터 데이터 초기화 (실제 운영 시 구글 시트 연동)
if "master_df" not in st.session_state:
    st.session_state["master_df"] = pd.DataFrame(columns=COLUMNS)


# ─────────────────────────────────────────────
# [메뉴 1]: 보건스케줄 입력
# ─────────────────────────────────────────────
if menu == "📥 보건스케줄 입력":
    st.header("📥 신규 보건스케줄 등록 및 공통 증빙 세팅")
    st.markdown("---")
    
    # 1. 상단 공통 정보 입력 영역
    col1, col2, col3 = st.columns(3)
    with col1:
        common_requester = st.text_input("의뢰인 이름", value="홍길동")
    with col2:
        request_date_str = st.date_input("의뢰 일자", datetime.today()).strftime("%Y-%m-%d")
    with col3:
        common_agency = st.text_input("대표 의뢰 기관", value="서울보건소")

    st.markdown("#### 📁 공통 증빙 자료 첨부")
    st.caption("※ 이번 의뢰 묶음에 포함된 모든 강의 일들의 '01_원본의뢰' 폴더에 공통으로 저장됩니다.")
    
    col_file, col_text = st.columns(2)
    with col_file:
        # 드라이브 전송용 엑셀 파일 버퍼를 세션에 저장
        uploaded_excel = st.file_uploader("공통 의뢰 엑셀 파일", type=["xlsx", "xls"])
        if uploaded_excel:
            st.session_state["excel_file_for_drive"] = uploaded_excel
            
    with col_text:
        raw_text = st.text_area("공통 카톡/이메일 원문 텍스트 붙여넣기", height=100, placeholder="여기에 붙여넣은 원문은 구글 Docs 파일로 자동 변환되어 저장됩니다.")
        st.session_state["raw_text_for_drive"] = raw_text

    st.markdown("---")
    st.markdown("#### 📊 강의 일정 세부 편집")
    st.caption("아래 표에 강의 일정을 입력하거나 붙여넣으세요. 저장 시 일자별/과정별 구글 드라이브 폴더가 자동 생성됩니다.")

    # 편집용 임시 데이터프레임 생성 (예시 행 2개 배치)
    init_data = [
        {"강의일시": "2026-07-01", "의뢰기관": common_agency, "과정명": "심폐소생술 교육", "강사명": "김강사", "변경이력": "", "증빙폴더": ""},
        {"강의일시": "2026-07-02", "의뢰기관": common_agency, "과정명": "아동보건 위생교육", "강사명": "이강사", "변경이력": "", "증빙폴der": ""}
    ]
    input_df = pd.DataFrame(init_data)
    
    edited_df = st.data_editor(input_df, num_rows="dynamic", use_container_width=True)

    # 저장 버튼 로직
    if st.button("💾 일정 등록 및 구글 드라이브 연동 시작", use_container_width=True):
        if edited_df.empty:
            st.error("❌ 등록할 강의 일정이 없습니다.")
        else:
            with st.spinner("🚀 구글 드라이브에 표준 폴더 구조를 생성하고 공통 증빙을 배포하는 중입니다..."):
                created_folder_ids = []
                drive_errors = []
                current_year = datetime.today().year

                # 각 행을 순회하며 강의 폴더 구조 생성
                for idx in edited_df.index:
                    row = edited_df.loc[idx].to_dict()
                    try:
                        date_str = str(row.get("강의일시", "")).strip()
                        agency   = str(row.get("의뢰기관", common_agency)).strip()
                        subject  = str(row.get("과정명", "미지정")).replace(" ", "")
                        
                        # 연도 추출 (YYYY-MM-DD 형식 가정)
                        try:
                            yr = int(date_str[:4])
                        except:
                            yr = current_year

                        if not date_str or not agency:
                            continue

                        # 1단계: gdrive.py를 호출하여 연도/기관/강의폴더 및 4대 서브폴더 일괄 생성
                        folder_id = create_careerlog_structure(yr, agency, date_str, subject)
                        folder_url = get_folder_url(folder_id)
                        
                        # 데이터프레임에 생성된 구글 드라이브 URL 심기
                        edited_df.loc[idx, "증빙폴더"] = folder_url
                        created_folder_ids.append(folder_id)

                    except Exception as e:
                        drive_errors.append(f"[{date_str} - {subject}] 폴더 생성 실패: {e}")

                # ⭐ 2단계: 핵심 기능 - 이번 의뢰 묶음의 모든 폴더에 공통 증빙(엑셀/카톡)을 단 한 번의 연산으로 일괄 분배 저장
                if created_folder_ids:
                    try:
                        save_common_request_evidence(
                            lecture_folder_ids=created_folder_ids,
                            uploaded_excel=st.session_state.get("excel_file_for_drive"),
                            raw_text=st.session_state.get("raw_text_for_drive", ""),
                            requester=common_requester,
                            request_date=request_date_str
                        )
                    except Exception as e:
                        st.error(f"❌ 공통 증빙 파일 드라이브 배포 중 오류 발생: {e}")

                # 결과 출력 및 마스터 데이터 저장 (구글 시트 대신 세션에 축적)
                if drive_errors:
                    for err in drive_errors:
                        st.warning(err)
                
                # 성공 데이터 반영
                st.session_state["master_df"] = pd.concat([st.session_state["master_df"], edited_df], ignore_index=True)
                st.success(f"🎉 총 {len(created_folder_ids)}개 강의의 구글 드라이브 폴더 체계 구축 및 공통 원본 증빙 저장이 완료되었습니다!")
                st.balloons()


# ─────────────────────────────────────────────
# [메뉴 2]: 최종 스케줄 (취소/변경 반영)
# ─────────────────────────────────────────────
elif menu == "📅 최종 스케줄(취소/변경 반영)":
    st.header("📅 최종 스케줄 조회 및 실시간 변동이력 추적")
    st.markdown("---")
    
    original_df = st.session_state["master_df"].copy()
    
    if original_df.empty:
        st.info("💡 현재 등록된 보건스케줄 마스터 데이터가 없습니다. 먼저 '보건스케줄 입력' 메뉴에서 일정을 등록해 주세요.")
    else:
        st.markdown("#### ✏️ 스케줄 실시간 수정 (Data Editor)")
        st.caption("강사 매칭 변경, 일정 취소, 과정명 변경 등 변동사항이 발생하면 테이블 안의 셀을 더블클릭하여 즉시 수정하세요.")
        
        # 사용자가 화면에서 수정할 수 있는 테이블 배치
        edited_gsheet_df = st.data_editor(original_df, use_container_width=True)

        st.markdown("---")
        st.markdown("### 🔄 핀포인트 스케줄 변동사항 관리 및 이미지/텍스트 증빙")
        st.caption("셀을 수정했다면, 수정을 지시한 담당자와 카톡 캡처 이미지 등 증빙 자료를 넣고 아래 버튼을 눌러 이력을 남기세요.")
        
        col_modifier, col_img, col_txt = st.columns([1, 1.5, 2])
        
        with col_modifier:
            modifier = st.text_input("📋 변경 승인/담당자 이름", placeholder="담당자 이름 입력 (필수)")
        with col_img:
            change_image = st.file_uploader("📸 변동 증빙 이미지 (카톡 지시 캡처 등)", type=["png", "jpg", "jpeg"])
        with col_txt:
            change_text_content = st.text_area("💬 변동 안내 카톡/문자 내용 복사", height=68, placeholder="여기에 입력한 변동 사유 텍스트는 해당 강의의 변경이력 문서에 기록됩니다.")

        # 변경사항 저장 버튼
        if st.button("💾 변경사항 및 드라이브 히스토리 저장", use_container_width=True):
            if not modifier.strip():
                st.error("❌ 변경 처리를 승인한 '변경 담당자 이름'을 입력해야 저장이 가능합니다.")
            else:
                with st.spinner("🔄 데이터 변경점을 추적하여 구글 드라이브에 이력을 격리 기록하는 중..."):
                    any_changed = False
                    
                    # 마스터 데이터프레임을 돌며 어떤 셀이 기존 데이터와 달라졌는지 정밀 비교
                    for idx in edited_gsheet_df.index:
                        changes = []
                        for col in COLUMNS:
                            if col in ("변경이력", "증빙폴더"): 
                                continue
                            
                            # 기존 값과 새 값 비교
                            orig_val = str(original_df.loc[idx, col]).strip() if idx in original_df.index else ""
                            new_val  = str(edited_gsheet_df.loc[idx, col]).strip()
                            
                            if orig_val != new_val:
                                changes.append(f"[{col}] {orig_val} ➡️ {new_val}")

                        # 💡 변경점이 포착된 특정 행(강의)이 있다면 구글 드라이브의 해당 폴더 이력에만 핀포인트 저장
                        if changes:
                            any_changed = True
                            summary_text = ", ".join(changes)
                            
                            # 셀의 '변경이력' 열에도 텍스트 히스토리 업데이트
                            timestamp = datetime.now().strftime("%m/%d %H:%M")
                            existing_log = str(edited_gsheet_df.loc[idx, "변경이력"])
                            new_log = f"[{timestamp} {modifier}]: {summary_text}"
                            edited_gsheet_df.loc[idx, "변경이력"] = f"{existing_log} | {new_log}" if existing_log and existing_log != "nan" else new_log
                            
                            # 해당 강의 폴더의 '03_변경이력' 서브폴더 링크 파싱 및 파일 업로드
                            folder_url = str(edited_gsheet_df.loc[idx, "증빙폴더"])
                            if folder_url.startswith("https://drive.google.com"):
                                try:
                                    # URL 주소 맨 뒤의 폴더 ID 값만 슬라이싱 추출
                                    folder_id = folder_url.split("/")[-1]
                                    
                                    # gdrive.py의 변동이력 이미지/텍스트 복합 업로드 함수 호출
                                    append_change_log_with_evidence(
                                        folder_id=folder_id,
                                        change_summary=summary_text,
                                        modifier=modifier,
                                        evidence_image=change_image,
                                        evidence_text=change_text_content
                                    )
                                except Exception as e:
                                    st.error(f"❌ 드라이브 변경이력 저장 실패 (행 번호 {idx}): {e}")

                    if any_changed:
                        # 수정된 데이터프레임을 마스터 세션에 최종 갱신
                        st.session_state["master_df"] = edited_gsheet_df
                        st.success("🎯 변경된 일정의 구글 드라이브 '03_변경이력' 폴더 내부에 증빙 이미지 및 텍스트 로그 저장이 완료되었습니다!")
                        st.rerun()
                    else:
                        st.info("ℹ️ 테이블에서 변경된 데이터 셀이 감지되지 않았습니다.")
