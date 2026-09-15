from datetime import datetime, timedelta

from app import create_app
from app.extensions import db
from app.models import (
    Attachment,
    Inquiry,
    Message,
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_CLOSED,
    STATUS_WAITING,
    User,
    WAITING_FOR_ADMIN,
    WAITING_FOR_NONE,
)

app = create_app()

DEPARTMENT = "연말정산TF"

with app.app_context():
    # schema changed again (attachments / delete-request / cancellation
    # fields added) -- still demo data, so recreate fresh rather than
    # hand-writing a migration
    db.drop_all()
    db.create_all()

    admin_names = ["관리자A", "관리자B", "관리자C", "관리자D", "관리자E", "관리자F", "관리자G"]
    admin_users = {}
    for i, name in enumerate(admin_names, start=1):
        emp_no = f"A{1000 + i}"
        email = f"admin{name[-1].lower()}@etns.com"
        user = User(employee_number=emp_no, name=name, email=email, role=ROLE_ADMIN, department=DEPARTMENT)
        user.set_password("admin1234")
        db.session.add(user)
        db.session.commit()
        admin_users[name] = user

    employees = [
        ("E1000", "권세현", "kwon@etns.com", "인재성장팀"),
        ("E1001", "홍길동", "hong@etns.com", "마케팅팀"),
        ("E1002", "김민준", "kim@etns.com", "재무팀"),
        ("E1003", "이서연", "lee@etns.com", "개발팀"),
        ("E1004", "박지훈", "park@etns.com", "디자인팀"),
        ("E1005", "최유진", "choi@etns.com", "총무팀"),
    ]
    employee_users = {}
    for emp_no, name, email, dept in employees:
        user = User(employee_number=emp_no, name=name, email=email, role=ROLE_EMPLOYEE, department=dept)
        user.set_password("demo1234")
        db.session.add(user)
        db.session.commit()
        employee_users[name] = user

    # 박지훈 계정은 "비활성화 계정" 데모용 -- 관리자가 임직원 관리 화면에서
    # 활성/비활성 토글을 바로 확인할 수 있도록 처음부터 비활성 상태로 시딩
    employee_users["박지훈"].is_active = False
    db.session.commit()

    def make_inquiry(employee, admin, title, first_message, **overrides):
        inquiry = Inquiry(
            employee_id=employee.id, admin_id=admin.id, title=title,
            status=STATUS_WAITING, waiting_for=WAITING_FOR_ADMIN,
        )
        for k, v in overrides.items():
            setattr(inquiry, k, v)
        db.session.add(inquiry)
        db.session.flush()
        db.session.add(Message(inquiry_id=inquiry.id, sender_id=employee.id, content=first_message))
        db.session.commit()
        return inquiry

    def add_message(inquiry, sender, content, with_attachment=False):
        message = Message(inquiry_id=inquiry.id, sender_id=sender.id, content=content)
        db.session.add(message)
        db.session.flush()
        if with_attachment:
            db.session.add(
                Attachment(
                    message_id=message.id,
                    original_filename="증빙자료.pdf",
                    stored_filename="demo-seed-attachment.pdf",
                    file_size=12345,
                    mime_type="application/pdf",
                    file_data=b"%PDF-1.4 demo seed attachment\n",
                )
            )
        db.session.commit()
        return message

    def close(inquiry, closed_at):
        inquiry.status = STATUS_CLOSED
        inquiry.waiting_for = WAITING_FOR_NONE
        inquiry.closed_at = closed_at
        db.session.commit()

    def cancel_via_delete_approval(inquiry, employee, admin, requested_at, approved_at):
        inquiry.delete_requested = True
        inquiry.delete_requested_at = requested_at
        inquiry.delete_requested_by = employee.id
        inquiry.delete_approved = True
        inquiry.delete_approved_at = approved_at
        inquiry.delete_approved_by = admin.id
        inquiry.status = STATUS_CANCELLED
        inquiry.waiting_for = WAITING_FOR_NONE
        inquiry.cancelled_at = approved_at
        inquiry.cancelled_by = admin.id
        db.session.commit()

    # ---- 권세현 (인재성장팀): the flagship demo account from the spec's own
    # mockups -- 1 active conversation + 3 closed ones kept as history ----
    kwon = employee_users["권세현"]

    active_kwon = make_inquiry(
        kwon, admin_users["관리자A"], "교육비 정산 문의",
        "이번 분기 교육비 정산 관련해서 문의드립니다.",
    )
    add_message(active_kwon, kwon, "관련 증빙자료 첨부드립니다.", with_attachment=True)

    c1 = make_inquiry(
        kwon, admin_users["관리자C"], "연말정산 서류 문의",
        "연말정산 관련 문의드립니다.",
        created_at=datetime(2026, 9, 12, 10, 0),
        is_read=True, read_at=datetime(2026, 9, 12, 10, 32), status=STATUS_ACTIVE,
    )
    add_message(c1, admin_users["관리자C"], "확인해보겠습니다.")
    add_message(c1, kwon, "필요한 서류가 있을까요?")
    add_message(c1, admin_users["관리자C"], "해당 서류를 제출해주시면 됩니다.")
    close(c1, datetime(2026, 9, 12, 10, 40))

    c2 = make_inquiry(
        kwon, admin_users["관리자B"], "급여 관련 문의",
        "이번 달 급여 명세서 관련 문의드립니다.",
        created_at=datetime(2026, 9, 10, 8, 50),
        is_read=True, read_at=datetime(2026, 9, 10, 9, 10), status=STATUS_ACTIVE,
    )
    add_message(c2, admin_users["관리자B"], "확인 후 안내드리겠습니다.")
    close(c2, datetime(2026, 9, 10, 9, 30))

    c3 = make_inquiry(
        kwon, admin_users["관리자G"], "증빙자료 문의",
        "제출한 증빙자료가 잘 반영되었는지 확인 부탁드립니다.",
        created_at=datetime(2026, 9, 5, 13, 40),
        is_read=True, read_at=datetime(2026, 9, 5, 14, 0), status=STATUS_ACTIVE,
    )
    add_message(c3, admin_users["관리자G"], "정상 반영되었습니다. 감사합니다.")
    close(c3, datetime(2026, 9, 5, 14, 20))

    # ---- delete/cancel workflow demo scenarios ----
    # 1) unread -- employee can still delete directly
    make_inquiry(
        employee_users["홍길동"], admin_users["관리자B"], "노트북 지급 문의",
        "신규 입사자용 노트북은 언제쯤 받을 수 있을까요?",
    )

    # 2) read but no delete request yet -- employee must request, not delete directly
    kim_inquiry = make_inquiry(
        employee_users["김민준"], admin_users["관리자D"], "연차 사용 문의",
        "다음 주 연차 사용 가능한지 확인 부탁드립니다.",
        status=STATUS_ACTIVE,
    )
    kim_inquiry.is_read = True
    kim_inquiry.read_at = kim_inquiry.created_at + timedelta(minutes=5)
    db.session.commit()

    # 3) read + delete requested, awaiting admin approval -- shows up in the
    # "삭제 승인 요청" queue
    choi_inquiry = make_inquiry(
        employee_users["최유진"], admin_users["관리자E"], "비품 신청 문의",
        "모니터 거치대 추가로 신청하고 싶습니다.",
        status=STATUS_ACTIVE,
    )
    choi_inquiry.is_read = True
    choi_inquiry.read_at = choi_inquiry.created_at + timedelta(minutes=5)
    choi_inquiry.delete_requested = True
    choi_inquiry.delete_requested_at = choi_inquiry.read_at + timedelta(minutes=10)
    choi_inquiry.delete_requested_by = employee_users["최유진"].id
    db.session.commit()

    # 4) read + delete requested + already approved -- CANCELLED (never CLOSED)
    lee_inquiry = make_inquiry(
        employee_users["이서연"], admin_users["관리자F"], "비품 신청 문의",
        "책상 서랍장 추가로 신청하고 싶습니다.",
        created_at=datetime(2026, 9, 8, 10, 50),
        is_read=True, read_at=datetime(2026, 9, 8, 11, 0), status=STATUS_ACTIVE,
    )
    cancel_via_delete_approval(
        lee_inquiry, employee_users["이서연"], admin_users["관리자F"],
        requested_at=datetime(2026, 9, 8, 11, 5), approved_at=datetime(2026, 9, 8, 13, 0),
    )

    # 5) normal close -- distinct from CANCELLED above
    park_inquiry = make_inquiry(
        employee_users["박지훈"], admin_users["관리자G"], "출장비 정산 문의",
        "지난달 출장비 정산이 아직 안 된 것 같습니다.",
        status=STATUS_ACTIVE,
    )
    park_inquiry.is_read = True
    park_inquiry.read_at = park_inquiry.created_at + timedelta(minutes=5)
    db.session.commit()
    add_message(park_inquiry, admin_users["관리자G"], "확인 후 정산 완료했습니다. 감사합니다.")
    close(park_inquiry, park_inquiry.read_at + timedelta(minutes=15))

    # ---- fill the remaining waiting-count targets with synthetic employees,
    # one active (unread, WAITING) inquiry each -- A=1 B=1 C=4 D=2 E=8 F=3 G=7
    target_counts = {"관리자A": 1, "관리자B": 1, "관리자C": 4, "관리자D": 2, "관리자E": 8, "관리자F": 3, "관리자G": 7}
    already_counted = {"관리자A": 1, "관리자B": 1, "관리자D": 1, "관리자E": 1}

    synthetic_index = 1
    for admin_name, target in target_counts.items():
        remaining = target - already_counted.get(admin_name, 0)
        for _ in range(remaining):
            emp_no = f"S{2000 + synthetic_index}"
            name = f"임직원{synthetic_index:02d}"
            email = f"staff{synthetic_index:02d}@etns.com"
            user = User(employee_number=emp_no, name=name, email=email, role=ROLE_EMPLOYEE, department="현업부서")
            user.set_password("demo1234")
            db.session.add(user)
            db.session.commit()
            make_inquiry(
                user, admin_users[admin_name], "연말정산 서류 문의",
                "연말정산 서류 제출 방법이 궁금합니다.",
            )
            synthetic_index += 1

    print("Seed complete.")
    print("Admin logins (password: admin1234):")
    for name in admin_names:
        print(f"  {name} ({DEPARTMENT}) - {admin_users[name].email}")
    print("Employee logins (password: demo1234):")
    for emp_no, name, email, dept in employees:
        print(f"  {name} ({dept}) - {email}{'  [비활성 계정 데모]' if name == '박지훈' else ''}")
    print(f"  + {synthetic_index - 1} synthetic staff accounts (staff01@etns.com .. , password: demo1234)")
