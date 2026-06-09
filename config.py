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
    "김미림": "f4c809b6acf9b83337c7dd002df2901570f5cf2c21339482275ecadb4c5dd93f@group.calendar.google.com",
    "문하나":  "bea1c93cd56025c81414d906aee1f0737047108e8a9e20172b440c132b36e0f0@group.calendar.google.com",
    "노미영":  "cd923d2a08c856f63d059018afeffd0f4ab2001d9bd97b073c56a49c3ed6adb0@group.calendar.google.com",
    "여길매":  "0e2d87416aca73a099081362ab45e227911cfadcd2452db1ea044497890f513d@group.calendar.google.com",
    "이다인":  "ee68b5f7012f4173198c9c2ece6bdcb6e301e8030ca9961ddbe13992d05014c6@group.calendar.google.com",
}


INSTRUCTOR_CONFIG = {
    "송주영": {
        "limit": None,
        "zoom": True,
        "preferred_agency": [],
        "unavailable_dates": [],
        "morning_only": False,
        "backup": False,
    },
    "문하나": {
        "limit": None,
        "zoom": False,
        "preferred_agency": ["수원대한협"],
        "unavailable_dates": [],
        "morning_only": False,
        "backup": False,
    },
    "김미림": {
        "limit": None,
        "zoom": False,
        "preferred_agency": ["인천대한협"],
        "unavailable_dates": [],
        "morning_only": False,
        "backup": False,
    },
    "노미영": {
        "limit": 300,
        "zoom": True,
        "preferred_agency": [],
        "unavailable_dates": [],
        "morning_only": False,
        "backup": False,
    },
    "여길매": {
        "limit": 120,
        "zoom": True,
        "preferred_agency": [],
        "unavailable_dates": [],
        "morning_only": True,
        "backup": False,
    },
    "이다인": {
        "limit": None,
        "zoom": False,
        "preferred_agency": [],
        "unavailable_dates": [],
        "morning_only": False,
        "backup": True,
    },
}
