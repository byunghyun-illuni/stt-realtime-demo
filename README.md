# 🎤 Real-time STT Demo with Deepgram

> Deepgram Nova-2 모델을 활용한 **실시간 음성 인식 시스템**  
> WebSocket 기반 저지연 스트리밍으로 토큰 단위 실시간 전사 구현

## ✨ 특징

- **🚀 초저지연**: WebSocket 기반 실시간 스트리밍 (< 100ms)
- **🧠 최신 AI**: Deepgram Nova-2 STT 모델 
- **🌍 다국어**: 한국어 우선, 다국어 음성 인식 지원
- **🎯 고정밀도**: 신뢰도 점수와 함께 정확한 전사
- **📱 웹 기반**: 별도 앱 설치 없이 브라우저에서 바로 실행
- **⚡ 실시간**: 토큰 단위 중간 결과와 최종 결과 동시 제공
- **🔄 양방향**: 실시간 오디오 업로드 및 텍스트 다운로드

## 🏗️ 시스템 아키텍처

### 전체 구조
```
┌─────────────────────┐    WebSocket     ┌─────────────────────┐    WebSocket     ┌─────────────────────┐
│    Streamlit        │ ◄──────────────► │     Starlette       │ ◄──────────────► │      Deepgram       │
│   (Frontend UI)     │  실시간 양방향    │   (Backend API)     │   실시간 스트림   │    (STT Service)    │
│     :8501           │     통신         │      :8001          │      전송        │    Nova-2 Model     │
└─────────────────────┘                  └─────────────────────┘                  └─────────────────────┘
        │                                         │                                         │
        │ 1. 마이크 캡처                           │ 2. 오디오 중계                           │ 3. 실시간 전사
        │ 2. Base64 인코딩                        │ 3. 프로토콜 변환                        │ 4. 신뢰도 계산
        │ 3. 실시간 표시                          │ 4. 에러 핸들링                          │ 5. 토큰 스트리밍
```

### 🔌 통신 방식: **WebSocket** 선택 이유

| 방식 | 장점 | 단점 | 적합성 |
|------|------|------|--------|
| **WebSocket** ✅ | • 실시간 양방향 통신<br>• 저지연 (<100ms)<br>• 연결 유지 | • 복잡한 상태 관리<br>• 연결 안정성 필요 | **🎯 실시간 STT 최적** |
| HTTP Polling | • 구현 단순<br>• 안정성 높음 | • 높은 지연시간<br>• 서버 부하 | ❌ 실시간 부적합 |
| Server-Sent Events | • 단방향 스트리밍<br>• 자동 재연결 | • 업로드 불가<br>• 브라우저 제한 | ❌ 양방향 필요 |
| gRPC Streaming | • 고성능<br>• 타입 안전성 | • 브라우저 제한<br>• 복잡한 설정 | △ 서버간 통신용 |

### 💾 데이터 플로우

```
📱 Client (Streamlit)           🖥️  Server (Starlette)           ☁️  Deepgram API
─────────────────────           ──────────────────────           ─────────────────

1. 🎤 마이크 캡처                 
   │ PCM16, 16kHz, Mono
   ▼
2. 📦 Base64 인코딩              ──► 4. 📡 WebSocket 수신
   │ JSON 메시지                     │ Base64 디코딩
   ▼                                ▼
3. 🌐 WebSocket 전송             5. 🔄 Deepgram 중계          ──► 7. 🧠 실시간 전사
                                   │ Binary 스트림                  │ Nova-2 모델
                                   ▼                              ▼
6. 📥 결과 수신              ◄──── 8. 📤 응답 중계            ◄── 9. 📝 토큰 스트림
   │ 실시간 + 최종                   │ JSON 변환                      │ 신뢰도 점수
   ▼                                ▼                              ▼
10. 🖥️ UI 업데이트                11. 🔍 로깅 & 모니터링          12. ⚡ 실시간 응답
    │ 타이핑 효과                    │ 성능 추적                      │ 중간/최종 결과
```

## 📂 프로젝트 구조

