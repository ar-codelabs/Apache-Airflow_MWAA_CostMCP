#!/bin/bash

echo "🚀 CMDB MCP 서버 & Streamlit 챗봇 시작"

# cmdbmcp313_new 가상환경 활성화 (Python 3.13.7, mcp 패키지 포함)
if [ ! -d "cmdbmcp313_new" ]; then
    echo "⚠️  cmdbmcp313_new 가상환경이 없습니다. 먼저 생성해주세요."
    exit 1
fi

source cmdbmcp313_new/bin/activate

# 패키지 설치
echo "📦 패키지 설치 중..."
pip install -r requirements.txt

# 환경 변수 확인
if [ ! -f ".env" ]; then
    echo "⚠️  .env 파일을 .env.example을 참고하여 생성해주세요"
    echo "cp .env.example .env"
    echo "그 후 실제 AWS 자격증명을 입력하세요"
    exit 1
fi

# Streamlit 앱 실행 (MCP 서버 자동 시작)
echo "🌟 Streamlit 챗봇 시작 (Python 3.13 환경, MCP 서버 자동 시작)..."
python -m streamlit run streamlit_app.py --server.port 8505 --server.address 0.0.0.0

echo "✅ 완료!"