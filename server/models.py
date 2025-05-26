import uuid
from datetime import datetime
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

# ===== API 응답 모델 =====


class HealthResponse(BaseModel):
    """헬스체크 응답 모델"""

    status: str = Field(..., description="서버 상태", example="healthy")
    service: str = Field(..., description="서비스 이름", example="realtime-stt-server")
    version: str = Field(..., description="서비스 버전", example="2.0.0")
    timestamp: str = Field(..., description="응답 시간", example="2024-01-01T12:00:00Z")


class ServerInfo(BaseModel):
    """서버 정보 응답 모델"""

    service: str = Field(..., description="서비스 이름")
    description: str = Field(..., description="서비스 설명")
    endpoints: dict = Field(..., description="사용 가능한 엔드포인트")
    supported_formats: list[str] = Field(..., description="지원하는 오디오 포맷")
    features: list[str] = Field(..., description="서비스 기능")


class STTConfig(BaseModel):
    """STT 설정 모델"""

    model: str = Field(
        default="nova-2", description="사용할 STT 모델", example="nova-2"
    )
    language: str = Field(default="ko", description="인식 언어", example="ko")
    smart_format: bool = Field(default=True, description="스마트 포맷팅 사용")
    interim_results: bool = Field(default=True, description="실시간 중간 결과 반환")
    punctuate: bool = Field(default=True, description="구두점 자동 삽입")
    sample_rate: int = Field(
        default=16000, description="오디오 샘플링 레이트", example=16000
    )
    channels: int = Field(default=1, description="오디오 채널 수", example=1)


# ===== 스트리밍 세션 모델 =====


class StreamingSession(BaseModel):
    """실시간 스트리밍 세션"""

    session_id: str = Field(..., description="세션 고유 ID", example="sess_123456")
    config: STTConfig = Field(..., description="STT 설정")
    created_at: float = Field(..., description="세션 생성 시간")
    status: Literal["active", "inactive", "completed"] = Field(
        ..., description="세션 상태"
    )


class CreateSessionRequest(BaseModel):
    """스트리밍 세션 생성 요청"""

    config: Optional[STTConfig] = Field(
        None, description="STT 설정 (기본값 사용시 생략 가능)"
    )


class CreateSessionResponse(BaseModel):
    """스트리밍 세션 생성 응답"""

    session_id: str = Field(..., description="생성된 세션 ID")
    stream_url: str = Field(..., description="실시간 스트리밍 URL")
    upload_url: str = Field(..., description="오디오 업로드 URL")
    config: STTConfig = Field(..., description="적용된 STT 설정")

    model_config = {
        "json_schema_extra": {
            "example": {
                "session_id": "sess_abc123",
                "stream_url": "/stream/stt/sess_abc123",
                "upload_url": "/upload/audio/sess_abc123",
                "config": {
                    "model": "nova-2",
                    "language": "ko",
                    "interim_results": True,
                },
            }
        }
    }


class AudioUploadRequest(BaseModel):
    """오디오 업로드 요청"""

    audio_data: str = Field(..., description="Base64 인코딩된 PCM16 오디오 데이터")
    chunk_id: Optional[str] = Field(None, description="청크 식별자")
    timestamp: Optional[float] = Field(None, description="클라이언트 타임스탬프")


class AudioUploadResponse(BaseModel):
    """오디오 업로드 응답"""

    session_id: str = Field(..., description="세션 ID")
    chunk_id: Optional[str] = Field(None, description="처리된 청크 ID")
    received_bytes: int = Field(..., description="수신된 바이트 수")
    timestamp: float = Field(..., description="서버 수신 시간")


# ===== 스트리밍 응답 모델 =====


class StreamingTokenResponse(BaseModel):
    """실시간 토큰 스트리밍 응답"""

    event_type: Literal[
        "token", "final", "speech_start", "speech_end", "error", "session_end"
    ] = Field(..., description="이벤트 타입")
    data: Union[dict, str] = Field(..., description="이벤트 데이터")
    timestamp: float = Field(..., description="이벤트 시간")
    session_id: str = Field(..., description="세션 ID")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "event_type": "token",
                    "data": {"text": "안녕", "confidence": 0.85, "is_partial": True},
                    "timestamp": 1704067200.123,
                    "session_id": "sess_abc123",
                },
                {
                    "event_type": "final",
                    "data": {
                        "text": "안녕하세요",
                        "confidence": 0.95,
                        "is_partial": False,
                    },
                    "timestamp": 1704067201.456,
                    "session_id": "sess_abc123",
                },
            ]
        }
    }


# ===== API 사용 예시 모델 =====


class StreamingUsageExample(BaseModel):
    """HTTP 스트리밍 사용 예시"""

    step1_create_session: dict = Field(..., description="1단계: 세션 생성")
    step2_start_streaming: dict = Field(..., description="2단계: 스트리밍 시작")
    step3_upload_audio: dict = Field(..., description="3단계: 오디오 업로드")
    step4_receive_tokens: dict = Field(..., description="4단계: 실시간 토큰 수신")

    model_config = {
        "json_schema_extra": {
            "example": {
                "step1_create_session": {
                    "method": "POST",
                    "url": "/sessions/create",
                    "body": {"config": {"language": "ko", "interim_results": True}},
                    "response": {
                        "session_id": "sess_abc123",
                        "stream_url": "/stream/stt/sess_abc123",
                    },
                },
                "step2_start_streaming": {
                    "method": "GET",
                    "url": "/stream/stt/sess_abc123",
                    "headers": {"Accept": "text/event-stream"},
                    "description": "Server-Sent Events로 실시간 토큰 수신",
                },
                "step3_upload_audio": {
                    "method": "POST",
                    "url": "/upload/audio/sess_abc123",
                    "body": {
                        "audio_data": "base64_pcm16_data...",
                        "chunk_id": "chunk_001",
                    },
                },
                "step4_receive_tokens": {
                    "sse_events": [
                        'data: {"event_type": "token", "data": {"text": "안녕", "confidence": 0.8}}',
                        'data: {"event_type": "token", "data": {"text": "안녕하", "confidence": 0.85}}',
                        'data: {"event_type": "final", "data": {"text": "안녕하세요", "confidence": 0.95}}',
                    ]
                },
            }
        }
    }
