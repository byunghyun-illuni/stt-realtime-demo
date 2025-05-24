from starlette.applications import Starlette
from starlette.endpoints import WebSocketEndpoint
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.middleware.cors import CORSMiddleware
import logging
from .stt_service import STTService

# 로깅 설정
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# STT 서비스 인스턴스
stt_service = STTService()


class STTWebSocket(WebSocketEndpoint):
    encoding = "text"

    async def on_connect(self, websocket):
        await websocket.accept()
        logger.info("WebSocket 연결 수락")

    async def on_receive(self, websocket, data):
        # 실제 메시지 처리는 STTService에서 담당
        pass

    async def on_disconnect(self, websocket, close_code):
        logger.info(f"WebSocket 연결 해제: {close_code}")


async def websocket_endpoint(websocket):
    """STT WebSocket 엔드포인트"""
    await websocket.accept()
    await stt_service.handle_websocket_connection(websocket)


async def health_check(request):
    """헬스체크 엔드포인트"""
    return JSONResponse(
        {"status": "healthy", "service": "realtime-stt-server", "version": "1.0.0"}
    )


async def info_endpoint(request):
    """서버 정보 엔드포인트"""
    return JSONResponse(
        {
            "service": "Realtime STT Server",
            "description": "실시간 음성 인식 서버 (Deepgram Nova-2)",
            "endpoints": {"health": "/health", "info": "/info", "websocket": "/ws/stt"},
            "supported_formats": ["pcm16"],
            "features": [
                "실시간 음성 인식",
                "중간 전사 결과",
                "음성 감지",
                "신뢰도 점수",
                "다국어 지원",
            ],
        }
    )


# 라우트 정의
routes = [
    Route("/health", health_check, methods=["GET"]),
    Route("/info", info_endpoint, methods=["GET"]),
    WebSocketRoute("/ws/stt", websocket_endpoint),
]

# Starlette 앱 생성
app = Starlette(debug=False, routes=routes)

# CORS 미들웨어 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Realtime STT Server 시작")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Realtime STT Server 종료")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False, log_level="info")

