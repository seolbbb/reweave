# SBS Pipeline Architecture

> ChatGPT / Claude 대화 JSON → Zettelkasten Obsidian Vault 변환 파이프라인

---

## 1. 전체 흐름 한눈에 보기

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                          sbs convert <input_dir>                           │
└──────┬──────────────────────────────────────────────────────────────────────┘
       │
       ▼
 ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
 │  Stage 0  │───▶│  Stage 1  │───▶│  Stage 2  │───▶│  Stage 3  │───▶│  Stage 4  │───▶│  Stage 5  │
 │   Parse   │    │  Segment  │    │  Extract  │    │ Synthesize│    │   Link    │    │ Validate  │
 │  (no LLM) │    │ (cheap 🟢)│    │ (main 🔵) │    │ (main 🔵) │    │(cheap+main│    │ (cheap 🟢)│
 └───────────┘    └───────────┘    └───────────┘    └───────────┘    │   🟢🔵)  │    └─────┬─────┘
                                                                     └───────────┘          │
                                                                                           ▼
                                                                                   ┌──────────────┐
                                                                                   │  Write Vault  │
                                                                                   │  (no LLM)     │
                                                                                   └──────────────┘
```

**모델 범례**: 🟢 cheap model (경량·저비용) / 🔵 main model (고성능·고비용)

각 스테이지가 완료될 때마다 **체크포인트**가 자동 저장되어, 중단 시 `sbs resume`으로 이어서 실행할 수 있습니다.

---

## 2. 데이터 흐름 (Data Flow)

아래 다이어그램은 파이프라인을 통과하며 **어떤 데이터가 생성되고 다음 단계로 전달되는지** 보여줍니다.

```text
JSON Files
   │
   ▼
NormalizedConversation[]        ← Stage 0 출력
   │
   ▼
Segment[]                       ← Stage 1 출력  (대화를 주제별로 분할)
   │
   ▼
ExtractedKnowledge[]            ← Stage 2 출력  (구조화된 지식 추출)
   │
   ▼
DraftNote[] + SourceNote[]      ← Stage 3 출력  (원자적 노트 합성)
+ LiteratureNote[]
   │
   ▼
NoteLink[] + MOC[]              ← Stage 4 출력  (노트 간 링크 & MOC 생성)
+ FinalNote[]
   │
   ▼
ValidationReport                ← Stage 5 출력  (품질 검증 보고서)
   │
   ▼
Obsidian Vault (파일 시스템)      ← Write Vault
```

위 모든 데이터는 `PipelineState` 객체 하나에 누적되며, 매 스테이지마다 JSON으로 직렬화됩니다.

---

## 3. 각 스테이지 상세

### Stage 0: Parse — 대화 파싱

| 항목 | 내용 |
|------|------|
| **모듈** | `sbs.parsers.detector` → `chatgpt.py` / `claude.py` |
| **LLM 사용** | ❌ 없음 |
| **입력** | `input_dir/` 안의 `*.json` 파일들 |
| **출력** | `NormalizedConversation[]` |

**동작 방식:**

1. `input_dir` 내 모든 `.json` 파일을 탐색
2. 각 파일마다 **자동 포맷 감지** (`can_parse()` Protocol)
   - ChatGPT export → `ChatGPTParser`
   - Claude export → `ClaudeParser`
3. 파서가 대화를 **정규화된 형식**(`NormalizedConversation`)으로 변환
   - 각 메시지: `role` (human / assistant / system) + `content`

> **설계 포인트**: 파서는 `typing.Protocol` 기반 — 클래스 상속 없이 `can_parse()` + `parse()`만 구현하면 새 포맷 추가 가능

---

### Stage 1: Segment — 주제별 분할

| 항목 | 내용 |
|------|------|
| **모듈** | `sbs.agents.segmentation` |
| **LLM 사용** | 🟢 cheap model (긴 대화만) |
| **입력** | `NormalizedConversation[]` |
| **출력** | `Segment[]` |

**동작 방식:**

```text
대화 메시지 수 < 20?
  ├─ YES → 대화 전체를 하나의 Segment로 (LLM 호출 없음)
  └─ NO  → LLM에게 주제 경계(topic boundaries) 식별 요청
            → SegmentBoundary[] 반환
            → 각 경계를 Segment 객체로 변환
