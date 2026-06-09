SPREADSHEET_ID = "1A5e_Z31lSQHGJkUPocwBYOca-CAQs-ItnAHqnz-q1Qw"

# 구글 드라이브 CareerLog 루트 폴더 ID (본인 폴더 ID로 교체)
DRIVE_ROOT_FOLDER_ID = "1AtxUFhHDixQzKss5mWs6yIfiTZ78Z7M-"

COLUMNS = [
    "강의일시", "요일", "시작", "종료", "의뢰기관", "출강기업",
    "과정명", "대상자", "업종",
    "방식/위치", "강사님", "시수", "강의료(1시간)", "강의료(1일)",
    "상태",
    "요청사항", "내부메모", "의뢰일", "의뢰인", "의뢰방법",
    "변경일자", "변경이력", "변경의뢰인", "증빙폴더"
]

STATUS_OPTIONS = ["정상", "날짜변경", "강사변경", "과목변경", "취소"]


DEFAULT_HOURLY_FEE = 100000
DEFAULT_LOCATION = ""
DEFAULT_INDUSTRY = ""

AGENCY_OPTIONS = ["수원대한협", "인천대한협", "서울대한협", "중대협", "한안협", "잡그레이드"]

LOCATION_OPTIONS = [
    "동시송출", "줌",
    "인천1", "인천2",
    "수원2층", "수원5층", "수원광교", "수원동탄", "수원상공회의소",
    "광교",
    "서울", "외부출강", "기타"
]

# config.py에 추가

CALENDAR_ID = "9898287aa6269a3c978e829d18f7856cac7910552b98a706af6376c25ea7f8a5@group.calendar.google.com"

INSTRUCTOR_CALENDARS = {
    "송주영": "9898287aa6269a3c978e829d18f7856cac7910552b98a706af6376c25ea7f8a5@group.calendar.google.com",
    "문하나": "",
    "김미림": "",  # 추후 추가
    "노미영": "",
    "여길매": "",
    "서순진": "",
    "이다인": "",
    "이진영": "",
    "표재은": "",
    "김미연": "",
    "김한나": "",
}
