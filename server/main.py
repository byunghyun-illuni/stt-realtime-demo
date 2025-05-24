import base64
import logging
import time
from datetime import datetime
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
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
    STTStats,
    WebSocketUsageExample,
)
from .streaming_manager import streaming_manager
from .stt_service import STTService

# 로깅 설정
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 서버 시작 시간 기록
server_start_time = time.time()

# 통계 데이터 저장
stats = {
    "total_connections": 0,
    "active_connections": 0,
    "total_transcriptions": 0,
    "confidence_scores": [],
}


def stats_callback(event_type: str, data: dict):
    """STT 서비스 통계 업데이트 콜백"""
    if event_type == "transcription_completed":
        stats["total_transcriptions"] += 1
        confidence = data.get("confidence", 0)
        if confidence > 0:
            stats["confidence_scores"].append(confidence)
            # 최근 100개만 유지
            if len(stats["confidence_scores"]) > 100:
                stats["confidence_scores"] = stats["confidence_scores"][-100:]
        logger.info(
            f"📊 통계 업데이트: 전사 {stats['total_transcriptions']}회, 신뢰도 {confidence:.2f}"
        )


# STT 서비스 인스턴스 생성 (통계 콜백 포함)
stt_service = STTService(stats_callback=stats_callback)

# FastAPI 앱 생성
app = FastAPI(
    title="🎤 실시간 STT API",
    description="""
    ## Deepgram Nova-2 기반 실시간 음성 인식 API
    
    **주요 기능:**
    - 🚀 **실시간 WebSocket 스트리밍**: 저지연 음성 인식
    - 🌊 **HTTP 스트리밍**: Server-Sent Events로 토큰 단위 실시간 전사
    - 🧠 **Deepgram Nova-2**: 최신 AI 모델 사용
    - 🌍 **다국어 지원**: 한국어 우선, 영어 등 다양한 언어
    - 📊 **신뢰도 점수**: 각 전사 결과의 정확도 제공
    - ⚡ **실시간 스트림**: 중간 결과 + 최종 결과
    
    **사용 방법 (2가지):**
    
    ### 1. WebSocket 방식 (양방향 실시간)
    1. WebSocket으로 `/ws/stt`에 연결
    2. Base64 인코딩된 PCM16 오디오 데이터 전송
    3. 실시간으로 전사 결과 수신
    
    ### 2. HTTP 스트리밍 방식 (토큰 단위)
    1. POST `/sessions/create`로 세션 생성
    2. GET `/stream/stt/{session_id}`로 Server-Sent Events 연결
    3. POST `/upload/audio/{session_id}`로 오디오 업로드
    4. 실시간으로 토큰 단위 전사 결과 수신
    
    **지원 오디오 포맷:**
    - 포맷: PCM16
    - 샘플링 레이트: 16kHz 권장
    - 채널: 모노 (1채널)
    
    **개발자 참고:**
    - WebSocket 연결 URL: `ws://localhost:8001/ws/stt`
    - 메시지 프로토콜: JSON 형태
    - 실시간 중간 결과와 최종 결과 구분 제공
    - HTTP 스트리밍: 세션 기반 토큰 단위 스트리밍
    """,
    version="2.0.0",
    contact={
        "name": "STT API 지원팀",
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
            
            <h2>🚀 두 가지 사용 방법</h2>
            
            <div class="info">
                <strong>1. WebSocket 방식 (양방향 실시간):</strong><br>
                <div class="code">ws://localhost:8001/ws/stt</div>
            </div>
            
            <div class="streaming">
                <strong>2. 🌊 HTTP 스트리밍 방식 (토큰 단위):</strong><br>
                <a href="/streaming-example" class="btn secondary">🎯 스트리밍 가이드</a>
                <a href="/usage-streaming" class="btn secondary">📖 사용법 예시</a>
            </div>
            
            <h3>🌊 HTTP 스트리밍 빠른 시작</h3>
            <div class="code">
// 1. 세션 생성
const session = await fetch('/sessions/create', { method: 'POST' });
const { session_id, stream_url } = await session.json();

// 2. 실시간 스트리밍 연결
const eventSource = new EventSource(`/stream/stt/${session_id}`);
eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.event_type === 'token') {
        console.log('실시간 토큰:', data.data.text);
    }
};

