# SBS 검증 & 개선 가이드

> Gemini 3 Flash/Pro를 사용한 파이프라인 검증 실험 → 결과 분석 → 프로바이더 교체까지의 전체 워크플로우

---

## 0. 실험 환경 개요

| 항목 | 값 |
|------|-----|
| **입력 데이터** | `data/` 내 ChatGPT·Claude 내보내기 아카이브 |
| **실험 프로바이더** | Google Gemini (`gemini-3-flash` / `gemini-3-pro`) |
| **프로덕션 프로바이더** | 실험 결과에 따라 결정 (Anthropic, OpenAI, Google 중) |
| **검증 목표** | 파이프라인이 end-to-end로 정상 동작하는지 확인, 출력 품질 평가, 비용 효율 측정 |

```text
실험 흐름:

Phase 1: 스모크 테스트 (동작 여부)
   │
   ▼
Phase 2: 소규모 실행 (품질 확인)
   │
   ▼
Phase 3: 전체 데이터 실행 (비용·성능 측정)
   │
   ▼
Phase 4: 결과 분석 & 개선
   │
   ▼
Phase 5: 프로바이더 비교 & 전환
```

---

## 1. 사전 준비

### 1.1 환경 설정

```bash
# .env 파일에 Google API 키 설정
GOOGLE_API_KEY=AIza...
SBS_PROVIDER=google
SBS_MODEL=gemini-3-pro
SBS_CHEAP_MODEL=gemini-3-flash
```

### 1.2 설치 확인

```bash
# 패키지 설치
uv sync

# CLI 동작 확인
sbs --version
```

### 1.3 입력 데이터 확인

```bash
# 파싱이 되는지 먼저 확인 (LLM 호출 없이)
sbs estimate data/
```

이 명령으로 확인할 것:
- 대화 수, 총 메시지 수, 예상 토큰 수
- 예상 비용 (Gemini 기준)

---

## 2. Phase 1 — 스모크 테스트

> 목표: 파이프라인이 에러 없이 끝까지 돌아가는지 확인

### 2.1 소량 데이터 준비

전체 데이터를 한 번에 돌리지 말고, 작은 서브셋으로 먼저 테스트합니다.

```bash
# 테스트용 디렉토리 생성 — conversations.json에서 대화 2~3개만 추출
mkdir -p data/test-small
# conversations.json에서 처음 2개 대화만 잘라내서 복사
# (Python이나 jq 사용)
python -c "
import json
from pathlib import Path

# ChatGPT 데이터 예시
for json_file in Path('data/').rglob('conversations.json'):
    data = json.loads(json_file.read_text(encoding='utf-8'))
    if isinstance(data, list) and len(data) > 2:
        subset = data[:2]
    else:
        subset = data
    out = Path('data/test-small') / json_file.name
    out.write_text(json.dumps(subset, ensure_ascii=False), encoding='utf-8')
    print(f'Wrote {len(subset) if isinstance(subset, list) else 1} conversations to {out}')
    break
"
```

### 2.2 첫 실행

```bash
sbs convert data/test-small \
  -o vault-test-smoke \
  --provider google \
  --concurrency 2 \
  --verbose
```

### 2.3 스모크 테스트 체크리스트

| # | 확인 항목 | 통과 기준 | 결과 |
|---|----------|----------|------|
| 1 | Stage 0 (Parse) 완료 | 에러 없이 NormalizedConversation 생성 | |
| 2 | Stage 1 (Segment) 완료 | Segment 객체 생성, LLM 응답 파싱 성공 | |
| 3 | Stage 2 (Extract) 완료 | Structured output이 Pydantic 모델에 매핑 | |
| 4 | Stage 3 (Synthesize) 완료 | DraftNote, SourceNote 생성 | |
| 5 | Stage 4 (Link) 완료 | NoteLink, MOC 생성 | |
| 6 | Stage 5 (Validate) 완료 | ValidationReport 점수 출력 | |
| 7 | Vault 디렉토리 생성 | `vault-test-smoke/` 하위 폴더 존재 | |
| 8 | 마크다운 파일 생성 | `.md` 파일들이 올바른 frontmatter 포함 | |
| 9 | 비용 리포트 | 총 토큰 사용량·비용 출력 | |

### 2.4 실패 시 디버깅

