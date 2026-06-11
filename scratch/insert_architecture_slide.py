import re
import os

# Paths
prompts_file = "/home/yoon/cobot3_ws/docs/PRESENTATION_GEMINI_PROMPTS.md"
guide_file = "/home/yoon/cobot3_ws/docs/INTEGRATED_PRESENTATION_GUIDE.md"

def shift_slides_prompts(content):
    # First, let's find all headers like "### 📝 Slide XX. Title" and shift the number if >= 3
    # We also need to update the total count of slides in header if any, let's check
    
    # We will do this by processing the file slide by slide
    # Slide 01 to 02 are unchanged
    # Shift Slide 03 -> 04, Slide 04 -> 05, etc.
    
    def replace_header(match):
        num = int(match.group(1))
        if num >= 3:
            return f"### 📝 Slide {num + 1:02d}."
        return match.group(0)
    
    new_content = re.sub(r"### 📝 Slide (\d+)\.", replace_header, content)
    
    # Also update any other mentions of Slide numbers if they are like Slide 03 -> Slide 04
    # Let's do this carefully. In PRESENTATION_GEMINI_PROMPTS.md, we have mentions like (Slide 07 ~ 11) -> (Slide 08 ~ 12)
    # Let's shift track descriptions too
    # Track 1 (Slide 01 ~ 06) -> (Slide 01 ~ 07)
    # Track 2 (Slide 07 ~ 11) -> (Slide 08 ~ 12)
    # Track 3 (Slide 12 ~ 15) -> (Slide 13 ~ 16)
    # Track 4 (Slide 16 ~ 18) -> (Slide 17 ~ 19) (or 16-19 -> 17-20)
    # Let's write a helper to replace slide ranges
    def replace_range(match):
        start = int(match.group(1))
        end = int(match.group(2))
        new_start = start + 1 if start >= 3 else start
        new_end = end + 1 if end >= 3 else end
        return f"Slide {new_start:02d} ~ {new_end:02d}"
    
    new_content = re.sub(r"Slide (\d+) ~ (\d+)", replace_range, new_content)
    
    # Also update Total 26 Slides -> Total 27 Slides
    new_content = re.sub(r"Total 26 Slides", "Total 27 Slides", new_content)
    new_content = re.sub(r"total 26 slides", "total 27 slides", new_content)
    
    return new_content

