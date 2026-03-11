# 🔍 CMDB MCP 서버 & Streamlit 챗봇

S3에 저장된 AWS/GCP CMDB 정책 데이터를 MCP 서버로 제공하고, Streamlit 챗봇으로 대화형 조회를 지원합니다.

## 📋 프로젝트 개요

### 🎯 주요 기능

1. **내부 MCP 서버**: S3 CMDB 데이터를 AI가 사용할 수 있는 "도구"로 제공
2. **외부 MCP 서버 통합**: AWS Billing, Cost Explorer, Knowledge, Pricing 연동
3. **유연한 MCP 선택**: UI 토글로 필요한 MCP만 선택적 활성화
4. **Streamlit 챗봇**: Bedrock AI를 활용한 대화형 CMDB 조회
5. **통합 분석**: 여러 MCP 데이터를 종합하여 인사이트 제공
6. **대시보드**: 리소스 현황 시각화
7. **데이터 탐색**: 카테고리별 상세 데이터 조회

### 💡 MCP(Model Context Protocol)란?

**MCP는 AI 모델이 외부 데이터와 도구에 접근할 수 있게 해주는 표준 프로토콜입니다.**

- **일반적인 방식**: AI에게 모든 데이터를 텍스트로 전달 → 토큰 낭비, 느림
- **MCP 방식**: AI가 필요할 때 "도구"를 호출해서 데이터 조회 → 효율적, 빠름

**이 프로젝트에서:**
- 내부 MCP 서버가 S3 CMDB 데이터를 8개의 "도구"로 제공
- 외부 AWS MCP 서버들이 비용, 문서, 가격 정보 제공
- AI가 질문을 분석해서 필요한 도구만 선택적으로 호출
- 여러 MCP 서버의 데이터를 통합하여 종합적인 인사이트 제공

## 🏗️ 아키텍처

```
┌─────────────┐
│   S3 CMDB   │  ← 실제 CMDB 데이터 저장소
│   Bucket    │     (IAM, S3, EC2, RDS 등)
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────┐
│              MCP 통합 레이어                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ 내부 CMDB│  │AWS Billing│  │AWS Cost  │      │
│  │ MCP 서버 │  │ MCP 서버  │  │Explorer  │ ...  │
│  └──────────┘  └──────────┘  └──────────┘      │
└─────────────────────────────────────────────────┘
       │
       ▼
┌─────────────┐
│  Streamlit  │  ← 사용자 질문 받음
│   챗봇       │     "지난 달 비용 증가 원인은?"
│  (UI 토글)  │     ☑ CMDB ☑ Cost Explorer
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Bedrock    │  ← AI가 필요한 도구 선택
│  Claude 3   │     → 여러 MCP 도구 호출
└─────────────┘     → 통합 데이터 분석 후 답변
```

**데이터 흐름:**
1. 사용자가 질문 입력 + MCP 서버 선택 (UI 토글)
2. AI가 질문 분석 → 활성화된 MCP 서버에서 필요한 도구 선택
3. 여러 MCP 서버에서 병렬로 데이터 조회
4. AI가 통합 데이터 분석 후 종합적인 답변 생성

## 📊 MCP 서버 도구

### 내부 CMDB MCP 서버

S3에 저장된 조직 내 AWS 리소스 데이터를 제공합니다.

#### 1. 정책 조회 도구 (카테고리별 데이터 조회)
- `get_identity_policies`: IAM, Organizations, Cognito 정책
- `get_storage_policies`: S3, EFS, FSx 정책
- `get_compute_policies`: EC2, Lambda, ECS 정책
- `get_database_policies`: RDS, DynamoDB 정책
- `get_network_policies`: VPC, CloudFront, Route53 정책
- `get_security_policies`: KMS, Secrets Manager, WAF 정책

#### 2. 검색 및 분석 도구
- `search_resources`: 리소스 검색 (이름, 타입, 태그 등)
- `get_resource_summary`: 전체 리소스 요약 통계

### 외부 AWS MCP 서버

#### 1. 💰 AWS Billing & Cost Management
비용 청구 및 결제 정보를 제공합니다.

**사용 예시:**
- "이번 달 AWS 비용은 얼마야?"
- "지난 달 청구 내역 보여줘"

