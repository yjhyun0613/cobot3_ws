# 📝 구글 프레젠테이션 제미나이(Gemini in Slides) 전용 프롬프트 북 (선택적 이미지 배치 개정판)

이 문서는 **`docs/INTEGRATED_PRESENTATION_GUIDE.md`**에 설계된 26개 슬라이드 전체를 구글 프레젠테이션의 제미나이(Gemini) 기능을 사용하여 자동 빌드하기 위한 **영문 지시어 - 한글 내용 출력** 프롬프트 모음입니다. 

사용자님의 피드백을 반영하여 **모든 페이지에 무의식적으로 들어가던 사진 공간을 정리**하고, **시각적 자료가 꼭 필요한 11개 슬라이드에만 한정하여 이미지 공간(Placeholder)을 구성하고 어떤 사진을 배치해야 하는지 명확히 한글로 표시**해 두었습니다. 사진이 필요 없는 나머지 15개 슬라이드는 넓고 깔끔하게 텍스트 카드로만 슬라이드를 꽉 채우도록 레이아웃 지시어를 조정했습니다.

---

## 🎨 공통 디자인 원칙 (Theme & Typography)
*   **슬라이드 전체 배경**: 퓨어 화이트 (`#FFFFFF`)
*   **상단 타이틀 영역**: 가로를 꽉 채우는 라이트 그레이 띠 (`#F1F3F5` horizontal header strip) 배치 후 그 내부에 제목과 부제목 배치
*   **글꼴**: 현대적이고 깔끔한 고딕/산세리프 계열 (`Inter` or `sans-serif`)
*   **내용 언어**: 전체 텍스트 및 결과물은 **한국어**로 출력
*   **선택적 이미지 가이드**: 사진 배치가 지정된 슬라이드에는 `[넣어야 할 사진/그림 가이드]` 지침이 명확히 기재되어 있습니다.

---

## 🎴 [트랙 1] 기초 인프라 및 DB 설계 (Slide 01 ~ 07)

### 📝 Slide 01. 오프닝 및 발표 주제
*   **이미지 포함 여부**: **YES**
*   **레이아웃 스타일**: **Style D (중앙 집중형 타이틀 + 하단 이미지 공간)**
```text
Create a clean and professional presentation title slide with a pure white background (#FFFFFF).

The main title of the slide should be: "하이브리드 데이터 플로우를 활용한 Isaac Sim 및 ROS 2 기반 지능형 물류창고 관제 시스템 개발"
The subtitle of the slide should be: "시스템 백엔드, DB, 관제 알고리즘 및 시뮬레이션 최적화 보고서"
Add a presenter info text at the bottom: "발표자: XXX (백엔드 및 시뮬레이션 최적화 담당)"

Layout: 
- Center-align all text on the slide.
- Allocate a wide banner-style blank image placeholder at the very bottom.
  * [넣어야 할 사진 가이드: Isaac Sim 3D 물류 창고 전체 구동 렌더링 화면 또는 메인 시스템 아키텍처 조감도]
- Add a thick navy accent line separating the title and the image placeholder.
```

---

### 📝 Slide 02. 전체 개발 환경 및 기술 명세
*   **이미지 포함 여부**: **NO (테이블만 배치)**
*   **레이아웃 스타일**: **Style C (헤더 띠 + 가로 전체 테이블)**
```text
Create a clean and professional table-style slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "개발 환경 및 기술 스택"
- Subtitle: "하이브리드 DB 인프라와 ROS 2 기반의 풀스택 통합 관제 시스템 인프라 명세"

Layout: Below the gray header strip, create a full-width structured table with 3 columns.
- Table Header background color: Dark Navy (White text)
- Column 1 header: "구분"
- Column 2 header: "사용 기술"
- Column 3 header: "적용 용도 및 특징"
- Table Rows:
  Row 1: "운영 및 미들웨어" | "Ubuntu 22.04 LTS / ROS 2 Humble" | "관제탑 노드 구동, 가상 로봇 에뮬레이터 및 분산 통신 제어"
  Row 2: "통신 프로토콜" | "Eclipse Cyclone DDS" | "다중 PC 및 무선 WiFi 환경에서의 실시간 액션/서비스 통신 신뢰성 확보"
  Row 3: "하이브리드 DB" | "PostgreSQL 15 & Redis 7.0" | "영속 트랜잭션 보존 데이터 저장 및 ZSET 기반 실시간 고속 명령 큐 관리"
  Row 4: "대시보드 서버" | "FastAPI / Uvicorn (Python)" | "웹소켓(WebSocket) 기반 1.5초 주기 실시간 양방향 모니터링 데이터 브로드캐스트"
  Row 5: "대시보드 UI" | "HTML5 / Vanilla CSS3 / JS" | "Absolute positioning 기법 활용으로 DOM 부하 95% 감축 및 2D 플랜 시각화"
  Row 6: "시뮬레이션 & 비전" | "NVIDIA Isaac Sim / OpenUSD / zxing-cpp" | "3D 물류 창고 월드 모의 실험, USD 인스턴싱 최적화 및 패키지 QR 코드 디코딩 연동"
```

---

### 📝 Slide 03. 전체 시스템 아키텍처 및 데이터/제어 토폴로지
*   **이미지 포함 여부**: **YES**
*   **레이아웃 스타일**: **Style A (헤더 띠 + 좌측 텍스트 + 우측 세로형 이미지 공간)**
```text
Create a clean and professional slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "전체 시스템 아키텍처 및 데이터/제어 토폴로지"
- Subtitle: "ROS 2 관제 노드와 하이브리드 DB 간의 유기적 통신 및 흐름도"

Layout: Below the gray header strip, split the white main area into 2 columns side-by-side. 
- Left Column (40% width): Contains text explanations of the architecture.
- Right Column (60% width): Contains a large blank image placeholder.

Left Column Content:
- Header Title: "시스템 통합 데이터 흐름"
- Sub-header: "제어 평면과 데이터 평면의 실시간 조율"
- Bullet Points:
  * **중앙 관제탑 (control_tower_node)**: PostgreSQL pool을 통해 영속 데이터를 조회하고, Redis ZSET 큐를 Push/Pop하며 AMR/로봇 팔에 주행 및 포장 액션 명령 하향
  * **하이브리드 데이터베이스**: 정적/영속적 WMS 트랜잭션은 PostgreSQL 15에서 처리하고, 고속 실시간 위치 및 캐싱은 Redis 7.0에서 처리
  * **물리 시뮬레이션 브릿지**: Isaac Sim 커넥터가 Redis의 AMR 실시간 위치 데이터를 읽어 PhysX 3D 물체를 실시간 텔레포트 동기화

Right Column Content:
- Create a large, centered blank image placeholder.
  * [넣어야 할 사진 가이드: control_tower_node, WMS DB, Redis Cache, Isaac Sim 간의 제어 신호와 데이터 흐름을 도시한 시스템 아키텍처 블록 다이어그램]
```

---



### 📝 Slide 04. 초기 Git 형상관리 및 도커 컨테이너 인프라 구축
*   **이미지 포함 여부**: **NO**
*   **레이아웃 스타일**: **Style B (헤더 띠 + 2단 카테고리 카드 전체 가득 채움)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "초기 Git 형상관리 및 도커 컨테이너 인프라 구축"
- Subtitle: "안정적인 코드 형상 관리 및 데이터베이스 격리 환경 구성"

