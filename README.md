# 🔍 CMDB MCP 챗봇

S3에 저장된 AWS CMDB 정책 데이터와 7개의 AWS MCP 서버를 연동하여, 자연어로 AWS 리소스 현황·비용·보안·모니터링을 조회하는 AI 챗봇입니다.

---

## 📋 프로젝트 개요

### 🎯 주요 기능

| 기능 | 설명 |
|---|---|
| CMDB 조회 | S3에 저장된 IAM, EC2, S3, RDS, VPC, KMS 정책 스냅샷 조회 |
| 비용 분석 | AWS Billing + Cost Explorer로 실시간 비용 조회 및 전월 비교 |
| 문서 검색 | AWS 공식 문서에서 업그레이드 방법, 베스트 프랙티스 검색 |
| 모니터링 | CloudWatch 메트릭, 로그, 알람 실시간 조회 |
| 감사 추적 | CloudTrail로 API 호출 이력 및 변경 감사 |
| IAM 분석 | IAM 사용자/역할/정책 실시간 조회 및 권한 시뮬레이션 |
| 익명화 | 계정 ID, ARN, Access Key 등 민감 정보 자동 마스킹 |

### 💡 MCP(Model Context Protocol)란?

AI 모델이 외부 데이터와 도구에 접근할 수 있게 해주는 표준 프로토콜입니다.

- 일반 방식: AI에게 모든 데이터를 텍스트로 전달 → 토큰 낭비, 느림
- MCP 방식: AI가 필요할 때 도구를 호출해서 데이터 조회 → 효율적, 정확

---

## 🏗️ 아키텍처

```
사용자 질문
    ↓
Streamlit 챗봇 (UI)
    ↓
질문 유형 분류 (라우팅)
    ↓
┌─────────────────────────────────────────────┐
│  📊 CMDB (S3)     ☁️ AWS MCP 서버 (7개)     │
│  - IAM 정책       - 💰 AWS Billing           │
│  - EC2 현황       - 📈 Cost Explorer         │
│  - S3 버킷        - 📚 AWS Knowledge         │
│  - RDS/VPC        - 💵 AWS Pricing           │
│  - KMS/보안       - 📊 CloudWatch            │
│                   - 🔍 CloudTrail            │
│                   - 🔐 IAM                   │
└─────────────────────────────────────────────┘
    ↓
Strands Agent + Bedrock Claude Sonnet 4
    ↓
통합 분석 → 한국어 답변 + 사용된 MCP 표시
```

**데이터 흐름:**
1. 사용자 질문 입력
2. 질문 키워드 분석 → 필요한 MCP만 선택적 호출
3. Strands Agent가 MCP 도구를 자율적으로 실행
4. 여러 소스 데이터 통합 → Bedrock이 분석 후 답변
5. 민감 정보 익명화 → 사용된 MCP 서버 표시

---

## 📊 MCP 서버 구성

### 내부 CMDB MCP (S3 직접 조회)

S3 버킷에 저장된 AWS 리소스 정책 스냅샷 데이터를 조회합니다.

| 도구 | 데이터 |
|---|---|
| `get_identity_policies` | IAM, Organizations, Cognito 정책 |
| `get_storage_policies` | S3, EFS, FSx 정책 |
| `get_compute_policies` | EC2, Lambda, ECS 정책 |
| `get_database_policies` | RDS, DynamoDB 정책 |
| `get_network_policies` | VPC, CloudFront, Route53 정책 |
| `get_security_policies` | KMS, Secrets Manager, WAF 정책 |
| `search_resources` | 전체 리소스 검색 |
| `get_resource_summary` | 리소스 요약 통계 |

**S3 데이터 구조:**
```
s3://mwaa-cmdb-bucket/
└── aws-policies/
    └── YYYYMMDD/
        ├── identity_policies.json
        ├── storage_policies.json
        ├── compute_policies.json
        ├── database_policies.json
        ├── network_policies.json
        └── security_policies.json
```

### 외부 AWS MCP 서버 (7개)

Strands Agent 기반으로 실행됩니다. 질문 유형에 따라 필요한 서버만 자동 선택됩니다.

