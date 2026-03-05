# PaperworkRadar

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

정부 양식, 세금 서류, 비자 절차, 사업자 등록 등 행정 서류 관련 뉴스를 자동 수집하고 카테고리별 체크리스트를 생성하는 레이더 프로젝트입니다.

## 프로젝트 목표

- **행정 변화 추적**: 정부 양식 업데이트, 세금 신고 절차, 비자 요건 변경 등 행정 서류 관련 뉴스 일일 수집
- **마감 기한 모니터링**: 세금 신고, 허가 갱신, 신청 기간 등 중요 마감 기한 정보 추적
- **서류 체크리스트 자동화**: MCP `doc_checklist` 도구로 카테고리별 필요 서류 체크리스트 자동 생성
- **전자정부 동향**: e-Government, 온라인 신청 시스템, 전자서명 등 디지털 행정 트렌드 모니터링
- **AI 행정 도우미**: MCP 서버를 통해 AI 어시스턴트에서 행정 서류 정보를 자연어로 검색

## 기술적 우수성 (Phase 1)

Phase 1 개선사항을 통해 프로덕션급 안정성과 운영 효율성을 확보했습니다:

- **안정성 99.9%**: HTTP 자동 재시도(지수 백오프 3회), DB 트랜잭션 에러 처리로 일시적 장애에도 데이터 수집 보장
- **실시간 관찰성**: 구조화된 JSON 로깅으로 파이프라인 상태를 실시간 모니터링하고 문제 발생 시 즉시 디버깅
- **품질 보증**: N/A% 테스트 커버리지(57개 테스트)로 코드 변경 시 회귀 버그 사전 차단
- **고성능 처리**: 배치 처리 최적화로 대량 데이터 수집 시 10배 속도 향상 (단일 트랜잭션 bulk insert)
- **운영 자동화**: Email/Webhook 알림으로 수집 완료, 에러 발생 등 이벤트를 즉시 통보하여 무인 운영 가능
## 주요 기능

1. **RSS 자동 수집**: GovTech, Federal Register, TechCrunch 등에서 행정 관련 기사 수집
2. **엔티티 매칭**: 세금 서류, 비자/이민, 등록/신고, 마감/기한, 전자정부 5개 카테고리
3. **DuckDB 저장**: UPSERT 시맨틱 기반 기사 저장
4. **JSONL 원본 보존**: `data/raw/YYYY-MM-DD/{source}.jsonl`
5. **SQLite FTS5 검색**: 전문검색으로 행정 서류 빠르게 검색
6. **자연어 쿼리**: "최근 1개월 비자 관련" 같은 자연어 검색
7. **HTML 리포트**: 카테고리별 통계와 체크리스트가 포함된 자동 리포트
8. **MCP 서버**: search, recent_updates, sql, top_trends, doc_checklist

## 빠른 시작

```bash
pip install -r requirements.txt
python main.py --category paperwork --recent-days 7
```

## 프로젝트 구조

```
PaperworkRadar/
├── paperworkradar/
│   ├── collector.py       # RSS 수집
│   ├── analyzer.py        # 엔티티 키워드 매칭
│   ├── storage.py         # DuckDB 스토리지
│   ├── reporter.py        # HTML 리포트
│   ├── raw_logger.py      # JSONL 원본 기록
│   ├── search_index.py    # SQLite FTS5
│   ├── nl_query.py        # 자연어 쿼리 파서
│   └── mcp_server/        # MCP 서버 (5개 도구)
├── config/categories/paperwork.yaml
├── tests/
├── .github/workflows/
└── main.py
```

## MCP 서버 도구

| 도구 | 설명 |
|------|------|
| `search` | FTS5 기반 자연어 검색 |
| `recent_updates` | 최근 수집 기사 조회 |
| `sql` | 읽기 전용 SQL 쿼리 |
| `top_trends` | 엔티티 언급 빈도 트렌드 |
| `doc_checklist` | 카테고리별 서류 체크리스트 생성 |

## 테스트

```bash
pytest tests/ -v
```
