# Data Quality Plan

- 생성 시각: `2026-04-11T16:05:37.910248+00:00`
- 우선순위: `P0`
- 데이터 품질 점수: `96`
- 가장 약한 축: `추적성`
- Governance: `high`
- Primary Motion: `compliance-risk`

## 현재 이슈

- 현재 설정상 즉시 차단 이슈 없음. 운영 지표와 freshness SLA만 명시하면 됨

## 필수 신호

- 서식 원본 파일의 버전·개정일·발행기관
- 제출 마감일과 접수 포털 공지
- 서식 변경 diff와 필수 첨부서류 변경 여부

## 품질 게이트

- 문서 hash와 원본 URL을 함께 저장
- 서식명만 같고 발행기관이 다른 문서를 별도 entity로 분리
- 개정일이 없으면 수집일 기준 provisional 상태로 표시

## 다음 구현 순서

- form_revision과 filing_deadline freshness/stale 리포트를 검증 산출물에 추가
- document_url/content_hash 기반 form diff 저장 경로를 구현
- source_backlog의 USCIS/IRS/Companies House 후보는 parser·hash diff·deadline 검증 후 단계적 활성화

## 운영 규칙

- 원문 URL, 수집일, 이벤트 발생일은 별도 필드로 유지한다.
- 공식 source와 커뮤니티/시장 source를 같은 신뢰 등급으로 병합하지 않는다.
- collector가 인증키나 네트워크 제한으로 skip되면 실패를 숨기지 말고 skip 사유를 기록한다.
- 이 문서는 `scripts/build_data_quality_review.py --write-repo-plans`로 재생성한다.