| # | MCP 서버 | 패키지 | 도구 수 | 주요 용도 |
|---|---|---|---|---|
| 1 | 💰 AWS Billing | `awslabs.billing-cost-management-mcp-server` | 20+ | 비용 청구, 예산, 이상 탐지 |
| 2 | 📈 Cost Explorer | `awslabs.cost-explorer-mcp-server` | 7 | 비용 비교, 예측, 드라이버 분석 |
| 3 | 📚 AWS Knowledge | `awslabs.aws-documentation-mcp-server` | 4 | AWS 공식 문서 검색 |
| 4 | 💵 AWS Pricing | `awslabs.aws-pricing-mcp-server` | 5 | 서비스 가격 조회 |
| 5 | 📊 CloudWatch | `awslabs.cloudwatch-mcp-server` | 11 | 메트릭, 로그, 알람 |
| 6 | 🔍 CloudTrail | `awslabs.cloudtrail-mcp-server` | 5 | API 이벤트, 감사 로그 |
| 7 | 🔐 IAM | `awslabs.iam-mcp-server` | 29 | 사용자/역할/정책 실시간 조회 |

---

## ⚙️ MCP 설정 파일

### mcp_config.json

```json
{
  "mcpServers": {
    "cmdb-server": {
      "command": "python",
      "args": ["mcp_server.py"],
      "env": {
        "AWS_DEFAULT_REGION": "us-east-1"
      }
    },
    "aws-billing": {
      "command": "uvx",
      "args": ["awslabs.billing-cost-management-mcp-server@latest"],
      "env": {
        "AWS_REGION": "us-east-1",
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    },
    "aws-cost-explorer": {
      "command": "uvx",
      "args": ["awslabs.cost-explorer-mcp-server@latest"],
      "env": {
        "AWS_REGION": "us-east-1",
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    },
    "aws-knowledge": {
      "command": "uvx",
      "args": ["awslabs.aws-documentation-mcp-server@latest"],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    },
    "aws-pricing": {
      "command": "uvx",
      "args": ["awslabs.aws-pricing-mcp-server@latest"],
      "env": {
        "AWS_REGION": "us-east-1",
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    },
    "aws-cloudwatch": {
      "command": "uvx",
      "args": ["awslabs.cloudwatch-mcp-server@latest"],
      "env": {
        "AWS_REGION": "us-east-1",
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    },
    "aws-cloudtrail": {
      "command": "uvx",
      "args": ["awslabs.cloudtrail-mcp-server@latest"],
      "env": {
        "AWS_REGION": "us-east-1",
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    },
    "aws-iam": {
      "command": "uvx",
      "args": ["awslabs.iam-mcp-server@latest"],
      "env": {
        "AWS_REGION": "us-east-1",
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    }
  }
}
```

---

## 🚀 실행 방법

### 1. 사전 요구사항

- Python 3.13+
- uv / uvx 설치 (`pip install uv`)
- AWS 자격증명 설정

### 2. 환경 설정

```bash
# 가상환경 생성
python3 -m venv cmdbmcp313_new
source cmdbmcp313_new/bin/activate

# 패키지 설치
pip install -r requirements.txt

# 환경 변수 설정
cp .env.example .env
# .env 파일에 실제 AWS 자격증명 입력
```

### 3. .env 파일 설정

```bash
# AWS 자격증명
AWS_ACCESS_KEY_ID=YOUR_ACCESS_KEY_HERE
AWS_SECRET_ACCESS_KEY=YOUR_SECRET_KEY_HERE

# S3 CMDB 버킷
S3_CMDB_BUCKET=mwaa-cmdb-bucket

# Bedrock 설정 (us. 접두사 필수)
BEDROCK_REGION=us-east-1
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-20250514-v1:0
```

### 4. 실행

```bash
# 통합 실행 스크립트 (권장)
./run.sh

# 또는 직접 실행
python -m streamlit run streamlit_app.py --server.port 8505
```

**접속 URL:** http://localhost:8505

---

## 🖥️ UI 구성

### 사이드바

```
🔍 CMDB 설정
S3 버킷: [mwaa-cmdb-bucket]

─────────────────────────
🔧 데이터 소스 설정

☑ 📊 CMDB (S3 데이터)
   조직 내 AWS 리소스 현황 (IAM, EC2, S3 등)

☑ ☁️ AWS MCP
   💰 Billing  📈 Cost Explorer  📚 Knowledge
   💵 Pricing  📊 CloudWatch  🔍 CloudTrail  🔐 IAM

✅ 활성화: 📊 CMDB · ☁️ AWS MCP
```

