# PaperworkRadar

서류/행정 영역의 변화(정부 양식 업데이트, 신고/허가 절차, 비자/이민 서류, 전자정부 서비스)를
추적하는 경량 레이더 프로젝트입니다. `python main.py --category paperwork` 실행 한 번으로
RSS 수집 -> 엔티티 매칭 -> DuckDB 저장 -> HTML 리포트 생성까지 처리합니다.

## 빠른 시작
1. 가상환경을 만들고 의존성을 설치합니다.
   ```bash
   pip install -r requirements.txt
   ```
2. 실행:
   ```bash
   python main.py --category paperwork --recent-days 7
   ```
3. 결과 확인:
   - 리포트: `reports/paperwork_report.html`
   - DB: `data/radar_data.duckdb`
   - Raw JSONL: `data/raw/YYYY-MM-DD/*.jsonl`

주요 옵션: `--per-source-limit 30`, `--recent-days 7`, `--keep-days 90`, `--timeout 15`.

## 카테고리 구성
- 파일: `config/categories/paperwork.yaml`
- 소스: GovTech, Federal Register, TechCrunch RSS
- 엔티티:
  - `TaxDocs` (세금 서류)
  - `Visa` (비자/이민)
  - `Registration` (등록/신고)
  - `Deadline` (마감/기한)
  - `DigitalGov` (전자정부)

## MCP Server
- 패키지: `paperworkradar/mcp_server`
- 서버 이름: `paperworkradar`
- 도구:
  - `search`
  - `recent_updates`
  - `sql`
  - `top_trends`
  - `doc_checklist` (최근 기사 기반 서류 체크리스트 생성)

## GitHub Actions / Pages
- 워크플로: `.github/workflows/radar-crawler.yml`
- 워크플로 이름: `PaperworkRadar Crawler`
- 기본 카테고리: `RADAR_CATEGORY=paperwork`
- 배포: `reports/` -> `gh-pages`

## 테스트
```bash
pytest tests/ -v
```