def shift_slides_guide(content):
    def replace_header(match):
        num = int(match.group(1))
        if num >= 3:
            return f"#### 📝 Slide {num + 1:02d}."
        return match.group(0)
    
    new_content = re.sub(r"#### 📝 Slide (\d+)\.", replace_header, content)
    
    # Also update Track ranges and Slide ranges
    def replace_range(match):
        start = int(match.group(1))
        end = int(match.group(2))
        new_start = start + 1 if start >= 3 else start
        new_end = end + 1 if end >= 3 else end
        return f"Slide {new_start:02d} ~ {new_end:02d}"
    
    new_content = re.sub(r"Slide (\d+) ~ (\d+)", replace_range, new_content)
    new_content = re.sub(r"Slide (\d+)-(\d+)", lambda m: f"Slide {int(m.group(1))+1 if int(m.group(1))>=3 else int(m.group(1))}-{int(m.group(2))+1 if int(m.group(2))>=3 else int(m.group(2))}", new_content)
    new_content = re.sub(r"Total 26 Slides", "Total 27 Slides", new_content)
    
    # In mermaid graph:
    # S3[초기 Git & 개발 환경] --> S4[ROS 2 커스텀 인터페이스] --> S5[DB 스키마 정규화] --> S6[QR ID 통합 매핑]
    # We should shift:
    # S3 -> S4, S4 -> S5, etc.
    # And insert S3[전체 아키텍처 및 데이터 흐름]
    # Let's do this by string replacement
    
    # Let's update S nodes in Track1:
    # S1[오프닝] --> S2[기술 스택] --> S3[초기 Git & 개발 환경] --> S4[ROS 2 커스텀 인터페이스] --> S5[DB 스키마 정규화] --> S6[QR ID 통합 매핑]
    old_track1 = "S1[오프닝] --> S2[기술 스택] --> S3[초기 Git & 개발 환경] --> S4[ROS 2 커스텀 인터페이스] --> S5[DB 스키마 정규화] --> S6[QR ID 통합 매핑]"
    new_track1 = "S1[오프닝] --> S2[기술 스택] --> S3[전체 아키텍처 및 데이터 흐름] --> S4[초기 Git & 개발 환경] --> S5[ROS 2 커스텀 인터페이스] --> S6[DB 스키마 정규화] --> S7[QR ID 통합 매핑]"
    new_content = new_content.replace(old_track1, new_track1)
    
    # Shifting S7..S26 nodes to S8..S27 in the rest of the mermaid
    # S7[중앙 관제 노드 설계] --> S8[동적 날짜 기반 라우팅] --> S9[AMR 플릿 ZSET 우선순위 큐] --> S10[최단거리 동적 배정] --> S11[창고 주차 관리 및 자동 배정]
    new_content = new_content.replace("S7[중앙 관제 노드 설계]", "S8[중앙 관제 노드 설계]")
    new_content = new_content.replace("S8[동적 날짜 기반 라우팅]", "S9[동적 날짜 기반 라우팅]")
    new_content = new_content.replace("S9[AMR 플릿 ZSET 우선순위 큐]", "S10[AMR 플릿 ZSET 우선순위 큐]")
    new_content = new_content.replace("S10[최단거리 동적 배정]", "S11[최단거리 동적 배정]")
    new_content = new_content.replace("S11[창고 주차 관리 및 자동 배정]", "S12[창고 주차 관리 및 자동 배정]")
    
    # S12[JIT 인터로킹 충돌 방지] --> S13[A/B 이중 버퍼 & Look-ahead] --> S14[작업대 180도 회전 시퀀스] --> S15[출고 포장 라인 이중화 및 승격]
    new_content = new_content.replace("S12[JIT 인터로킹 충돌 방지]", "S13[JIT 인터로킹 충돌 방지]")
    new_content = new_content.replace("S13[A/B 이중 버퍼 & Look-ahead]", "S14[A/B 이중 버퍼 & Look-ahead]")
    new_content = new_content.replace("S14[작업대 180도 회전 시퀀스]", "S15[작업대 180도 회전 시퀀스]")
    new_content = new_content.replace("S15[출고 포장 라인 이중화 및 승격]", "S16[출고 포장 라인 이중화 및 승격]")
    
    # S16[분산 시뮬레이션 동기화] --> S17[USD 바닥 QR 격자 맵 최적화] --> S18[조명 글레어 튜닝 및 비전 디코딩] --> S19[Isaac Sim 실시간 AMR 커넥터]
    new_content = new_content.replace("S16[분산 시뮬레이션 동기화]", "S17[분산 시뮬레이션 동기화]")
    new_content = new_content.replace("S17[USD 바닥 QR 격자 맵 최적화]", "S18[USD 바닥 QR 격자 맵 최적화]")
    new_content = new_content.replace("S18[조명 글레어 튜닝 및 비전 디코딩]", "S19[조명 글레어 튜닝 및 비전 디코딩]")
    new_content = new_content.replace("S19[Isaac Sim 실시간 AMR 커넥터]", "S20[Isaac Sim 실시간 AMR 커넥터]")
    
    # S20[대시보드 렌더링 성능 최적화] --> S21[대시보드 통신 웹소켓 전환] --> S22[자동 영업 마감 및 이월 제어] --> S23[포트 충돌 해소 및 프로세스 킬러] --> S24[스레드 안정성 및 커넥션 풀] --> S25[AMR 오프라인 대응 및 DB 롤백] --> S26[종합 성과 요약]
    new_content = new_content.replace("S20[대시보드 렌더링 성능 최적화]", "S21[대시보드 렌더링 성능 최적화]")
    new_content = new_content.replace("S21[대시보드 통신 웹소켓 전환]", "S22[대시보드 통신 웹소켓 전환]")
    new_content = new_content.replace("S22[자동 영업 마감 및 이월 제어]", "S23[자동 영업 마감 및 이월 제어]")
    new_content = new_content.replace("S23[포트 충돌 해소 및 프로세스 킬러]", "S24[포트 충돌 해소 및 프로세스 킬러]")
    new_content = new_content.replace("S24[스레드 안정성 및 커넥션 풀]", "S25[스레드 안정성 및 커넥션 풀]")
    new_content = new_content.replace("S25[AMR 오프라인 대응 및 DB 롤백]", "S26[AMR 오프라인 대응 및 DB 롤백]")
    new_content = new_content.replace("S26[종합 성과 요약]", "S27[종합 성과 요약]")

    # Also shift header lists like:
    # Track 1: 기초 인프라 및 DB 설계 (Slide 1~6)
    # Track 2: 관제 스케줄러 및 라우팅 알고리즘 (Slide 7~11)
    # Track 3: JIT 공정 제어 및 로봇 협업 (Slide 12~15)
    # Track 4: Isaac Sim 3D 시뮬레이션 최적화 (Slide 16~19)
    # Track 5: 대시보드 고도화 및 예외 처리 (Slide 20~26)
    new_content = new_content.replace("(Slide 1~6)", "(Slide 1~7)")
    new_content = new_content.replace("(Slide 7~11)", "(Slide 8~12)")
    new_content = new_content.replace("(Slide 12~15)", "(Slide 13~16)")
    new_content = new_content.replace("(Slide 16~19)", "(Slide 17~20)")
    new_content = new_content.replace("(Slide 20~26)", "(Slide 21~27)")
    
    return new_content