### 탭 구성

| 탭 | 기능 |
|---|---|
| 💬 챗봇 | 자연어 질문으로 AWS 리소스/비용/보안 조회 |
| 📊 대시보드 | 카테고리별 리소스 수 차트, 파이 차트 |
| 🔍 데이터 탐색 | S3 CMDB 데이터 직접 조회 및 JSON 뷰어 |

### 답변 형식

```
[AI 분석 답변]

---
🔌 활용된 MCP 서버: 📊 CMDB (S3) · 📈 AWS Cost Explorer
```

---

## 💬 추천 질문 예시

### 🔐 IAM / 보안

**현황 파악**
- "IAM 역할이 몇 개나 있지?"
- "IAM 사용자 현황 알려줘"
- "관리자 권한을 가진 역할들 보여줘"

**상세 분석**
- "CloudWatch 권한이 있는 역할은?"
- "S3 관련 권한을 가진 정책들은?"
- "액세스 키 만료된 사용자 있어?"

### 💰 비용 분석

- "지난달 대비 이번달 비용 특이사항 나열해줘"
- "서비스별 비용 증가 원인 분석해줘"
- "EC2 비용 최적화 방안은?"
- "다음달 예상 비용은?"

### 🖥️ 리소스 현황

- "현재 조직 내 어카운트별 6세대 이하 인스턴스 목록과 최신세대로 업그레이드하는 방법"
- "S3 버킷이 몇 개 있어?"
- "RDS 데이터베이스 목록 보여줘"
- "VPC 네트워크 구성은 어떻게 돼?"

### 📊 모니터링

- "EC2 CPU 사용률 확인해줘"
- "Lambda 에러 로그 분석해줘"
- "현재 CloudWatch 알람 상태는?"

### 🔍 감사 / 변경 이력

- "누가 S3 버킷 설정을 변경했어?"
- "최근 IAM 역할 변경 이력 보여줘"
- "어제 콘솔 로그인 기록 확인해줘"

### 📚 가이드 / 문서

- "EC2 인스턴스 타입 변경 시 주의사항"
- "S3 보안 베스트 프랙티스"
- "RDS 백업 설정 방법"

---

## 🔐 필수 IAM 권한