Layout: Below the gray header strip, split the white main area into 2 equal-width columns side-by-side using the full width of the slide.

Column 1:
- Header Title: "1. Git 형상관리 및 협업 체계 확립"
- Sub-header: "코드 정합성 및 배포 자동화의 초석"
- Bullet Points:
  * 로컬 워크스페이스 'cobot3_ws' 내 Git 형상관리 구성
  * 빌드 임시 파일(.pyc, build, install) 배제를 위한 .gitignore 고도화
  * GitHub 원격 저장소 강제 연동 및 협업 브랜치 초기화

Column 2:
- Header Title: "2. Docker 기반 데이터베이스 인프라 구축"
- Sub-header: "독립적이고 격리된 WMS 및 캐시 인프라 확보"
- Bullet Points:
  * PostgreSQL 15 및 Redis 7.0의 컨테이너 설계 및 docker-compose.yml 생성
  * 데이터 무결성 조회를 돕는 웹 기반 GUI Adminer 및 Redis Commander 통합 구축
  * 컨테이너 포트 및 로컬 볼륨 마운트 설정을 통한 개발 편의성 극대화
```

---

### 📝 Slide 05. ROS 2 통신 인터페이스 설계
*   **이미지 포함 여부**: **NO**
*   **레이아웃 스타일**: **Style B (헤더 띠 + 3단 카테고리 카드 전체 가득 채움)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "ROS 2 통신 인터페이스 설계"
- Subtitle: "협동 로봇 및 AMR 간의 유기적 연동을 위한 표준 데이터 규격 정의"

Layout: Below the gray header strip, split the white main area into 3 equal columns side-by-side using the full width of the slide.

Column 1 (Header Style: Purple Pill):
- Header Title: "메시지 (Messages)"
- Sub-header: "이벤트 브로드캐스트"
- Bullet Points:
  * WorkstationSimTrigger.msg: Isaac Sim 환경 간 작업대 상태 동기화
- Key Fields:
  * workstation_id (ID)
  * location (위치 좌표)
  * action (Spawn/Despawn)

Column 2 (Header Style: Blue Pill):
- Header Title: "서비스 (Services)"
- Sub-header: "동적 명령 및 상태 조회"
- Bullet Points:
  * CheckWarehouseStatus.srv: 입고 등록 및 작업대 매핑 확인
  * GetDailyPackageList.srv: 일차별 작업 지시 목록 획득
  * ReportInboundProgress.srv: 적재 현황 및 슬롯 수 실시간 보고
  * TransitPackage.srv: 라인 간 상자 물리적 이동 요청

Column 3 (Header Style: Orange Pill):
- Header Title: "액션 (Actions)"
- Sub-header: "장시간 작업 제어 및 피드백"
- Bullet Points:
  * MovePackage.action: 로봇 암 패키지 이송 및 진척도 보고
  * ManageWorkstation.action: AMR 작업대 제어 및 상태 모니터링
  * StartPackaging.action: 자동 랩핑 공정 지시 및 완료율 수신
```

---

### 📝 Slide 06. PostgreSQL 데이터베이스 스키마 정규화
*   **이미지 포함 여부**: **YES**
*   **레이아웃 스타일**: **Style A (헤더 띠 + 2단 Problem-Solution-Result + 중앙 이미지 공간)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "PostgreSQL 데이터베이스 스키마 정규화"
- Subtitle: "데이터 정합성 확보 및 1:N 관계 정규화를 통한 아키텍처 확장성 개선"

Layout: Below the gray header strip, split the white main area into 3 sections: Left Column (35% width), Center Column (30% width), and Right Column (35% width).

Left Column:
- Header Title: "1. 기존 데이터 모델 구조와 한계"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "workstations 테이블 내 1~8번 슬롯 정보 컬럼이 하드코딩 형태로 존재하여 데이터 중복 및 가변 슬롯 수 대응이 불가한 상태"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "workstations 내 슬롯 속성을 완전히 삭제하고, packages 테이블에 workstation_id와 slot_number 외래키를 추가하는 1:N 관계로 정규화 리팩토링"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "데이터 중복 원천 차단 및 SQL JOIN 문을 통해 실시간 작업대 슬롯 점유 상황을 유연하게 동적 계산하는 효율적 정규화 모델 수립"

Center Column:
- Allocate a vertical blank image placeholder in this center column.
  * [넣어야 할 사진 가이드: 정규화 전(Slot 1~8 컬럼 존재)과 정규화 후(Packages 테이블 분리)의 스키마 구조 ERD 다이어그램]

Right Column:
- Header Title: "2. 데이터 정규화에 따른 실무 쿼리 적용"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "정규화 이전에는 단순 컬럼 업데이트 쿼리 위주였으나, 정규화 이후 packages 외래키 조인 연산이 필수적으로 도입되며 성능 부하 우려 발생"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "실시간 슬롯 점유 계산 시 Full Table Scan 방지를 위해 idx_packages_workstation 및 idx_packages_status 등의 핵심 인덱스 5개 생성 적용"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "트랜잭션 안전성 확보와 동시에 대용량 패키지 탐색 쿼리 속도를 획기적으로 개선하여 데이터 조회 안정성 100% 보장"
```

---

### 📝 Slide 07. QR ID 통합 물류 매핑 체계 구축
*   **이미지 포함 여부**: **NO**
*   **레이아웃 스타일**: **Style B (헤더 띠 + 2단 카테고리 카드 전체 가득 채움)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "QR ID 통합 물류 매핑 체계 구축"
- Subtitle: "물리 객체 식별과 백엔드 데이터베이스 엔티티 간의 유기적 매핑 설계"

Layout: Below the gray header strip, split the white main area into 2 equal-width columns side-by-side.

Column 1:
- Header Title: "1. 데이터베이스 테이블 스키마 확장"
- Sub-header: "물리 센서 식별자와 논리 엔티티 바인딩"
- Bullet Points:
  * robots, workstations, packages 테이블에 qr_id 고유 식별 컬럼을 전면 추가
  * 실시간 물품 추적 및 식별 오류를 방지하기 위해 QR ID 기준의 유니크 제약 조건 설계
  * 초기 SQL 시드 데이터에 QR ID를 맵 정보와 연동하여 팩토리 초기화 상태 구축

Column 2:
- Header Title: "2. 제어 흐름 및 통신 파이프라인 적용"
- Sub-header: "센싱 데이터를 통한 중앙 관제 연동"
- Bullet Points:
  * ROS 2 서비스 및 액션 인터페이스에 QR ID 데이터 필드 적용
  * 로봇 카메라가 QR 코드를 스캔 시, 관제탑 노드가 이 ID로 WMS 데이터베이스를 즉각 쿼리
  * 작업대 호출, 이송 목적지 유효성 검증 시 QR ID를 교차 검증하여 하드웨어 제어 안정성 강화
```

---

## 🎗 [트랙 2] 관제 스케줄러 및 라우팅 알고리즘 (Slide 08 ~ 12)

