import sys
import os

# 프로젝트 루트 디렉터리를 sys.path에 추가하여 app 및 tools 모듈 인식
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

# Vercel Serverless Function 진입점
app = app
