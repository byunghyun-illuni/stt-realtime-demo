# 🎤 Real-time STT Demo with Deepgram

> Deepgram Nova-2 모델을 활용한 **실시간 음성 인식 시스템**  
> FastAPI + WebSocket 기반 저지연 스트리밍으로 토큰 단위 실시간 전사 구현

## ✨ 특징

- **🚀 초저지연**: WebSocket 기반 실시간 스트리밍 (< 100ms)
- **🧠 최신 AI**: Deepgram Nova-2 STT 모델 
- **🌍 다국어**: 한국어 우선, 다국어 음성 인식 지원
- **🎯 고정밀도**: 신뢰도 점수와 함께 정확한 전사
- **📱 웹 기반**: 별도 앱 설치 없이 브라우저에서 바로 실행
- **⚡ 실시간**: 토큰 단위 중간 결과와 최종 결과 동시 제공
- **🔄 양방향**: 실시간 오디오 업로드 및 텍스트 다운로드
- **📖 Swagger**: 자동 생성된 API 문서 및 테스트 UI

## 🏗️ 시스템 아키텍처

### 전체 구조
```
┌─────────────────────┐    WebSocket     ┌─────────────────────┐    WebSocket     ┌─────────────────────┐
│    Streamlit        │ ◄──────────────► │      FastAPI        │ ◄──────────────► │      Deepgram       │
│   (Frontend UI)     │  실시간 양방향    │   (Backend API)     │   실시간 스트림   │    (STT Service)    │
│     :8501           │     통신         │      :8001          │      전송        │    Nova-2 Model     │
└─────────────────────┘                  └─────────────────────┘                  └─────────────────────┘
        │                                         │                                         │
        │ 1. 마이크 캡처                           │ 2. 오디오 중계                           │ 3. 실시간 전사
        │ 2. Base64 인코딩                        │ 3. 프로토콜 변환                        │ 4. 신뢰도 계산
        │ 3. 실시간 표시                          │ 4. Swagger 문서                         │ 5. 토큰 스트리밍
        │                                         │ 5. 통계 모니터링                        │
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
📱 Client (Streamlit)           🖥️  Server (FastAPI)           ☁️  Deepgram API
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
│   ├── main.py                  # FastAPI 앱 + 라우팅 + Swagger
│   ├── models.py                # Pydantic 모델 (API 스키마)
│   └── stt_service.py           # Deepgram STT 로직
├── 📱 client/                    # 프론트엔드 클라이언트
│   └── streamlit_app.py         # Streamlit UI + WebSocket 클라이언트
├── ⚙️ pyproject.toml            # 의존성 관리 (FastAPI + uv/pip)
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

# 의존성 설치 (FastAPI 포함)
uv pip install -e .
# 또는 pip install -e .
```

### 2. API 키 설정

```bash
echo "DEEPGRAM_API_KEY=your_deepgram_api_key_here" > .env
```

### 3. 서버 실행 (필수)

```bash
# 터미널 1: FastAPI 서버 실행
uvicorn server.main:app --reload --port 8001

# 🎯 주요 URL들:
# • 홈페이지: http://localhost:8001
# • Swagger UI: http://localhost:8001/docs  ⭐
# • ReDoc: http://localhost:8001/redoc
# • WebSocket: ws://localhost:8001/ws/stt
# • Health Check: http://localhost:8001/health
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
| **FastAPI 서버** | `localhost` | `8001` | STT WebSocket API + Swagger |
| **Swagger UI** | `http://localhost:8001/docs` | - | **🎯 API 문서 및 테스트** |
| **프론트엔드** | `localhost` | `8501` | Streamlit Web UI |
| **WebSocket** | `ws://localhost:8001/ws/stt` | - | 실시간 음성 통신 |
| **ReDoc** | `http://localhost:8001/redoc` | - | 대안 API 문서 |

## 🔧 API 엔드포인트

| 엔드포인트 | 메서드 | 설명 | Swagger에서 테스트 |
|-----------|--------|------|------------------|
| `/` | GET | 홈페이지 (문서 링크) | ✅ |
| `/docs` | GET | **Swagger UI** | **🎯 메인 문서** |
| `/health` | GET | 서버 상태 확인 | ✅ |
| `/info` | GET | 서비스 정보 | ✅ |
| `/stats` | GET | 실시간 사용 통계 | ✅ |
| `/usage` | GET | WebSocket 사용법 | ✅ |
| `/ws/stt` | WebSocket | 실시간 음성 인식 | WebSocket 전용 |