### 📝 Slide 08. 멀티스레드 기반 중앙 관제탑 노드 설계
*   **이미지 포함 여부**: **YES**
*   **레이아웃 스타일**: **Style A (헤더 띠 + 2단 Problem-Solution-Result + 하단 이미지 공간)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "멀티스레드 기반 중앙 관제탑 노드 설계"
- Subtitle: "ROS 2 비동기 콜백 처리 및 하이브리드 데이터베이스 연동 구조 설계"

Layout: Below the gray header strip, split the white main area vertically: Top part contains 2 columns side-by-side, Bottom part allocates a horizontal blank placeholder.
- [넣어야 할 사진 가이드: ROS 2 MultiThreadedExecutor 내에서 실행되는 스레드 풀과 각 콜백 그룹(DB 트랜잭션, AMR 제어 액션) 간의 병렬 구조도]

Column 1:
- Header Title: "1. ROS 2 MultiThreadedExecutor 설계"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "단일 스레드 구조에서는 AMR 제어 액션 대기, 로봇 팔 적재 진행 보고 등의 입출고 이벤트가 병목되어 전체 시스템 지연 유발"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "MultiThreadedExecutor 기반의 비동기 실행 루프 구조를 구현하여, 여러 로봇의 제어 콜백을 독립 스레드로 분산 병렬 처리"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "액션 피드백 수신 도중에도 서비스 요청 및 DB 쿼리가 무대기로 처리되어 관제 신속성 300% 향상"

Column 2:
- Header Title: "2. 하이브리드 DB 라이브러리 연동"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "데이터베이스와 캐시 서버가 실시간으로 고주파 상태 데이터를 기록할 때, 라이브러리 호출 오버헤드로 인한 병목 발생 가능성 존재"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "Python DB 드라이버 패키징 최적화 및 Redis 라이브러리 비동기 세션을 관제 노드 기동 시 단일 바인딩 처리"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "데이터 영속성과 실시간 캐싱 통신 통로가 완전히 분리되어 연산 효율 향상"
```

---

### 📝 Slide 09. 동적 날짜 기반 라우팅 및 자동 영업일 관리
*   **이미지 포함 여부**: **NO**
*   **레이아웃 스타일**: **Style A (헤더 띠 + 2단 Problem-Solution-Result 전체 가득 채움)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "동적 날짜 기반 라우팅 및 자동 영업일 관리"
- Subtitle: "배송 예정일에 맞춘 지능형 분류 및 라인 배정 엔진 구현"

Layout: Below the gray header strip, split the white main area into 2 equal-width columns side-by-side.

Column 1:
- Header Title: "1. 고정 하드코딩 날짜 비교의 한계와 탈피"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "기존의 '오늘/내일/모레' 텍스트 기반 분기 로직은 실제 날짜 전환 시 DB의 모든 데이터를 수동 변경해야만 하는 치명적 한계 노출"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "실제 배송 날짜(YYYY-MM-DD) 데이터 포맷을 적용하고, 미처리 패키지의 날짜 순서에 따라 '오늘의 출고 대상 일자'를 동적으로 자동 셋업"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "영업일이 바뀔 때 수동 데이터 튜닝이 완전히 제거되어 가동 유연성을 비약적으로 높임"

Column 2:
- Header Title: "2. 날짜 정렬에 따른 입고 분류 라우팅"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "인바운드 분류 시, 패키지가 들어오는 시점에 적절한 목적 작업대 라인으로 유기적 분배가 불가능하여 물량 병목 발생"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "조회된 미처리 예정일 순서에 따라 오늘(Line 1), 내일(Line 2), 모레(Line 3) 라인으로 분기 라우팅하는 스케줄러 구현"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "작업 지시가 떨어지자마자 컨베이어 게이트 분기 장치와 동기화되어 물류 분류 정확도 100% 실현"
```

---

### 📝 Slide 10. Redis Sorted Set (ZSET) 기반 우선순위 제어 명령 큐 구축
*   **이미지 포함 여부**: **YES**
*   **레이아웃 스타일**: **Style B (헤더 띠 + 3단 카테고리 카드 + 하단 이미지 공간)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "Redis Sorted Set (ZSET) 기반 우선순위 제어 명령 큐"
- Subtitle: "AMR 실시간 주행 명령 병목 해소를 위한 가중치 스코어 모델 적용"

Layout: Below the gray header strip, split the white main area vertically: Top part contains 3 equal columns side-by-side, Bottom part allocates a wide horizontal blank placeholder.
- [넣어야 할 사진 가이드: Redis Sorted Set(ZSET)의 Score 가중치 맵(100점부터 20점까지)과 스케줄러가 zpopmax로 선입선출하는 대기열 개념 구조도]

Column 1 (Header Style: Purple Pill):
- Header Title: "자료구조의 혁신"
- Sub-header: "FIFO 리스트에서 ZSET으로 전환"
- Bullet Points:
  * 기존 FIFO(Lpush/Rpop) 큐는 긴급 탈출 및 정지 명령이 뒷전으로 밀리는 심각한 문제 유발
  * Redis Sorted Set(ZSET) 도입으로 명령어마다 실시간 우선순위 스코어(Score)를 강제 배정
  * zpopmax 명령을 통해 가장 높은 점수를 가진 제어 메시지를 관제 스케줄러가 항상 최선순위로 꺼내어 실행

Column 2 (Header Style: Blue Pill):
- Header Title: "가중치 스코어 모델"
- Sub-header: "작업 유형별 실시간 점수 설계"
- Bullet Points:
  * Score 100 (P1): 작업대 180도 회전, 긴급 정지 및 합적 직송 지시
  * Score 90 (P1.5): 입고 A구역 활성 작업대 자동 공급
  * Score 80 (P2): 포장 존으로 완충 작업대 공급 및 이송
  * Score 50 (P3): Look-ahead 기반 B구역 예비 작업대 사전 이송
  * Score 20 (P4): 빈 작업대 및 파레트 창고 회수

Column 3 (Header Style: Orange Pill):
- Header Title: "중복 진입 원천 차단"
- Sub-header: "UUID 기반 멱등성 설계"
- Bullet Points:
  * 다중 로봇이 동일한 작업대 공급 명령을 중복 처리하여 동선 충돌이 유발되는 에러 발생
  * 각 명령 구조에 동적 고유 UUID를 부여하여 직렬화하는 중복 방지 필터 구현
  * 큐 내부에 동일 UUID 또는 동일 타겟의 작업이 있으면 진입을 차단하는 멱등성 확보
```

---

### 📝 Slide 11. 공차 주행 최적화를 위한 실시간 동적 자원 배정 알고리즘
*   **이미지 포함 여부**: **NO**
*   **레이아웃 스타일**: **Style A (헤더 띠 + 2단 Problem-Solution-Result 전체 가득 채움)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "공차 주행 최적화를 위한 실시간 동적 자원 배정 알고리즘"
- Subtitle: "고정식 로봇 배정의 탈피와 실시간 유클리드 최단거리 매핑 구현"

Layout: Below the gray header strip, split the white main area into 2 equal-width columns side-by-side using the full width of the slide.

Column 1:
- Header Title: "1. 고정식 AMR 배치 모델의 한계"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "특정 라인 전담으로 AMR을 강제 고정 배치 시, 다른 라인이 터져나갈 때 공차 주행거리가 누적되고 노는 장비가 생기는 전체 자원 비효율 초래"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "AMR들을 단일 통합 공유 풀(Fleet Resource Pool)로 묶고, 상태값 캐시를 Redis 해시로 초 단위 추적"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "특정 기기가 멈추거나 놀지 않는 유연한 Fleet 분산 자원 활용의 기초적 토대 완비"

Column 2:
- Header Title: "2. 실시간 유클리드 동적 매핑 알고리즘"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "가장 먼 곳에 있는 IDLE 로봇이 우연히 호출될 시 주행 전력 소모 급증 및 공정 딜레이 누적"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "명령 발생 시점의 주행 가능 상태(IDLE) 로봇들과 대상 작업대 간의 유클리드 좌표 거리를 비교해 최단거리 AMR을 즉각 매핑하는 동적 배정 엔진 탑재"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "AMR의 공차 주행 거리를 단축하고 배터리 소모율을 25% 이상 감축하는 저탄소 효율 가동 실현"
```

