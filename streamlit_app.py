import streamlit as st
import boto3
import json
from datetime import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
from dotenv import load_dotenv
import asyncio
import nest_asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Strands Agent (awsops 패턴)
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

# Streamlit 환경에서 asyncio 이벤트 루프 중첩 허용
nest_asyncio.apply()

# 환경 변수 로드
load_dotenv()

# AWS 자격증명 환경변수 설정 (MCP 서버에서도 사용)
os.environ.setdefault('AWS_ACCESS_KEY_ID', os.getenv('AWS_ACCESS_KEY_ID', ''))
os.environ.setdefault('AWS_SECRET_ACCESS_KEY', os.getenv('AWS_SECRET_ACCESS_KEY', ''))
os.environ.setdefault('AWS_DEFAULT_REGION', os.getenv('BEDROCK_REGION', 'us-east-1'))

# AWS Bedrock 설정
bedrock = boto3.client('bedrock-runtime', region_name=os.getenv('BEDROCK_REGION', 'us-east-1'))
s3_client = boto3.client('s3')

# Strands Bedrock 모델
strands_model = BedrockModel(
    model_id=os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-20250514-v1:0'),
    region_name=os.getenv('BEDROCK_REGION', 'us-east-1'),
)

# 페이지 설정
st.set_page_config(
    page_title="🔍 CMDB 챗봇",
    page_icon="🔍",
    layout="wide"
)

# 사이드바 설정
st.sidebar.title("🔍 CMDB 설정")
S3_BUCKET = st.sidebar.text_input("S3 버킷", value="mwaa-cmdb-bucket")

# MCP 서버 설정
st.sidebar.markdown("---")
st.sidebar.subheader("🔧 데이터 소스 설정")

# 세션 상태 초기화 — mcp_config.json에서 서버 목록 동적 로드
def get_external_server_names():
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'mcp_config.json')
        with open(config_path, 'r') as f:
            config = json.load(f)
        return [name for name, cfg in config['mcpServers'].items() if not cfg.get('internal')]
    except Exception:
        return ['billing', 'cost_explorer', 'knowledge', 'pricing', 'cloudwatch', 'cloudtrail', 'iam']

if 'mcp_servers' not in st.session_state:
    st.session_state.mcp_servers = {'cmdb': True}
    for name in get_external_server_names():
        st.session_state.mcp_servers[name] = False

# 체크박스 2개로 통합
enable_cmdb = st.sidebar.checkbox(
    "📊 CMDB (S3 데이터)",
    value=st.session_state.mcp_servers['cmdb'],
    help="조직 내 AWS 리소스 현황 (IAM, EC2, S3 등)"
)

enable_aws_mcp = st.sidebar.checkbox(
    "☁️ AWS MCP",
    value=any(
        v for k, v in st.session_state.mcp_servers.items() if k != 'cmdb'
    ),
    help="💰 Billing  📈 Cost Explorer  📚 Knowledge  💵 Pricing  📊 CloudWatch  🔍 CloudTrail  🔐 IAM"
)

# 체크박스 상태를 mcp_servers에 반영
st.session_state.mcp_servers['cmdb'] = enable_cmdb
for name in get_external_server_names():
    st.session_state.mcp_servers[name] = enable_aws_mcp

# 활성화 상태 표시
active_labels = []
if enable_cmdb:
    active_labels.append("📊 CMDB")
if enable_aws_mcp:
    active_labels.append("☁️ AWS MCP")

if active_labels:
    st.sidebar.success(f"✅ 활성화: {' · '.join(active_labels)}")
else:
    st.sidebar.warning("⚠️ 데이터 소스를 선택해주세요")

def get_latest_date():
    """S3에서 가장 최근 날짜 폴더 찾기"""
    try:
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET,
            Prefix='aws-policies/',
            Delimiter='/'
        )
        dates = [p['Prefix'].split('/')[-2] for p in response.get('CommonPrefixes', [])]
        return max(dates) if dates else datetime.now().strftime('%Y%m%d')
    except Exception as e:
        st.error(f"날짜 조회 오류: {e}")
        return datetime.now().strftime('%Y%m%d')

def list_s3_structure():
    """S3 버킷 구조 확인"""
    try:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, MaxKeys=20)
        return [obj['Key'] for obj in response.get('Contents', [])]
    except Exception as e:
        return [f"오류: {e}"]

import re

def anonymize_data(data):
    """민감 정보 익명화 (포괄적 버전)"""
    try:
        if isinstance(data, dict):
            # 딕셔너리 키도 익명화 처리
            anonymized_dict = {}
            for k, v in data.items():
                # 키가 AWS Account ID인지 확인
                if isinstance(k, str) and re.match(r'^\d{12}$', k):
                    anonymized_key = k[:3] + '*' * 9  # Account ID 익명화
                else:
                    anonymized_key = anonymize_data(k) if isinstance(k, str) else k
                
                anonymized_dict[anonymized_key] = anonymize_data(v)
            return anonymized_dict
        elif isinstance(data, list):
            return [anonymize_data(item) for item in data]
        elif isinstance(data, str):
            # 정책명/롤명/그룹명은 익명화하지 않음 (비즈니스 로직 파악에 필요)
            # AWS 리소스 이름 패턴 (정책, 롤, 그룹, 사용자명 등)
            if (len(data) < 100 and  # 너무 긴 문자열은 제외
                not re.match(r'^\d{12}$', data) and  # Account ID 아님
                not data.startswith('AKIA') and  # Access Key 아님
                not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', data) and  # IP 주소 아님
                not data.startswith('arn:aws:') and  # ARN 아님
                not '@' in data and  # 이메일 아님
                not re.match(r'^[A-Za-z0-9+/=_-]{40,}$', data)):  # 긴 토큰 아님 (40자 이상)
                # 일반적인 AWS 리소스 이름이라고 판단되면 그대로 반환
                return data
            # 1. 인증 정보 익명화
            # AWS Account ID (12자리)
            if re.match(r'^\d{12}$', data):
                return data[:3] + '*' * 9
            
            # Access Key ID
            if data.startswith('AKIA') and len(data) == 20:
                return data[:8] + '*' * 12
            
            # Secret Access Key (완전 마스킹)
            if len(data) == 40 and re.match(r'^[A-Za-z0-9+/]+$', data):
                return data[:4] + '*' * 36
            
            # API 키, 토큰 (긴 영숫자 문자열)
            if len(data) > 20 and re.match(r'^[A-Za-z0-9+/=_-]+$', data):
                return data[:4] + '*' * (len(data) - 4)
            
            # 2. 보안 설정 익명화
            # 내부 IP 주소 (10.x.x.x, 172.16-31.x.x, 192.168.x.x)
            if re.match(r'^(10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.)', data):
                parts = data.split('.')
                return f"{parts[0]}.{parts[1]}.*.**"
            
            # 일반 IP 주소
            if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', data):
                parts = data.split('.')
                return f"{parts[0]}.*.*.**"
            
            # 포트 범위 (1024-65535)
            if re.match(r'^\d{4,5}$', data) and 1024 <= int(data) <= 65535:
                return '***'
            
            # KMS Key ID (실제 키 값 마스킹, ID는 유지)
            if data.startswith('arn:aws:kms:') and 'key/' in data:
                return data  # KMS Key ID는 유지
            
            # 3. 내부 정보 익명화
            # 내부 도메인
            if re.match(r'.*\.(internal|local|corp|company)$', data):
                return '***.' + data.split('.')[-1]
            
            # 이메일 주소
            if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', data):
                return '***@***.***'
            
            # ARN 익명화 (계정 ID 부분만)
            if data.startswith('arn:aws:'):
                parts = data.split(':')
                if len(parts) >= 5 and re.match(r'^\d{12}$', parts[4]):
                    parts[4] = parts[4][:3] + '*' * 9
                    return ':'.join(parts)
            
            # AWS 리소스 ID
            if re.match(r'^(vpc|subnet|sg|i|vol|snap|ami|key|db|rtb|igw|nat|eni)-[a-zA-Z0-9]+$', data):
                prefix = data.split('-')[0]
                suffix = data.split('-')[1]
                if len(suffix) > 3:
                    return f"{prefix}-{suffix[:3]}***"
                else:
                    return f"{prefix}-***"
            
            # 정책명/롤명은 익명화하지 않음 (비즈니스 로직 파악에 필요)
            # PolicyName, RoleName, GroupName 등은 그대로 유지
            
            # 데이터베이스 연결 문자열
            if any(keyword in data.lower() for keyword in ['password=', 'pwd=', 'user=', 'uid=']):
                return '***'
            
            # 호스트명 (내부 서버)
            if re.match(r'^[a-zA-Z0-9-]+\.(internal|local|corp)$', data):
                return '***.' + data.split('.')[-1]
            
            return data
        else:
            return data
    except Exception as e:
        # 익명화 실패시 원본 데이터 반환
        return data