```
stt-transcribe-demo/
├── 🖥️ server/                    # 백엔드 서버
│   ├── main.py                  # Starlette 앱 + 라우팅
│   └── stt_service.py           # Deepgram STT 로직
├── 📱 client/                    # 프론트엔드 클라이언트
│   └── streamlit_app.py         # Streamlit UI + WebSocket 클라이언트
├── ⚙️ pyproject.toml            # 의존성 관리 (uv/pip)
├── 🔑 .env                      # API 키 설정
└── 📖 README.md                 # 이 파일
```

## 🚀 빠른 실행

### 1. 환경 설정

```bash
# 저장소 클론
git clone <repository-url>
cd stt-transcribe-demo

# Python 3.12 + 가상환경 권장
uv venv
source .venv/bin/activate

# 의존성 설치 (uv 또는 pip)
uv pip install -e .
# 또는 pip install -e .
```

### 2. API 키 설정

```bash
echo "DEEPGRAM_API_KEY=your_deepgram_api_key_here" > .env
```

### 3. 서버 실행 (필수)

```bash
# 터미널 1: 백엔드 서버 실행
uvicorn server.main:app --reload --port 8001

# 서버 URL: http://localhost:8001
# WebSocket: ws://localhost:8001/ws/stt
# Health Check: http://localhost:8001/health
```

### 4. 클라이언트 실행

```bash
# 터미널 2: 프론트엔드 클라이언트 실행  
streamlit run client/streamlit_app.py

# 클라이언트 URL: http://localhost:8501
# 브라우저에서 자동으로 열림
```

## 🌐 네트워크 설정

| 구분 | 주소 | 포트 | 용도 |
|------|------|------|------|
| **백엔드 서버** | `localhost` | `8001` | STT WebSocket API |
| **프론트엔드** | `localhost` | `8501` | Streamlit Web UI |
| **WebSocket** | `ws://localhost:8001/ws/stt` | - | 실시간 음성 통신 |
| **Health Check** | `http://localhost:8001/health` | - | 서버 상태 확인 |
| **API Info** | `http://localhost:8001/info` | - | 서버 정보 |

## 🔧 API 엔드포인트

| 엔드포인트 | 메서드 | 설명 | 예제 |
|-----------|--------|------|------|
| `/health` | GET | 서버 상태 확인 | `curl http://localhost:8001/health` |
| `/info` | GET | 서비스 정보 | `curl http://localhost:8001/info` |
| `/ws/stt` | WebSocket | 실시간 음성 인식 | 클라이언트에서 자동 연결 |

## 💡 사용법

### 🎙️ 실시간 전사 과정
1. **서버 시작**: `uvicorn server.main:app --reload --port 8001`
2. **클라이언트 접속**: 브라우저에서 `http://localhost:8501` 열기
3. **서버 연결**: UI에서 "연결" 버튼 클릭
4. **녹음 시작**: "🔴 녹음 시작" 버튼 클릭
5. **음성 입력**: 마이크에 대고 말하기
6. **실시간 결과**: 화면에서 전사 결과 확인
7. **녹음 중지**: "⏹️ 녹음 중지" 버튼 클릭

### 🔄 WebSocket 통신 프로토콜
```json
// 클라이언트 → 서버 (오디오 데이터)
{
  "type": "audio_data",
  "audio": "base64_encoded_pcm16"
}

// 서버 → 클라이언트 (실시간 전사)
{
  "type": "transcript_interim",
  "text": "실시간 부분 전사...",
  "confidence": 0.85,
  "is_final": false
}

// 서버 → 클라이언트 (최종 전사)
{
  "type": "transcript_final",
  "text": "최종 전사 결과",
  "confidence": 0.92,
  "is_final": true
}

// 서버 → 클라이언트 (음성 이벤트)
{
  "type": "speech_started",
  "timestamp": 1234567890
}
```

### 🎯 전사 결과 종류
- **실시간 중간 결과**: 말하는 중에 실시간으로 업데이트
- **최종 결과**: 발화 완료 후 최종 확정된 전사
- **신뢰도 점수**: 0.0~1.0 범위의 전사 정확도
- **음성 감지**: 말하기 시작/종료 이벤트

## 🛠️ 기술 스택

