import base64
import logging
import time
from datetime import datetime
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse

from .models import (
    AudioUploadRequest,
    AudioUploadResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    HealthResponse,
    ServerInfo,
    StreamingUsageExample,
    STTConfig,
)
from .streaming_manager import streaming_manager

# 로깅 설정
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 서버 시작 시간 기록
server_start_time = time.time()

# FastAPI 앱 생성
app = FastAPI(
    title="🎤 실시간 STT API",
    description="""
    ## Deepgram Nova-2 기반 실시간 음성 인식 API
    
    **주요 기능:**
    - 🌊 **HTTP 스트리밍**: Server-Sent Events로 토큰 단위 실시간 전사
    - 🧠 **Deepgram Nova-2**: 최신 AI 모델 사용
    - 🌍 **다국어 지원**: 한국어 우선, 영어 등 다양한 언어
    - 📊 **신뢰도 점수**: 각 전사 결과의 정확도 제공
    - ⚡ **실시간 스트림**: 중간 결과 + 최종 결과
    
    **사용 방법:**
    
    ### HTTP 스트리밍 방식 (토큰 단위)
    1. POST `/sessions/create`로 세션 생성
    2. GET `/stream/stt/{session_id}`로 Server-Sent Events 연결
    3. POST `/upload/audio/{session_id}`로 오디오 업로드
    4. 실시간으로 토큰 단위 전사 결과 수신
    
    **지원 오디오 포맷:**
    - 포맷: PCM16
    - 샘플링 레이트: 16kHz 권장
    - 채널: 모노 (1채널)
    
    **개발자 참고:**
    - 메시지 프로토콜: JSON 형태
    - 실시간 중간 결과와 최종 결과 구분 제공
    - HTTP 스트리밍: 세션 기반 토큰 단위 스트리밍
    """,
    version="2.0.0",
    contact={
        "name": "illuni",
        "email": "byunghyun@illuni.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS 미들웨어 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/",
    response_class=HTMLResponse,
    summary="API 홈페이지",
    description="API 문서 링크와 기본 정보를 제공합니다.",
)
async def root():
    """API 홈페이지 - Swagger 문서 링크 제공"""
    return HTMLResponse(
        content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🎤 실시간 STT API</title>
        <meta charset="utf-8">
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 40px; background: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #2563eb; border-bottom: 3px solid #2563eb; padding-bottom: 10px; }
            .btn { display: inline-block; padding: 12px 24px; margin: 10px 10px 10px 0; background: #2563eb; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; }
            .btn:hover { background: #1d4ed8; }
            .btn.secondary { background: #10b981; }
            .btn.secondary:hover { background: #059669; }
            .info { background: #f0f9ff; padding: 15px; border-radius: 5px; border-left: 4px solid #2563eb; margin: 20px 0; }
            .streaming { background: #f0fdf4; padding: 15px; border-radius: 5px; border-left: 4px solid #10b981; margin: 20px 0; }
            .code { background: #1f2937; color: #f9fafb; padding: 15px; border-radius: 5px; font-family: 'Courier New', monospace; overflow-x: auto; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎤 실시간 STT API</h1>
            <p><strong>Deepgram Nova-2 기반 실시간 음성 인식 서비스</strong></p>
            
            <div class="info">
                <strong>📚 개발자 문서:</strong><br>
                • <a href="/docs" class="btn">📖 Swagger UI</a>
                • <a href="/redoc" class="btn">📋 ReDoc</a>
                • <a href="/openapi.json" class="btn">🔧 OpenAPI Schema</a>
            </div>
            
            <h2>🌊 HTTP 스트리밍 방식</h2>
            
            <div class="streaming">
                <strong>🌊 HTTP 스트리밍 방식 (토큰 단위):</strong><br>
                <a href="/usage" class="btn secondary">🎯 스트리밍 가이드</a>
                <a href="/usage" class="btn secondary">📖 사용법 예시</a>
            </div>
            
            <h3>🌊 HTTP 스트리밍 빠른 시작</h3>
            <div class="code">
// 1. 세션 생성
const session = await fetch('/sessions', { method: 'POST' });
const { session_id, stream_url } = await session.json();

// 2. 실시간 스트리밍 연결
const eventSource = new EventSource(`/sessions/${session_id}/stream`);
eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.event_type === 'token') {
        console.log('실시간 토큰:', data.data.text);
    }
};

// 3. 오디오 업로드
await fetch(`/sessions/${session_id}/audio`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ audio_data: base64AudioData })
});
            </div>
            
            <h3>🎯 주요 기능</h3>
            <ul>
                <li>⚡ <strong>실시간 스트리밍</strong>: 저지연 음성 인식</li>
                <li>🧠 <strong>Deepgram Nova-2</strong>: 최신 AI STT 모델</li>
                <li>🌍 <strong>다국어 지원</strong>: 한국어 우선, 다국어 인식</li>
                <li>📊 <strong>신뢰도 점수</strong>: 정확도 측정 제공</li>
                <li>🔄 <strong>실시간 + 최종</strong>: 토큰 단위 중간 결과와 확정 결과</li>
                <li>🌊 <strong>HTTP 스트리밍</strong>: Server-Sent Events 지원</li>
            </ul>
            
            <div class="info">
                <strong>⚙️ 서비스 상태:</strong> <span style="color: green;">✅ 정상 운영</span><br>
                <strong>📞 지원:</strong> byunghyun@illuni.com
            </div>
        </div>
    </body>
    </html>
    """
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="헬스체크",
    description="서버 상태와 기본 정보를 확인합니다.",
    tags=["System"],
)
async def health_check():
    """서버 헬스체크 - 상태 확인"""
    return HealthResponse(
        status="healthy",
        service="realtime-stt-server",
        version="2.0.0",
        timestamp=datetime.now().isoformat(),
    )


@app.get(
    "/info",
    response_model=ServerInfo,
    summary="서버 정보",
    description="STT 서비스의 상세 정보와 사용 가능한 기능을 확인합니다.",
    tags=["System"],
)
async def get_server_info():
    """서버 정보 조회"""
    return ServerInfo(
        service="Realtime STT Server",
        description="실시간 음성 인식 서버 (Deepgram Nova-2)",
        endpoints={
            "health": "/health",
            "info": "/info",
            "docs": "/docs",
            "create_session": "/sessions",
            "stream_stt": "/sessions/{session_id}/stream",
            "upload_audio": "/sessions/{session_id}/audio",
            "delete_session": "/sessions/{session_id}",
            "usage_guide": "/usage",
        },
        supported_formats=["pcm16"],
        features=[
            "실시간 음성 인식",
            "중간 전사 결과",
            "음성 감지",
            "신뢰도 점수",
            "다국어 지원",
            "HTTP Server-Sent Events 스트리밍",
            "세션 기반 토큰 단위 스트리밍",
            "Deepgram Nova-2 모델",
        ],
    )


@app.post(
    "/sessions",
    response_model=CreateSessionResponse,
    summary="🎯 스트리밍 세션 생성",
    description="HTTP 스트리밍을 위한 새로운 세션을 생성합니다. 생성된 세션 ID로 스트리밍 연결과 오디오 업로드가 가능합니다.",
    tags=["🌊 HTTP Streaming"],
)
async def create_streaming_session(request: CreateSessionRequest = None):
    """새로운 스트리밍 세션 생성"""
    try:
        config = request.config if request else None
        session_id = await streaming_manager.create_session(config)

        if not config:
            config = STTConfig()

        return CreateSessionResponse(
            session_id=session_id,
            stream_url=f"/sessions/{session_id}/stream",
            upload_url=f"/sessions/{session_id}/audio",
            config=config,
        )
    except Exception as e:
        logger.error(f"❌ 세션 생성 오류: {e}")
        raise HTTPException(status_code=500, detail=f"세션 생성 실패: {str(e)}")


@app.get(
    "/sessions/{session_id}/stream",
    summary="🌊 실시간 토큰 스트리밍",
    description="""
    **Server-Sent Events를 통한 실시간 토큰 단위 전사 스트리밍**
    
    이 엔드포인트는 지정된 세션의 실시간 음성 인식 결과를 토큰 단위로 스트리밍합니다.
    
    **사용법:**
    ```javascript
    const eventSource = new EventSource('/sessions/sess_abc123/stream');
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.event_type === 'token') {
            console.log('실시간 토큰:', data.data.text);
        }
    };
    ```
    
    **이벤트 타입:**
    - `token`: 실시간 중간 토큰 (타이핑 중인 텍스트)
    - `final`: 최종 확정된 전사 결과
    - `speech_start`: 음성 감지 시작
    - `speech_end`: 발화 종료
    - `heartbeat`: 연결 유지 신호
    - `error`: 오류 발생
    - `session_end`: 세션 종료
    """,
    tags=["🌊 HTTP Streaming"],
    responses={
        200: {
            "description": "Server-Sent Events 스트림",
            "content": {
                "text/event-stream": {
                    "example": 'data: {"event_type": "token", "data": {"text": "안녕", "confidence": 0.85}, "timestamp": 1704067200.123}\n\n'
                }
            },
        },
        404: {"description": "세션을 찾을 수 없음"},
    },
)
async def stream_stt_results(session_id: str):
    """실시간 STT 결과 스트리밍 (Server-Sent Events)"""
    session = streaming_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404, detail=f"세션을 찾을 수 없습니다: {session_id}"
        )

    async def generate_stream():
        async for chunk in streaming_manager.stream_results(session_id):
            yield chunk

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        },
    )


@app.post(
    "/sessions/{session_id}/audio",
    response_model=AudioUploadResponse,
    summary="🎤 오디오 업로드",
    description="""
    **세션에 오디오 데이터를 업로드하여 실시간 전사 처리**
    
    Base64로 인코딩된 PCM16 오디오 데이터를 업로드하면, 해당 세션의 스트리밍 연결로 실시간 전사 결과가 전송됩니다.
    
    **오디오 포맷:**
    - 포맷: PCM16
    - 샘플링 레이트: 16kHz 권장
    - 채널: 모노 (1채널)
    - 인코딩: Base64
    
    **사용 예시:**
    ```javascript
    const audioData = base64EncodeAudio(pcm16Buffer);
    await fetch('/sessions/sess_abc123/audio', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audio_data: audioData })
    });
    ```
    """,
    tags=["🌊 HTTP Streaming"],
)
async def upload_audio_data(session_id: str, request: AudioUploadRequest):
    """세션에 오디오 데이터 업로드"""
    session = streaming_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404, detail=f"세션을 찾을 수 없습니다: {session_id}"
        )

    try:
        # Base64 디코딩
        audio_bytes = base64.b64decode(request.audio_data)

        # 스트리밍 매니저로 오디오 전송
        success = await streaming_manager.upload_audio(session_id, audio_bytes)

        if not success:
            raise HTTPException(status_code=500, detail="오디오 처리 실패")

        return AudioUploadResponse(
            session_id=session_id,
            chunk_id=request.chunk_id,
            received_bytes=len(audio_bytes),
            timestamp=time.time(),
        )

    except base64.binascii.Error:
        raise HTTPException(status_code=400, detail="잘못된 Base64 오디오 데이터")
    except Exception as e:
        logger.error(f"❌ 오디오 업로드 오류 ({session_id}): {e}")
        raise HTTPException(status_code=500, detail=f"오디오 업로드 실패: {str(e)}")


@app.delete(
    "/sessions/{session_id}",
    summary="🗑️ 세션 종료",
    description="지정된 세션을 종료하고 관련 리소스를 정리합니다.",
    tags=["🌊 HTTP Streaming"],
)
async def close_streaming_session(session_id: str):
    """스트리밍 세션 종료"""
    session = streaming_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404, detail=f"세션을 찾을 수 없습니다: {session_id}"
        )

    await streaming_manager.close_session(session_id)
    return {"message": f"세션 {session_id}가 성공적으로 종료되었습니다."}


@app.get(
    "/usage",
    response_model=StreamingUsageExample,
    summary="🌊 HTTP 스트리밍 사용법",
    description="HTTP Server-Sent Events를 통한 실시간 토큰 스트리밍 사용법과 예시를 제공합니다.",
    tags=["📖 Documentation"],
)
async def get_streaming_usage_guide():
    """HTTP 스트리밍 사용법 가이드"""
    return StreamingUsageExample(
        step1_create_session={
            "method": "POST",
            "url": "/sessions",
            "body": {"config": {"language": "ko", "interim_results": True}},
            "response": {
                "session_id": "sess_abc123",
                "stream_url": "/sessions/sess_abc123/stream",
            },
        },
        step2_start_streaming={
            "method": "GET",
            "url": "/sessions/sess_abc123/stream",
            "headers": {"Accept": "text/event-stream"},
            "description": "Server-Sent Events로 실시간 토큰 수신",
        },
        step3_upload_audio={
            "method": "POST",
            "url": "/sessions/sess_abc123/audio",
            "body": {"audio_data": "base64_pcm16_data...", "chunk_id": "chunk_001"},
        },
        step4_receive_tokens={
            "sse_events": [
                'data: {"event_type": "token", "data": {"text": "안녕", "confidence": 0.8}}',
                'data: {"event_type": "token", "data": {"text": "안녕하", "confidence": 0.85}}',
                'data: {"event_type": "final", "data": {"text": "안녕하세요", "confidence": 0.95}}',
            ]
        },
    )


# FastAPI 이벤트 핸들러
@app.on_event("startup")
async def startup_event():
    """서버 시작 시 실행"""
    logger.info("🚀 FastAPI STT Server 시작")
    logger.info("📖 API 문서: http://localhost:8001/docs")
    logger.info("🌊 HTTP 스트리밍: http://localhost:8001/sessions/create")

    # 스트리밍 매니저 정리 태스크 시작
    streaming_manager.start_cleanup_task()


@app.on_event("shutdown")
async def shutdown_event():
    """서버 종료 시 실행"""
    logger.info("🛑 FastAPI STT Server 종료")

    # 모든 세션 정리
    all_sessions = streaming_manager.get_all_sessions()
    for session_id in all_sessions.keys():
        await streaming_manager.close_session(session_id)


# 개발 실행용
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server.main:app", host="0.0.0.0", port=8001, reload=True, log_level="info"
    )