def load_cmdb_data(category, date=None, anonymize=True):
    """S3에서 CMDB 데이터 로드 (선택적 익명화)"""
    if not date:
        date = get_latest_date()
    
    key = f"aws-policies/{date}/{category}.json"
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
        data = json.loads(response['Body'].read().decode('utf-8'))
        # 익명화 선택적 적용
        if anonymize:
            return anonymize_data(data)
        else:
            return data
    except Exception as e:
        return {"error": str(e)}

# MCP 서버 자동 시작 - 더 이상 사용하지 않음 (직접 S3 조회로 대체)
# @st.cache_resource
# def start_mcp_server():
#     pass

def ensure_mcp_server_running():
    """MCP 서버 확인 - 더 이상 필요 없음 (직접 S3 조회)"""
    return True  # 항상 True 반환

# async def call_mcp_tool_async(tool_name, **kwargs):
#     """실제 MCP 서버 도구 호출 - 더 이상 사용하지 않음 (subprocess 방식으로 대체)"""
#     pass

def call_mcp_tool(tool_name, **kwargs):
    """MCP 도구를 직접 S3에서 데이터 조회로 대체 (asyncio 문제 완전 회피)"""
    try:
        # MCP 도구명을 카테고리로 변환
        tool_to_category = {
            'get_identity_policies': 'identity_policies',
            'get_storage_policies': 'storage_policies',
            'get_compute_policies': 'compute_policies',
            'get_database_policies': 'database_policies',
            'get_network_policies': 'network_policies',
            'get_security_policies': 'security_policies',
        }
        
        category = tool_to_category.get(tool_name)
        
        if category:
            # S3에서 직접 데이터 로드 (익명화 없이)
            date = kwargs.get('date', get_latest_date())
            data = load_cmdb_data(category, date, anonymize=False)
            return data
        
        elif tool_name == 'search_resources':
            # 검색 기능
            query = kwargs.get('query', '').lower()
            results = {}
            
            for cat in tool_to_category.values():
                data = load_cmdb_data(cat, anonymize=False)
                if query in json.dumps(data).lower():
                    results[cat] = data
            
            return results if results else {"message": "검색 결과 없음"}
        
        elif tool_name == 'get_resource_summary':
            # 요약 통계
            summary = {}
            for cat in tool_to_category.values():
                data = load_cmdb_data(cat, anonymize=False)
                if 'error' not in data:
                    summary[cat] = {
                        "total_accounts": len(data.keys()) if isinstance(data, dict) else 0,
                        "data_size": len(json.dumps(data, default=str))
                    }
            return summary
        
        else:
            return {"error": f"알 수 없는 도구: {tool_name}"}
            
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return {"error": f"{str(e)}\n\n상세:\n{error_detail}"}

async def call_external_mcp_tool_async(server_name, prompt):
    """외부 MCP 서버를 실제 MCP 프로토콜로 호출 (Python 3.13 + asyncio)"""
    
    # 서버별 명령어 설정
    server_commands = {
        'billing': {
            'command': 'uvx',
            'args': ['awslabs.billing-cost-management-mcp-server@latest']
        },
        'cost_explorer': {
            'command': 'uvx',
            'args': ['awslabs.cost-explorer-mcp-server@latest']
        },
        'knowledge': {
            'command': 'uvx',
            'args': ['awslabs.aws-documentation-mcp-server@latest']
        },
        'pricing': {
            'command': 'uvx',
            'args': ['awslabs.aws-pricing-mcp-server@latest']
        }
    }
    
    server_config = server_commands.get(server_name)
    if not server_config:
        return {"error": f"알 수 없는 MCP 서버: {server_name}"}
    
    try:
        # MCP 서버 파라미터 설정
        server_params = StdioServerParameters(
            command=server_config['command'],
            args=server_config['args'],
            env={
                'AWS_ACCESS_KEY_ID': os.getenv('AWS_ACCESS_KEY_ID', ''),
                'AWS_SECRET_ACCESS_KEY': os.getenv('AWS_SECRET_ACCESS_KEY', ''),
                'AWS_DEFAULT_REGION': os.getenv('BEDROCK_REGION', 'us-east-1'),
                'AWS_REGION': os.getenv('BEDROCK_REGION', 'us-east-1'),
                'FASTMCP_LOG_LEVEL': 'ERROR'
            }
        )
        
        # MCP 클라이언트로 서버 연결
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # 서버 초기화
                await session.initialize()
                
                # 사용 가능한 도구 목록 가져오기
                tools_result = await session.list_tools()
                tools = tools_result.tools
                
                if not tools:
                    return {"error": f"{server_name} 서버에 사용 가능한 도구가 없습니다"}
                
                # 적절한 도구 선택
                selected_tool = select_external_tool(tools, prompt, server_name)
                
                if not selected_tool:
                    return {
                        "message": f"{server_name} 서버에서 적절한 도구를 찾지 못했습니다",
                        "available_tools": [tool.name for tool in tools]
                    }
                
                # 도구 실행
                result = await session.call_tool(
                    selected_tool['name'],
                    arguments=selected_tool['args']
                )
                
                # 결과 파싱
                if result.content:
                    content_text = ""
                    for content in result.content:
                        if hasattr(content, 'text'):
                            content_text += content.text
                    
                    return {
                        "server": server_name,
                        "tool": selected_tool['name'],
                        "result": content_text,
                        "args": selected_tool['args']
                    }
                else:
                    return {"error": "도구 실행 결과가 비어있습니다"}
                    
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return {
            "error": f"{server_name} MCP 서버 호출 실패: {str(e)}",
            "detail": error_detail[:500]
        }