```bash
# 체크포인트에서 어디까지 진행됐는지 확인
ls .sbs-checkpoints/

# 특정 스테이지 체크포인트 내용 확인 (JSON)
python -c "
import json
from pathlib import Path
cp = sorted(Path('.sbs-checkpoints').glob('stage_*.json'))
for f in cp:
    data = json.loads(f.read_text())
    print(f'{f.name}: completed_stage={data.get(\"completed_stage\", \"?\")}')
"

# 실패한 스테이지부터 재실행
sbs resume .sbs-checkpoints/latest.json --verbose
```

**흔한 실패 원인:**

| 증상 | 원인 | 해결 |
|------|------|------|
| `401 Unauthorized` | API 키 미설정/잘못됨 | `.env`의 `GOOGLE_API_KEY` 확인 |
| `429 Rate Limited` | 동시 요청 초과 | `--concurrency 1`로 낮추기 |
| JSON 파싱 실패 | Gemini가 스키마에 안 맞는 응답 반환 | `--verbose`로 원본 응답 확인, 이슈 기록 |
| `ValidationError` | 구조화 출력 필드 누락 | Gemini의 `response_schema` 지원 범위 확인 |

---

## 3. Phase 2 — 소규모 품질 검증

> 목표: 생성된 노트의 내용 품질을 직접 눈으로 확인

### 3.1 좀 더 큰 데이터로 실행

```bash
# 대화 10~20개 정도의 서브셋 준비 후
sbs convert data/test-medium \
  -o vault-test-quality \
  --provider google \
  --concurrency 3 \
  --verbose
```

### 3.2 수동 품질 체크리스트

#### A. Permanent 노트 (`300_permanent/`)

| # | 평가 항목 | 기준 | 점수 (1-5) | 비고 |
|---|----------|------|-----------|------|
| 1 | **원자성** | 노트 하나가 하나의 아이디어만 다루는가? | | |
| 2 | **정확성** | 원본 대화의 내용을 정확히 반영하는가? | | |
| 3 | **완결성** | 맥락 없이 읽어도 이해 가능한가? | | |
| 4 | **태그 품질** | 태그가 내용과 관련 있고 일관적인가? | | |
| 5 | **제목 품질** | 노트 제목이 내용을 잘 요약하는가? | | |

#### B. Fleeting 노트 (`200_fleeting/`)

| # | 평가 항목 | 기준 | 점수 (1-5) | 비고 |
|---|----------|------|-----------|------|
| 1 | **분류 적절성** | permanent가 아닌 fleeting으로 분류된 게 맞는가? | | |
| 2 | **확장 프롬프트** | `## Expansion Prompts`가 실제로 유용한가? | | |

#### C. 링크 & MOC (`400_mocs/`)

| # | 평가 항목 | 기준 | 점수 (1-5) | 비고 |
|---|----------|------|-----------|------|
| 1 | **관계 정확성** | 링크된 노트들이 실제로 관련이 있는가? | | |
| 2 | **관계 유형** | supports/contradicts/extends 등이 적절한가? | | |
| 3 | **MOC 구조** | MOC가 주제를 잘 대표하는가? | | |
| 4 | **누락 링크** | 연결되어야 할 노트가 빠져있는가? | | |

#### D. Source 노트 (`900_sources/`)

| # | 평가 항목 | 기준 | 점수 (1-5) | 비고 |
|---|----------|------|-----------|------|
| 1 | **추적성** | 원본 대화로의 역추적이 가능한가? | | |
| 2 | **매핑 완전성** | 모든 대화에 source 노트가 있는가? | | |

### 3.3 자동 검증 실행

```bash
# 파이프라인 내장 검증 (Stage 5 결과 재확인)
sbs validate vault-test-quality
```

검증 점수 해석:

| 점수 | 판정 | 의미 |
|------|------|------|
| 90-100 | 우수 | 프로덕션 사용 가능 |
| 70-89 | 양호 | 사소한 개선 필요 |
| 50-69 | 미흡 | 주요 문제 있음, 프롬프트/로직 개선 필요 |
| 0-49 | 불량 | 근본적 문제, 프로바이더 변경 또는 대폭 수정 필요 |

### 3.4 Obsidian에서 직접 확인

```bash
# Obsidian에서 vault를 열어 실제 사용 관점에서 확인
# vault-test-quality 폴더를 Obsidian vault로 열기
```

Obsidian에서 확인할 것:
- `[[wikilink]]`가 정상 작동하는가?
- 그래프 뷰에서 노트 간 연결이 자연스러운가?
- MOC에서 관련 노트로 탐색이 원활한가?
- 태그 기반 필터링이 유용한가?

---