- **Backend**: Starlette + Uvicorn (비동기 WebSocket)
- **Frontend**: Streamlit (실시간 웹 UI)
- **Audio**: sounddevice + numpy (크로스 플랫폼)
- **STT**: Deepgram Nova-2 (실시간 음성 인식)
- **Protocol**: WebSocket (양방향 실시간 통신)

## 🔧 Deepgram 설정

### Nova-2 모델 특징
- **고성능**: 최신 딥러닝 기반 STT 모델
- **다국어**: 한국어, 영어 등 다양한 언어 지원
- **실시간**: 스트리밍 전사와 중간 결과 제공
- **고정밀**: 높은 인식 정확도와 신뢰도 점수

### 오디오 설정
- **포맷**: PCM16
- **샘플링 레이트**: 16kHz (권장)
- **채널**: 모노 (1채널)
- **청크 크기**: 1024 샘플

## 📝 주의사항

- **API 키**: Deepgram API 키 필수 (.env 파일)
- **마이크 권한**: 브라우저에서 마이크 접근 허용 필요
- **Python 버전**: 3.12 권장
- **네트워크**: 실시간 처리로 안정적인 네트워크 필요
- **포트 충돌**: 8001, 8501 포트 사용 가능 확인

## 🚨 트러블슈팅

### 연결 실패 시
```bash
# 서버 상태 확인
curl http://localhost:8001/health

# 포트 사용 확인
lsof -i :8001
lsof -i :8501
```

### 오디오 문제 시
- 마이크 권한 확인
- 브라우저 오디오 설정 점검
- sounddevice 재설치: `uv pip install --force-reinstall sounddevice`

### Deepgram API 오류 시
- API 키 확인: `.env` 파일의 `DEEPGRAM_API_KEY`
- 계정 크레딧 확인
- 네트워크 연결 상태 확인

## 📊 성능 최적화

### 지연시간 최소화
- `no_delay=True` 옵션 사용
- 16kHz 샘플링 레이트 권장
- 네트워크 대역폭 충분히 확보

### 정확도 향상
- 조용한 환경에서 녹음
- 명확한 발음으로 말하기
- 마이크와 적절한 거리 유지

## 🔧 설계 대안 및 확장 방안

### 🏗️ 아키텍처 옵션

#### 1. **현재 구조 (권장)** ⭐
```
Client ◄──WebSocket──► Starlette ◄──WebSocket──► Deepgram
```
- **장점**: 단순함, 저지연, 실시간 양방향
- **단점**: 상태 관리 복잡, 스케일링 제한
- **적합**: 프로토타입, 소규모 서비스

#### 2. **마이크로서비스 + Queue**
```
Client ◄──WebSocket──► API Gateway ◄──Redis──► STT Service ◄──► Deepgram
                             │                      │
                             └──MongoDB──► Analytics Service
```
- **장점**: 확장성, 내결함성, 모니터링
- **단점**: 복잡성 증가, 지연시간 증가
- **적합**: 대규모 프로덕션

#### 3. **서버리스 + WebRTC**
```
Client ◄──WebRTC──► Lambda/Vercel ◄──HTTP──► Deepgram
```
- **장점**: 서버리스, P2P 직접 연결
- **단점**: WebRTC 복잡성, 디버깅 어려움
- **적합**: 글로벌 서비스

### 🔌 인터페이스 설계 가이드

#### WebSocket 메시지 프로토콜
```typescript
// 클라이언트 → 서버
interface AudioMessage {
  type: "audio_data"
  audio: string          // Base64 encoded PCM16
  timestamp?: number
  chunk_id?: string      // 청크 추적용
}

interface ControlMessage {
  type: "start_transcription" | "stop_transcription"
  config?: {
    language?: string
    model?: string
    interim_results?: boolean
  }
}

// 서버 → 클라이언트  
interface TranscriptResponse {
  type: "transcript_interim" | "transcript_final"
  text: string
  confidence: number
  is_final: boolean
  timestamp: number
  chunk_id?: string
}

interface EventResponse {
  type: "speech_started" | "utterance_end" | "error"
  timestamp?: number
  message?: string
}
```