// 3. 오디오 업로드
await fetch(`/upload/audio/${session_id}`, {
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
            "stats": "/stats",
            "websocket": "/ws/stt",
            "docs": "/docs",
            "usage": "/usage",
            "create_session": "/sessions/create",
            "stream_stt": "/stream/stt/{session_id}",
            "upload_audio": "/upload/audio/{session_id}",
            "usage_streaming": "/usage-streaming",
        },
        websocket_url="ws://localhost:8001/ws/stt",
        supported_formats=["pcm16"],
        features=[
            "실시간 음성 인식",
            "중간 전사 결과",
            "음성 감지",
            "신뢰도 점수",
            "다국어 지원",
            "WebSocket 스트리밍",
            "HTTP Server-Sent Events 스트리밍",
            "세션 기반 토큰 단위 스트리밍",
            "Deepgram Nova-2 모델",
        ],
    )


@app.get(
    "/stats",
    response_model=STTStats,
    summary="서비스 통계",
    description="실시간 STT 서비스의 사용 통계와 성능 지표를 확인합니다.",
    tags=["Monitoring"],
)
async def get_stats():
    """서비스 통계 조회"""
    avg_confidence = (
        sum(stats["confidence_scores"]) / len(stats["confidence_scores"])
        if stats["confidence_scores"]
        else 0.0
    )

    return STTStats(
        active_connections=stats["active_connections"],
        active_sessions=streaming_manager.get_active_sessions_count(),
        total_transcriptions=stats["total_transcriptions"],
        average_confidence=round(avg_confidence, 3),
        uptime_seconds=round(time.time() - server_start_time, 1),
        supported_languages=["ko", "en", "ja", "zh", "es", "fr", "de"],
    )


@app.get(
    "/usage",
    response_model=WebSocketUsageExample,
    summary="WebSocket 사용법",
    description="WebSocket을 통한 실시간 STT 사용법과 메시지 예시를 제공합니다.",
    tags=["Documentation"],
)
async def get_usage_guide():
    """WebSocket API 사용법 가이드"""
    return WebSocketUsageExample(
        connection_url="ws://localhost:8001/ws/stt",
        message_examples={
            "1_connect": {
                "description": "WebSocket 연결 후 자동으로 연결 상태 메시지 수신"
            },
            "2_send_audio": {
                "type": "audio_data",
                "audio": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=",
                "timestamp": 1704067200.123,
                "description": "Base64로 인코딩된 PCM16 오디오 데이터 전송",
            },
            "3_receive_interim": {
                "type": "transcript_interim",
                "text": "안녕하",
                "confidence": 0.78,
                "is_final": False,
                "timestamp": 1704067200.456,
                "description": "실시간 중간 전사 결과 수신",
            },
            "4_receive_final": {
                "type": "transcript_final",
                "text": "안녕하세요, 실시간 음성 인식입니다.",
                "confidence": 0.95,
                "is_final": True,
                "timestamp": 1704067201.789,
                "description": "최종 확정된 전사 결과 수신",
            },
            "5_speech_events": {
                "type": "speech_started",
                "timestamp": 1704067200.100,
                "message": "음성 감지됨",
                "description": "음성 활동 감지 이벤트",
            },
            "6_control_messages": {
                "type": "start_transcription",
                "config": {
                    "model": "nova-2",
                    "language": "ko",
                    "interim_results": True,
                    "sample_rate": 16000,
                },
                "description": "음성 인식 시작/설정 (선택사항)",
            },
        },
    )


@app.post(
    "/sessions/create",
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
            stream_url=f"/stream/stt/{session_id}",
            upload_url=f"/upload/audio/{session_id}",
            config=config,
        )
    except Exception as e:
        logger.error(f"❌ 세션 생성 오류: {e}")
        raise HTTPException(status_code=500, detail=f"세션 생성 실패: {str(e)}")