#### 2. 📈 AWS Cost Explorer
비용 분석 및 예측 기능을 제공합니다.

**사용 예시:**
- "지난 달 대비 비용 증가 원인 분석해줘"
- "다음 달 예상 비용은?"
- "비용 특이사항 있어?"

#### 3. 📚 AWS Knowledge
AWS 공식 문서 및 베스트 프랙티스를 제공합니다.

**사용 예시:**
- "EC2 6세대를 7세대로 업그레이드하는 방법"
- "S3 보안 베스트 프랙티스"
- "Lambda 성능 최적화 가이드"

#### 4. 💵 AWS Pricing
AWS 서비스 가격 정보를 제공합니다.

**사용 예시:**
- "EC2 t3.medium 가격은?"
- "S3 스토리지 비용 계산"

### MCP 서버 활성화 방법

**Streamlit 사이드바에서 원하는 MCP 서버 선택:**

```
🔧 MCP 서버 설정
☑ 📊 내부 CMDB (S3 데이터)
☐ 💰 AWS Billing & Cost Management
☑ 📈 AWS Cost Explorer
☑ 📚 AWS Knowledge
☐ 💵 AWS Pricing

✅ 활성화된 MCP 서버: 3개
```

**특징:**
- 여러 MCP 서버를 동시에 활성화 가능
- 질문에 따라 적절한 MCP 도구가 자동으로 선택됨
- 필요한 MCP만 선택하여 응답 속도 최적화

### 3. 도구 사용 예시

**사용자 질문**: "IAM 정책 현황은?"

```
1. AI 분석: "이 질문에는 get_identity_policies 도구가 필요"
2. MCP 호출: call_mcp_tool("get_identity_policies")
3. S3 조회: aws-policies/20241223/identity_policies.json
4. 데이터 반환: {"123456789012": {"IAM": [...]}}
5. AI 답변: "현재 IAM 사용자는 5명이며..."
```

**주요 특징:**
- ✅ 자동 익명화: 계정 ID, ARN 등 민감 정보 보호
- ✅ 정책명/역할명 보존: 비즈니스 로직 파악용
- ✅ 실시간 S3 데이터 연동
- ✅ 날짜별 히스토리 조회 가능
- ✅ AI 답변 익명화: 답변에 포함된 계정 번호도 자동 마스킹 (예: 70********* )

## 🤖 AI 모델 설정

### Bedrock 사용 (기본)
기본적으로 AWS Bedrock Claude 3.5 Sonnet을 사용합니다.

```bash
# .env 파일에서 설정
BEDROCK_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

### Local LLM Endpoint 사용
Ollama, LM Studio 등 로컬 LLM을 사용하려면:

1. **.env 파일 수정**:
```bash
# Bedrock 대신 로컬 LLM 사용
USE_LOCAL_LLM=true
LOCAL_LLM_ENDPOINT=http://localhost:11434/v1/chat/completions
LOCAL_LLM_MODEL=llama3.1:8b

```

2. **streamlit_app.py 수정**:
```python
# query_bedrock 함수를 다음으로 교체:
def query_local_llm(prompt, context=""):
    """로컬 LLM을 사용한 AI 응답 생성"""
    import requests
    import os
    
    endpoint = os.getenv('LOCAL_LLM_ENDPOINT')
    model = os.getenv('LOCAL_LLM_MODEL')
    
    full_prompt = f"""
당신은 AWS CMDB 전문가입니다. 다음 CMDB 데이터를 바탕으로 질문에 답해주세요.

CMDB 데이터:
{context}

질문: {prompt}

답변은 한국어로, 구체적이고 실용적으로 제공해주세요.
"""
    
    try:
        response = requests.post(endpoint, json={
            "model": model,
            "messages": [{"role": "user", "content": full_prompt}],
            "max_tokens": 2000,
            "temperature": 0.7
        })
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"로컬 LLM 오류: {str(e)}"

# main() 함수에서 사용:
if os.getenv('USE_LOCAL_LLM') == 'true':
    response = query_local_llm(prompt, context)
else:
    response = query_bedrock(prompt, context)
