# 🎤 실시간 STT 서비스 (HTTP 스트리밍)

Deepgram Nova-2 기반 실시간 음성 인식 서비스입니다. HTTP Server-Sent Events를 통한 토큰 단위 스트리밍을 지원합니다.

## ✨ 주요 기능

- 🌊 **HTTP 스트리밍**: Server-Sent Events 기반 실시간 토큰 스트리밍
- 🧠 **Deepgram Nova-2**: 최신 AI STT 모델 사용
- 🌍 **다국어 지원**: 한국어 우선, 다국어 인식
- 📊 **신뢰도 점수**: 각 전사 결과의 정확도 제공
- ⚡ **실시간 처리**: 중간 결과 + 최종 결과
- 🔄 **세션 기반**: 안정적인 세션 관리

## 📚 클라이언트 개발자 가이드

### 🚀 빠른 시작
- **[5분 빠른 시작](QUICK_START.md)** - 바로 사용할 수 있는 예제 코드
- **[상세 클라이언트 가이드](CLIENT_API_GUIDE.md)** - 완전한 사용법과 예제

### 🔧 개발자용
- **[내부 동작 원리](streaming_flow_explanation.md)** - HTTP 스트리밍 구조 설명

## 🚀 서버 설정 및 실행

### 1. 환경 설정

```bash
# 가상환경 생성
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일에 DEEPGRAM_API_KEY 설정
```

### 2. 서버 실행

```bash
# FastAPI 서버 시작
uvicorn server.main:app --reload --port 8001
```

### 3. 클라이언트 실행

```bash
# Streamlit 클라이언트 시작
streamlit run client/streamlit_app.py --server.port 8501
```

## 📖 API 사용법

### HTTP 스트리밍 방식

```javascript
// 1. 세션 생성
const session = await fetch('/sessions', { method: 'POST' });
const { session_id, stream_url } = await session.json();

// 2. 실시간 스트리밍 연결
const eventSource = new EventSource(`/sessions/${session_id}/stream`);
eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.event_type === 'token') {
        console.log('실시간 토큰:', data.data.text);
    } else if (data.event_type === 'final') {
        console.log('최종 결과:', data.data.text);
    }
};

// 3. 오디오 업로드
const audioData = base64EncodeAudio(pcm16Buffer);
await fetch(`/sessions/${session_id}/audio`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ audio_data: audioData })
});

// 4. 세션 종료
await fetch(`/sessions/${session_id}`, { method: 'DELETE' });
```

## 🌊 HTTP 스트리밍 장점

- ✅ **표준 HTTP**: 모든 인프라와 호환
- ✅ **확장성**: 세션 기반으로 서버 간 분산 가능
- ✅ **안정성**: 네트워크 끊김에 강함 (자동 재연결)
- ✅ **모니터링**: 표준 HTTP 로그 활용
- ✅ **CDN 지원**: CloudFlare 등에서 SSE 지원

## 📁 프로젝트 구조

```
stt-realtime-demo/
├── server/                 # FastAPI 서버
│   ├── main.py            # 메인 API 서버
│   ├── models.py          # 데이터 모델
│   ├── stt_service.py     # STT 서비스 로직
│   └── streaming_manager.py # 스트리밍 세션 관리
├── client/                # 클라이언트
│   └── streamlit_app.py   # Streamlit 웹 클라이언트
├── .vscode/               # VS Code 설정
│   └── launch.json        # 디버그 설정
├── CLIENT_API_GUIDE.md    # 📚 클라이언트 개발자 가이드
├── QUICK_START.md         # ⚡ 5분 빠른 시작
├── requirements.txt       # Python 의존성
├── .env.example          # 환경변수 예시
└── README.md             # 프로젝트 문서
```

## 🔧 API 엔드포인트

### 세션 관리
- `POST /sessions` - 새 세션 생성
- `DELETE /sessions/{session_id}` - 세션 종료

### 스트리밍
- `GET /sessions/{session_id}/stream` - SSE 스트리밍 연결
- `POST /sessions/{session_id}/audio` - 오디오 업로드

### 시스템
- `GET /health` - 헬스체크
- `GET /info` - 서버 정보
- `GET /usage` - 사용법 가이드
- `GET /docs` - Swagger UI

## 🎯 지원 오디오 포맷

- **포맷**: PCM16
- **샘플링 레이트**: 16kHz (권장)
- **채널**: 모노 (1채널)
- **인코딩**: Base64

## 📊 이벤트 타입

### SSE 스트리밍 이벤트
- `token`: 실시간 중간 토큰
- `final`: 최종 확정된 전사 결과
- `speech_start`: 음성 감지 시작
- `speech_end`: 발화 종료
- `heartbeat`: 연결 유지 신호
- `error`: 오류 발생
- `session_end`: 세션 종료

## 🔗 관련 링크

- **API 문서**: http://localhost:8001/docs
- **서버 상태**: http://localhost:8001/health
- **클라이언트**: http://localhost:8501

## 📝 라이선스

MIT License

## 🤝 기여

이슈나 PR을 통해 기여해주세요!

## 📞 지원

문의사항이 있으시면 byunghyun@illuni.com으로 연락주세요.
