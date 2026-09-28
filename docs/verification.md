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