```

- **Semaphore 기반 동시성**: `asyncio.Semaphore(config.concurrency)`로 병렬 처리
- **윈도우 청킹**: 긴 대화는 `WINDOW_SIZE=30`, `OVERLAP=5` 메시지 단위로 분할
- 메시지는 `[index] role: content(최대 500자)` 형식으로 LLM에 전달

---

### Stage 2: Extract — 구조화 지식 추출

| 항목 | 내용 |
|------|------|
| **모듈** | `sbs.agents.extraction` |
| **LLM 사용** | 🔵 main model |
| **입력** | `Segment[]` |
| **출력** | `ExtractedKnowledge[]` |

**동작 방식:**

각 Segment에서 아래 7가지 카테고리의 지식을 구조화하여 추출합니다:

| 카테고리 | 설명 | Pydantic 모델 |
|----------|------|---------------|
| **Concepts** | 핵심 개념·정의 | `ConceptItem` |
| **Decisions** | 의사결정과 그 근거 | `DecisionItem` |
| **Insights** | 통찰·발견 | `InsightItem` |
| **Todos** | 해야 할 일 | `TodoItem` |
| **Open Questions** | 미해결 질문 | `OpenQuestion` |
| **References** | 인용된 외부 자료 | `ReferenceItem` |
| **Summary** | 세그먼트 요약 | `str` |

- 메시지가 `MIN_MESSAGES=3` 미만인 세그먼트는 건너뜀
- main model의 **Structured Output** 사용 (Anthropic: `tool_use` / OpenAI: `json_schema`)

---

### Stage 3: Synthesize — 원자적 노트 합성

| 항목 | 내용 |
|------|------|
| **모듈** | `sbs.agents.synthesis` |
| **LLM 사용** | 🔵 main model (노트 합성) + 결정론적 생성 (소스 & 문헌) |
| **입력** | `ExtractedKnowledge[]` + `NormalizedConversation[]` |
| **출력** | `DraftNote[]` + `SourceNote[]` + `LiteratureNote[]` |

**이 스테이지에서 3종류의 노트가 만들어집니다:**

#### A. Knowledge Notes (LLM 생성)

```text
ExtractedKnowledge → LLM → SynthesizedNote[] → DraftNote[]
                                                   ↓
                                          타입 분류: fleeting / permanent
```

- LLM이 각 추출 결과를 **원자적 단일 아이디어 노트**로 합성
- 노트 타입 분류:
  - `permanent` — 근거가 충분한 검증된 지식
  - `fleeting` — 아이디어·초안 수준, 추후 정리 필요
- **결정론적 가드레일** (`_resolve_note_type`): LLM 추천만으로 결정하지 않고, 실제 추출 데이터(concepts + decisions 존재 여부)를 기준으로 보정
- Fleeting 노트에는 `## Expansion Prompts` 섹션 자동 추가 (발전 가이드)

#### B. Source Notes (결정론적 생성, LLM 미사용)

- 각 원본 대화에 대한 **출처 참조 노트** (`SRC-*`)
- 대화 메타데이터 + 어떤 세그먼트가 추출됐는지 기록

#### C. Literature Notes (결정론적 생성, LLM 미사용)

- 추출된 `ReferenceItem`들을 수집하여 `500_literature/Literature.md` 인덱스 생성
- 중복 제거: `title + year` 기반 결정론적 키

---

### Stage 4: Link — 연결 & MOC 생성

| 항목 | 내용 |
|------|------|
| **모듈** | `sbs.agents.linking` |
| **LLM 사용** | 🟢 cheap model (클러스터링) + 🔵 main model (링크 발견) |
| **입력** | `DraftNote[]` |
| **출력** | `NoteLink[]` + `MOC[]` + `FinalNote[]` |

**6단계 내부 프로세스:**

```text
1. Permanent 노트 필터링
      │
      ▼
2. 🟢 클러스터링 (cheap model)
   → ClusterItem[] (주제별 노트 그룹)
      │
      ▼
3. 🔵 클러스터 내 링크 발견 (main model)
   → NoteLink[] (관계: supports, contradicts, extends 등)
      │
      ▼
4. MOC 생성 (3개 이상 permanent 노트가 있는 클러스터)
   → MOC[] (Map of Content)
      │
      ▼
5. 모든 DraftNote의 frontmatter.related에 링크 주입
   → FinalNote[]
      │
      ▼
6. 부가 MOC 생성
   ├─ 고아 permanent 노트 → MOC-miscellaneous.md
   └─ Fleeting 노트 존재 시 → MOC-inbox-triage.md (트리아지 가이드)
```

---

### Stage 5: Validate — 품질 검증

| 항목 | 내용 |
|------|------|
| **모듈** | `sbs.agents.validation` |
| **LLM 사용** | 🟢 cheap model (10% 샘플링 원자성 검사만) |
| **입력** | `PipelineState` 전체 |
| **출력** | `ValidationReport` (점수 0~100) |

**4가지 검증 항목:**

| 검증 | 방식 | 대상 | 내용 |
|------|------|------|------|
| **Frontmatter** | 결정론적 | 모든 노트 | `created` 필수, permanent에 tags 필수, fleeting에 expansion prompts 필수, source에 source_ref 필수 |
| **Link Quality** | 결정론적 | Permanent만 | 존재하지 않는 노트 참조 감지, 노트당 링크 수 상한(15개), 고아 노트 집계 |
| **Completeness** | 결정론적 | 전체 | 모든 원본 대화에 대응하는 source note 존재 여부 |
| **Atomicity** | 🟢 LLM | Permanent 10% 샘플 | 노트가 진정한 "하나의 아이디어"인지 LLM으로 검증 |

**점수 산정:**

```text
기본 점수: 100
  - error 1건당:   -10
  - warning 1건당: -2
  - 원자성 미통과율: -(1 - pass_rate) × 20
최종 점수: max(0, min(100, 계산값))
```