---

### 📝 Slide 12. 창고 주차 Spot 동적 배정 및 스케줄러 통합
*   **이미지 포함 여부**: **NO**
*   **레이아웃 스타일**: **Style B (헤더 띠 + 2단 카테고리 카드 전체 가득 채움)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "창고 주차 Spot 동적 배정 및 스케줄러 통합"
- Subtitle: "창고 내 유휴 주차 구역의 실시간 관리 및 점유 상태 동기화"

Layout: Below the gray header strip, split the white main area into 2 equal-width columns side-by-side using the full width of the slide.

Column 1:
- Header Title: "1. warehouse_locations 테이블 설계"
- Sub-header: "스팟 단위 점유 상태 및 식별자 관리"
- Bullet Points:
  * 창고 내부 12개 스팟의 논리적 위치와 물리적 Goal X, Y 좌표를 정의하는 테이블 구축
  * 각 스팟의 상태를 EMPTY와 OCCUPIED로 정의하고, 점유 중인 workstation_id를 외래키로 관계 바인딩
  * 작업대가 창고로 주차 명령이 떨어질 때, 쿼리를 통해 빈 스팟(EMPTY)을 즉각 예약하는 기능 구현

Column 2:
- Header Title: "2. 관제탑 스케줄러 동적 할당 및 해제"
- Sub-header: "AMR 이송 상태 전이에 따른 상태 불일치 해소"
- Bullet Points:
  * 작업대 이송 명령 시 목적 주차 스팟을 실시간 배정하고, 도킹 및 주차 완료 시점에 점유 상태를 최종 확정
  * 작업대를 창고에서 작업 라인으로 출차시킬 때, 점유 중이던 스팟의 ID를 파싱하여 즉각 EMPTY로 상태 해제
  * 상태 해제 누수로 인한 동일 주차 스팟 중복 진입 및 AMR 충돌 위험 요소를 원천 제거
```

---

## 🎘 [트랙 3] JIT 공정 제어 및 로봇 협업 (Slide 13 ~ 16)

### 📝 Slide 13. JIT 인터로킹 물리 충돌 방지 시스템
*   **이미지 포함 여부**: **YES**
*   **레이아웃 스타일**: **Style A (헤더 띠 + 2단 Problem-Solution-Result + 중앙 이미지 공간)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "JIT 인터로킹 물리 충돌 방지 시스템"
- Subtitle: "로봇 팔 적재 진행 상황과 AMR 도킹 동작 간의 안전 인터로킹 구현"

Layout: Below the gray header strip, split the white main area into 3 sections: Left Column (35% width), Center Column (30% width), and Right Column (35% width).

Left Column:
- Header Title: "1. 작업대 이송/회전 중 로봇 팔 충돌 위험"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "AMR이 도킹을 시도하거나 작업대를 들어 올리는 등 물리적 교체가 진행되는 도중, 로봇 팔이 상자를 올려놓으면서 충돌 및 상자가 추락하는 물리 월드 붕괴 유발"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "관제탑 노드가 이송 트리거 발동 시, 로봇 팔 노드로 즉각 /pause_status = True(일시정지) 토픽을 발행하여 구동 정지"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "물리 충돌에 따른 에셋 비정상 이탈 문제를 완전히 예방하여 하드웨어 파괴율 0% 달성"

Center Column:
- Allocate a vertical blank image placeholder in this center column.
  * [넣어야 할 사진 가이드: Isaac Sim 내에서 AMR이 작업대를 이송/회전하는 도중 로봇 팔이 정지해 있는 협업 상태 스크린샷 또는 pause_status 시퀀스 매핑 순서도]

Right Column:
- Header Title: "2. 교체 공정 완료 후 작업 자동 재개"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "이송이 완전히 끝난 후에도 사람이 개입하거나 타임아웃 방식으로 대기할 시, 생산 대기 지연이 추가 발생"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "AMR 액션 서버가 완료 상태(SUCCEEDED)를 보고하는 즉시 관제탑이 /pause_status = False(작업 재개)를 발행하는 연쇄 시퀀스 탑재"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "수동 조작 없이 안전 범위 내에서 자동으로 연속 적재가 즉각 속행되는 무인화 공정 완성"
```

---

### 📝 Slide 14. A/B 이중 버퍼 배치 및 Look-ahead 사전 이송
*   **이미지 포함 여부**: **YES**
*   **레이아웃 스타일**: **Style A (헤더 띠 + 2단 Problem-Solution-Result + 중앙 이미지 공간)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "A/B 이중 버퍼 배치 및 Look-ahead 사전 이송"
- Subtitle: "로봇 유휴(Idle) 시간 단축을 위한 이중 적재 구역 및 선행 호출 알고리즘"

Layout: Below the gray header strip, split the white main area into 3 sections: Left Column (35% width), Center Column (30% width), and Right Column (35% width).

Left Column:
- Header Title: "1. 라인별 A/B 구역 이중 버퍼 도입"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "단일 적재 구역에서는 가득 찬 작업대를 빼고 빈 작업대를 채워 넣는 이송 시간(평균 45초) 동안 로봇 팔이 상자를 쥔 채 정지해 있는 시간 병목 발생"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "각 적재 라인에 A구역(활성 적재)과 B구역(예비 대기)으로 버퍼 공간을 쪼개어 배치하도록 물리 좌표계 및 DB 매핑 다각화"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "하나의 작업대를 들어 올리더라도 백업 구역이 존재하여 작업 병목의 탈출구를 안전하게 제공"

Center Column:
- Allocate a vertical blank image placeholder in this center column.
  * [넣어야 할 사진 가이드: 작업대 A구역(활성)에 로봇이 상자를 쌓는 도중 B구역(예비)에 AMR이 빈 작업대를 미리 갖다 놓는 2D 레이아웃 구성 설명도]