#### 에러 처리 전략
```typescript
interface ErrorResponse {
  type: "error"
  code: string           // "AUDIO_FORMAT_ERROR", "API_LIMIT_EXCEEDED"
  message: string        // 사용자 친화적 메시지
  details?: any         // 디버깅용 상세 정보
  retry_after?: number  // 재시도 권장 시간(초)
}
```

### 📈 확장성 고려사항

#### 1. **수평 확장 (Scale Out)**
```python
# Load Balancer + Multiple Instances
nginx ──┬──► STT Server 1 (8001)
        ├──► STT Server 2 (8002)
        └──► STT Server 3 (8003)

# Redis for Session Sharing
session_store = Redis(host="redis-cluster")
```

#### 2. **성능 최적화**
- **연결 풀링**: Deepgram 연결 재사용
- **오디오 압축**: Opus/MP3 → PCM16 변환
- **배치 처리**: 여러 오디오 청크 동시 처리
- **캐싱**: 자주 사용되는 전사 결과 캐시

#### 3. **모니터링 & 관측성**
```python
# Prometheus + Grafana 메트릭
transcription_latency = Histogram("stt_latency_seconds")
active_connections = Gauge("websocket_connections_active")
error_rate = Counter("stt_errors_total")

# Structured Logging
logger.info("transcript_completed", {
    "duration_ms": 150,
    "confidence": 0.92,
    "text_length": 45,
    "user_id": "user123"
})
```

## 🛠️ 기술 스택 심화

### Backend Framework 선택

| Framework | 장점 | 단점 | 실시간 STT 적합성 |
|-----------|------|------|------------------|
| **Starlette** ✅ | • 경량, 빠름<br>• WebSocket 내장<br>• 비동기 최적화 | • 에코시스템 작음<br>• 미들웨어 제한 | **🎯 완벽** |
| FastAPI | • 자동 문서화<br>• 타입 안전성<br>• 큰 에코시스템 | • 오버헤드 있음<br>• 복잡한 설정 | ✅ 좋음 |
| Flask + SocketIO | • 간단한 설정<br>• 풍부한 확장 | • 동기식 기본<br>• 성능 제한 | ⚠️ 제한적 |
| Django Channels | • 풀스택 프레임워크<br>• ORM 내장 | • 무거움<br>• 복잡한 설정 | ⚠️ 과도함 |

### Frontend 대안

| 기술 | 장점 | 단점 | 개발 속도 |
|------|------|------|-----------|
| **Streamlit** ✅ | • 빠른 프로토타입<br>• Python 통합<br>• 자동 리로드 | • 커스터마이징 제한<br>• 성능 제한 | **🚀 최고** |
| React + WebSocket | • 완전한 제어<br>• 풍부한 UI<br>• 성능 우수 | • 복잡한 설정<br>• 긴 개발 시간 | 🐌 느림 |
| Vue.js | • 학습 곡선 완만<br>• 좋은 성능 | • 에코시스템 작음 | ⚡ 보통 |
| Svelte | • 빠른 성능<br>• 작은 번들 | • 새로운 기술<br>• 제한된 자료 | ⚡ 보통 |


## 🎯 사용 사례별 권장 설정

### 📞 콜센터 / 고객상담
```python
# 높은 정확도 + 화자 분리
options = LiveOptions(
    model="nova-2",
    language="ko",
    diarize=True,           # 화자 분리
    punctuate=True,
    smart_format=True,
    profanity_filter=True,  # 욕설 필터
    redact=["pii"],        # 개인정보 마스킹
    sentiment=True,         # 감정 분석
)
```

### 🎓 교육 / 강의
```python
# 실시간 자막 + 키워드 추출
options = LiveOptions(
    model="nova-2",
    language="ko",
    interim_results=True,
    no_delay=True,          # 최소 지연
    keywords=["수학", "과학", "역사"],  # 주요 키워드
    summarize=True,         # 요약 생성
)
```

### 🏥 의료 / 진료
```python
# 의료 전문 용어 + 보안
options = LiveOptions(
    model="nova-2-medical",  # 의료 특화 모델
    language="ko",
    redact=["pii", "medical"],  # 의료정보 보호
    smart_format=True,
    punctuate=True,
)
```

---

**개발**: [byunghyun@illuni.com](mailto:byunghyun@illuni.com)