```

## 🚀 실행 방법

### 0. 사전 요구사항
```bash
# uvx 설치 (외부 MCP 서버 사용 시 필요)
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 설치 확인
uvx --version
```

### 1. 환경 설정
```bash
# .env 파일 수정
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
S3_CMDB_BUCKET=mwaa-cmdb-bucket
```

### 2. 통합 실행 (권장)
```bash
./run.sh
```

**자동으로 실행되는 것들:**
- 가상환경 생성 및 활성화
- 패키지 설치
- MCP 서버 자동 시작
- Streamlit 챗봇 실행

### 3. 수동 실행 (개발용)
```bash
# MCP 서버 별도 실행 (선택사항)
python mcp_server.py &

# Streamlit 실행
streamlit run streamlit_app.py --server.port=8503 --server.address=0.0.0.0
```

**접속 URL:**
- 로컬: http://localhost:8503

## 💬 챗봇 사용 예시

### 🔗 통합 분석 질문 (여러 MCP 활용)

#### DevOps - 리소스 현황 파악
**활성화 MCP:** 내부 CMDB + AWS Knowledge
```
"현재 조직 내 6세대 이하 EC2 인스턴스 목록과 최신 세대로 업그레이드하는 방법 알려줘"
```

**예상 답변:**
- CMDB에서 6세대 이하 인스턴스 목록 추출 (t2, m4 등)
- AWS Knowledge에서 업그레이드 가이드 제공
- 단계별 마이그레이션 방법 및 주의사항
- 예상 성능 향상 및 비용 절감 효과

#### FinOps - 비용 최적화
**활성화 MCP:** 내부 CMDB + AWS Cost Explorer + AWS Billing
```
"지난 달 대비 비용 증가 원인 분석하고, 사용하지 않는 리소스 찾아줘"
```

**예상 답변:**
- Cost Explorer: 서비스별 비용 증가 분석 (EC2 +23%, S3 +15%)
- CMDB: 미사용 리소스 식별 (미연결 EBS 3개, 미할당 EIP 2개)
- 통합 인사이트: 신규 프로젝트의 EC2 증가가 주요 원인
- 예상 절감액: 월 $52.2

#### Security - 보안 취약점 분석
**활성화 MCP:** 내부 CMDB + AWS Knowledge
```
"퍼블릭 액세스가 허용된 S3 버킷과 보안 그룹 설정 문제 찾아줘"
```

**예상 답변:**
- CMDB: 퍼블릭 S3 버킷 2개, 0.0.0.0/0 오픈 보안 그룹 3개 발견
- AWS Knowledge: 보안 베스트 프랙티스 제공
- 권장 조치: 버킷 정책 검토, CloudFront 사용, 보안 그룹 IP 제한

#### Compliance - 규정 준수 체크
**활성화 MCP:** 내부 CMDB + AWS Knowledge
```
"PCI-DSS 규정에 맞게 설정된 리소스 확인하고 개선 방안 제시해줘"
```

### 📊 내부 CMDB 전용 질문

### 🔐 IAM 정책 관련 질문들

**📊 현황 파악**
- "IAM 정책이 총 몇 개 있어?"
- "IAM 역할이 몇 개나 있지?"
- "IAM 사용자 현황 알려줘"
- "IAM 그룹은 어떻게 구성되어 있어?"

**🔍 상세 분석**
- "관리형 정책과 인라인 정책 비율은?"
- "AWS 관리형 정책 vs 고객 관리형 정책 현황은?"
- "가장 많이 사용되는 IAM 정책은 뭐야?"
- "권한이 가장 많은 역할은?"

**🚨 보안 관련**
- "관리자 권한을 가진 역할들 보여줘"
- "PowerUser 권한을 가진 리소스는?"
- "S3 관련 권한을 가진 정책들은?"
- "EC2 관련 권한이 있는 역할들은?"

**📈 정책 분석**
- "정책별 연결된 리소스 수는?"
- "사용되지 않는 정책이 있어?"
- "가장 복잡한 정책은 어떤 거야?"
- "특정 서비스에 대한 권한 현황은?"

**🔎 검색 질문**
- "ReadOnly 권한 관련 정책들 찾아줘"
- "Lambda 관련 정책 있어?"
- "CloudWatch 권한이 있는 역할은?"
- "특정 정책명으로 검색해줘"


### 챗봇 기능
1. **자연어 질문**: 일상 언어로 CMDB 조회
2. **컨텍스트 인식**: 질문에 맞는 데이터 자동 로드
3. **상세 분석**: Bedrock AI가 데이터 분석 및 설명

## 📊 대시보드 기능

### 1. 리소스 요약
- 카테고리별 리소스 수 차트
- 리소스 분포 파이 차트
- 총 리소스 수 메트릭

### 2. 데이터 탐색
- 카테고리별 데이터 조회
- 날짜별 히스토리 조회
- JSON 원본 데이터 확인
- 테이블 형식 데이터 표시

## 🔧 MCP 서버 통합

### Claude Desktop 설정
`~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "cmdb-server": {
      "command": "python",
      "args": ["/path/to/cmdb_mcp/mcp_server.py"],
      "env": {
        "AWS_DEFAULT_REGION": "us-east-1"
      }
    }
  }
}
```


## 🔐 필수 권한

### AWS IAM 권한
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::mwaa-cmdb-bucket",
                "arn:aws:s3:::mwaa-cmdb-bucket/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel"
            ],
            "Resource": "*"
        }
    ]
}
```

