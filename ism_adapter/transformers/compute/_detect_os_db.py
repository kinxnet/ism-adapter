"""이미지명에서 Windows/SQL 라이선스 속성을 추출.

legacy `ixcloud_service/common/ixcdaemon/ism/utils/get_os_image_types.py`의
`detect_os_db()`를 그대로 포팅했다 — DB 접근 없는 순수 문자열 파싱 함수라
이식에 로직 변경이 필요 없었다. os_image는 "이미지 사용량"이 아니라 Windows
라이선스 과금이고(legacy `ism/resource.py::run_os_image`), THAAD 상품은 이
함수가 뽑아내는 windows_type/server_type/server_version/sql_type/sql_version
속성으로 매칭된다.
"""

import re
from collections import namedtuple

WinInfo = namedtuple("WinInfo", ["edition", "version"])
SqlInfo = namedtuple("SqlInfo", ["edition", "version"])
DetectResult = namedtuple("DetectResult", ["windows", "sql"])

_P_WIN_ANY = re.compile(
    r"""
    (?<![a-z0-9])                       # 앞이 영숫자면 시작 X (오검출 감소). '_'는 허용
    (windows|windowserver|ws|w)
    (?:[-_])?
    (?:
        (?P<server_version>\d{4})       # 2012, 2016, 2008...
        (?:[-_]?r(?P<server_r>\d))?     # R2
    )?
    (?=$|[_-])                          # 뒤가 끝 또는 구분자면 OK
    """,
    re.I | re.VERBOSE,
)

_P_SQL_ANY = re.compile(
    r"""
    (?<![a-z0-9])
    (sql|sqlserver)
    (?:[-_])?
    (?P<sql_version>\d{4})
    (?:[-_]?r(?P<sql_r>\d))?
    (?=$|[_-])
    """,
    re.I | re.VERBOSE,
)

_P_ED_WIN_DC = re.compile(r"(?<![a-z0-9])(dc|datacenter)(?![a-z0-9])", re.I)
_P_ED_WIN_ENT = re.compile(r"(?<![a-z0-9])(ent|enterprise)(?![a-z0-9])", re.I)
_P_ED_SQL_ENT = re.compile(r"(?<![a-z0-9])(ent|enterprise)(?![a-z0-9])", re.I)


def _fmt_version(m: re.Match, year_group: str, r_group: str) -> str | None:
    year = m.group(year_group)
    r = m.group(r_group)
    if not year:
        return None
    return f"{year}R{r}" if r else year


def detect_os_db(name: str) -> DetectResult:
    s = name.lower()

    win_m = _P_WIN_ANY.search(s)
    sql_m = _P_SQL_ANY.search(s)

    windows = None
    sql = None

    if win_m:
        win_start = win_m.start()
        win_end = sql_m.start() if (sql_m and sql_m.start() > win_start) else len(s)
        win_section = s[win_start:win_end]

        if _P_ED_WIN_DC.search(win_section):
            win_ed = "datacenter"
        elif _P_ED_WIN_ENT.search(win_section):
            win_ed = "enterprise"
        else:
            win_ed = "standard"

        windows = WinInfo(win_ed, _fmt_version(win_m, "server_version", "server_r"))

    if sql_m:
        sql_section = s[sql_m.start() :]

        sql_ed = "enterprise" if _P_ED_SQL_ENT.search(sql_section) else "standard"

        sql = SqlInfo(sql_ed, _fmt_version(sql_m, "sql_version", "sql_r"))

    return DetectResult(windows, sql)