def call_external_mcp_tool(server_name, prompt):
    """외부 MCP 서버 호출 (동기 래퍼)"""
    try:
        # 새로운 이벤트 루프 생성하여 실행
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(call_external_mcp_tool_async(server_name, prompt))
            return result
        finally:
            loop.close()
    except Exception as e:
        import traceback
        return {
            "error": f"외부 MCP 호출 실패: {str(e)}",
            "detail": traceback.format_exc()[:500]
        }

# select_external_tool_simple 함수 제거됨 - 더 이상 사용하지 않음

def select_external_tool(tools, prompt, server_name):
    """외부 MCP 서버의 적절한 도구 선택 (개선된 버전)"""
    prompt_lower = prompt.lower()
    
    # 서버별 도구 매칭 규칙
    tool_selection_rules = {
        'billing': {
            'cost-comparison': ['지난달 대비', '전월 대비', '비교', '특이사항', '증가', '감소', '변화'],
            'cost-anomaly': ['이상', 'anomaly', '급증', '급감'],
            'cost-explorer': ['비용', '청구', '지출', '사용량', 'cost', 'usage', '지난달', '이번달'],
            'budgets': ['예산', 'budget', '한도'],
            'compute-optimizer': ['최적화', 'optimize', '권장사항', 'recommendation'],
            'default': 'cost-explorer'
        },
        'cost_explorer': {
            'get_cost_and_usage_comparisons': ['지난달 대비', '전월 대비', '비교', '특이사항', '증가', '감소', '변화'],
            'get_cost_comparison_drivers': ['원인', '드라이버', '이유'],
            'get_cost_and_usage': ['비용', '지출', '사용량', 'cost', 'usage', '지난달', '이번달'],
            'get_cost_forecast': ['예측', '예상', 'forecast', 'predict'],
            'default': 'get_cost_and_usage_comparisons'
        },
        'knowledge': {
            'search_documentation': ['방법', '어떻게', '가이드', 'how', 'guide', '업그레이드', '마이그레이션'],
            'read_documentation': ['문서', '상세', 'documentation', 'detail'],
            'default': 'search_documentation'
        },
        'pricing': {
            'get_products': ['가격', '요금', 'price', 'pricing', '얼마'],
            'get_attribute_values': ['속성', '옵션', 'attribute', 'option'],
            'default': 'get_products'
        }
    }
    
    rules = tool_selection_rules.get(server_name, {})
    default_tool = rules.get('default')
    
    # 키워드 기반 도구 선택
    for tool_name, keywords in rules.items():
        if tool_name == 'default':
            continue
        
        if any(kw in prompt_lower for kw in keywords):
            # 해당 도구가 실제로 존재하는지 확인
            for tool in tools:
                if tool_name in tool.name:
                    args = extract_tool_args(prompt, tool, server_name)
                    return {'name': tool.name, 'args': args}
    
    # 기본 도구 사용
    if default_tool:
        for tool in tools:
            if default_tool in tool.name:
                args = extract_tool_args(prompt, tool, server_name)
                return {'name': tool.name, 'args': args}
    
    # 첫 번째 도구 사용 (fallback)
    if tools:
        args = extract_tool_args(prompt, tools[0], server_name)
        return {'name': tools[0].name, 'args': args}
    
    return None

def extract_tool_args(prompt, tool, server_name):
    """질문에서 도구 인자 추출 - 실제 MCP 스키마 기반"""
    from datetime import datetime, timedelta
    import calendar
    args = {}
    prompt_lower = prompt.lower()
    tool_name = tool.name if hasattr(tool, 'name') else str(tool)

    # 날짜 헬퍼
    today = datetime.now()
    first_this_month = today.strftime('%Y-%m-01')
    today_str = today.strftime('%Y-%m-%d')
    first_last_month = (today.replace(day=1) - timedelta(days=1)).strftime('%Y-%m-01')
    last_day_last_month = (today.replace(day=1) - timedelta(days=1)).strftime('%Y-%m-%d')
    two_months_ago_first = (today.replace(day=1) - timedelta(days=1)).replace(day=1) - timedelta(days=1)
    two_months_ago_first = two_months_ago_first.strftime('%Y-%m-01')

    # === Billing 서버 ===
    if server_name == 'billing':
        if 'cost-explorer' in tool_name:
            # 지난달 대비 비교 질문
            if any(k in prompt for k in ['지난달', '전월', '비교', '특이사항', '증가', '감소']):
                args['operation'] = 'GetCostAndUsage'
                args['start_date'] = first_last_month
                args['end_date'] = last_day_last_month
                args['granularity'] = 'MONTHLY'
                args['group_by'] = '[{"Type": "DIMENSION", "Key": "SERVICE"}]'
            else:
                args['operation'] = 'GetCostAndUsage'
                args['start_date'] = first_this_month
                args['end_date'] = today_str
                args['granularity'] = 'MONTHLY'
                args['group_by'] = '[{"Type": "DIMENSION", "Key": "SERVICE"}]'

        elif 'cost-anomaly' in tool_name:
            args['start_date'] = first_last_month
            args['end_date'] = today_str

        elif 'cost-comparison' in tool_name:
            args['operation'] = 'GetCostAndUsageComparisons'
            args['baseline_start_date'] = two_months_ago_first
            args['baseline_end_date'] = first_last_month
            args['comparison_start_date'] = first_last_month
            args['comparison_end_date'] = last_day_last_month
            args['metric_for_comparison'] = 'UnblendedCost'

        elif 'compute-optimizer' in tool_name:
            args['operation'] = 'GetEC2InstanceRecommendations'

        elif 'cost-optimization' in tool_name:
            args['operation'] = 'ListRecommendations'

    # === Cost Explorer 서버 (실제 스키마: date_range 객체) ===
    elif server_name == 'cost_explorer':
        if tool_name == 'get_cost_and_usage_comparisons':
            # 지난달 vs 전전달 비교 - 정답지와 동일한 도구
            args['baseline_date_range'] = {
                'start': two_months_ago_first,
                'end': first_last_month
            }
            args['comparison_date_range'] = {
                'start': first_last_month,
                'end': last_day_last_month
            }
            args['metric_for_comparison'] = 'UnblendedCost'
            args['group_by'] = [{'Type': 'DIMENSION', 'Key': 'SERVICE'}]

        elif tool_name == 'get_cost_comparison_drivers':
            args['baseline_date_range'] = {
                'start': two_months_ago_first,
                'end': first_last_month
            }
            args['comparison_date_range'] = {
                'start': first_last_month,
                'end': last_day_last_month
            }
            args['metric_for_comparison'] = 'UnblendedCost'
            args['group_by'] = [{'Type': 'DIMENSION', 'Key': 'SERVICE'}]

        elif tool_name == 'get_cost_and_usage':
            if any(k in prompt for k in ['지난달', '전월', '특이사항', '비교']):
                args['date_range'] = {
                    'start': first_last_month,
                    'end': last_day_last_month
                }
            else:
                args['date_range'] = {
                    'start': first_this_month,
                    'end': today_str
                }
            args['granularity'] = 'MONTHLY'
            args['group_by'] = [{'Type': 'DIMENSION', 'Key': 'SERVICE'}]

        elif tool_name == 'get_cost_forecast':
            args['date_range'] = {
                'start': today_str,
                'end': (today + timedelta(days=30)).strftime('%Y-%m-%d')
            }
    
    # === Knowledge 서버 ===
    elif server_name == 'knowledge':
        # 인스턴스 세대 업그레이드 관련 질문 - 구체적인 검색어 사용
        if any(k in prompt for k in ['세대', '업그레이드', '인스턴스 타입', 'generation', 'upgrade']):
            if any(k in prompt for k in ['xen', 'nitro', 't2', 'm4', 'c4']):
                args['search_phrase'] = 'EC2 Xen to Nitro migration upgrade instance type change'
            elif any(k in prompt for k in ['graviton', 'arm', 'g4', 'g5']):
                args['search_phrase'] = 'EC2 Graviton ARM instance migration upgrade guide'
            else:
                args['search_phrase'] = 'EC2 instance type upgrade latest generation migration guide best practices'
            args['search_intent'] = 'DeveloperGuide'
            args['limit'] = 5
        elif any(k in prompt for k in ['주의사항', '체크리스트', '고려사항']):
            args['search_phrase'] = 'EC2 instance type change considerations checklist ENA NVMe driver'
            args['search_intent'] = 'DeveloperGuide'
            args['limit'] = 5
        else:
            # 서비스명 추출
            keywords = []
            services = ['ec2', 's3', 'rds', 'lambda', 'dynamodb', 'cloudwatch', 'vpc',
                       'ecs', 'eks', 'fargate', 'aurora', 'redshift']
            for service in services:
                if service in prompt_lower:
                    keywords.append(service.upper())
            if '마이그레이션' in prompt or 'migration' in prompt_lower:
                keywords.append('migration guide')
            if '방법' in prompt:
                keywords.append('how to guide')
            args['search_phrase'] = ' '.join(keywords) if keywords else prompt[:100]
            args['limit'] = 5
    
    # === Pricing 서버 ===
    elif server_name == 'pricing':
        # 서비스 코드 추출
        service_mapping = {
            'ec2': 'AmazonEC2',
            's3': 'AmazonS3',
            'rds': 'AmazonRDS',
            'lambda': 'AWSLambda',
            'dynamodb': 'AmazonDynamoDB'
        }
        
        for key, value in service_mapping.items():
            if key in prompt_lower:
                args['service_code'] = value
                break
        
        # 기본 서비스 코드
        if 'service_code' not in args:
            args['service_code'] = 'AmazonEC2'
    
    return args