## 4. Phase 3 — 전체 데이터 실행 & 비용 측정

> 목표: 실제 전체 데이터로 실행하여 비용과 시간 측정

### 4.1 비용 사전 추정

```bash
sbs estimate data/ --provider google
```

**Gemini 가격 참고 (per 1M tokens):**

| 모델 | Input | Output |
|------|-------|--------|
| `gemini-3-pro` (main) | $3.50 | $10.50 |
| `gemini-3-flash` (cheap) | $0.30 | $2.50 |

### 4.2 전체 실행

```bash
sbs convert data/ \
  -o vault-full \
  --provider google \
  --concurrency 3 \
  --verbose 2>&1 | tee run-full.log
```

> `tee`로 로그를 파일에도 저장하여 나중에 분석 가능

### 4.3 측정 기록 템플릿

아래 표를 실행 후 채워 넣으세요:

```markdown
## 실행 결과 기록

| 항목 | 값 |
|------|-----|
| **실행 일시** | |
| **프로바이더** | google (gemini-3-pro / gemini-3-flash) |
| **입력 대화 수** | |
| **총 메시지 수** | |
| **총 세그먼트 수** | |
| **생성 노트 수 (permanent)** | |
| **생성 노트 수 (fleeting)** | |
| **생성 MOC 수** | |
| **총 input 토큰** | |
| **총 output 토큰** | |
| **총 비용 (USD)** | |
| **소요 시간** | |
| **Validation 점수** | |
| **에러/재시도 횟수** | |
| **concurrency** | 3 |
```

### 4.4 스테이지별 토큰 분석

체크포인트에서 스테이지별 비용을 추출하여 어느 단계가 비용을 많이 쓰는지 파악합니다.

```python
# 스테이지별 비용 분석 스크립트
import json
from pathlib import Path

checkpoints = sorted(Path('.sbs-checkpoints').glob('stage_*.json'))
prev_cost = 0.0
prev_input = 0
prev_output = 0

for cp_file in checkpoints:
    data = json.loads(cp_file.read_text(encoding='utf-8'))
    cost_data = data.get('cost_summary', {})
    cur_cost = cost_data.get('estimated_cost_usd', 0)
    cur_input = cost_data.get('total_input_tokens', 0)
    cur_output = cost_data.get('total_output_tokens', 0)

    stage_cost = cur_cost - prev_cost
    stage_input = cur_input - prev_input
    stage_output = cur_output - prev_output

    print(f"{cp_file.stem}:")
    print(f"  input tokens:  {stage_input:>10,}")
    print(f"  output tokens: {stage_output:>10,}")
    print(f"  cost:          ${stage_cost:.4f}")
    print()

    prev_cost = cur_cost
    prev_input = cur_input
    prev_output = cur_output

print(f"TOTAL: ${prev_cost:.4f}")
```

---

## 5. Phase 4 — 결과 분석 & 개선

### 5.1 발견된 문제 분류 & 대응

문제를 아래 카테고리로 분류하고 각각의 개선 방법을 적용합니다.

#### Category A: 파싱 문제 (Stage 0)

| 문제 | 원인 | 개선 방안 |
|------|------|----------|
| 일부 대화가 누락됨 | JSON 구조 불일치 | 파서 로직 수정 (`chatgpt.py`, `claude.py`) |
| 빈 대화가 포함됨 | 필터링 미비 | `detector.py`에 최소 메시지 수 필터 추가 |
| 인코딩 에러 | 특수문자 처리 | 파서에 인코딩 폴백 추가 |

#### Category B: 세그먼트 품질 (Stage 1)

| 문제 | 원인 | 개선 방안 |
|------|------|----------|
| 세그먼트가 너무 잘게 나뉨 | 프롬프트가 과도하게 분할 유도 | 프롬프트 수정: 최소 세그먼트 크기 기준 추가 |
| 세그먼트 경계가 부자연스러움 | 모델 성능 한계 | WINDOW_SIZE/OVERLAP 조정, 또는 main model 사용 |
| 같은 주제가 여러 세그먼트로 | 윈도우 간 주제 연속성 미감지 | 윈도우 간 병합 로직 추가 |

#### Category C: 추출 품질 (Stage 2)

| 문제 | 원인 | 개선 방안 |
|------|------|----------|
| 추출된 개념이 피상적 | 프롬프트 부족 | 더 구체적인 추출 프롬프트, 예시 추가 |
| 중요 정보 누락 | 세그먼트가 너무 짧음 | MIN_MESSAGES 임계값 조정 |
| 할루시네이션 | 모델 한계 | temperature 조정, 원본 텍스트 참조 강제 |
| 한국어 처리 미흡 | 다국어 프롬프트 부재 | 프롬프트에 언어 감지/처리 지시 추가 |