### 📊 새로운 모니터링 API

```bash
# 실시간 서비스 통계 확인
curl http://localhost:8001/stats

# 응답 예시:
{
  "active_connections": 2,
  "total_transcriptions": 157,
  "average_confidence": 0.934,
  "uptime_seconds": 3600.5,
  "supported_languages": ["ko", "en", "ja", "zh", "es", "fr", "de"]
}
```

## 💡 Swagger UI 활용법

### 🎯 **핵심**: http://localhost:8001/docs 접속

1. **API 문서 탐색**: 모든 엔드포인트 자동 문서화
2. **실시간 테스트**: "Try it out" 버튼으로 API 직접 호출
3. **스키마 확인**: Request/Response 모델 상세 보기
4. **WebSocket 가이드**: `/usage` 엔드포인트에서 연결법 확인

### 📋 프론트엔드 개발자를 위한 가이드

```typescript
// TypeScript 타입 정의 (Swagger에서 자동 생성 가능)
interface TranscriptResponse {
  type: "transcript_interim" | "transcript_final";
  text: string;
  confidence: number;
  is_final: boolean;
  timestamp: number;
}

interface AudioMessage {
  type: "audio_data";
  audio: string; // Base64 PCM16
  timestamp?: number;
}

// WebSocket 연결 예시
const ws = new WebSocket('ws://localhost:8001/ws/stt');

ws.onmessage = (event) => {
  const data: TranscriptResponse = JSON.parse(event.data);
  if (data.type === 'transcript_final') {
    console.log(`최종 전사: ${data.text} (신뢰도: ${data.confidence})`);
  }
};
```

## 🛠️ 기술 스택

- **Backend**: FastAPI + Uvicorn (비동기 WebSocket + Swagger)
- **Frontend**: Streamlit (실시간 웹 UI)
- **Audio**: sounddevice + numpy (크로스 플랫폼)
- **STT**: Deepgram Nova-2 (실시간 음성 인식)
- **Protocol**: WebSocket (양방향 실시간 통신)
- **Documentation**: OpenAPI 3.0 + Swagger UI

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

# Swagger UI 접속
open http://localhost:8001/docs

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

### FastAPI 문제 시
- 의존성 확인: `uv pip install fastapi pydantic`
- Swagger 접속: http://localhost:8001/docs
- 로그 확인: 터미널에서 자세한 오류 메시지 확인

## 📊 성능 최적화

### 지연시간 최소화
- `no_delay=True` 옵션 사용
- 16kHz 샘플링 레이트 권장
- 네트워크 대역폭 충분히 확보

### 정확도 향상
- 조용한 환경에서 녹음
- 명확한 발음으로 말하기
- 마이크와 적절한 거리 유지

## 🎯 프론트엔드 개발자 가이드

### 1. **Swagger로 API 이해하기**
1. http://localhost:8001/docs 접속
2. `/usage` 엔드포인트로 WebSocket 사용법 확인
3. 각 스키마 모델 확인하여 TypeScript 타입 생성

### 2. **WebSocket 연결**
```javascript
const ws = new WebSocket('ws://localhost:8001/ws/stt');
ws.onopen = () => console.log('STT 연결됨');
```

### 3. **오디오 데이터 전송**
```javascript
// 마이크에서 PCM16 데이터를 Base64로 인코딩하여 전송
ws.send(JSON.stringify({
  type: 'audio_data',
  audio: base64AudioData
}));
```

### 4. **실시간 전사 결과 처리**
```javascript
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'transcript_interim') {
    // 실시간 입력 중인 텍스트 (타이핑 효과)
    updateRealtimeText(data.text);
  } else if (data.type === 'transcript_final') {
    // 최종 확정된 전사 결과
    addFinalTranscript(data.text, data.confidence);
  }
};
```

### 5. **에러 처리**
```javascript
ws.onerror = (error) => {
  console.error('STT 오류:', error);
};

ws.onclose = (event) => {
  console.log('STT 연결 종료:', event.code);
};
```

---

**개발**: [byunghyun@illuni.com](mailto:byunghyun@illuni.com)  
**API 문서**: http://localhost:8001/docs 🎯  
**GitHub**: [STT Real-time Demo](https://github.com/your-repo)
