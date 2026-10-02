# ISM push 검증 가이드

각 push가 실제로 THAAD(CONTRACT 스키마) DB의 어느 테이블/컬럼에 반영되는지,
그리고 반영 여부를 어떤 쿼리로 확인하는지 정리한다. push 실행 방법 자체는
[README.md](../README.md)를 참고한다.

## account push (`ism_adapter.cli accounts`)

### 영향받는 테이블

| 테이블 | 역할 | 반영 여부 |
|---|---|---|
| `CONTRACT.tAccount` | 계정 본체 | ✅ 신규 생성/갱신 |
| `CONTRACT.tCustomer` | 고객사(회사) 정보 | ✅ 신규 생성/갱신 |
| `CONTRACT.tServiceMap` | IXcloud ↔ THAAD 매핑 | ✅ 신규 생성 |
| `CONTRACT.tAccountMember` | 담당자 개인정보 | ❌ 반영 안 됨 — THAAD REST API의 저장 코드가 죽어있음(2026-09-16 코드 조사 + 2026-09-17 실제 push 전/후 데이터 비교로 재확인). 실제 담당자 데이터는 별도 앱 `thaad_web`이 AES_ENCRYPT로 관리 |

### 키 연결 관계

```
portal_db.account.id (UUID)
        │ sServiceKey로 저장
        ▼
CONTRACT.tServiceMap
   ├─ nTHAADSeq   ──────────┐  (sType='Account'일 때 tAccount.nAccountSeq를 가리킴)
   ├─ sServiceKey = account.id (UUID)
   ├─ sService    = 'cloud'
   └─ sType       = 'Account'
                             ▼
                   CONTRACT.tAccount
                      ├─ nAccountSeq (PK) ◄─┘
                      ├─ sAccountID   (= master user.username)
                      ├─ sName        (= account.name)
                      └─ nCustomerSeq ──────┐
                                             ▼
                                   CONTRACT.tCustomer
                                      ├─ nCustomerSeq (PK)
                                      ├─ sName    (= account.name, tAccount와 동일값)
                                      └─ sOwnerNm (= account_extend.ceo_name)

CONTRACT.tAccountMember  (참고용 — push로 반영되지 않음)
   └─ nAccountSeq → tAccount.nAccountSeq (FK)
```

연결 순서: `portal_db.account.id`(UUID) → **tServiceMap.sServiceKey**로 매칭 →
**tServiceMap.nTHAADSeq**가 곧 **tAccount.nAccountSeq** →
`tAccount.nCustomerSeq`로 **tCustomer** 조회.

### 검증 쿼리

**Step 1 — IXcloud account.id로 THAAD 매핑 찾기**
```sql
SELECT nTHAADSeq, sService, sType, sServiceKey, sMappingKey
FROM CONTRACT.tServiceMap
WHERE sService = 'cloud'
  AND sType = 'Account'
  AND sServiceKey = '<account.id UUID>';
```

**Step 2 — nTHAADSeq(=nAccountSeq)로 tAccount 확인**
```sql
SELECT nAccountSeq, nCustomerSeq, sAccountID, sName, sStatus, sPaymentKey, dtCreate
FROM CONTRACT.tAccount
WHERE nAccountSeq = <Step 1의 nTHAADSeq>;
```

**Step 3 — nCustomerSeq로 tCustomer 확인**
```sql
SELECT nCustomerSeq, sName, sOwnerNm, sType, sStatus
FROM CONTRACT.tCustomer
WHERE nCustomerSeq = <Step 2의 nCustomerSeq>;
```

**Step 4 (참고용) — tAccountMember가 정말 반영 안 되는지 재확인**
```sql
SELECT nAccountMemberSeq, nAccountSeq, sDutyType, sName, sEmail
FROM CONTRACT.tAccountMember
WHERE nAccountSeq = <Step 2의 nAccountSeq>;
-- 결과가 없거나, 있어도 이번 push 시각과 무관하면 "반영 안 됨"이 맞다는 뜻
```

**한 번에 조회 (JOIN 버전)**
```sql
SELECT
    sm.sServiceKey        AS ixcloud_account_id,
    a.nAccountSeq,
    a.sAccountID,
    a.sName               AS account_name,
    a.sStatus,
    a.dtCreate,
    c.nCustomerSeq,
    c.sOwnerNm
FROM CONTRACT.tServiceMap sm
JOIN CONTRACT.tAccount  a ON a.nAccountSeq = sm.nTHAADSeq
JOIN CONTRACT.tCustomer c ON c.nCustomerSeq = a.nCustomerSeq
WHERE sm.sService = 'cloud'
  AND sm.sType = 'Account'
ORDER BY a.dtCreate DESC
LIMIT 40;
```

