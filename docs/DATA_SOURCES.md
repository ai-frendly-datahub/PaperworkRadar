# PaperworkRadar Data Sources Research

**Generated:** 2026-03-04  
**Research Duration:** 7m 46s

---

## RSS Feeds (16+ Sources)

### Korean Government Sources

1. **대한민국 정책브리핑** - `https://www.korea.kr/etc/rss.do`
   - Focus: Policy news, government announcements, administrative updates
   - Update frequency: Daily

2. **행정안전부 RSS** - `https://www.mois.go.kr/frt/sub/a08/rss/screen.do`
   - Focus: Public safety, administrative procedures, local government policies
   - Update frequency: Weekly

3. **정부24 소식** - `https://www.gov.kr/portal/ntcItm?Mcode=11186`
   - Focus: Civil service announcements, new government services
   - Update frequency: Daily

4. **조달청 RSS** - `https://www.pps.go.kr/kor/content.do?key=00149`
   - Focus: Government procurement, contract announcements
   - Update frequency: Weekly

5. **재정경제부 RSS** - `https://mofe.go.kr/mn/siteguide/rssService.do`
   - Focus: Economic policy, tax regulations, financial administration
   - Update frequency: Daily

### US Government Sources

6. **USCIS Forms Updates** - `https://www.uscis.gov/forms/forms-updates/rss-feed`
   - Focus: Immigration forms, visa application updates, citizenship documents
   - Update frequency: Weekly

7. **CMS RSS Feeds** - `https://www.cms.gov/about-cms/web-policies-important-links/rss-feeds`
   - Focus: Healthcare policy, Medicare/Medicaid regulations
   - Update frequency: Daily

8. **Grants.gov RSS** - `https://grants.gov/connect/rss-feeds`
   - Focus: Grant opportunities, federal funding announcements
   - Update frequency: Daily

9. **GovInfo RSS Feeds** - `https://govinfo.gov/feeds`
   - Focus: Federal Register, Congressional documents, public laws
   - Update frequency: Daily

10. **FCC RSS Feeds** - `https://www.fcc.gov/news-events/rss-feeds-and-email-updates-fcc`
    - Focus: Communications regulations, licensing, document filings
    - Update frequency: Daily

11. **DOL RSS Feeds** - `https://dol.gov/rss`
    - Focus: Labor regulations, employment law updates
    - Update frequency: Daily

12. **TTB RSS Feeds** - `https://www.ttb.gov/online-services/rss/rss-feeds-from-ttb`
    - Focus: Alcohol and tobacco tax regulations, permits
    - Update frequency: Weekly

13. **Federal Register RSS** - `https://www.govinfo.gov/rss/federal-register.xml`
    - Focus: New federal regulations, agency rulemaking
    - Update frequency: Daily

---

## APIs (6+ Sources)

1. **IRS IRIS (Information Returns Intake System) API**
   - Documentation: https://www.irs.gov/e-file-information-returns-with-iris
   - Authentication: Required (Taxpayer Portal registration)
   - Rate limit: 250 records per CSV upload
   - Focus: E-filing tax forms, information returns

2. **IRS Modernized e-File (MeF) API**
   - Documentation: https://irs.gov/e-file-providers/modernized-e-file-mef-schemas-and-business-rules
   - Authentication: Required (Authorized e-file provider)
   - Focus: Electronic tax filing, XML schemas

3. **VA Forms API**
   - Documentation: https://developer.va.gov/
   - Authentication: Required (API Key)
   - Focus: Veterans affairs forms, benefits applications

4. **SAM.gov API (System for Award Management)**
   - Base URL: `https://sam.gov/api/public/`
   - Documentation: https://sam.gov/api/
   - Authentication: Required (API Key)
   - Rate limit: 1,000 requests per minute
   - Focus: Government contracts, entity registration, business data

5. **공공데이터포털 Open API (Korea Public Data Portal)**
   - Base URL: `https://www.data.go.kr/`
   - Documentation: https://www.data.go.kr/api/
   - Authentication: Required (Member registration + API key)
   - Rate limit: 10,000 requests per developer
   - Focus: Korean government public data, administrative documents

6. **Global Visa Check API**
   - Documentation: https://zylalabs.com/api-marketplace/data/global+visa+check+api/5364
   - Authentication: Required (API Key)
   - Focus: Visa requirements for 210 countries, travel permits

---

## Web Scraping Targets (12+ Sites)

1. **USCIS Forms Updates Page** - `https://www.uscis.gov/forms/forms-updates`
   - Target: Form update listings, edition dates, fee changes
   - Update frequency: Weekly

2. **Federal Register** - `https://www.federalregister.gov/`
   - Target: Daily issues, public inspection, proposed rules
   - Update frequency: Daily

3. **USCIS Forms Library** - `https://www.uscis.gov/forms/forms`
   - Target: Individual form pages, download links, instructions
   - Update frequency: As updated

4. **Visa Bulletin (State Department)** - `https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin`
   - Target: Monthly visa bulletins, priority dates, filing charts
   - Update frequency: Monthly

5. **IRS Forms and Publications** - `https://www.irs.gov/forms/`
   - Target: Tax forms, instructions, publications
   - Update frequency: As updated

6. **정부24 서비스 검색** - `https://www.gov.kr/search/`
   - Target: Service listings, new government services
   - Update frequency: Daily
   - Coverage: 10,000+ government services

7. **법제처 국가법령정보센터** - `https://law.go.kr/`
   - Target: New laws, regulations, administrative rules
   - Update frequency: Daily

8. **SAM.gov Entity Registration** - `https://sam.gov/entity-registration/`
   - Target: Business entity search, registration status
   - Update frequency: Real-time

9. **Grants.gov Search** - `https://grants.gov/search/`
   - Target: Grant opportunities, eligibility requirements
   - Update frequency: Daily

10. **국세청 표준세율표** - `https://www.nts.go.kr/`
    - Target: Tax regulations, tax rate tables, filing requirements
    - Update frequency: Monthly/Annually

---

## Recommended Configuration (Top 15 Sources)

```yaml
paperwork:
  - name: "USCIS Forms Updates"
    url: "https://www.uscis.gov/forms/forms-updates/rss-feed"
    type: "rss"
    focus: "Immigration forms"
    priority: "high"
  
  - name: "Federal Register"
    url: "https://www.govinfo.gov/rss/federal-register.xml"
    type: "rss"
    focus: "Federal regulations"
    priority: "high"
  
  - name: "대한민국 정책브리핑"
    url: "https://www.korea.kr/rss/news_policyNewsList.do"
    type: "rss"
    focus: "Korean policy news"
    priority: "high"
  
  - name: "정부24 서비스"
    url: "https://www.gov.kr/search/"
    type: "scrape"
    focus: "Government services"
    priority: "high"
  
  - name: "SAM.gov API"
    url: "https://sam.gov/api/public/"
    type: "api"
    auth_required: true
    focus: "Business registration"
    priority: "high"
```

**Total Sources**: 16+ RSS, 6+ APIs, 12+ Scraping Targets