## ⚙️ 설정 파일

### mcp_config.json
MCP 서버 설정을 관리합니다.

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
        "AWS_PROFILE": "default",
        "AWS_REGION": "us-east-1"
      }
    },
    "aws-cost-explorer": {
      "command": "uvx",
      "args": ["awslabs.cost-explorer-mcp-server@latest"],
      "env": {
        "AWS_PROFILE": "default",
        "AWS_REGION": "us-east-1"
      }
    }
  }
}
```

### .env 파일
AWS 자격증명 및 환경 변수를 설정합니다.

```bash
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=us-east-1
AWS_PROFILE=default
```

## 🔒 보안 및 익명화

### 자동 익명화 기능

이 프로젝트는 **2단계 익명화**로 민감 정보를 보호합니다:

**1단계: 데이터 로드 시 익명화**
- S3에서 데이터를 가져올 때 자동 익명화
- 계정 ID:  `70*********`
- ARN:  `arn:aws:iam::70*********:role/...`
- Access Key:`A*****************`
- IP 주소:  → `10.0.*.**`

**2단계: AI 답변 익명화**
- AI가 생성한 답변에서도 민감 정보 자동 마스킹
- 답변에 계정 번호가 포함되어도 자동으로 `***` 처리
- 이메일, IP 주소 등도 자동 마스킹

**보존되는 정보**:
- ✅ IAM 역할명, 정책명 (비즈니스 로직 파악용)
- ✅ 리소스 이름 (분석용)
- ✅ 서비스명, 리전명




### 5. AI가 데이터를 찾지 못하는 경우

**증상**: "CloudWatch 권한이 있는 역할은?"이라고 물었는데 "데이터가 없다"고 답변

**원인**:
- AI가 잘못된 도구를 선택
- 데이터 크기 제한으로 일부 데이터만 전달됨 (가장 흔한 원인)
- 검색 키워드가 데이터와 매칭되지 않음

**해결 방법**:

1. **더 구체적으로 질문하기**
   - ❌ "CloudWatch 권한"
   - ✅ "IAM 역할 중에서 CloudWatch가 포함된 역할 찾아줘"
   - ✅ "cloudwatch 또는 logs가 포함된 IAM 역할"

2. **카테고리 명시하기**
   - ❌ "권한 있는 역할"
   - ✅ "IAM 역할 목록에서 CloudWatch 관련 역할"

3. **데이터 탐색 탭 사용 (가장 확실한 방법)**
   - 챗봇 대신 "데이터 탐색" 탭에서 `identity_policies` 직접 조회
   - 원본 JSON 데이터 확인
   - 브라우저 검색 (Ctrl+F)으로 "cloudwatch" 검색




## 📝 사용 팁

### 효과적인 질문 방법
1. **구체적으로**: "IAM 정책" 보다 "IAM 사용자 정책 목록"
2. **카테고리 명시**: "보안 관련 리소스 현황"
3. **비교 요청**: "지난주와 비교해서 변경된 리소스"
4. **MCP 조합 활용**: 여러 MCP를 활성화하여 통합 인사이트 얻기

### MCP 서버 선택 가이드

**DevOps 작업:**
- ☑ 내부 CMDB (리소스 현황)
- ☑ AWS Knowledge (가이드)

**비용 분석:**
- ☑ 내부 CMDB (리소스 현황)
- ☑ AWS Cost Explorer (비용 분석)
- ☑ AWS Billing (청구 정보)

**보안 감사:**
- ☑ 내부 CMDB (리소스 현황)
- ☑ AWS Knowledge (보안 베스트 프랙티스)

**가격 비교:**
- ☑ AWS Pricing (가격 정보)
- ☑ AWS Cost Explorer (실제 사용 비용)

### 대시보드 활용
1. 먼저 대시보드에서 전체 현황 파악
2. 관심 카테고리를 데이터 탐색에서 상세 조회
3. 챗봇으로 구체적인 질문

## 🎓 사용 시나리오

### 시나리오 1: 비용 급증 원인 분석
```
1. MCP 활성화: CMDB + Cost Explorer + Billing
2. 질문: "지난 달 대비 비용이 30% 증가했는데 원인이 뭐야?"
3. 결과:
   - Cost Explorer: 서비스별 비용 증가 분석
   - CMDB: 신규 생성된 리소스 식별
   - 통합 인사이트: 특정 프로젝트의 EC2 인스턴스 증가가 주요 원인