### 실전 검증 기록

- **2026-09-17**: dev portal_db → stage THAAD, `python -m ism_adapter.cli accounts`
  실행, 37건 전부 success(error=0). 위 Step 1~3 쿼리로 신규 계정
  (nAccountSeq=4590, 4591 등) 및 매핑을 직접 확인함. tAccountMember는 push
  이후에도 해당 nAccountSeq로 신규 레코드가 생기지 않아 "반영 안 됨" 판단을
  재확인.

## contract push (`ism_adapter.cli contracts`)

계정 다음, 자원/사용량 push보다 먼저 실행되어야 한다 — THAAD가 자원 등록
시 project의 계약(tServiceMap sType='Contract')이 먼저 있는지 확인하기
때문이다(없으면 `ServiceMap not found`로 거절).

### 실전 검증 기록

- **2026-10-02**: 코드는 있었으나(최초 커밋 이후 무수정) 실행 기록이 없던
  상태였음 — dev portal_db(+billing_db) → stage THAAD, `python -m
  ism_adapter.cli contracts` 최초 실행. `total=164 success=164`, 전건
  성공(첫 실패 시 즉시 중단하는 설계라 끝까지 돌았다는 것 자체가 전건
  성공의 증거). 이후 volume push 재실행 시 `ServiceMap not found` 133건이
  전부 해소되어(→0건) 계약 등록이 실제 원인이었음을 교차 확인함.

## resource/metering push 공통 (`ism_adapter.cli resources --resource-type=...`)

### 영향받는 테이블

| 테이블 | 역할 |
|---|---|
| `CONTRACT.tResource` | 자원 등록(mID 기준 upsert) |
| `AGGREGATE.tCloudMetering` | 일별 사용량(metering push, resource 선등록 필요) |

### ⚠️ 공용 클라이언트 버그 발견 및 수정 (2026-10-02)