def filter_old_generation_instances(compute_data):
    """CMDB compute 데이터에서 6세대 이하 EC2 인스턴스 필터링"""
    import re
    
    # 세대 추출 패턴: t2, m5, c6i, r7g 등에서 숫자 추출
    def get_generation(instance_type):
        match = re.match(r'^[a-z]+(\d+)', instance_type.lower())
        if match:
            return int(match.group(1))
        return 0
    
    # 6세대 이하 판단 (t1/t2/t3/t3a는 세대 기준 다름 - t3까지 구세대로 포함)
    def is_old_generation(instance_type):
        gen = get_generation(instance_type)
        return 0 < gen <= 6
    
    old_gen_by_account = {}
    
    for account_id, account_data in compute_data.items():
        if not isinstance(account_data, dict):
            continue
        old_instances = []
        for service, resources in account_data.items():
            if not isinstance(resources, list):
                continue
            for resource in resources:
                if not isinstance(resource, dict):
                    continue
                instance_type = resource.get('InstanceType', '')
                if instance_type and is_old_generation(instance_type):
                    old_instances.append({
                        'InstanceId': resource.get('InstanceId', 'N/A'),
                        'InstanceType': instance_type,
                        'Generation': get_generation(instance_type),
                        'State': resource.get('State', {}).get('Name', 'N/A') if isinstance(resource.get('State'), dict) else resource.get('State', 'N/A'),
                        'Name': next((t['Value'] for t in resource.get('Tags', []) if t.get('Key') == 'Name'), 'N/A'),
                        'Region': resource.get('Placement', {}).get('AvailabilityZone', 'N/A') if isinstance(resource.get('Placement'), dict) else 'N/A'
                    })
        if old_instances:
            old_gen_by_account[account_id] = old_instances
    
    total = sum(len(v) for v in old_gen_by_account.values())
    return {
        'summary': f'6세대 이하 인스턴스 총 {total}개 발견',
        'total_count': total,
        'by_account': old_gen_by_account
    }


async def call_multiple_mcp_tools_async(active_servers, prompt):
    """여러 MCP 서버의 도구를 호출 (비동기)"""
    results = {}
    prompt_lower = prompt.lower()
    
    for server_name in active_servers:
        try:
            if server_name == 'cmdb':
                # 비용 관련 질문은 CMDB 스킵 (billing/cost_explorer가 담당)
                cost_keywords = ['비용', '청구', '지출', '특이사항', '지난달', '전월', '이번달', 'cost', 'billing', '증가', '감소', '예산']
                if any(k in prompt for k in cost_keywords) and not any(k in prompt for k in ['세대', '인스턴스 목록', '리소스 현황']):
                    results['cmdb_skipped'] = 'CMDB는 비용 질문에 해당 없음 (billing/cost_explorer 사용)'
                    continue
                
                # 인스턴스 세대 관련 질문이면 compute_policies 직접 조회 후 필터링
                if any(k in prompt for k in ['세대', '인스턴스', 'instance', '6세대', '업그레이드']):
                    raw_data = call_mcp_tool('get_compute_policies')
                    if isinstance(raw_data, dict) and 'error' not in raw_data:
                        filtered = filter_old_generation_instances(raw_data)
                        results['cmdb_old_gen_instances'] = filtered
                    else:
                        results['cmdb_compute_error'] = raw_data
                
                # 기존 내부 MCP 호출 (subprocess 방식)
                selected_tools = select_mcp_tools(prompt)
                for tool in selected_tools:
                    try:
                        if "search_resources" in tool:
                            search_query = prompt.split()
                            query = " ".join([word for word in search_query if len(word) > 2])[:50]
                            result = call_mcp_tool(tool, query=query)
                        else:
                            result = call_mcp_tool(tool)
                        
                        # 에러 체크
                        if isinstance(result, dict) and 'error' in result:
                            # 에러 내용을 Streamlit에 표시
                            st.error(f"🔴 CMDB {tool} 에러: {result['error']}")
                            results[f"cmdb_{tool}_error"] = result['error']
                        else:
                            results[f"cmdb_{tool}"] = result
                    except Exception as e:
                        import traceback
                        error_detail = traceback.format_exc()
                        st.error(f"🔴 CMDB {tool} 예외:\n{error_detail}")
                        results[f"cmdb_{tool}_error"] = f"{str(e)}\n{error_detail}"
            else:
                # 외부 MCP 서버 호출 (subprocess 방식으로 변경)
                try:
                    result = call_external_mcp_tool(server_name, prompt)
                    if isinstance(result, dict) and 'error' in result:
                        st.warning(f"⚠️ {server_name} MCP 에러: {result['error']}")
                        results[f"{server_name}_error"] = result['error']
                    else:
                        results[f"{server_name}_result"] = result
                except Exception as e:
                    import traceback
                    error_detail = traceback.format_exc()
                    st.warning(f"⚠️ {server_name} MCP 예외: {str(e)}")
                    results[f"{server_name}_error"] = f"{str(e)}\n{error_detail}"
        except Exception as e:
            results[f"{server_name}_error"] = f"서버 연결 실패: {str(e)}"
    
    return results

