import pandas as pd

from parsers.parser_utils import (
    extract_instructor,
    detect_agency,
    detect_target,
    detect_subject,
    parse_dates_from_text,
    parse_time_range,
    make_row,
)

DEFAULT_HOURLY_FEE = 100000
DEFAULT_LOCATION = "줌"
DEFAULT_INDUSTRY = "기타업"