volume_snapshot 실전 검증 중 발견: THAAD는 배치(최대 20건) 중 **일부 항목만
실패해도 전체 HTTP 상태코드를 그 실패의 severity로 내린다**(Contract
미등록 `ServiceMap not found`는 400, 등록 안 된 product를 가리키는
`Product not found`는 500) — 본문엔 성공/실패가 섞인 리스트를 그대로
담고 있는데도. 기존 `ism_client.py`는 `raise_for_status()`를 먼저 호출해
이 경우 본문(성공 건 포함)을 전부 버리고 예외로 크래시했다(network/router
때부터 있던 버그 — 그동안 "전건 성공"만 겪어서 안 드러남). `_send_list_request()`가
400/500 + 리스트 본문 조합만 예외로 취급하지 않고 복원하도록 수정함
(PR #20, 커밋 `31e85da`/`49bf3d6`).

### 검증 쿼리

```sql
SELECT nResourceSeq, mID, dtStart, dtEnd, dtCreate
FROM CONTRACT.tResource
WHERE mID = '<push한 mID>';

SELECT nMeteringSeq, sResourceId, nActiveSec, dtPeriodStart, dtPeriodEnd
FROM AGGREGATE.tCloudMetering
WHERE sResourceId = '<push한 mID와 동일값>';
```

### volume_snapshot push — 실전 검증 기록

- **2026-10-02(1차)**: `resources --resource-type=volume_snapshot` 실행,
  `total=13 pushed=13 resource_errors=10 metering_errors=10` — 10건은
  Contract 미등록(알려진 상태), 3건은 실제 THAAD 레코드 생성 확인
  (nResourceSeq 425480~425482).
- **2026-10-02(2차, contract push 실행 후)**: 재실행 결과
  `total=13 pushed=13 resource_errors=0 metering_errors=0` — 전건 성공.

### share_snapshot push — 실전 검증 기록 및 버그 수정

- **2026-10-02(1차)**: `resources --resource-type=share_snapshot` 실행,
  `total=2 pushed=2 resource_errors=2`(전건 실패) — `"No query results for
  model [Product]"`. THAAD에 등록된 상품(nProductSeq=352, "NAS 스냅샷",
  카테고리 87)은 `attribute.resource_type == "nas_snapshot"`로 매칭하는데,
  기존 구현이 `SimpleResourceTransformer`를 상속해 내부 키 이름
  (`"share_snapshot"`)을 detail에 그대로 썼던 게 원인 — 코드 버그로 확정,
  수정(`share.py`가 이미 쓰던 `_THAAD_RESOURCE_TYPE` 하드코딩 패턴 적용).
- **2026-10-02(2차, 수정 후)**: `total=2 pushed=2 resource_errors=0
  metering_errors=0` — 전건 성공.

### lbaasv2_loadbalancer push — 실전 검증 기록 및 버그 수정

- **2026-10-02(1차)**: `resources --resource-type=loadbalancer` 실행,
  `total=45 pushed=41 resource_errors=41`(전건 실패) — `"No query results
  for model [Product]"`. THAAD 상품(236~239, Basic/Standard/Premium/
  CloudJ, 카테고리 48)은 `attribute.resource_type == "lbaas"` **그리고**
  `attribute.lb_provider`(각 provider 값) 둘 다로 매칭하는데, 기존 구현은
  resource_type에 내부 키 이름(`"loadbalancer"`)을 쓰고 lb_provider는
  mID에만 넣고 detail엔 안 실었음 — 코드 버그로 확정, 수정.
- **2026-10-02(2차, 수정 후)**: `total=45 pushed=41 resource_errors=1` —
  1건만 남음: `"Column 'sValue' cannot be null"`(THAAD DB 제약, `sValue`는
  `detail.display_name`에서 채워지는데 kube-service 자동 생성 LB 등
  `display_name`이 없는 자원이 실제로 있었음). legacy `share.py`와 동일한
  폴백(없으면 resource_id)을 적용해 수정.
- **2026-10-02(3차, 수정 후)**: `total=45 pushed=41 resource_errors=0
  metering_errors=0` — 전건 성공(nResourceSeq 426077~426095 등).

### share(NAS) push — 실전 검증 기록

THAAD 상품(nProductSeq=351, "NAS Standard", 카테고리 86)은
`attribute.resource_type=="nas"` **그리고** `attribute.share_type_id`(8개
UUID + `null`)로 매칭한다. metering-api `ShareMeteringDTO`에는
`share_type_id` 필드 자체가 없어(size_gib만 존재) 저희 payload엔 이 키가
아예 없는데, THAAD가 `null`을 목록에 포함해둬서 매칭이 그대로 통과됐다.

- **2026-10-02**: `resources --resource-type=share` 실행,
  `total=31 pushed=31 resource_errors=0 metering_errors=0` — 수정 없이
  전건 성공.

## volume push — 실전 검증 기록

- **2026-10-02(1차)**: `resources --resource-type=volume` 실행,
  `total=670 pushed=582 resource_errors=582`(=pushed와 동일, 즉 전건 실패).
  에러 분류: `ServiceMap not found` 133건(Contract 미등록, 기존과 동일),
  `Product not found` 449건(신규 발견) — dev 환경의 volume_type_id 3종
  (`322b5d33-...`=supreme, `75f571a5-...`=standard, `d4cb3034-...`=premium,
  metering-api `volume_history`로 확인)이 THAAD `tProduct`(229 Standard/
  230 Premium/231 Supreme)의 `arExtendSet.attribute.volume_type_id` 목록
  어디에도 없었음 — dev와 testbed 카탈로그가 서로 다른 OpenStack 배포의
  volume_type UUID를 기준으로 했기 때문(이름은 같으나 ID가 다름).
- **2026-10-02(2차, 카탈로그 보정 후)**: 사용자가 위 3개 UUID를 각 상품의
  `arExtendSet.attribute.volume_type_id`에 `JSON_ARRAY_APPEND`로 추가 등록.
  재실행 결과 `total=670 pushed=582 resource_errors=133 metering_errors=133`
  — `Product not found` 완전히 해소(449→0), 449건 실제 THAAD 레코드 생성
  확인(nResourceSeq 425483 이후). 남은 133건은 Contract 미등록(알려진 상태).
- **2026-10-02(3차, contract push 실행 후)**: `contracts` 실행(위 섹션
  참고)으로 164개 project 전체 계약 등록 후 재실행. `total=670 pushed=582
  resource_errors=0 metering_errors=0` — **전건 성공.**

### instance push — 실전 검증 기록

THAAD 상품(195~500번대, 다수)은 `resource_type=="instance"` **그리고**
`charge_type`(정확히 `"Reserved"` 또는 `"On_demand"`, 단 상품 221번은
등록 자체가 `"On_Demand"`로 오타/불일치가 있음) **그리고**
`instance_flavor_id`(목록, 예: `"r_01001"`, `"gpu_16062"`)로 매칭한다.

- **2026-10-02**: `resources --resource-type=instance --period-start=2026-09-01 --period-end=2026-09-08`
  실행, `total=139 pushed=130 skipped_no_project=9 resource_errors=0
  metering_errors=0` — 전건 성공(최상위 TRANSFORMERS wiring 누락만
  있었음, 커밋 `f711fb6`으로 수정).
- **⚠️ 미확인 잔여 리스크**: 이번 테스트 응답에 에러가 없어 실제 payload가
  로그에 안 남았다 — 이번에 push된 130건 중 실제로 `On_demand`(종량제)
  인스턴스가 있었는지 로그만으로는 확인 불가. legacy `.title()`과 동일하게
  정규화 결과는 `"On_Demand"`(대문자 D)인데 THAAD 등록 상품 대부분은
  `"On_demand"`(소문자 d)라 대소문자 불일치 가능성이 있다 — 이번 실행이
  전부 Reserved 인스턴스였을 경우 이 리스크가 전혀 발동하지 않았을 수
  있다. On_demand 인스턴스가 있는 기간으로 재검증하거나, THAAD DB에서
  실제 생성된 레코드의 `nProductSeq`가 On_demand 계열 상품(195/197/199...)
  을 포함하는지 확인 필요.

### os_image push — 실전 검증 기록

os_image는 metering-api 쪽 N+1 타임아웃(#109/#112, 2026-10-02 수정·배포)이
풀린 뒤 재검증했다. 쿼리 자체는 0.46초로 정상 응답했지만, push된 19건
전부가 THAAD `ModelNotFoundException: No query results for model [Product]`로
실패했고 전부 `os_type: "linux"`였다.

legacy(`ixcloud_service/common/ixcdaemon/ism/resource.py::run_os_image`,
`ism/metering.py::run_os_image`)를 확인한 결과 **os_image는 범용 이미지
사용량이 아니라 Windows 라이선스 과금**이다 — `os_type IN ('windows',
'windosw', 'winddows', 'window')`로 조회 자체를 필터링하고, `custom` 접두
이미지와 무과금 테넌트 1곳(`OSIMAGE_FREE_TENANTS`)을 제외하며, THAAD 상품
매칭에 `windows_type`/`server_type`/`server_version`/`sql_type`/
`sql_version`(이미지명 파싱, `detect_os_db()`)까지 쓴다.

metering-api 쪽에는 필터링 책임이 없다고 판단해(billing/policy 영역, 이미
`base_image_name`/`os_type`을 주고 있어 metering-api 수정 불필요)
ism-adapter의 `is_excluded` 훅과 `detect_os_db()` 포팅으로 전부 구현했다
(커밋 `29981e5`, `feat/8-os-image`).

- **2026-10-02**: `resources --resource-type=os_image` 1주일
  (`2026-09-01~2026-09-08`, `total=21`)과 2개월(`2026-08-01~2026-10-02`,
  `total=115`) 범위 모두 재실행 — **115건 전부 linux라 is_excluded로
  걸러져 `pushed=0 skipped_excluded=115 resource_errors=0
  metering_errors=0`.** 잘못 push되던 것(Product not found 에러)이 전부
  제외로 바뀐 것은 확인했다.
- **⚠️ happy path 미검증(환경 제약, 코드 문제 아님)**: dev 환경에 Windows
  os_image 데이터 자체가 없어(2026-01-01~2026-10-02 전체 조회로 확인,
  115건 전부 `os_type=linux`) **Windows 이미지가 실제로 THAAD에 성공적으로
  매칭·생성되는 happy path는 검증하지 못했다.** 인스턴스 생성 시 이미지
  선택지에도 Windows 자체가 없어, dev에서 테스트용 Windows 인스턴스를 새로
  만드는 것도 불가능함을 확인했다 — dev 이미지 카탈로그에 Windows 이미지가
  등록돼 있지 않은 구조적 제약이다.
- **마무리 결정**: 이 환경 제약 때문에 THAAD 카탈로그 쪽 속성명 대조 포함한
  실전 happy path 검증은 보류하고, `is_excluded` 필터링(비Windows 거름)과
  `detect_os_db()` 파생 로직은 단위테스트(`tests/transformers/compute/test_os_image.py`)
  커버리지로 갈음하기로 결정했다(2026-10-02). Windows 이미지가 dev에
  등록되는 시점이 생기면 그때 실전 재검증한다.