Right Column:
- Header Title: "2. Look-ahead 3/7 슬롯 트리거 알고리즘"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "작업대가 8칸 다 찼을 때 비로소 빈 작업대를 부르면 AMR의 이동 지연을 이기지 못하고 로봇 팔 대기가 고스란히 유지됨"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "현재 작업대 적재량이 3번째(입고) 혹은 7번째(출고 포장) 슬롯에 도달한 시점에 관제탑이 창고에서 예비 빈 작업대를 B구역으로 미리 호출해 두는 알고리즘 설계"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "A구역 만재 직후 B구역 예비 작업대가 즉각 적재 구역으로 자동 승격되어, 로봇 대기 시간을 45초에서 3초 미만으로 단축"
```

---

### 📝 Slide 15. 180도 제자리 회전(Rotate in-place) 제어 시퀀스
*   **이미지 포함 여부**: **NO**
*   **레이아웃 스타일**: **Style B (헤더 띠 + 3단 카테고리 카드 전체 가득 채움)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "180도 제자리 회전(Rotate in-place) 제어 시퀀스"
- Subtitle: "협동 로봇의 물리적 적재 도달 범위(Reach Limit) 극복을 위한 회전 공정"

Layout: Below the gray header strip, split the white main area into 3 equal columns side-by-side using the full width of the slide.

Column 1 (Header Style: Purple Pill):
- Header Title: "물리적 리치 한계"
- Sub-header: "2x4 적재 레이아웃의 장애"
- Bullet Points:
  * 로봇 팔의 관절 길이가 짧아 작업대 뒷부분인 5~8번 슬롯 구역까지 상자를 얹기 위한 리치 한계 돌입
  * 억지로 진입하려 할 시 조인트 제한 에러(Joint Limit Violation)로 로봇 구동 정지
  * 하드웨어 위치를 재조정하기 어려운 고정 프레임 구조 하에서 기동 보정 방안 강구

Column 2 (Header Style: Blue Pill):
- Header Title: "180도 회전 시퀀스 가동"
- Sub-header: "4슬롯 완료 시점 회전 제어"
- Bullet Points:
  * 작업대에 4번째 상자가 정확히 차는 순간, 로봇 팔 노드로 일시정지(`pause_status = True`) 명령 즉시 하향
  * 관제탑이 ZSET 큐에 최우선순위(P1, Score 100)로 해당 작업대 제자리 180도 회전 태스크 발행
  * AMR이 작업대 하단으로 신속 도킹한 뒤 그 자리에서 180도 스핀 동작 수행 후 도킹 해제

Column 3 (Header Style: Orange Pill):
- Header Title: "연속 적재 복구"
- Sub-header: "물리 방향 전환 완료"
- Bullet Points:
  * 작업대 상태가 `_A_ROTATING`에서 회전 완료 후 다시 `_A` 구역 상태로 복구
  * 비어있던 뒷면(5~8번)이 로봇 팔 앞으로 정렬되는 기하학적 형상 확보
  * 로봇 팔에 다시 동작 재개(`pause_status = False`)를 보내 남은 4칸 슬롯을 매끄럽고 완벽하게 적재 완료
```

---

### 📝 Slide 16. 아웃바운드 포장 로봇 A/B 이중화 및 동적 승격 스케줄링
*   **이미지 포함 여부**: **NO**
*   **레이아웃 스타일**: **Style B (헤더 띠 + 2단 카테고리 카드 전체 가득 채움)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "아웃바운드 포장 로봇 A/B 이중화 및 동적 승격"
- Subtitle: "병목이 잦은 출고 포장 라인의 대기 정체 완화를 위한 공급 제어"

Layout: Below the gray header strip, split the white main area into 2 equal-width columns side-by-side using the full width of the slide.

Column 1:
- Header Title: "1. 포장 대기존 B(Look-ahead) 및 완충 작업대 공급"
- Sub-header: "사전 버퍼 공급을 통한 끊김 없는 포장"
- Bullet Points:
  * 포장 로봇 라인 또한 A구역(포장 가동)과 B구역(사전 대기)의 이중화 아키텍처 도입
  * 입고 라인 완충 작업대 발생 시, 포장 A구역에 작업대가 이미 있다면 즉각 B구역으로 자동 경로 전환 이송
  * 포장 로봇이 7번째 패키지를 래핑할 때, 스케줄러가 B구역에 대기할 작업대를 선제적으로 호출

Column 2:
- Header Title: "2. Keep-alive 동적 승격 스케줄러 탑재"
- Sub-header: "유휴 스레드 감시를 통한 자동 보충"
- Bullet Points:
  * 관제탑 1Hz 동적 스케줄러 루프 내에 포장 작업대 전용 승격 디스패처 통합
  * 포장 완료된 A구역 작업대가 회수되자마자 B구역의 예비 작업대를 A구역으로 동적 승격 공급
  * AMR 가용량에 맞춰 회수와 공급 작업이 물리 동선 간섭 없이 최적의 시퀀스로 교대하도록 유도
```

---

## 🎗 [트랙 4] Isaac Sim 3D 시뮬레이션 최적화 (Slide 17 ~ 20)

### 📝 Slide 17. sim_sync_node 기반 분산 시뮬레이션 상자 동기화
*   **이미지 포함 여부**: **YES**
*   **레이아웃 스타일**: **Style B (헤더 띠 + 3단 카테고리 카드 + 하단 이미지 공간)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "sim_sync_node 분산 시뮬레이션 상자 동기화"
- Subtitle: "이기종 PC 간 분산 기동 환경 하에서의 데이터 무결성 동기화 브리지"

Layout: Below the gray header strip, split the white main area vertically: Top part contains 3 equal columns side-by-side, Bottom part allocates a horizontal blank placeholder.
- [넣어야 할 사진 가이드: PC A(분류 시뮬레이션)와 PC B(적재 시뮬레이션)가 중앙의 sim_sync_node(TransitPackage.srv)를 통해 상자 데이터 및 이벤트를 송수신하는 분산 아키텍처 흐름도]

Column 1 (Header Style: Purple Pill):
- Header Title: "분산 환경의 한계"
- Sub-header: "물리 시뮬레이터 파편화"
- Bullet Points:
  * 단일 워크스테이션에서 분류(bg2)와 적재(sg2) 물리 엔진 동시 기동 시 그래픽 카드 부하 과중
  * PC A와 PC B로 시뮬레이터를 분산 배포했으나, 분류 완료된 상자 오브젝트가 적재 구역 컨베이어에 나타나지 않고 증발하는 문제 직면

Column 2 (Header Style: Blue Pill):
- Header Title: "전담 브리지 노드"
- Sub-header: "sim_sync_node 및 서비스 구축"
- Bullet Points:
  * 분산 PC 간의 상자 소멸/소환 신호를 전담 릴레이하는 sim_sync_node 백그라운드 구동
  * 커스텀 TransitPackage.srv 인터페이스를 통해 상자 ID와 최종 분류 라인 목적지 데이터를 동시 전달
  * 타겟 PC의 ROS 2 서비스 콜백이 신호를 수신하는 즉시 Isaac Sim 상에 동일 상자 에셋 동적 스폰

Column 3 (Header Style: Orange Pill):
- Header Title: "연속성 및 데이터 일치"
- Sub-header: "분산 데이터 및 상태 정합성 보장"
- Bullet Points:
  * 물리적으로 다른 PC 2대에서 연산이 이뤄지지만, 사용자 대시보드 및 WMS DB 상에는 단 하나의 흐름으로 동기화
  * 상자의 좌표 데이터 및 입출고 타임스탬프가 네트워크 지연 없이 0.05초 미만으로 실시간 수렴 완료
```

---