#### Category D: 합성 품질 (Stage 3)

| 문제 | 원인 | 개선 방안 |
|------|------|----------|
| 노트가 원자적이지 않음 | 여러 아이디어 혼재 | 합성 프롬프트에 원자성 기준 강화 |
| fleeting/permanent 분류 오류 | 가드레일 로직 부족 | `_resolve_note_type` 기준 조정 |
| 노트 제목이 모호함 | 제목 생성 프롬프트 부족 | 제목 규칙 명시 (동사+목적어, 구체적 키워드) |

#### Category E: 링크 품질 (Stage 4)

| 문제 | 원인 | 개선 방안 |
|------|------|----------|
| 관련 없는 노트가 링크됨 | 클러스터링 오류 | 클러스터 수/크기 기준 조정 |
| 중요 연결이 누락됨 | 클러스터 간 링크 미탐색 | cross-cluster 링크 탐색 추가 |
| MOC가 너무 많음/적음 | 클러스터 임계값 | MOC 생성 기준 조정 (최소 노트 수) |

### 5.2 프롬프트 개선 워크플로우

프롬프트 수정이 가장 효과적인 개선 방법입니다. 아래 순서로 진행합니다.

```text
1. 문제 있는 출력 샘플 수집 (2~3건)
      │
      ▼
2. 해당 스테이지의 프롬프트 코드 확인
   - segmentation.py → SEGMENTATION_PROMPT
   - extraction.py   → EXTRACTION_PROMPT
   - synthesis.py    → SYNTHESIS_PROMPT
   - linking.py      → CLUSTERING_PROMPT, LINKING_PROMPT
      │
      ▼
3. 프롬프트 수정 (한 번에 하나의 변수만)
      │
      ▼
4. 동일 입력으로 재실행하여 비교
      │
      ▼
5. 개선 확인 시 다음 문제로, 미개선 시 다른 수정 시도
```

### 5.3 파라미터 튜닝 가이드

| 파라미터 | 위치 | 기본값 | 조정 방향 |
|---------|------|--------|----------|
| `WINDOW_SIZE` | `segmentation.py` | 30 | 대화가 길면 ↑, 세그먼트 품질 낮으면 ↓ |
| `OVERLAP` | `segmentation.py` | 5 | 주제 연속성 끊기면 ↑ |
| `MIN_MESSAGES` | `extraction.py` | 3 | 노이즈 많으면 ↑ |
| `concurrency` | CLI 옵션 | 3 | Rate limit 나면 ↓, 빠르게 하려면 ↑ |
| 클러스터 최소 노트 수 | `linking.py` | 3 | MOC 너무 많으면 ↑ |

---

## 6. Phase 5 — 프로바이더 비교 & 전환

### 6.1 비교 실험 설계

동일한 입력 데이터(Phase 2에서 사용한 test-medium)로 프로바이더별 실행:

```bash
# Gemini (이미 완료)
sbs convert data/test-medium -o vault-gemini --provider google

# Anthropic
sbs convert data/test-medium -o vault-anthropic --provider anthropic

# OpenAI
sbs convert data/test-medium -o vault-openai --provider openai
```

### 6.2 비교 평가 매트릭스

| 평가 항목 | Gemini | Anthropic | OpenAI |
|----------|--------|-----------|--------|
| **Validation 점수** | | | |
| **총 비용 (USD)** | | | |
| **소요 시간** | | | |
| **에러/재시도 횟수** | | | |
| **Permanent 노트 수** | | | |
| **Fleeting 노트 수** | | | |
| **노트 원자성 (수동 1-5)** | | | |
| **추출 정확성 (수동 1-5)** | | | |
| **링크 품질 (수동 1-5)** | | | |
| **한국어 처리 (수동 1-5)** | | | |
| **구조화 출력 안정성** | | | |

### 6.3 비용 효율 비교

```text
가격 비교 (per 1M tokens):

                    Input     Output
                    ------    ------
gemini-3-pro        $3.50     $10.50
claude-sonnet-4.5   $3.00     $15.00
gpt-4o              $2.50     $10.00

gemini-3-flash      $0.30     $2.50
claude-haiku-4.5    $0.80     $4.00
gpt-4o-mini         $0.15     $0.60
```

