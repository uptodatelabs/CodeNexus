# CodeNexus AI

**AI 코딩 에이전트를 위한 컨텍스트 엔진**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/pypi/v/codenexus-ai.svg)](https://pypi.org/project/codenexus-ai/)

[English](README.md) | [한국어](README.ko.md)

---

## CodeNexus란?

CodeNexus는 **로컬 우선 컨텍스트 엔진**으로, AI 코딩 에이전트가 코드베이스를 더 잘 이해하도록 돕습니다. 코드의 실시간 의존성 그래프를 구축하고, AI 에이전트에 관련된 컨텍스트만 제공하여 토큰 사용량을 **50-70%** 절감하면서 코드 품질을 향상시킵니다.

### 주요 기능

- **로컬 우선**: 코드가 기계를 벗어나지 않음
- **토큰 절감**: AI API 비용 50-70% 절약
- **멀티 언어**: Python, JavaScript, TypeScript 지원
- **MCP 호환**: Claude Code, Cursor 등과 연동
- **빠른 인덱싱**: SQLite 기반 의존성 그래프
- **PageRank**: 중요도 기반 스마트 랭킹

---

## 빠른 시작

### 설치

```bash
pip install codenexus-ai
```

### 기본 사용법

```bash
# 프로젝트 인덱싱
codenexus index

# 컨텍스트 검색
codenexus search "인증 미들웨어"

# 컨텍스트 파이프라인 실행
codenexus pipeline "로그인 버그 수정"

# 상태 확인
codenexus status

# 상위 노드 보기
codenexus top

# 임팩트 분석
codenexus impact "main"
```

---

## 작동 방식

```
코드베이스
     ↓
[CodeNexus 인덱서]
     ↓
┌─────────────────────────────────────┐
│  의존성 그래프 (SQLite + FTS5)      │
│  - 함수, 클래스, 임포트             │
│  - 호출 관계                        │
│  - 타입 정보                        │
│  - PageRank 중앙성                  │
└─────────────────────────────────────┘
     ↓
[컨텍스트 캡슐 생성기]
     ↓
┌─────────────────────────────────────┐
│  AI 에이전트를 위한 최적화된 컨텍스트│
│  - 피봇 파일: 전체 소스             │
│  - 지원 파일: 스켈리톤만            │
│  - 토큰 예산: 준수                  │
└─────────────────────────────────────┘
     ↓
AI 에이전트 (Claude Code, Cursor 등)
```

---

## Claude Code 연동

CodeNexus는 Claude Code와 연동하여 AI 코딩 에이전트의 토큰 사용량을 줄입니다.

### 설정 방법

#### 1. CodeNexus 설치

```bash
pip install codenexus-ai
```

#### 2. `.claude.json` 파일 편집

**파일 위치:**
- macOS/Linux: `~/.claude.json`
- Windows: `C:\Users\사용자이름\.claude.json`

#### 3. 설정 추가

`~/.claude.json` 파일에 다음 내용을 추가하세요:

```json
{
  "mcpServers": {
    "codenexus": {
      "command": "codenexus",
      "args": ["serve", "-w", "여기에_프로젝트_경로"]
    }
  }
}
```

**⚠️ 중요: `여기에_프로젝트_경로`는 CodeNexus를 사용할 프로젝트의 경로입니다.**

### 경로 설정 예시

**❌ 잘못된 예시:**
```json
"args": ["serve", "-w", "C:\\Users\\username\\.codenexus"]
```
→ CodeNexus 설정 디렉토리 (오류)

**✅ 올바른 예시:**
```json
"args": ["serve", "-w", "C:\\Users\\username\\projects\\my-app"]
```
→ CodeNexus를 사용할 프로젝트 디렉토리

### OS별 경로 예시

**Windows:**
```json
{
  "mcpServers": {
    "codenexus": {
      "command": "codenexus",
      "args": ["serve", "-w", "C:\\Users\\username\\projects\\my-app"]
    }
  }
}
```

**macOS/Linux:**
```json
{
  "mcpServers": {
    "codenexus": {
      "command": "codenexus",
      "args": ["serve", "-w", "/home/username/projects/my-app"]
    }
  }
}
```

### 여러 프로젝트 설정

여러 프로젝트에서 CodeNexus를 사용하려면, 각 프로젝트별로 설정을 추가하세요:

```json
{
  "projects": {
    "C:\\Users\\username\\projects\\app1": {
      "mcpServers": {
        "codenexus": {
          "command": "codenexus",
          "args": ["serve", "-w", "C:\\Users\\username\\projects\\app1"]
        }
      }
    },
    "C:\\Users\\username\\projects\\app2": {
      "mcpServers": {
        "codenexus": {
          "command": "codenexus",
          "args": ["serve", "-w", "C:\\Users\\username\\projects\\app2"]
        }
      }
    }
  }
}
```

### 설정 확인

1. `.claude.json` 파일 저장
2. Claude Code 재시작
3. CodeNexus를 사용할 프로젝트 디렉토리에서 Claude 실행

```bash
cd C:\Users\username\projects\my-app
claude
```

### 문제 해결

**MCP 서버가 연결되지 않는 경우:**

1. CodeNexus가 설치되어 있는지 확인:
   ```bash
   pip show codenexus-ai
   ```

2. 코드 실행 테스트:
   ```bash
   codenexus --version
   ```

3. 경로가 올바른지 확인 (따옴표 주의)

---

## 지원 언어

| 언어 | 상태 |
|------|------|
| Python | ✅ 완전 지원 |
| JavaScript | ✅ 완전 지원 |
| TypeScript | ✅ 완전 지원 |
| Go | ✅ 완전 지원 |
| Rust | ✅ 완전 지원 |
| Java | ✅ 완전 지원 |
| C# | ✅ 완전 지원 |

---

## 다른 AI 에이전트 연동

CodeNexus는 다양한 AI 코딩 에이전트와 함께 사용할 수 있습니다.

### OpenClaw 연동

[OpenClaw](https://github.com/openclaw/openclaw)는 WhatsApp, Telegram, Slack, Discord 등과 연결되는 개인 AI 어시스턴트입니다.

#### 설정 방법

OpenClaw는 MCP를 직접 지원하지 않습니다. 스킬 시스템을 통해 CLI 명령어를 사용합니다.

**1. CodeNexus 설치:**

```bash
pip install codenexus-ai
```

**2. OpenClaw 스킬 생성:**

`~/.openclaw/workspace/skills/codenexus/SKILL.md` 파일 생성:

```markdown
---
name: codenexus
description: CodeNexus로 코드 검색 및 분석
allowed_tools:
  - bash
---

# CodeNexus 스킬

CodeNexus를 사용하여 워크스페이스의 코드를 검색하고 분석합니다.

## 명령어

- `codenexus index` - 워크스페이스 인덱싱
- `codenexus search "query"` - 코드 검색
- `codenexus pipeline "task"` - 태스크용 컨텍스트 생성
```

**3. OpenClaw에서 사용:**

```
/codenexus search "인증 미들웨어"
/codenexus pipeline "로그인 버그 수정"
```

### Hermes Agent 연동

[Hermes Agent](https://github.com/NousResearch/hermes-agent)는 Nous Research의 자기 개선 AI 에이전트입니다.

#### 설정 방법

Hermes는 MCP 서버를 지원합니다. CodeNexus를 MCP 서버로 설정하세요.

**1. CodeNexus 설치:**

```bash
pip install codenexus-ai
```

**2. MCP 서버 추가:**

```bash
hermes mcp add codenexus -- codenexus serve -w /path/to/your/project
```

또는 `~/.hermes/config.yaml`에 추가:

```yaml
mcp_servers:
  codenexus:
    command: codenexus
    args:
      - serve
      - -w
      - /path/to/your/project
```

**3. Hermes에서 사용:**

```
/hermes search "인증 미들웨어"
/hermes pipeline "로그인 버그 수정"
```

### 다른 에이전트

CLI 명령어를 지원하는 모든 에이전트에서 사용 가능:

```bash
# 직접 CLI 사용
codenexus index
codenexus search "query"
codenexus pipeline "task"
codenexus status

# 프로그래밍 방식 사용을 위한 JSON 출력
codenexus search "query" --json
```

---

## 토큰 절감 예시

**CodeNexus 사용 전:**
```
8,247 토큰 / 쿼리
```

**CodeNexus 사용 후:**
```
2,140 토큰 / 쿼리 (74% 절감)
```

---

## CLI 명령어

| 명령어 | 설명 |
|--------|------|
| `codenexus index` | 워크스페이스 인덱싱 |
| `codenexus search <query>` | 컨텍스트 검색 |
| `codenexus pipeline <task>` | 컨텍스트 파이프라인 실행 |
| `codenexus status` | 인덱스 상태 확인 |
| `codenexus top` | 상위 노드 보기 |
| `codenexus impact <symbol>` | 임팩트 분석 |
| `codenexus serve` | MCP 서버 시작 |
| `codenexus clear` | 인덱스 데이터 삭제 |

---

## 로드맵

- [x] 기본 의존성 그래프
- [x] PageRank 중앙성
- [x] 병렬 인덱싱
- [x] 증분 인덱싱
- [ ] Tree-sitter 통합 (진행 중)
- [ ] 로컬 LLM 지원
- [ ] 멀티 레포 워크스페이스
- [ ] VS Code 확장

---

## 기여하기

기여를 환영합니다! Pull Request를 제출해주세요.

1. Fork 하기
2. 피처 브랜치 만들기 (`git checkout -b feature/amazing-feature`)
3. 커밋하기 (`git commit -m 'Amazing feature 추가'`)
4. 푸시하기 (`git push origin feature/amazing-feature`)
5. Pull Request 열기

---

## 라이선스

이 프로젝트는 MIT 라이선스로 라이선스가 부여됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

---

## 감사의 말

- [vexp](https://vexp.dev/)에서 영감을 받음
- Python, SQLite, MCP로 구축
- 모든 기여자에게 감사

---

## 지원

CodeNexus가 유용하다면 프로젝트 지원을 고려해주세요:

[![Ko-fi](https://img.shields.io/badge/Ko--fi-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/uptodatelabs)
[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-CodeNexus-ea4aaa?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/uptodatelabs)

---

**코드를 연결하세요. AI를 강화하세요.**