```

### 시나리오 2: 레거시 인프라 현대화
```
1. MCP 활성화: CMDB + Knowledge
2. 질문: "6세대 이하 인스턴스를 최신 세대로 업그레이드하는 로드맵 만들어줘"
3. 결과:
   - CMDB: 현재 6세대 이하 인스턴스 목록 (t2, m4 등)
   - Knowledge: 세대별 업그레이드 가이드
   - 통합 인사이트: 단계별 마이그레이션 계획 + 예상 비용 절감액
```

### 시나리오 3: 보안 감사 준비
```
1. MCP 활성화: CMDB + Knowledge
2. 질문: "보안 감사를 위해 취약한 설정 찾고 개선 방안 제시해줘"
3. 결과:
   - CMDB: 0.0.0.0/0 오픈된 보안 그룹, 퍼블릭 S3 버킷 등
   - Knowledge: AWS 보안 베스트 프랙티스
   - 통합 인사이트: 우선순위별 개선 조치 리스트
```

## 🐛 트러블슈팅

### asyncio 이벤트 루프 충돌 (해결됨)

**증상:** "Cannot run the event loop while another loop is running" 오류

**원인:** Streamlit 환경에서 asyncio 이벤트 루프가 이미 실행 중인 상태에서 새로운 루프를 생성하려고 시도

**해결 방법:**
이 프로젝트는 `nest-asyncio` 패키지를 사용하여 이 문제를 해결했습니다.

```python
# streamlit_app.py 상단에 추가됨
import nest_asyncio
nest_asyncio.apply()  # Streamlit 환경에서 asyncio 이벤트 루프 중첩 허용
```

**설치 확인:**
```bash
pip list | grep nest-asyncio
# nest-asyncio 1.6.0 (또는 최신 버전)
```

만약 설치되지 않았다면:
```bash
pip install nest-asyncio
```

### 외부 MCP 서버 연결 실패

**증상:** "MCP 서버 연결 실패" 오류

**해결 방법:**
1. `uvx` 설치 확인
   ```bash
   uvx --version
   ```
   
2. AWS 자격증명 확인
   ```bash
   aws sts get-caller-identity
   ```
   
3. 인터넷 연결 확인 (외부 MCP 서버 다운로드 필요)

4. AWS 프로필 설정
   ```bash
   export AWS_PROFILE=default
   ```

### MCP 서버 응답 느림

**원인:** 여러 MCP 서버 동시 호출

**해결 방법:**
- 필요한 MCP만 선택적으로 활성화
- 질문을 구체적으로 작성하여 불필요한 도구 호출 방지

### 기존 트러블슈팅