**비용 관점 고려사항:**
- Gemini Flash는 cheap model로 가성비 좋음 (Flash $0.30 vs Mini $0.15 — 큰 차이 아님)
- Main model은 GPT-4o가 input 기준 가장 저렴하지만, 구조화 출력 품질도 고려해야 함
- 실제 비용은 토큰 효율(같은 입력에 대해 출력 토큰 수)에도 의존

### 6.4 프로바이더 전환 방법

비교 결과 프로덕션 프로바이더를 결정한 후:

```bash
# .env 수정
SBS_PROVIDER=anthropic          # 또는 openai, google
SBS_MODEL=claude-sonnet-4-5-20250929
SBS_CHEAP_MODEL=claude-haiku-4-5-20251001
```

또는 CLI에서 직접:

```bash
sbs convert data/ \
  -o vault \
  --provider anthropic \
  --model claude-sonnet-4-5-20250929 \
  --cheap-model claude-haiku-4-5-20251001
```

### 6.5 하이브리드 전략 (향후 고려)

현재 아키텍처는 파이프라인 전체가 하나의 프로바이더를 사용하지만, 스테이지별로 최적의 모델이 다를 수 있습니다:

```text
예시: 비용 최적 조합 (가설)
  Stage 1 (Segment):   gemini-3-flash  — 가성비 좋은 분류
  Stage 2 (Extract):   claude-sonnet   — 정확한 구조화 추출
  Stage 3 (Synthesize): claude-sonnet   — 고품질 노트 합성
  Stage 4 (Link):      gpt-4o-mini     — 저렴한 클러스터링
  Stage 5 (Validate):  gemini-3-flash  — 저렴한 검증
```

이 전략을 구현하려면 스테이지별 프로바이더/모델 오버라이드 기능이 필요합니다. 실험 결과에 따라 향후 개선 과제로 고려하세요.

---

## 7. 반복 개선 체크리스트

매 실험 라운드마다 아래 항목을 점검합니다:

### Round N 기록 템플릿

```markdown
### Round [N] — [날짜]

**변경 사항:**
- [ 변경한 내용 기술 ]

**실행 조건:**
- Provider:
- Model:
- Data:
- Concurrency:

**결과:**
- Validation 점수:
- 총 비용: $
- 소요 시간:

**관찰:**
- [ 좋아진 점 ]
- [ 여전히 문제인 점 ]

**다음 라운드 계획:**
- [ 다음에 시도할 것 ]
```

---

## 8. 알려진 주의사항

### Gemini 관련

- **구조화 출력**: `response_schema`를 사용하지만, 복잡한 nested 스키마에서 필드 누락이 간헐적으로 발생할 수 있음. `--verbose`로 원본 응답을 확인하세요.
- **Rate Limit**: 무료 티어는 분당 요청 제한이 낮음. `--concurrency 1~2`로 시작하세요.
- **한국어**: Gemini의 한국어 구조화 출력 품질은 영어 대비 낮을 수 있음. 프롬프트를 영어로 유지하되 입력 데이터는 원본 언어 그대로 전달하는 것을 권장합니다.

### 데이터 관련

- **대용량 ZIP**: `data/` 내 대용량 아카이브는 메모리 사용량 주의. 압축 해제 후 사용 권장.
- **이미지 포함 대화**: 현재 파이프라인은 텍스트만 처리. 이미지가 포함된 메시지의 `content`가 비어있을 수 있음.

### 체크포인트 관련

- 프로바이더를 바꿔서 실행할 때는 이전 체크포인트를 사용하지 마세요. 새로 시작하거나 체크포인트 디렉토리를 분리하세요.
  ```bash
  sbs convert data/ -o vault-gemini --provider google --checkpoint-dir .sbs-cp-gemini
  sbs convert data/ -o vault-anthropic --provider anthropic --checkpoint-dir .sbs-cp-anthropic
  ```

---

## 9. 요약: 최소 실행 경로

가장 빠르게 검증을 시작하려면:

```bash
# 1. 비용 추정
sbs estimate data/ --provider google

# 2. 소량 스모크 테스트
sbs convert data/test-small -o vault-smoke --provider google --concurrency 2 -v

# 3. 결과 확인
sbs validate vault-smoke
# + Obsidian에서 열어보기

# 4. 문제 없으면 전체 실행
sbs convert data/ -o vault-full --provider google --concurrency 3 -v 2>&1 | tee run.log

# 5. 결과 기록 & 다음 프로바이더 비교
```