# Read
with open(prompts_file, "r") as f:
    prompts_content = f.read()

with open(guide_file, "r") as f:
    guide_content = f.read()

# Shift
prompts_shifted = shift_slides_prompts(prompts_content)
guide_shifted = shift_slides_guide(guide_content)

# Insert Slide 03
new_slide_prompt = """### 📝 Slide 03. 전체 시스템 아키텍처 및 데이터/제어 토폴로지
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

"""

# Insert into prompts_shifted after Slide 02
slide02_end_marker = """  Row 6: "시뮬레이션 & 비전" | "NVIDIA Isaac Sim / OpenUSD / zxing-cpp" | "3D 물류 창고 월드 모의 실험, USD 인스턴싱 최적화 및 패키지 QR 코드 디코딩 연동"
```

---"""

if slide02_end_marker in prompts_shifted:
    prompts_final = prompts_shifted.replace(slide02_end_marker, slide02_end_marker + "\n\n" + new_slide_prompt)
    print("Inserted slide prompt in PRESENTATION_GEMINI_PROMPTS.md successfully!")
else:
    print("Marker not found in PRESENTATION_GEMINI_PROMPTS.md")
    prompts_final = prompts_shifted

# Insert Slide 03 into guide_shifted
new_slide_guide = """#### 📝 Slide 03. 전체 시스템 아키텍처 및 데이터/제어 토폴로지
* **슬라이드 내용**:
  - **제어 평면**: 중앙 관제탑(`control_tower_node`)이 AMR 에뮬레이터(`mock_full_robot_node`) 및 포장기 에뮬레이터(`mock_sg2_out_node`)에 액션 명령을 내리고 피드백을 수령
  - **데이터 평면**: PostgreSQL 15(WMS DB)와 Redis 7.0(캐시 및 ZSET 큐)의 하이브리드 운용. 관제탑이 ZSET에서 태스크를 Push/Pop하고 DB 커넥션 풀로 영속 트랜잭션을 처리
  - **시뮬레이션 동기화**: `sim_sync_node`가 상자 이동을 감지해 `TransitPackage` 서비스를 호출하고, `isaac_amr_connector`가 Redis 위치를 읽어 Isaac Sim에 텔레포트 동기화
* **발표 스크립트 (Script)**:
  > "이 장표는 저희 물류 시스템의 전체 아키텍처와 제어/데이터 흐름을 도식화한 다이어그램입니다. 보시는 것처럼 관제탑 노드는 ROS 2 액션과 서비스를 통해 AMR 및 로봇들의 물리 행동을 직접 통제하며, 동시에 PostgreSQL 데이터베이스와 Redis 메모리 큐에 실시간으로 접근합니다. 시뮬레이터 브릿지인 커넥터는 Redis의 기기 좌표를 실시간 조회하여 Isaac Sim 내의 3D 객체들과 가시적으로 완벽히 동기화해 줍니다."

---

"""

guide_slide02_end_marker = """* **발표 스크립트 (Script)**:
  > "저희 시스템은 실시간 분산 로봇 제어와 대용량 WMS 데이터 트랜잭션을 동시에 처리해야 하는 과제를 안고 있었습니다. 이를 해결하기 위해 ROS 2 Humble 미들웨어 위에 Cyclone DDS를 채택하고, PostgreSQL과 Redis를 결합한 하이브리드 데이터 플랫폼을 설계하여 고속 인메모리 처리와 영속적 트랜잭션 보전을 실현했습니다."

---"""

if guide_slide02_end_marker in guide_shifted:
    guide_final = guide_shifted.replace(guide_slide02_end_marker, guide_slide02_end_marker + "\n\n" + new_slide_guide)
    print("Inserted slide guide in INTEGRATED_PRESENTATION_GUIDE.md successfully!")
else:
    print("Marker not found in INTEGRATED_PRESENTATION_GUIDE.md")
    guide_final = guide_shifted

# Write back
with open(prompts_file, "w") as f:
    f.write(prompts_final)

with open(guide_file, "w") as f:
    f.write(guide_final)

print("Done shifting slide numbers and inserting architecture slide!")
