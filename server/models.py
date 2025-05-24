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
    websocket_url: str = Field(..., description="WebSocket 연결 URL")


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


# ===== WebSocket 메시지 모델 =====


class AudioDataMessage(BaseModel):
    """클라이언트에서 서버로 보내는 오디오 데이터"""

    type: Literal["audio_data"] = Field(..., description="메시지 타입")
    audio: str = Field(..., description="Base64 인코딩된 PCM16 오디오 데이터")
    timestamp: Optional[float] = Field(None, description="클라이언트 타임스탬프")
    chunk_id: Optional[str] = Field(None, description="청크 식별자")


class ControlMessage(BaseModel):
    """음성 인식 제어 메시지"""

    type: Literal["start_transcription", "stop_transcription"] = Field(
        ..., description="제어 타입"
    )
    config: Optional[STTConfig] = Field(None, description="STT 설정 (start시에만 사용)")


class TranscriptResponse(BaseModel):
    """서버에서 클라이언트로 보내는 전사 결과"""

    type: Literal["transcript_interim", "transcript_final"] = Field(
        ..., description="결과 타입"
    )
    text: str = Field(..., description="전사된 텍스트")
    confidence: float = Field(..., description="신뢰도 점수 (0.0-1.0)", ge=0.0, le=1.0)
    is_final: bool = Field(..., description="최종 결과 여부")
    timestamp: float = Field(..., description="서버 타임스탬프")
    chunk_id: Optional[str] = Field(None, description="관련 청크 식별자")


class SpeechEventResponse(BaseModel):
    """음성 감지 이벤트"""

    type: Literal["speech_started", "utterance_end", "vad_event"] = Field(
        ..., description="이벤트 타입"
    )
    timestamp: float = Field(..., description="이벤트 발생 시간")
    message: Optional[str] = Field(None, description="이벤트 메시지")


class ConnectionResponse(BaseModel):
    """연결 상태 응답"""

    type: Literal["connection"] = Field(..., description="메시지 타입")
    status: Literal["connected", "disconnected", "error"] = Field(
        ..., description="연결 상태"
    )
    message: str = Field(..., description="상태 메시지")
    timestamp: float = Field(..., description="응답 시간")


class ErrorResponse(BaseModel):
    """에러 응답"""

    type: Literal["error"] = Field(..., description="메시지 타입")
    code: str = Field(..., description="에러 코드", example="AUDIO_FORMAT_ERROR")
    message: str = Field(..., description="에러 메시지")
    details: Optional[dict] = Field(None, description="에러 상세 정보")
    retry_after: Optional[int] = Field(None, description="재시도 권장 시간(초)")


# ===== API 사용 예시 모델 =====


class WebSocketUsageExample(BaseModel):
    """WebSocket 사용 예시"""

    connection_url: str = Field(..., description="WebSocket 연결 URL")
    message_examples: dict = Field(..., description="메시지 예시들")

    model_config = {
        "json_schema_extra": {
            "example": {
                "connection_url": "ws://localhost:8001/ws/stt",
                "message_examples": {
                    "send_audio": {
                        "type": "audio_data",
                        "audio": "base64_encoded_pcm16_data...",
                        "timestamp": 1704067200.123,
                    },
                    "start_transcription": {
                        "type": "start_transcription",
                        "config": {
                            "model": "nova-2",
                            "language": "ko",
                            "interim_results": True,
                        },
                    },
                    "receive_transcript": {
                        "type": "transcript_final",
                        "text": "안녕하세요, 실시간 음성 인식입니다.",
                        "confidence": 0.95,
                        "is_final": True,
                        "timestamp": 1704067201.456,
                    },
                },
            }
        }
    }


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


# ===== 통계 및 모니터링 모델 =====


class STTStats(BaseModel):
    """STT 서비스 통계"""

    active_connections: int = Field(..., description="현재 활성 연결 수")
    active_sessions: int = Field(..., description="현재 활성 세션 수")
    total_transcriptions: int = Field(..., description="총 전사 완료 수")
    average_confidence: float = Field(..., description="평균 신뢰도")
    uptime_seconds: float = Field(..., description="서버 가동 시간(초)")
    supported_languages: list[str] = Field(..., description="지원 언어 목록")
