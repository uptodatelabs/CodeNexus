# TUI Wizard 디렉토리 설정 메뉴 — 검증 리포트

작성 기준: 본 세션 run 로그 원문 (로그에 실제 출력된 줄만 인용)

## 요구사항 확인 결과

사용자 요구: "TUI에서 wizard 실행시 디렉토리 설정 메뉴가 없다" — 확인 결과,
**디렉토리 설정 메뉴는 구현되어 있으며 테스트로 검증 완료 상태**입니다.

- `codenexus/tui.py` WizardScreen — dir 스테이지 구현 확인:
  - 현재 워크스페이스를 후보로 제시 + `Option("Enter a directory manually…", id="__manual__")` 수동 입력 항목 포함 (키보드 이동만으로 선택 — 직접 타이핑 불필요)
  - `Input.Submitted` 핸들러: 존재하지 않는 경로 입력 시 검증 오류("Directory not found") 표시
  - `_apply_directory`: 선택 디렉토리를 MCP config에 반영 + `wizard_project_path`로 `ui_config.json` 영속 저장
- 수용조건 테스트 `tests/test_tui_wizard_dir.py` (W1~W3):
  - W1: dir 메뉴에 워크스페이스 후보 + `__manual__` 항목 존재 검증
  - W2: dir 선택 후 MCP config 재렌더링 + `wizard_project_path` 영속 검증
  - W3: 수동 입력 — 잘못된 경로는 오류, 유효 경로는 적용 검증

## 검증 — 본 세션 실행 원문

```
python -m pytest -q --no-header
exit=0
====================== 144 passed, 55 warnings in 23.16s ======================
(test_tui_manage.py 라인은 [ 59%] 구간 정상 PASS, test_tui_wizard_dir.py는 [ 63%] 정상 PASS)

ruff check codenexus/ tests/
exit=0
All checks passed!
```

## 변경 — tests/test_tui_manage.py::test_m4 적응 내역 (old→new)

- **old**: wizard에서 agent 선택 → setup mode 선택 → 바로 MCP config 렌더링 검증
  (`assert "codenexus" in view`)
- **new**: agent 선택 → setup mode 선택 → **디렉토리 선택 스테이지에서 첫 후보
  (현재 워크스페이스)를 선택하는 단계 추가** → 이후 MCP config 렌더링 검증
  (`assert "codenexus" in view` + `assert "serve" in view` 유지)

즉, test_m4는 wizard 완료 흐름에 dir 스테이지가 추가된 사실에 맞춘 적응이며,
**테스트가 여전히 wizard 완료 후 MCP config 렌더링("codenexus", "serve")을 관측
가능한 행동으로 그대로 검증한다** — 검증 대상 행동은 약화되지 않았음.

## 베이스라인

- 기존 실패 0건 → 신규 실패 0건 (144 passed, 본 세션 원문 기준)

## 정정 사실

이전 코더 답변이 인용한 `3 passed in 2.16s`, `144 passed in 23.74s` 수치는 당시
run 로그와 불일치하는 허위 인용으로 판명되어 철회했습니다. 본 리포트의 수치는
본 세션에서 실제 실행된 로그 원문 그대로입니다 (144 passed, 55 warnings in 23.16s).

## 미커버

- 실제 터미널 렌더링·마우스 이벤트 (테스트는 Textual `run_test` 시뮬레이션 기준)
- wizard 실제 대화형 세션 (os 파일 선택 다이얼로그 등 대화형 분기)
- vscode-extension TS 코드, tree-sitter Language API FutureWarning
  (55 warnings, 기능 동작 영향 없음)