# ism-adapter

## 개요

`metering-api`가 집계한 클라우드 자원 사용량(`GET /metering`)을 ISM으로 push하는 어댑터. 
"metering은 사용량 집계만 책임지고, 정책·과금은 어댑터가 담당한다" 구조의 신규
어댑터로, 기존 `ixc_daemon_ism.py`(레거시 파이썬 배치)가 하던 일을 대체하는 것이
목표다.

**상태를 갖지 않는다** — 매 실행마다 지정된 기간의 usage를 metering-api에서 전체
조회해 ISM에 다시 push한다. 정기 배치와 특정 기간 재전송이 같은 경로를 인자만
다르게 써서 수행한다(아래 [사용 방법](#사용-방법) 참고).

</br>

## 폴더 구성

```
.
├── ism_adapter/
│   ├── cli.py              # 진입점 (argparse)
│   ├── clients/             # metering-api / ISM(THAAD) HTTP 클라이언트
│   ├── core/
│   │   ├── config/          # pydantic-settings + KMS(Vault)
│   │   ├── log/             # loguru 설정
│   │   └── rest_client/     # httpx 공통 요청 처리
│   ├── repositories/        # portal_db(project) 읽기 전용 조회
│   ├── transformers/        # metering-api usage → ISM payload 변환 (자원 타입별)
│   └── services/            # 파이프라인 오케스트레이션
└── tests/
```

</br>

## 실행 모델

레거시(`ixc_daemon_ism.py`)와 동일하게 **일 배치**로 동작하도록 설계했다.
`metering-api`(FastAPI 상시 서버)나 `metering-worker`(APScheduler로 상시 구동)와
달리, 이 서비스는 **상시 프로세스가 아니다** — 실행하면 지정된 기간을 push하고
바로 종료한다. 운영에서는 k8s CronJob이 하루 한 번 이 스크립트를 실행하는 방식을
염두에 두고 있다(아직 Helm 차트는 없음).

</br>

## 환경 설정 (env)

`metering-api`/`metering-worker`와 동일한 규칙을 따른다 — **민감정보는 KMS(Vault),
환경마다 값이 달라지는 설정은 `.env`/환경변수**로 분리한다.

### `.env`(또는 쉘 환경변수)로 관리하는 값

| 변수 | 용도 | 비고 |
|------|------|------|
| `METERING_API_HOST` | metering-api base URL | 환경(dev/stage/prod)마다 값이 달라 KMS 아님. 로컬 개발은 로컬 컨테이너가 아니라 dev 클러스터의 외부 주소(`https://dev-metering-api.kinxcloud.net:8443`)를 직접 호출한다 |
| `ISM_API_HOST` | ISM(THAAD) base URL | 위와 동일. 현재 레거시 운영 값은 인증 없는 사내망 평문 HTTP(`http://1.201.138.223:8303/v1`) — 이 무인증 방식을 그대로 이어받을지는 별도로 인프라/보안팀과 상의 필요 |
| `APP__DEBUG` | 디버그 로그 여부 | 기본 `false` |
| `APP__ENVIRONMENT` | `prod`/`dev`/`test` | `test`면 KMS 필수값 검증을 건너뜀 |
| `APP__TIMEZONE` | 기본 `UTC` | |
| `LOG__*` | 로그 경로/로테이션 | 기본값 있음, `.env.sample` 참고 |
| `SENTRY__DSN` | Sentry DSN | 선택 |

로컬 개발용 KMS 접속 정보(`DEV_KMS_*`)는 `.env`에 평문으로 두지 않고, `.secret.sample`을
`.secret`으로 복사해 채운 뒤 `source .secret`으로 쉘에 로드한다 (자세한 절차는
아래 [로컬 개발 (Docker Compose)](#로컬-개발-docker-compose) 참고).

### KMS(Vault)에서 로드하는 값

| 변수 | KMS 경로 | 용도 |
|------|---------|------|
| `app.master_apikey` | `common/api-keys` → `master_apikey` | metering-api 호출 인증(`IXcloud-Apikey` 헤더) |
| `database.portal_url` | `common/databases/portal-db` → `host`/`port`/`user`/`password`/`database` | `portal_db`(project 테이블) 접속 문자열 조립 |

⚠️ `common/databases/portal-db`는 ixcs-api-service와 동일한 일반(쓰기 가능)
계정이다 — project 테이블 전용 읽기 전용 계정이 별도로 없다(2026-09-15 확인).
이 서비스가 project 테이블에 쓰지 않는 것은 지금은 DB 권한이 아니라 코드
레벨(`repositories/project_repository.py`만 이 연결을 사용) 약속일 뿐이다.
읽기 전용 계정 발급은 후속 과제로 남아 있다.

기동 시 `validate_config()`가 위 4개 필수값(`master_apikey`, `portal_url`,
`METERING_API_HOST`, `ISM_API_HOST`)이 비어 있으면 즉시 실패한다(Fail Fast) —
`APP__ENVIRONMENT=test`일 때만 이 검증을 건너뛴다.

`.env.sample`을 복사해 `.env`로 사용한다.

</br>

## 로컬 개발 (Docker Compose)

`metering-api`/`metering-worker`와 동일한 패턴 — 컨테이너를 띄워두기만 하고,
개발자가 `docker exec`로 들어가 직접 명령을 실행한다. 이 서비스는 상시 서버가
아니라 배치 CLI라서 컨테이너가 기동과 동시에 뭔가를 계속 실행하지 않는다.

**1단계 — KMS 자격증명 준비**
```bash
cp .secret.sample .secret
# .secret을 열어 DEV_KMS_ENDPOINT/ENGINE/ROLE_ID/ROLE_SECRET 실제 값으로 채운다
# (.secret은 .gitignore 처리되어 커밋되지 않는다)
source .secret
```

**2단계 — `.env` 준비**
```bash
cp .env.sample .env
# METERING_API_HOST, ISM_API_HOST 등 필요한 값을 채운다
```

**3단계 — 컨테이너 실행**
```bash
docker compose -f docker-compose-dev.yaml up -d
```

**4단계 — 컨테이너 내부에서 CLI 실행**
```bash
docker exec -it ism-adapter bash
uv sync                                          # uv.lock이 아직 없으면 최초 실행 시 생성됨(이후 커밋 권장)
python -m ism_adapter.cli accounts               # 계정 push(전체 대상)
python -m ism_adapter.cli resources              # 자원/사용량 정기 배치(전일 하루치)
```

> `ixcloud-portal-network`(external)에 연결한다 — portal_db(ixcs-api-service)에
> 컨테이너 이름으로 접근하기 위함이며, 로컬에 미리 떠 있어야 한다
> (`docker network create` 또는 해당 레포의 docker-compose로 먼저 기동).
> metering-api는 로컬 컨테이너가 아니라 dev 클러스터의 외부 주소를 `.env`의
> `METERING_API_HOST`로 직접 호출하므로 별도 네트워크 연결이 필요 없다.

</br>

## 사용 방법

컨테이너 내부(`docker exec -it ism-adapter bash`) 또는 `uv run`이 가능한 환경
기준 실행 예시다.

CLI는 두 서브커맨드로 나뉜다 — `accounts`(계정 push, 기간 없음)와
`resources`(자원/사용량 push, 기간 지정). legacy 실행 순서(account → contract
→ resource → metering)를 감안하면 `accounts`를 `resources`보다 먼저 실행해야
한다.

### 계정 push (`accounts`)

project를 1개 이상 가진 전체 계정을 대상으로, 항상 전체를 다시 push한다(기간
개념 없음 — resource/metering과 달리 상태를 남기지 않고 매번 전량 재전송).
계정 1건마다 개별 요청으로 push되며, 한 계정의 실패가 다른 계정에 영향을
주지 않는다.

```bash
uv run python -m ism_adapter.cli accounts
```

### 자원/사용량 push (`resources`)

#### 정기 배치 (인자 없이 실행)

인자를 생략하면 **"어제 00:00 ~ 오늘 00:00" (전일 하루치)** 를, 지원하는 모든
자원 타입(`network`, `router`)에 대해 push한다. k8s CronJob이 매일 호출하는
기본 형태다.

```bash
uv run python -m ism_adapter.cli resources
```

#### 자원 타입 지정

콤마로 구분해 여러 개를 한 번에 지정할 수 있다.

```bash
uv run python -m ism_adapter.cli resources --resource-type=network
uv run python -m ism_adapter.cli resources --resource-type=network,router
```

#### 특정 기간 재전송 (날짜 지정)

운영자가 날짜별 자원 개수를 조회해 결측이나 이상을 발견했을 때, 그 기간만 다시
push하는 용도다. `--period-start`/`--period-end`는 ISO 형식(`YYYY-MM-DDTHH:mm:ss`)
문자열이며, 반열린 구간 `[period-start, period-end)`로 해석된다.

```bash
# 2026-09-01 하루치만 재전송
uv run python -m ism_adapter.cli resources --resource-type=network \
    --period-start=2026-09-01T00:00:00 --period-end=2026-09-02T00:00:00

# 2026-09-01 ~ 2026-09-03 사흘치를 한 번에 재전송
uv run python -m ism_adapter.cli resources --resource-type=network,router \
    --period-start=2026-09-01T00:00:00 --period-end=2026-09-04T00:00:00
```

> 지정한 기간 전체를 한 번에 조회해서 push한다(legacy처럼 날짜 단위로 쪼개
> 개별 배치로 처리하지 않는다). 날짜별로 끊어서 개별 처리해야 하는 경우가
> 있다면 여러 번 나눠 실행해야 한다.

### 전체 옵션 확인

```bash
uv run python -m ism_adapter.cli --help
uv run python -m ism_adapter.cli accounts --help
uv run python -m ism_adapter.cli resources --help
```

</br>

## 참고

- 실측/설계 근거: `kinx-ixcloud-metering/docs/2026H2-ism-migration-milestone.md`,
  `legacy-metering-analysis.md`
- ISM(THAAD) push payload 스펙 실측 근거는 `ism_adapter/transformers/base.py`
  상단 docstring 참고
- push가 실제로 어느 THAAD 테이블/컬럼에 반영되는지, 키가 어떻게 연결되는지,
  값을 확인하는 검증 쿼리는 [docs/verification.md](docs/verification.md) 참고