### 📝 Slide 18. Pixar OpenUSD 바닥 QR 격자 인스턴싱 최적화
*   **이미지 포함 여부**: **YES**
*   **레이아웃 스타일**: **Style A (헤더 띠 + 2단 Problem-Solution-Result + 중앙 이미지 공간)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "Pixar OpenUSD 바닥 QR 격자 인스턴싱 최적화"
- Subtitle: "대량의 독립 메쉬 렌더링에 따른 VRAM 과부하 해소 및 프레임 레이트 방어"

Layout: Below the gray header strip, split the white main area into 3 sections: Left Column (35% width), Center Column (30% width), and Right Column (35% width).

Left Column:
- Header Title: "1. 독립 메쉬 및 텍스처 개별 로드의 병목"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "143개 격자 위치마다 고유한 USD Quad Mesh와 독립 Material/Texture 에셋을 각각 생성하여 GPU VRAM이 과부하되고 프레임 레이트가 5 FPS 미만으로 추락"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "Pixar OpenUSD의 인스턴싱(Instancing) 설계를 도입하여, 메모리 상에 단 1개의 마스터 프로토타입 QR 메쉬만 등록하고 나머지 143개 위치는 SetInstanceable(True) 활성화한 내부 참조 인스턴스만 배치"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "USD 씬 파일 용량이 수십MB에서 372KB로 감소하고 실시간 렌더링 속도가 60 FPS 이상으로 보장되는 경량화 달성"

Center Column:
- Allocate a vertical blank image placeholder in this center column.
  * [넣어야 할 사진 가이드: 인스턴싱 미적용 시(5 FPS 버벅임)와 인스턴싱 적용 후(60 FPS 부드러움)의 프레임 레이트 성능 측정 비교 막대그래프]

Right Column:
- Header Title: "2. 맵 범위 축소 및 격자 최적화 설계"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "초기 광범위한 맵 영역에 불필요하게 2,300여 개가 넘는 과도한 바닥 마커가 생성되어 씬 파일이 낭비되고 렌더링 성능 저하 유발"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "실 가동 영역 Bounding Box 필터를 도입해 외곽 영역 생성을 억제하고 13.5m x 20m 격자 범위 내 143개 핵심 노드로 정제 설계"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "물류 창고 가동에 필요한 최소 노드 수량인 143개로 줄여 드로우콜 성능 저하 요소를 완전히 원천 방어"
```

---

### 📝 Slide 19. 시뮬레이션 조명 튜닝 및 카메라 비전 디코딩 개선
*   **이미지 포함 여부**: **YES**
*   **레이아웃 스타일**: **Style A (헤더 띠 + 2단 Problem-Solution-Result + 중앙 이미지 공간)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "시뮬레이션 조명 튜닝 및 비전 디코딩 개선"
- Subtitle: "반사광(Specular Glare) 억제를 통한 로봇 카메라 QR 디코딩 성공률 100% 확보"

Layout: Below the gray header strip, split the white main area into 3 sections: Left Column (35% width), Center Column (30% width), and Right Column (35% width).

Left Column:
- Header Title: "1. 직사광 하이라이트 글레어 문제"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "기존 기본 조명(DistantLight)의 세기가 너무 강하여 바닥 QR 마커 표면에 새하얀 반사광이 집중되어 로봇 하단 비전 카메라의 QR 코드 디코딩 실패율 급증"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "DistantLight의 강도를 3000.0에서 600.0으로 하향 조정하고, 사방에서 입사각을 분산시키는 부드러운 산란 환경광인 DomeLight(강도 1200.0)를 새로 추가"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "반사광 하이라이트를 완전히 지워 로봇 하단 카메라의 QR 비전 디코딩 성공률 100% 달성"

Center Column:
- Allocate a vertical blank image placeholder in this center column.
  * [넣어야 할 사진 가이드: 강한 조명으로 글레어가 생겨 QR 마커가 타버린 모습(Before) vs 돔 라이트 튜닝으로 선명하게 마커가 식별되는 모습(After) 비교 캡처본]

Right Column:
- Header Title: "2. 고성능 비전 라이브러리 교체 및 검증"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "가벼운 pyzbar 또는 OpenCV 내장 디텍터는 조도 노이즈나 약간의 흔들림(Motion Blur) 시 마커를 놓치는 신뢰성 불안정"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "Static 컴파일 바이너리 제공으로 설치 이식성이 높고 노이즈 억제력이 탁월한 zxing-cpp 디코딩 라이브러리로 백엔드 및 로봇 스캔 모듈 전면 전환"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "패키지 고유 ID 추출 성공률이 확실하게 향상되어 지능형 물류 공정 무정지 속행 달성"
```

---

### 📝 Slide 20. Isaac Sim 3D 월드 실시간 통합 AMR 커넥터 개발
*   **이미지 포함 여부**: **YES**
*   **레이아웃 스타일**: **Style B (헤더 띠 + 2단 카테고리 카드 + 우측 이미지 공간)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "Isaac Sim 3D 월드 실시간 통합 AMR 커넥터 개발"
- Subtitle: "관제탑 데이터 상태와 Omniverse 3D 가상 환경 간의 실시간 브리지 구축"

Layout: Below the gray header strip, split the white main area into 2 sections: Left Section (70% width) and Right Section (30% width).

Left Section (Split into 2 columns side-by-side):
- Column 1:
  * Header Title: "1. 30Hz 고속 실시간 텔레포트 동기화"
  * Sub-header: "isaac_amr_connector.py 코어 설계"
  * Bullet Points:
    - Redis에 저장된 AMR 고주파 위치 상태(HSET)와 PostgreSQL의 작업대 주차 좌표를 30Hz 주기로 연속 폴링
    - Isaac Sim Omniverse API를 직접 호출하여, 매 프레임마다 /World/AMRs 및 /World/Workstations 오브젝트를 물리 목표 좌표로 실시간 텔레포트 동기화
    - 실제 기기가 없어도 대시보드 및 시뮬레이터 화면 상에서 부드러운 위치 매핑 구현
- Column 2:
  * Header Title: "2. PhysX 물리 제어 충돌 방지 구조"
  * Sub-header: "경량 --only-amr 구동 모드 설계"
  * Bullet Points:
    - AMR 리프팅 및 작업대 적합 물리 동작 시, 커넥터가 작업대 위치를 강제로 텔레포트 시키면서 PhysX 물리 제어권과 충돌하여 오브젝트 겹침 오류 발생
    - --only-amr 옵션을 추가 설계하여, 실제 물리적 결합 테스트 시에는 작업대 텔레포트를 끄고 AMR 위치만 렌더링하도록 안전 제어 우회로 확보
    - 3D 시뮬레이션 상의 물리 법칙 유지와 상태 시각화를 동시에 달성

Right Section:
- Allocate a vertical blank placeholder in this right section.
  * [넣어야 할 사진 가이드: Isaac Sim 내에 다수의 AMR과 작업대 메쉬가 실시간 데이터와 동기화되어 주행하는 3D 시뮬레이션 인게임 스크린샷]