def call_multiple_mcp_tools(active_servers, prompt):
    """여러 MCP 서버의 도구를 호출 (동기 래퍼, nest_asyncio 사용)"""
    try:
        # nest_asyncio를 사용하면 기존 이벤트 루프에서 실행 가능
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(call_multiple_mcp_tools_async(active_servers, prompt))
        return result
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return {"error": f"{str(e)}\n\n상세 오류:\n{error_detail}"}

def select_mcp_tools(prompt):
    """Bedrock이 필요한 MCP 도구 선택"""
    tool_selection_prompt = f"""
질문: {prompt}

다음 CMDB 도구 중 필요한 것들을 선택하세요:

- get_identity_policies: IAM 사용자, 역할, 그룹, 정책, 권한 관련
  예: "IAM 역할", "CloudWatch 권한", "관리자 권한", "정책", "사용자"
  
- get_storage_policies: S3 버킷, EFS, FSx 스토리지 관련
  예: "S3 버킷", "스토리지", "파일 시스템"
  
- get_compute_policies: EC2 인스턴스, Lambda, ECS 컴퓨팅 관련
  예: "EC2", "Lambda", "컨테이너", "인스턴스"
  
- get_database_policies: RDS, DynamoDB 데이터베이스 관련
  예: "RDS", "데이터베이스", "DynamoDB"
  
- get_network_policies: VPC, 서브넷, 보안그룹, CloudFront, Route53 네트워크 관련
  예: "VPC", "네트워크", "보안그룹", "서브넷"
  
- get_security_policies: KMS, Secrets Manager, WAF 보안 관련
  예: "KMS", "암호화", "시크릿", "WAF"
  
- search_resources: 특정 리소스 이름이나 ID로 검색
  예: "특정 버킷 찾기", "리소스 검색"
  
- get_resource_summary: 전체 리소스 개수 및 요약
  예: "전체 현황", "리소스 수", "요약"

중요: 
- "권한", "역할", "정책", "사용자" 관련 질문은 반드시 get_identity_policies 선택
- CloudWatch, S3, EC2 등 서비스 권한 질문도 get_identity_policies 선택
- 여러 도구가 필요하면 모두 선택

필요한 도구들을 콤마로 구분해서 답하세요. 예: get_identity_policies,get_storage_policies
도구 이름만 답하세요.
"""
    
    try:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 100,
            "messages": [
                {
                    "role": "user",
                    "content": tool_selection_prompt
                }
            ]
        })
        
        response = bedrock.invoke_model(
            modelId='anthropic.claude-3-haiku-20240307-v1:0',
            body=body
        )
        
        result = json.loads(response['body'].read())
        tools_text = result['content'][0]['text'].strip()
        
        # 유효한 도구 이름 목록
        valid_tools = {
            'get_identity_policies', 'get_storage_policies', 'get_compute_policies',
            'get_database_policies', 'get_network_policies', 'get_security_policies',
            'search_resources', 'get_resource_summary'
        }
        
        # 콤마로 분리 후 유효한 도구만 필터링
        tools = [
            tool.strip() for tool in tools_text.split(',')
            if tool.strip() in valid_tools
        ]
        
        # 유효한 도구가 없으면 기본값
        return tools if tools else ["get_resource_summary"]
    
    except Exception as e:
        # 오류 시 기본 도구 반환
        return ["get_resource_summary"]