@app.get(
    "/stream/stt/{session_id}",
    summary="🌊 실시간 토큰 스트리밍",
    description="""
    **Server-Sent Events를 통한 실시간 토큰 단위 전사 스트리밍**
    
    이 엔드포인트는 지정된 세션의 실시간 음성 인식 결과를 토큰 단위로 스트리밍합니다.
    
    **사용법:**
    ```javascript
    const eventSource = new EventSource('/stream/stt/sess_abc123');
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
    "/upload/audio/{session_id}",
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
    await fetch('/upload/audio/sess_abc123', {
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
    "/usage-streaming",
    response_model=StreamingUsageExample,
    summary="🌊 HTTP 스트리밍 사용법",
    description="HTTP Server-Sent Events를 통한 실시간 토큰 스트리밍 사용법과 예시를 제공합니다.",
    tags=["🌊 HTTP Streaming"],
)
async def get_streaming_usage_guide():
    """HTTP 스트리밍 사용법 가이드"""
    return StreamingUsageExample(
        step1_create_session={
            "method": "POST",
            "url": "/sessions/create",
            "body": {"config": {"language": "ko", "interim_results": True}},
            "response": {
                "session_id": "sess_abc123",
                "stream_url": "/stream/stt/sess_abc123",
            },
        },
        step2_start_streaming={
            "method": "GET",
            "url": "/stream/stt/sess_abc123",
            "headers": {"Accept": "text/event-stream"},
            "description": "Server-Sent Events로 실시간 토큰 수신",
        },
        step3_upload_audio={
            "method": "POST",
            "url": "/upload/audio/sess_abc123",
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


@app.websocket("/ws/stt")
async def websocket_stt_endpoint(websocket: WebSocket):
    """
    ## 🎤 실시간 STT WebSocket 엔드포인트

    **실시간 음성 인식을 위한 WebSocket 연결**

    ### 연결 방법:
    ```javascript
    const ws = new WebSocket('ws://localhost:8001/ws/stt');
    ```

    ### 전송 메시지 형식:
    ```json
    {
        "type": "audio_data",
        "audio": "base64_encoded_pcm16_data",
        "timestamp": 1704067200.123
    }
    ```

    ### 수신 메시지 형식:
    ```json
    {
        "type": "transcript_final",
        "text": "인식된 텍스트",
        "confidence": 0.95,
        "is_final": true,
        "timestamp": 1704067201.456
    }
    ```

    ### 지원 오디오 포맷:
    - **포맷**: PCM16
    - **샘플링 레이트**: 16kHz (권장)
    - **채널**: 모노 (1채널)
    - **인코딩**: Base64

    ### 실시간 응답:
    - `transcript_interim`: 실시간 중간 결과
    - `transcript_final`: 최종 확정 결과
    - `speech_started`: 음성 감지 시작
    - `utterance_end`: 발화 종료
    """
    await websocket.accept()

    # 통계 업데이트
    stats["total_connections"] += 1
    stats["active_connections"] += 1

    logger.info(f"🔗 새로운 WebSocket 연결 (총 {stats['total_connections']}번째)")

    try:
        # STTService에서 WebSocket 연결 처리
        await stt_service.handle_websocket_connection(websocket)

    except WebSocketDisconnect:
        logger.info("📱 클라이언트 연결 해제")
    except Exception as e:
        logger.error(f"❌ WebSocket 오류: {e}")
    finally:
        # 통계 업데이트
        stats["active_connections"] = max(0, stats["active_connections"] - 1)
        logger.info(f"🧹 연결 정리 완료 (활성 연결: {stats['active_connections']}개)")


# FastAPI 이벤트 핸들러
@app.on_event("startup")
async def startup_event():
    """서버 시작 시 실행"""
    logger.info("🚀 FastAPI STT Server 시작")
    logger.info("📖 API 문서: http://localhost:8001/docs")
    logger.info("🔌 WebSocket: ws://localhost:8001/ws/stt")
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