### 전체 통합 정책 (모든 MCP 한번에 적용)

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "S3CMDBAccess",
            "Effect": "Allow",
            "Action": ["s3:GetObject", "s3:ListBucket"],
            "Resource": [
                "arn:aws:s3:::mwaa-cmdb-bucket",
                "arn:aws:s3:::mwaa-cmdb-bucket/*"
            ]
        },
        {
            "Sid": "BedrockAccess",
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream"
            ],
            "Resource": "*"
        },
        {
            "Sid": "CostExplorerAccess",
            "Effect": "Allow",
            "Action": [
                "ce:GetCostAndUsage",
                "ce:GetCostAndUsageComparisons",
                "ce:GetCostComparisonDrivers",
                "ce:GetCostForecast",
                "ce:GetDimensionValues",
                "ce:GetTagValues",
                "ce:GetAnomalies",
                "ce:GetAnomalyMonitors",
                "ce:GetReservationCoverage",
                "ce:GetReservationUtilization",
                "ce:GetSavingsPlansCoverage",
                "ce:GetSavingsPlansUtilization"
            ],
            "Resource": "*"
        },
        {
            "Sid": "BudgetsAccess",
            "Effect": "Allow",
            "Action": [
                "budgets:ViewBudget",
                "budgets:DescribeBudgets",
                "budgets:DescribeBudgetActionsForAccount"
            ],
            "Resource": "*"
        },
        {
            "Sid": "PricingAccess",
            "Effect": "Allow",
            "Action": [
                "pricing:GetProducts",
                "pricing:DescribeServices",
                "pricing:GetAttributeValues"
            ],
            "Resource": "*"
        },
        {
            "Sid": "CloudWatchAccess",
            "Effect": "Allow",
            "Action": [
                "cloudwatch:GetMetricData",
                "cloudwatch:GetMetricStatistics",
                "cloudwatch:ListMetrics",
                "cloudwatch:DescribeAlarms",
                "cloudwatch:DescribeAlarmHistory",
                "logs:DescribeLogGroups",
                "logs:DescribeLogStreams",
                "logs:GetLogEvents",
                "logs:FilterLogEvents",
                "logs:StartQuery",
                "logs:GetQueryResults",
                "logs:StopQuery"
            ],
            "Resource": "*"
        },
        {
            "Sid": "CloudTrailAccess",
            "Effect": "Allow",
            "Action": [
                "cloudtrail:LookupEvents",
                "cloudtrail:GetTrail",
                "cloudtrail:ListTrails",
                "cloudtrail:DescribeTrails",
                "cloudtrail:ListEventDataStores",
                "cloudtrail:StartQuery",
                "cloudtrail:GetQueryResults",
                "cloudtrail:DescribeQuery"
            ],
            "Resource": "*"
        },
        {
            "Sid": "IAMReadAccess",
            "Effect": "Allow",
            "Action": [
                "iam:ListUsers", "iam:GetUser",
                "iam:ListRoles", "iam:GetRole",
                "iam:ListGroups", "iam:GetGroup",
                "iam:ListPolicies", "iam:GetPolicy", "iam:GetPolicyVersion",
                "iam:ListUserPolicies", "iam:GetUserPolicy",
                "iam:ListRolePolicies", "iam:GetRolePolicy",
                "iam:ListAttachedUserPolicies", "iam:ListAttachedRolePolicies",
                "iam:ListAccessKeys", "iam:SimulatePrincipalPolicy"
            ],
            "Resource": "*"
        }
    ]
}
```

> ⚠️ 현재 알려진 권한 제한사항:
> - `ce:GetCostAndUsageComparisons` — 전월 대비 비교 기능 (별도 활성화 필요)
> - `ce:GetCostComparisonDrivers` — 비용 증가 원인 분석
> - `ce:GetAnomalies` — 비용 이상 탐지
>
> 위 권한이 없으면 `get_cost_and_usage`로 각 월 데이터를 개별 조회하여 수동 비교합니다.

---

## 🔒 보안 및 익명화

### 2단계 자동 익명화

**1단계: 데이터 로드 시**
- S3 CMDB 데이터를 가져올 때 자동 익명화

**2단계: AI 답변 생성 후**
- AI 답변에 포함된 민감 정보도 자동 마스킹

**마스킹 항목:**

| 항목 | 예시 |
|---|---|
| AWS 계정 ID | `123*********` |
| ARN 계정 부분 | `arn:aws:iam::123*********:role/...` |
| Access Key | `ABCDEFG*************` |
| IP 주소 | `10.0.*.**` |
| 이메일 | `***@***.***` |

**보존 항목:** 역할명, 정책명, 서비스명 (분석에 필요)

---

## 📁 프로젝트 구조

```
cmdb_mcp/
├── streamlit_app.py        # 메인 Streamlit 챗봇 앱
├── mcp_server.py           # 내부 CMDB MCP 서버 (S3 조회)
├── mcp_config.json         # MCP 서버 설정 (Claude Desktop 연동용)
├── requirements.txt        # Python 패키지
├── run.sh                  # 통합 실행 스크립트
```

---

## 🛠️ 트러블슈팅

### 1. MCP 서버 오류: ValidationException

```
An error occurred (ValidationException) when calling the ConverseStream operation
```

**원인:** Bedrock 모델 ID 형식 오류

**해결:** `.env`에서 `us.` 접두사 확인
```bash
# 잘못된 예
BEDROCK_MODEL_ID=anthropic.claude-sonnet-4-20250514-v1:0

# 올바른 예
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-20250514-v1:0
```

### 2. Cost Explorer 권한 오류

```
AccessDeniedException: not authorized to perform: ce:GetCostAndUsageComparisons
```

**해결:** IAM 사용자에 위 통합 정책 추가

### 3. uvx 없음 오류

```
FileNotFoundError: uvx not found
```

**해결:**
```bash
pip install uv
# 또는
brew install uv
```

### 4. AI가 데이터를 찾지 못하는 경우

**증상:** 데이터가 있는데 "없다"고 답변

**해결:**
1. 더 구체적으로 질문: "IAM 역할 중 CloudWatch 관련 역할 찾아줘"
2. 데이터 탐색 탭에서 직접 확인
3. 질문을 단계별로 나눠서 하기