def query_bedrock_with_mcp_tools(prompt):
    """Strands Agent + MCP 기반 통합 질의 (awsops 패턴)"""

    # =========================================================
    # 스킬 프롬프트 (awsops SKILL_BASE 패턴)
    # =========================================================
    SKILL_BASE = {
        'cost': """You are a FinOps Specialist. Analyze AWS costs and recommend optimizations.

## Decision Patterns:
| User asks about... | Tool chain |
|---|---|
| 이번 달/기간 비용 | get_today_date → get_cost_and_usage |
| 비용 비교 (전월 대비) | get_cost_and_usage_comparisons |
| 비용 증가 원인 | get_cost_comparison_drivers |
| 비용 예측 | get_cost_forecast |
| 예산 상태 | list_budgets |
| 필터 값 확인 | get_dimension_values or get_tag_values |

## Rules:
- ALWAYS call tools for real data — never answer from memory
- Always show costs in USD with 2 decimal places
- Always identify top cost drivers and suggest optimizations
- For 전월 대비: use get_cost_and_usage_comparisons with baseline=전전달, comparison=지난달""",

        'knowledge': """You are an AWS Documentation Specialist. You ONLY answer questions about AWS documentation, guides, and best practices.

## Your scope (ONLY these topics):
| User asks about... | Tool chain |
|---|---|
| 업그레이드 방법, 마이그레이션 | search_documentation → read_documentation |
| 인스턴스 세대 변경 주의사항 | search_documentation (EC2 instance type change) |
| AWS 서비스 가이드 | search_documentation → read_documentation |
| 베스트 프랙티스 | search_documentation |
| 아키텍처 권장사항 | search_documentation |

## STRICT Rules:
- ONLY use search_documentation and read_documentation tools
- NEVER answer questions about billing, costs, pricing, or account data
- If asked about costs/billing, respond: "비용 분석은 AWS Billing 또는 Cost Explorer MCP를 사용해주세요."
- ALWAYS search documentation for real content — never answer from memory
- Provide specific steps, commands, and checklists""",

        'cmdb': """You are a CMDB Analyst. Analyze AWS resource inventory from S3 CMDB data.

## Decision Patterns:
| User asks about... | Tool chain |
|---|---|
| IAM 역할/정책/사용자 | get_identity_policies |
| S3 버킷/스토리지 | get_storage_policies |
| EC2/Lambda/ECS | get_compute_policies |
| RDS/DynamoDB | get_database_policies |
| VPC/네트워크 | get_network_policies |
| KMS/보안 | get_security_policies |
| 전체 요약 | get_resource_summary |
| 리소스 검색 | search_resources |

## Rules:
- ALWAYS use tools to get real CMDB data
- Anonymize account IDs in responses (show first 3 digits + ***)""",

        'monitoring': """You are an AWS Monitoring Specialist. Analyze CloudWatch metrics, logs, and alarms.

## Decision Patterns:
| User asks about... | Tool chain |
|---|---|
| CPU/메모리/네트워크 메트릭 | get_metric_data |
| 알람 현황 | list_alarms |
| 로그 그룹 목록 | describe_log_groups |
| 로그 분석 | analyze_log_group or execute_log_insights_query |
| 특정 기간 로그 검색 | execute_log_insights_query |

## Rules:
- ALWAYS call tools for real-time data — never answer from memory
- For metric queries, use appropriate time ranges (last 1h, 24h, 7d)
- Identify anomalies and suggest remediation""",

        'audit': """You are an AWS Audit Specialist. Analyze CloudTrail events and API activity.

## Decision Patterns:
| User asks about... | Tool chain |
|---|---|
| 누가 변경했는지 | lookup_events |
| 특정 리소스 변경 이력 | lookup_events (filter by resource) |
| API 호출 패턴 | lookup_events or lake_query |
| 보안 이벤트 | lookup_events (filter by event type) |

## Rules:
- ALWAYS call tools for real audit data — never answer from memory
- Focus on who, what, when for each event
- Highlight suspicious or unauthorized activities""",

        'security': """You are an AWS IAM Security Specialist. Analyze IAM users, roles, policies, and permissions.

## Decision Patterns:
| User asks about... | Tool chain |
|---|---|
| IAM 사용자 목록/상세 | list_users → get_user |
| IAM 역할 목록/상세 | list_roles → get_role |
| 정책 목록 | list_policies |
| 특정 권한 확인 | simulate_principal_policy |
| 액세스 키 현황 | list_access_keys |
| 그룹 멤버십 | list_groups → get_group |

## Rules:
- ALWAYS call tools for real-time IAM data — never answer from memory
- Flag overly permissive policies (Action: *, Resource: *)
- Check for unused credentials and access keys
- Identify cross-account trust relationships""",
    }

    COMMON_FOOTER = """

## Response Rules:
- Respond in Korean (한국어)
- Format in markdown with clear structure
- Include specific resource names, numbers, and ARNs
- Provide actionable recommendations"""

    # =========================================================
    # MCP 서버 설정 — mcp_config.json에서 로드
    # =========================================================
    def load_mcp_servers():
        config_path = os.path.join(os.path.dirname(__file__), 'mcp_config.json')
        with open(config_path, 'r') as f:
            config = json.load(f)
        servers = {}
        for name, cfg in config['mcpServers'].items():
            if cfg.get('internal'):  # cmdb-server는 내부 처리
                continue
            servers[name] = {
                'command': cfg['command'],
                'args': cfg['args'],
                'env': cfg.get('env', {}),
                'skill': cfg.get('skill', 'general'),
                'label': cfg.get('label', name),
            }
        return servers

    MCP_SERVERS = load_mcp_servers()

    mcp_label_map = {
        'cmdb': '📊 CMDB (S3)',
        **{k: v['label'] for k, v in MCP_SERVERS.items()}
    }

    try:
        active_servers = [
            name for name, enabled in st.session_state.mcp_servers.items()
            if enabled
        ]

        if not active_servers:
            return "⚠️ 활성화된 MCP 서버가 없습니다. 사이드바에서 MCP 서버를 활성화해주세요."

        used_labels = []
        responses = []

        # =========================================================
        # 1. CMDB (S3 직접 조회) — 기존 방식 유지
        # =========================================================
        if 'cmdb' in active_servers:
            cost_keywords = ['비용', '청구', '지출', '특이사항', '지난달', '전월', '이번달', 'cost', 'billing']
            if not any(k in prompt for k in cost_keywords):
                with st.spinner("📊 CMDB 데이터 조회 중..."):
                    selected_tools = select_mcp_tools(prompt)
                    cmdb_results = {}
                    for tool in selected_tools:
                        if "search_resources" in tool:
                            query = " ".join([w for w in prompt.split() if len(w) > 2])[:50]
                            cmdb_results[tool] = call_mcp_tool(tool, query=query)
                        else:
                            cmdb_results[tool] = call_mcp_tool(tool)

                    # 인스턴스 세대 필터링
                    if any(k in prompt for k in ['세대', '인스턴스', '6세대', '업그레이드']):
                        raw = call_mcp_tool('get_compute_policies')
                        if isinstance(raw, dict) and 'error' not in raw:
                            cmdb_results['old_gen_instances'] = filter_old_generation_instances(raw)

                    if cmdb_results:
                        used_labels.append('📊 CMDB (S3)')
                        responses.append(('cmdb', json.dumps(cmdb_results, default=str, ensure_ascii=False)[:20000]))

        # =========================================================
        # 2. 외부 MCP 서버 — Strands Agent 방식
        # =========================================================
        aws_env = {
            'AWS_ACCESS_KEY_ID': os.getenv('AWS_ACCESS_KEY_ID', ''),
            'AWS_SECRET_ACCESS_KEY': os.getenv('AWS_SECRET_ACCESS_KEY', ''),
            'AWS_DEFAULT_REGION': os.getenv('BEDROCK_REGION', 'us-east-1'),
            'AWS_REGION': os.getenv('BEDROCK_REGION', 'us-east-1'),
            'FASTMCP_LOG_LEVEL': 'ERROR',
        }

        for server_name, server_cfg in MCP_SERVERS.items():
            if server_name not in active_servers:
                continue

            # Knowledge MCP는 비용/청구 질문에서 스킵
            cost_keywords = ['비용', '청구', '지출', '특이사항', '지난달', '전월', '이번달', 'cost', 'billing', '예산', '증가', '감소']
            if server_name == 'knowledge' and any(k in prompt for k in cost_keywords):
                if not any(k in prompt for k in ['방법', '가이드', '업그레이드', '마이그레이션', '주의사항', '베스트']):
                    continue  # 순수 비용 질문이면 Knowledge 스킵

            # Billing/Cost Explorer/Pricing은 문서 질문에서 스킵
            doc_only_keywords = ['공식문서', '가이드 문서', 'documentation', 'best practice']
            if server_name in ('billing', 'cost_explorer', 'pricing') and any(k in prompt for k in doc_only_keywords):
                if not any(k in prompt for k in ['비용', '청구', '가격', 'cost', 'billing']):
                    continue

            # CloudWatch는 모니터링/로그/메트릭 관련 질문에만 호출
            monitoring_keywords = ['로그', '메트릭', '알람', 'cloudwatch', 'cpu', '메모리', '모니터링', 'log', 'metric', 'alarm']
            if server_name == 'cloudwatch' and not any(k in prompt.lower() for k in monitoring_keywords):
                continue

            # CloudTrail은 감사/변경이력 관련 질문에만 호출
            audit_keywords = ['변경', '누가', '이력', 'cloudtrail', '감사', 'audit', 'api 호출', '이벤트']
            if server_name == 'cloudtrail' and not any(k in prompt.lower() for k in audit_keywords):
                continue

            # IAM MCP는 IAM/보안 관련 질문에만 호출 (CMDB와 중복 방지)
            iam_keywords = ['iam', '사용자', '역할', '정책', '권한', '액세스키', 'user', 'role', 'policy', 'permission']
            if server_name == 'iam' and not any(k in prompt.lower() for k in iam_keywords):
                continue

            with st.spinner(f"{server_cfg['label']} 조회 중..."):
                try:
                    skill_prompt = SKILL_BASE.get(server_cfg['skill'], '') + COMMON_FOOTER

                    mcp_client = MCPClient(lambda cfg=server_cfg: stdio_client(
                        StdioServerParameters(
                            command=cfg['command'],
                            args=cfg['args'],
                            env=aws_env,
                        )
                    ))

                    with mcp_client:
                        tools = mcp_client.list_tools_sync()
                        if not tools:
                            st.warning(f"⚠️ {server_cfg['label']}: 도구 없음")
                            continue

                        agent = Agent(
                            model=strands_model,
                            tools=tools,
                            system_prompt=skill_prompt,
                        )

                        result = agent(prompt)
                        result_text = result.message['content'][0]['text'] if hasattr(result, 'message') else str(result)

                        used_labels.append(server_cfg['label'])
                        responses.append((server_name, result_text))

                except Exception as e:
                    st.warning(f"⚠️ {server_cfg['label']} 오류: {str(e)[:100]}")

        # =========================================================
        # 3. 결과 통합 — 여러 소스가 있으면 Bedrock으로 통합
        # =========================================================
        if not responses:
            return "⚠️ 데이터를 가져오지 못했습니다. MCP 서버 연결을 확인해주세요."

        if len(responses) == 1:
            # 단일 소스면 바로 반환
            final_response = responses[0][1]
        else:
            # 여러 소스 통합
            combined = "\n\n".join([
                f"=== {mcp_label_map.get(src, src)} 데이터 ===\n{data}"
                for src, data in responses
            ])

            integration_prompt = f"""다음 여러 소스의 데이터를 종합하여 질문에 답해주세요.

{combined[:40000]}

질문: {prompt}

지침:
1. 모든 소스의 데이터를 종합적으로 분석하세요
2. CMDB 리소스 현황과 비용 데이터를 연결하여 인사이트 제공
3. 구체적인 수치, 리소스명, 권장 조치를 포함하세요
4. 한국어로 답변하세요"""

            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4000,
                "messages": [{"role": "user", "content": integration_prompt}]
            })
            resp = bedrock.invoke_model(
                modelId=os.getenv('BEDROCK_MODEL_ID', 'anthropic.claude-sonnet-4-20250514-v1:0'),
                body=body
            )
            final_response = json.loads(resp['body'].read())['content'][0]['text']

        # 익명화 + MCP 서버 표시
        final_response = anonymize_ai_response(final_response)
        mcp_footer = f"\n\n---\n🔌 **활용된 MCP 서버**: {' · '.join(used_labels)}"
        return final_response + mcp_footer

    except Exception as e:
        import traceback
        return f"❌ 오류: {str(e)}\n\n```\n{traceback.format_exc()[:500]}\n```"