```

---

## 🎗 [트랙 5] 대시보드 고도화 및 예외 처리 (Slide 21 ~ 27)

### 📝 Slide 21. 2D 실시간 웹 대시보드 렌더링 성능 최적화
*   **이미지 포함 여부**: **YES**
*   **레이아웃 스타일**: **Style A (헤더 띠 + 2단 Problem-Solution-Result + 중앙 이미지 공간)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "2D 실시간 웹 대시보드 렌더링 최적화"
- Subtitle: "DOM 객체 수량 감축을 통한 저스펙 모니터링 기기 브라우저 프레임 드롭 방지"

Layout: Below the gray header strip, split the white main area into 3 sections: Left Column (35% width), Center Column (30% width), and Right Column (35% width).

Left Column:
- Header Title: "1. 720개 격자 div 직접 DOM 렌더링 오버헤드"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "매 주기마다 2D 플로어 플랜의 720개 격자점을 나타내는 개별 div 요소를 브라우저가 매번 리렌더링하여 CPU 점유율이 95% 이상으로 치솟고 화면 렉이 심한 상태 발생"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "DOM의 모든 격자 div를 전면 삭제하고, CSS linear-gradient 단 1개의 속성으로 바둑판 모양의 격자 배경을 경량 드로잉하도록 대체"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "대시보드 브라우저 로딩 연산 부하가 95% 이상 대폭 감축되어 브라우저 다운 현상 원천 해결"

Center Column:
- Allocate a vertical blank image placeholder in this center column.
  * [넣어야 할 사진 가이드: 브라우저 상에 절대 좌표(absolute positioning)로 가볍게 렌더링된 2D 실시간 웹 모니터링 대시보드 구동 화면 스크린샷]

Right Column:
- Header Title: "2. Absolute Positioning 동적 상태 좌표 렌더링"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "전체 맵을 통째로 렌더링하지 않으면, AMR과 작업대의 실시간 위치 변화를 효과적으로 출력해 주기 어려워지는 문제"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "CSS absolute positioning 기법을 도입하여, 실제 실시간 데이터가 변화하는 31개 스팟 위치와 실시간 AMR, 로봇 팔 레이어만 동적 생성하여 얹는 구조로 개편"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "모니터링 대시보드 CPU 사용량이 5% 미만으로 경량 유지되어 모바일 및 저스펙 PC에서도 실시간 가동 보장"
```

---

### 📝 Slide 22. WebSocket 양방향 변경분 브로드캐스트 도입
*   **이미지 포함 여부**: **NO**
*   **레이아웃 스타일**: **Style A (헤더 띠 + 2단 Problem-Solution-Result 전체 가득 채움)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "WebSocket 양방향 변경분 브로드캐스트 도입"
- Subtitle: "매 주기 HTTP Polling 무거운 DB 조회 구조 개선을 통한 서버 리소스 최적화"

Layout: Below the gray header strip, split the white main area into 2 equal-width columns side-by-side using the full width of the slide.

Column 1:
- Header Title: "1. 1.0초 HTTP Polling 방식의 한계"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "다중 사용자가 대시보드를 열어둘 시, 1초마다 무조건적인 HTTP 요청이 들어와 PostgreSQL에 지속적인 Full Query 조회가 발생해 DB 세션 과부화 발생"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "FastAPI 웹소켓(WebSocket) 엔드포인트를 구현하여 백엔드 서버와 프론트엔드 간의 양방향 지속성 세션 통로 구성"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "불필요한 HTTP 커넥션 핸드셰이크가 소멸되어 네트워크 트래픽 및 오버헤드 급감"

Column 2:
- Header Title: "2. 이벤트 기반 변경 데이터 Push"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "변화가 없는 정적 상태에서도 주기적으로 패킷을 무제한 전송 시 서버 통신 스레드 점유 누적"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "관제탑 노드가 작업대 및 패키지 상태 변화 이벤트를 감지했을 때에만 1.5초 주기로 웹소켓을 통해 클라이언트에 최종 변경 데이터를 Push 브로드캐스트 하도록 구현"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "서버 백엔드 유휴 연산 부하가 0%에 가깝게 하향 안정되어 대시보드 서버 동시 접속 수용량 확장 확보"
```

---

### 📝 Slide 23. 자동 영업일 마감(Auto-EOD) 및 이월(Carry-over) 적재 시스템
*   **이미지 포함 여부**: **NO**
*   **레이아웃 스타일**: **Style B (헤더 띠 + 2단 카테고리 카드 전체 가득 채움)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "자동 영업일 마감(Auto-EOD) 및 이월(Carry-over) 적재"
- Subtitle: "일일 물류 연속성 보장을 위한 수동 EOD 제거 및 전날 미처리 작업대 자동 처리"

Layout: Below the gray header strip, split the white main area into 2 equal-width columns side-by-side using the full width of the slide.

Column 1:
- Header Title: "1. 포장 완료 트리거 기반 자동 영업일 마감(Auto-EOD)"
- Sub-header: "관리자 수동 개입 없는 지능형 EOD 전환"
- Bullet Points:
  * WMS DB 내부의 오늘 날짜 미처리 패키지가 0개가 되는 순간을 관제 스케줄러가 실시간 추적
  * 출고 포장 로봇의 마지막 작업대 완료 피드백 즉시 수동 개입 없이 자동으로 다음 예정일로 영업일 전환
  * 날짜 전환 직후 즉시 포장존으로 잔여 작업대가 플러시되는 오작동 방지를 위해 system:inbound_started 플래그 연동 제어

Column 2:
- Header Title: "2. 미처리 작업대 자동 이월(Carry-over) 적재"
- Sub-header: "자원 폐기 없는 연속 가동"
- Bullet Points:
  * 전날 8칸을 다 채우지 못하고 애매하게 남겨진 작업대(예: 6개 적재)를 폐기하지 않고 보존
  * 영업일 전환 직후, 이 이월 작업대를 1번 인바운드 라인(sg2_in_01_A)으로 최우선 자동 소환 배치
  * 오늘 새로 업로드된 신규 CSV 물량 중 동일 날짜 패키지를 남은 2개 슬롯에 마저 채워 포장존으로 연속 배출
```

---

### 📝 Slide 24. 시스템 포트 충돌 자동 정리 및 테스트 자동화 런처 개발
*   **이미지 포함 여부**: **NO**
*   **레이아웃 스타일**: **Style B (헤더 띠 + 2단 카테고리 카드 전체 가득 채움)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "포트 충돌 자동 정리 및 테스트 자동화 런처 개발"
- Subtitle: "다중 프로세스 실행 충돌 해소 및 원클릭 개발 환경 재구동 환경 구축"

Layout: Below the gray header strip, split the white main area into 2 equal-width columns side-by-side using the full width of the slide.

Column 1:
- Header Title: "1. 8080 및 8000 포트 충돌 및 자동 정리"
- Sub-header: "외부인증 데몬 및 호스트 포트 점유 해소"
- Bullet Points:
  * docker Adminer 컨테이너 기동 시 호스트 8080 포트 중복 점유 실패 ➔ "8082:8080" 포트 매핑 변경 우회
  * FastAPI 대시보드가 Omniverse Nucleus Auth(8000 포트 고정 점유)와 충돌 ➔ 대시보드 포트를 8009로 변경
  * 백그라운드 쉘 스크립트 실행 시 8009 tcp 프로세스를 사전에 감지하고 강제 종료(fuser -k 8009/tcp)하는 방어 유틸리티 배포

