# Business Quality Upgrade

- Generated: `2026-04-14T04:48:11.525239+00:00`
- Portfolio verdict: `충분`
- Business value score: `86.8`
- Upgrade phase: P0 포털 서비스 변경 추적
- Primary motion: `compliance-risk`
- Weakest dimension: `traceability`

## Current Evidence

- Primary rows: `2452`
- Today raw rows: `18`
- Latest report items: `18`
- Match rate: `100.0%`
- Collection errors: `0`
- Freshness gap: `6`

## Upgrade Actions

- portal_service_change를 tracked_event_models에 포함해 신청 절차/필수 첨부서류 변경을 품질 리포트에서 감시한다.
- document_url과 content_hash 기반 diff 결과를 stale/missing 요약과 함께 노출한다.
- USCIS/IRS/Companies House 후보는 hash diff, deadline parser, filing key 검증 후 재활성화한다.

## Quality Contracts

- `config/categories/paperwork.yaml`: output `reports/paperwork_quality.json`, tracked `form_revision, filing_deadline, portal_service_change`, backlog items `4`

## Contract Gaps

- None.