def anonymize_ai_response(text):
    """AI 답변에서 민감 정보 익명화"""
    import re
    
    # 1. AWS Account ID (12자리 숫자)
    text = re.sub(r'\b(\d{3})\d{9}\b', r'\1*********', text)
    
    # 2. ARN의 계정 ID 부분만 익명화
    def anonymize_arn(match):
        arn = match.group(0)
        parts = arn.split(':')
        if len(parts) >= 5 and re.match(r'^\d{12}$', parts[4]):
            parts[4] = parts[4][:3] + '*' * 9
        return ':'.join(parts)
    
    text = re.sub(r'arn:aws:[a-z0-9-]+:[a-z0-9-]*:\d{12}:[^\s]+', anonymize_arn, text)
    
    # 3. Access Key ID
    text = re.sub(r'\b(AKIA[A-Z0-9]{4})[A-Z0-9]{12}\b', r'\1************', text)
    
    # 4. IP 주소 (마지막 두 옥텟만 마스킹)
    text = re.sub(r'\b(\d{1,3}\.\d{1,3}\.)\d{1,3}\.\d{1,3}\b', r'\1*.**', text)
    
    # 5. 이메일 주소
    text = re.sub(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', '***@***.***', text)
    
    return text

def create_resource_summary():
    """리소스 요약 대시보드"""
    st.subheader("📊 리소스 요약")
    
    categories = {
        'identity_policies': 'IAM & 인증',
        'storage_policies': '스토리지',
        'compute_policies': '컴퓨팅',
        'database_policies': '데이터베이스',
        'network_policies': '네트워킹',
        'security_policies': '보안'
    }
    
    col1, col2, col3 = st.columns(3)
    
    summary_data = []
    for cat_key, cat_name in categories.items():
        data = load_cmdb_data(cat_key)
        if 'error' not in data:
            resource_count = 0
            for account_data in data.values():
                if isinstance(account_data, dict):
                    for service_data in account_data.values():
                        if isinstance(service_data, list):
                            resource_count += len(service_data)
            
            summary_data.append({
                'Category': cat_name,
                'Resources': resource_count,
                'Key': cat_key
            })
    
    if summary_data:
        df = pd.DataFrame(summary_data)
        
        with col1:
            fig = px.bar(df, x='Category', y='Resources', 
                        title='카테고리별 리소스 수')
            fig.update_layout(xaxis_tickangle=45)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            fig = px.pie(df, values='Resources', names='Category',
                        title='리소스 분포')
            st.plotly_chart(fig, use_container_width=True)
        
        with col3:
            st.metric("총 리소스", df['Resources'].sum())
            st.metric("카테고리 수", len(df))
            st.metric("최신 데이터", get_latest_date())

def main():
    st.title("🔍 CMDB 챗봇")
    st.markdown("AWS/GCP CMDB 정책 데이터를 조회하고 분석하는 AI 챗봇입니다.")
    
    # 탭 생성
    tab1, tab2, tab3 = st.tabs(["💬 챗봇", "📊 대시보드", "🔍 데이터 탐색"])
    
    with tab1:
        st.subheader("💬 CMDB 질문하기")
        
        # 채팅 히스토리 초기화
        if "messages" not in st.session_state:
            st.session_state.messages = []
        
        # 채팅 히스토리 표시
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        
        # 사용자 입력
        if prompt := st.chat_input("CMDB에 대해 질문해보세요 (예: IAM 정책 현황은?"):
            # 사용자 메시지 추가
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # AI 응답 생성
            with st.chat_message("assistant"):
                with st.spinner("분석 중..."):
                    # MCP 도구를 활용한 응답 생성
                    response = query_bedrock_with_mcp_tools(prompt)
                    st.markdown(response)
            
            # AI 응답 저장
            st.session_state.messages.append({"role": "assistant", "content": response})
    
    with tab2:
        create_resource_summary()
    
    with tab3:
        st.subheader("🔍 데이터 탐색")
        
        # S3 구조 확인
        if st.button("S3 버킷 구조 확인"):
            structure = list_s3_structure()
            st.write("📁 S3 버킷 파일 목록:")
            for item in structure[:10]:  # 처음 10개만 표시
                st.text(item)
        
        # 카테고리 선택
        category = st.selectbox(
            "카테고리 선택",
            ["identity_policies", "storage_policies", "compute_policies", 
             "database_policies", "network_policies", "security_policies"]
        )
        
        # 날짜 선택
        date = st.date_input("날짜 선택", value=datetime.now())
        date_str = date.strftime('%Y%m%d')
        
        # 예상 파일 경로 표시
        expected_key = f"aws-policies/{date_str}/{category}.json"
        st.info(f"📄 예상 파일 경로: {expected_key}")
        
        if st.button("데이터 로드"):
            # 데이터 탐색에서는 익명화 적용 (테이블 뷰 제외)
            data = load_cmdb_data(category, date_str, anonymize=True)
            # 테이블 뷰용 원본 데이터
            original_data = load_cmdb_data(category, date_str, anonymize=False)
            
            if 'error' in data:
                st.error(f"데이터 로드 실패: {data['error']}")
                st.warning("💡 해결 방법:")
                st.write("1. S3 버킷 구조를 확인해주세요")
                st.write("2. 날짜를 다른 날짜로 변경해보세요")
                st.write("3. AWS 자격증명을 확인해주세요")
            else:
                st.success(f"데이터 로드 성공: {category}")
                
                # 데이터 구조 디버깅
                st.write(f"📊 **데이터 타입**: {type(data)}")
                st.write(f"📊 **데이터 크기**: {len(data) if hasattr(data, '__len__') else 'N/A'}")
                
                if isinstance(data, dict):
                    st.write(f"🔑 **최상위 키**: {list(data.keys())[:10]}")
                    st.write(f"🔑 **전체 키 수**: {len(data.keys())}")
                    
                    # 빈 데이터 체크
                    if not data:
                        st.warning("⚠️ 데이터가 비어있습니다.")
                    else:
                        # 첫 번째 키의 데이터 구조 확인
                        first_key = list(data.keys())[0]
                        first_value = data[first_key]
                        st.write(f"🔍 **첫 번째 키 '{first_key}' 데이터 타입**: {type(first_value)}")
                        
                        if isinstance(first_value, dict):
                            st.write(f"🔍 **첫 번째 키의 서브키**: {list(first_value.keys())[:5]}")
                elif isinstance(data, list):
                    st.write(f"📊 **리스트 아이템 수**: {len(data)}")
                    if data:
                        st.write(f"🔍 **첫 번째 아이템 타입**: {type(data[0])}")
                
                # JSON 데이터 표시
                with st.expander("원본 JSON 데이터"):
                    st.json(data)
                
                # 구조화된 데이터 표시
                if isinstance(data, dict) and data:
                    data_found = False
                    for account_id, account_data in data.items():
                        if account_id == "error":  # 오류 키 건너뛰기
                            continue
                            
                        st.subheader(f"🏦 계정: {account_id}")
                        
                        if isinstance(account_data, dict) and account_data:
                            for service, resources in account_data.items():
                                st.write(f"⚙️ **{service}** (타입: {type(resources)})")
                                
                                if isinstance(resources, list):
                                    if resources:  # 비어있지 않은 리스트
                                        data_found = True
                                        st.write(f"📊 **{len(resources)}개 리소스**")
                                        
                                        # 테이블로 표시 (원본 데이터 사용하되 ARN 계정ID만 익명화)
                                        if isinstance(resources[0], dict):
                                            try:
                                                # 테이블 뷰에서는 완전히 원본 데이터 사용
                                                original_account_id = None
                                                # 익명화된 account_id에 대응하는 원본 찾기
                                                for orig_id in original_data.keys():
                                                    if orig_id.startswith(account_id[:3]):
                                                        original_account_id = orig_id
                                                        break
                                                
                                                if (original_account_id and 
                                                    original_account_id in original_data and
                                                    isinstance(original_data[original_account_id], dict) and
                                                    service in original_data[original_account_id] and
                                                    isinstance(original_data[original_account_id][service], list)):
                                                    # 원본 데이터에서 ARN의 계정 ID만 익명화
                                                    table_data = []
                                                    for item in original_data[original_account_id][service]:
                                                        if isinstance(item, dict):
                                                            anonymized_item = {}
                                                            for key, value in item.items():
                                                                if isinstance(value, str) and value.startswith('arn:aws:'):
                                                                    # ARN에서 계정 ID만 익명화
                                                                    parts = value.split(':')
                                                                    if len(parts) >= 5 and re.match(r'^\d{12}$', parts[4]):
                                                                        parts[4] = parts[4][:3] + '*' * 9
                                                                        anonymized_item[key] = ':'.join(parts)
                                                                    else:
                                                                        anonymized_item[key] = value
                                                                else:
                                                                    anonymized_item[key] = value
                                                            table_data.append(anonymized_item)
                                                        else:
                                                            table_data.append(item)
                                                    df = pd.DataFrame(table_data)
                                                else:
                                                    df = pd.DataFrame(resources)
                                                
                                                st.write("📋 **테이블 뷰**:")
                                                st.dataframe(df, use_container_width=True)
                                            except Exception as e:
                                                st.warning(f"테이블 변환 실패: {e}")
                                        else:
                                            # 리스트 데이터를 테이블로 표시
                                            try:
                                                df = pd.DataFrame([{'리소스': str(item)} for item in resources])
                                                st.dataframe(df, use_container_width=True)
                                            except Exception as e:
                                                st.warning(f"테이블 변환 실패: {e}")
                                    else:
                                        st.write("💭 빈 리스트")
                                elif isinstance(resources, dict):
                                    if resources:  # 비어있지 않은 딕셔너리
                                        data_found = True
                                        st.write("📋 **딕셔너리 데이터**:")
                                        st.json(resources)
                                    else:
                                        st.write("💭 빈 딕셔너리")
                                else:
                                    if resources:
                                        data_found = True
                                        st.write(f"📊 **데이터 타입**: {type(resources)}")
                                        st.text(str(resources)[:500])
                                    else:
                                        st.write("💭 빈 데이터")
                        else:
                            st.write(f"📊 **계정 데이터 타입**: {type(account_data)}")
                            if account_data:
                                data_found = True
                                st.text(str(account_data)[:500])
                            else:
                                st.write("💭 빈 계정 데이터")
                    
                    if not data_found:
                        st.warning("💭 모든 데이터가 비어있습니다.")
                else:
                    st.warning("💭 표시할 데이터가 없거나 비어있습니다.")

if __name__ == "__main__":
    main()