Column 2:
- Header Title: "2. reset_db.py 및 start_test_env.sh 통합 자동화"
- Sub-header: "원클릭 시나리오 기동 도구 완비"
- Bullet Points:
  * reset_db.py: PostgreSQL 테이블 완전 초기화, Redis 플러시, 143개 바닥 QR 공간 맵 재적재를 단독 실행하는 DB 리셋 툴 구현
  * start_test_env.sh: Docker 컨테이너 헬스체크 ➔ 데이터베이스 완전 초기화 ➔ colcon build 컴파일 검증 ➔ 대시보드, 관제탑, 가상 에뮬레이터를 백그라운드 스레드로 자동 동시 실행해 주는 런처 배포
```

---

### 📝 Slide 25. Thread-Safe 데이터베이스 락 및 커넥션 풀 구축
*   **이미지 포함 여부**: **NO**
*   **레이아웃 스타일**: **Style A (헤더 띠 + 2단 Problem-Solution-Result 전체 가득 채움)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "Thread-Safe 데이터베이스 락 및 커넥션 풀 구축"
- Subtitle: "멀티스레드 비동기 콜백 환경에서의 PostgreSQL 커서 충돌 방지 및 성능 개선"

Layout: Below the gray header strip, split the white main area into 2 equal-width columns side-by-side using the full width of the slide.

Column 1:
- Header Title: "1. MultiThreadedExecutor 내 PostgreSQL 커서 충돌"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "다중 콜백 스레드가 단일 PostgreSQL 커넥션 인스턴스를 공유하며 동시에 질의 및 커서 생성 시, 드라이버 레벨에서 커서 리소스 위반 크래시 및 데이터 누수 발생"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "파이썬 재진입 락인 threading.RLock() 기반의 뮤텍스(self.pg_lock)를 전 트랜잭션 구간에 도입하여 동일 스레드 내 중첩 호출은 허용하되 스레드 간 충돌은 차단"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "동시성 오류에 따른 관제탑 비정상 노드 다운 현상을 완전히 차단하여 24시간 가동 안정성 확보"

Column 2:
- Header Title: "2. ThreadedConnectionPool 도입을 통한 성능 가속"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "동시 호출 시 락 대기 시간이 늘어남에 따라 전체 제어 루프의 응답 속도가 간헐적으로 0.5초 이상 늘어나는 지연 현상 발생"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "psycopg2의 ThreadedConnectionPool을 도입하여 각 스레드가 전용 커넥션을 풀에서 독립적으로 획득하고 트랜잭션을 병렬 수행하도록 로직 리팩토링"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "락 대입 대기 병목이 완전히 소멸하고 데이터베이스 통신 지연 시간이 0.01초 이하로 급감"
```

---

### 📝 Slide 26. AMR 통신 오프라인 대응 롤백 및 중복 방지 예외 처리
*   **이미지 포함 여부**: **NO**
*   **레이아웃 스타일**: **Style A (헤더 띠 + 2단 Problem-Solution-Result 전체 가득 채움)**
```text
Create a clean and professional presentation slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "AMR 통신 오프라인 대응 롤백 및 예외 처리"
- Subtitle: "통신 장애 극복을 위한 DB 자동 롤백 및 작업대 이중 배정 방지 쿼리 설계"

Layout: Below the gray header strip, split the white main area into 2 equal-width columns side-by-side using the full width of the slide.

Column 1:
- Header Title: "1. AMR 통신 단절에 따른 작업대 고착 예방"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "AMR 에뮬레이터 지연 및 액션 서버 통신 에러 발생 시, 작업대가 '이동중' 상태로 영구 고착되어 스케줄러가 더 이상 동작을 하지 않는 데드락 발생"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "액션 클라이언트 대기 wait_for_server에 timeout=1.0초를 걸고, 실패 감지 즉시 DB 상태와 주차 스팟 예약을 원격 롤백시키는 recover_workstation_move_db_state() 엔진 구현"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "네트워크 단절 상황에서도 관제탑이 락 상태를 즉각 자동 해제하여 자가 복구 가동 100% 보장"

Column 2:
- Header Title: "2. 이중 배정 및 중복 호출 차단"
- Create 3 vertically stacked card blocks under the header:
  1. Top Card (Light Red background or Red border):
     - Section Title: "배경 및 문제점"
     - Body Text: "작업대가 입고 라인으로 이동 중인 과도 상태일 때, 관제탑이 해당 구역에 작업대가 없다고 오판해 창고에서 빈 작업대를 중복 할당하여 물리 겹침 현상 발생"
  2. Middle Card (Light Blue background or Blue border):
     - Section Title: "해결 방안"
     - Body Text: "대상 라인의 작업대를 검색할 때 단순 할당 완료가 아닌 '이동중, 회전중, 대기존배치' 상태까지 포괄 추적하는 다단계 우선순위 검증 쿼리 적용"
  3. Bottom Card (Light Green background or Green border):
     - Section Title: "최종 성과"
     - Body Text: "이송 상태 오차에 따른 다중 중복 이송 명령 오류를 완벽히 제거하여 물류 겹침 충돌률 0% 달성"
```

---

### 📝 Slide 27. 종합 기술 성과 요약 및 클로징
*   **이미지 포함 여부**: **NO (테이블 가득 채움)**
*   **레이아웃 스타일**: **Style C (헤더 띠 + 구조화된 테이블 전체)**
```text
Create a clean and professional table-style slide with a pure white background (#FFFFFF).

At the top of the slide, create a full-width horizontal light gray banner strip (#F1F3F5) as a header background. 
Place the following title and subtitle inside this gray header strip:
- Title: "종합 기술 성과 요약"
- Subtitle: "중앙 관제 소프트웨어 파이프라인 도입에 따른 전후 정량적 성과 대비 명세"

Layout: Below the gray header strip, create a full-width structured table with 3 columns.
- Table Header background color: Dark Navy (White text)
- Column 1 header: "핵심 평가 지표"
- Column 2 header: "개선 전 상태 (Legacies)"
- Column 3 header: "개선 후 성과 (Achievements)"

Table Rows:
Row 1: "물리 충돌 및 상자 추락" | "이송/도킹 회전 중 잦은 충돌 및 물리 월드 붕괴" | "0% (JIT 인터로킹 pause_status 제어로 충돌 전면 차단)"
Row 2: "시뮬레이션 렌더링 프레임" | "5 FPS 미만 (143개 QR 코드 개별 생성 과부하)" | "60 FPS 이상 (OpenUSD 인스턴싱 설계로 372KB 초경량화)"
Row 3: "로봇 팔 적재 대기 시간" | "평균 45초 (완충 작업대 입출고 교체 시 유휴 대기)" | "3초 미만 (A/B 이중 버퍼 및 Look-ahead 사전이송 결합)"
Row 4: "대시보드 모니터링 부하" | "브라우저 프리징 (720개 div DOM 강제 리렌더링)" | "CPU 5% 미만 (CSS absolute positioning 동적 렌더링)"
Row 5: "영업일 마감 절차" | "수동 EOD 마감 및 전날 미적재 자원 전량 수동 리셋" | "완전 자동화 (Auto-EOD 및 미적재 작업대 Carry-over 연속 적재)"
Row 6: "DDS 분산 환경 신뢰성" | "간헐적 통신 딜레이 및 패킷 락 교착" | "해소 완료 (Cyclone DDS 최적화 및 pg_lock 스레드 세이프 적용)"
```