---

### Write Vault — 볼트 출력

| 항목 | 내용 |
|------|------|
| **모듈** | `sbs.output.writer` + `templates.py` + `naming.py` |
| **LLM 사용** | ❌ 없음 |
| **입력** | `PipelineState` |
| **출력** | 파일 시스템에 Obsidian vault 디렉토리 생성 |

파이프라인 최종 단계에서 생성된 모든 노트를 마크다운 파일로 디스크에 씁니다:

```text
vault/
├── 100_inbox/           ← Run-Summary.md (실행 요약)
├── 200_fleeting/        ← fleeting 노트 (정리 필요한 초안)
├── 300_permanent/       ← permanent 노트 (검증된 원자적 지식)
├── 400_mocs/            ← MOC (Map of Content, 주제별 목차)
├── 500_literature/      ← Literature.md (외부 참고문헌 인덱스)
└── 900_sources/         ← SRC-* (원본 대화 출처 노트)
```

---

## 4. LLM 사용 전략

### Two-Tier 모델 구조

| 구분 | 용도 | 사용 스테이지 |
|------|------|--------------|
| **Main model** (🔵 고성능) | 고품질 추론이 필요한 작업 | Stage 2 (추출), Stage 3 (합성), Stage 4 (링크 발견) |
| **Cheap model** (🟢 경량) | 분류·클러스터링 등 단순 작업 | Stage 1 (분할), Stage 4 (클러스터링), Stage 5 (원자성 검사) |

### 구조화 출력 (Structured Output)

모든 LLM 호출은 **Pydantic 모델**로 정의된 스키마를 강제합니다:

| Provider | 방식 |
|----------|------|
| Anthropic | `tool_use` API (도구 호출 형태로 구조화 데이터 반환) |
| OpenAI | `json_schema` response format |

### 에러 처리 & 재시도

- 두 프로바이더 모두 **지수 백오프 재시도**: `[1, 4, 16]`초 대기
- Rate limit, API 에러 시 자동 재시도

### 비용 추적

- 모든 LLM 호출의 토큰 사용량이 `CostSummary`에 실시간 누적
- 파이프라인 완료 시 총 비용(USD) 출력
- `sbs estimate` 명령으로 실행 전 비용 사전 추정 가능

---

## 5. 체크포인트 & 이어하기

```text
.sbs-checkpoints/
├── stage_0_xxxxxxxx.json
├── stage_1_xxxxxxxx.json
├── ...
└── latest.json            ← 가장 최근 체크포인트 (항상 갱신)
```

- 매 스테이지 완료 시 `PipelineState`가 JSON으로 직렬화
- `latest.json`은 항상 최신 상태를 가리킴
- **이어하기**: 이미 완료된 스테이지는 자동으로 건너뜀

```bash
# 중단된 파이프라인 이어서 실행
sbs resume ./.sbs-checkpoints/latest.json
```

---

## 6. CLI 명령어 요약

| 명령어 | 설명 |
|--------|------|
| `sbs convert <input_dir>` | 전체 파이프라인 실행 (Parse → Write Vault) |
| `sbs estimate <input_dir>` | LLM 호출 없이 토큰·비용 사전 추정 |
| `sbs resume <checkpoint>` | 체크포인트에서 파이프라인 이어서 실행 |
| `sbs validate <vault_dir>` | 기존 vault에 대한 결정론적 품질 검사 |

### `sbs convert` 주요 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `-o` / `--output` | `./vault` | 출력 vault 디렉토리 |
| `--provider` | `anthropic` | LLM 프로바이더 (`anthropic` / `openai`) |
| `--model` | 프로바이더 기본값 | main model 이름 |
| `--cheap-model` | 프로바이더 기본값 | cheap model 이름 |
| `--concurrency` | `3` | 최대 LLM 동시 호출 수 |
| `--checkpoint-dir` | `./.sbs-checkpoints` | 체크포인트 저장 디렉토리 |
| `--dry-run` | `false` | LLM 호출 없이 비용만 추정 |
| `--verbose` / `-v` | `false` | 상세 로그 출력 |

---

## 7. 핵심 설계 원칙

| 원칙 | 설명 |
|------|------|
| **6단계 순차 파이프라인** | 각 단계가 명확한 입출력을 가져 디버깅과 재시작이 용이 |
| **Two-Tier LLM** | 비용 최적화: 단순 분류에 cheap model, 고품질 추론에 main model |
| **결정론적 우선** | Source/Literature 노트 생성은 LLM 미사용 → 재현성 보장 |
| **구조화 출력** | 모든 LLM 응답을 Pydantic 모델로 강제 → 타입 안전성 |
| **체크포인트/이어하기** | 스테이지 단위 저장으로 장시간 실행 중 중단에 대응 |
| **Fleeting vs Permanent** | 노트를 물리적으로 분리하여 Obsidian에서 트리아지 시 편의 제공 |
| **Protocol 기반 확장** | 파서, 프로바이더 모두 인터페이스 기반으로 새 구현체 추가 용이 |
