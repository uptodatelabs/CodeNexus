# CodeNexus Pro 플랜 구현 가이드

## 수정해야 할 파일 목록

### 1. license.py (생성 완료)
- 라이선스 관리 모듈
- Free/Pro 기능 분리

### 2. cli.py (수정 필요)
- 라이선스 검증 추가
- 기능 제한 적용

### 3. server.py (수정 필요)
- 인덱싱 시 라이선스 검증
- 노드 수 제한 적용

### 4. workspace.py (수정 필요)
- 멀티레포 기능 제한
- Pro 필수 기능 표시

### 5. llm.py (수정 필요)
- LLM 기능 Pro 전용 설정

---

## 구현 상세

### cli.py 수정

```python
# 기존 코드 위에 추가
from .license import get_license

# 명령어 실행 전 라이선스 검증
@main.command()
@click.option("--full", "-f", is_flag=True, help="Full re-index")
@click.pass_context
def index(ctx, full):
    lic = get_license()
    
    # Free 티어: 노드 수 제한
    if not lic.has_feature("multi_repo") and full:
        console.print("[yellow]Full re-index requires Pro license[/]")
        return
    
    # ... 기존 코드
```

### server.py 수정

```python
# index_workspace 메서드 수정
def index_workspace(self, incremental: bool = True):
    from .license import get_license
    
    lic = get_license()
    max_nodes = lic.get_limit("max_nodes")
    
    # 현재 노드 수 확인
    current_nodes = self.graph.conn.execute(
        "SELECT COUNT(*) FROM nodes"
    ).fetchone()[0]
    
    # 제한 초과 시 중단
    if max_nodes and current_nodes >= max_nodes:
        print(f"Node limit reached ({max_nodes})")
        print("Upgrade to Pro for unlimited nodes")
        return 0
    
    # ... 기존 코드
```

### workspace.py 수정

```python
# add_repo 메서드 수정
def add_repo(self, alias: str, path: Path, description: str = "") -> bool:
    from .license import get_license
    
    lic = get_license()
    
    # Free 티어: 레포 수 제한
    max_repos = lic.get_limit("max_repos")
    if max_repos and len(self.config.repos) >= max_repos:
        print(f"Repository limit reached ({max_repos})")
        print("Upgrade to Pro for more repositories")
        return False
    
    # ... 기존 코드
```

### llm.py 수정

```python
# load_model 메서드 수정
def load_model(self, model_path: Optional[str] = None) -> bool:
    from .license import get_license
    
    lic = get_license()
    
    # Free 티어: LLM 사용 불가
    if not lic.has_feature("llm"):
        print("Local LLM requires Pro license")
        print("Upgrade at: https://codenexus.dev/pricing")
        return False
    
    # ... 기존 코드
```

---

## Free vs Pro 기능 비교

| 기능 | Free | Pro ($19/월) |
|------|------|-------------|
| 기본 파싱 (Python, JS, TS) | ✓ | ✓ |
| 전체 파싱 (9개 언어) | ✗ | ✓ |
| 기본 인덱싱 (5,000 노드) | ✓ | ✓ |
| 전체 인덱싱 (100,000 노드) | ✗ | ✓ |
| 로컬 LLM | ✗ | ✓ |
| 멀티레포 (1개) | ✓ | ✓ |
| 멀티레포 (10개) | ✗ | ✓ |
| 세션 메모리 | ✗ | ✓ |
| VS Code 확장 | ✓ | ✓ |
| CLI | ✓ | ✓ |
| 이메일 지원 | ✗ | ✓ |
| 우선 지원 | ✗ | ✓ |

---

## 라이선스 키 형식

```
CNX-PRO-username-YYYYMMDD
CNX-TEAM-organization-YYYYMMDD
CNX-ENT-organization-YYYYMMDD

예시:
CNX-PRO-john-20270722
CNX-TEAM-acme-20270722
```

---

## 결제 시스템 연동

### Stripe 연동

```python
# payment.py (새 파일)
import stripe

class PaymentManager:
    def __init__(self):
        stripe.api_key = "sk_live_..."
    
    def create_subscription(self, email: str, plan: str) -> dict:
        # 고객 생성
        customer = stripe.Customer.create(
            email=email,
            description="CodeNexus Pro"
        )
        
        # 구독 생성
        subscription = stripe.Subscription.create(
            customer=customer.id,
            items=[{"price": plan}],
            payment_behavior="default_incomplete",
            expand=["latest_invoice.payment_intent"]
        )
        
        return {
            "subscription_id": subscription.id,
            "client_secret": subscription.latest_invoice.payment_intent.client_secret
        }
    
    def cancel_subscription(self, subscription_id: str) -> bool:
        stripe.Subscription.delete(subscription_id)
        return True
```

---

## 마케팅 전략

### 1. Free tier 유인
- 기본 기능 충분히 제공
- Pro 업그레이드 유도
- "5,000 노드 초과 시" 알림

### 2. Pro 가치 강조
- "9개 언어 지원"
- "로컬 LLM으로 70% 절감"
- "팀 협업"

### 3. 트라이얼 제공
- 14일 무료 Pro 체험
- 카드 등록 불필요
- 자동 전환

---

## 다음 단계

1. ✅ license.py 생성
2. ✅ CLI 라이선스 명령어
3. ☐ cli.py 기능 제한 적용
4. ☐ server.py 노드 제한
5. ☐ workspace.py 레포 제한
6. ☐ llm.py Pro 검증
7. ☐ Stripe 연동
8. ☐ 웹사이트/결제 페이지
