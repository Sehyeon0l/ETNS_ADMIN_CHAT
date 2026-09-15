from datetime import datetime

from app import create_app
from app.extensions import db
from app.models import (
    Inquiry,
    Message,
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
    STATUS_CLOSED,
    STATUS_READ,
    STATUS_WAITING,
    User,
    WAITING_FOR_ADMIN,
    WAITING_FOR_NONE,
)

app = create_app()

DEPARTMENT = "연말정산TF"

with app.app_context():
    # schema changed (waiting_for / closed_at added) -- this is still demo
    # data, so recreate the tables fresh rather than hand-writing a migration
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
    ]
    employee_users = {}
    for emp_no, name, email, dept in employees:
        user = User(employee_number=emp_no, name=name, email=email, role=ROLE_EMPLOYEE, department=dept)
        user.set_password("demo1234")
        db.session.add(user)
        db.session.commit()
        employee_users[name] = user

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

    def add_message(inquiry, sender, content):
        db.session.add(Message(inquiry_id=inquiry.id, sender_id=sender.id, content=content))
        db.session.commit()

    def close(inquiry, closed_at):
        inquiry.status = STATUS_CLOSED
        inquiry.waiting_for = WAITING_FOR_NONE
        inquiry.closed_at = closed_at
        db.session.commit()

    # ---- 권세현 (인재성장팀): the flagship demo account from the spec's own
    # mockups -- 1 active conversation + 3 closed ones kept as history ----
    kwon = employee_users["권세현"]

    active_kwon = make_inquiry(
        kwon, admin_users["관리자A"], "교육비 정산 문의",
        "이번 분기 교육비 정산 관련해서 문의드립니다.",
    )

    c1 = make_inquiry(
        kwon, admin_users["관리자C"], "연말정산 서류 문의",
        "연말정산 관련 문의드립니다.",
        is_read=True, read_at=datetime(2026, 9, 12, 10, 32),
    )
    add_message(c1, admin_users["관리자C"], "확인해보겠습니다.")
    add_message(c1, kwon, "필요한 서류가 있을까요?")
    add_message(c1, admin_users["관리자C"], "해당 서류를 제출해주시면 됩니다.")
    close(c1, datetime(2026, 9, 12, 10, 40))

    c2 = make_inquiry(
        kwon, admin_users["관리자B"], "급여 관련 문의",
        "이번 달 급여 명세서 관련 문의드립니다.",
        is_read=True, read_at=datetime(2026, 9, 10, 9, 10),
    )
    add_message(c2, admin_users["관리자B"], "확인 후 안내드리겠습니다.")
    close(c2, datetime(2026, 9, 10, 9, 30))

    c3 = make_inquiry(
        kwon, admin_users["관리자G"], "증빙자료 문의",
        "제출한 증빙자료가 잘 반영되었는지 확인 부탁드립니다.",
        is_read=True, read_at=datetime(2026, 9, 5, 14, 0),
    )
    add_message(c3, admin_users["관리자G"], "정상 반영되었습니다. 감사합니다.")
    close(c3, datetime(2026, 9, 5, 14, 20))

    # ---- the 4 existing policy-test scenarios (unread / read / read+approved
    # / closed), spread across different admins so they also count toward
    # those admins' totals ----
    make_inquiry(
        employee_users["홍길동"], admin_users["관리자B"], "노트북 지급 문의",
        "신규 입사자용 노트북은 언제쯤 받을 수 있을까요?",
    )
    make_inquiry(
        employee_users["김민준"], admin_users["관리자D"], "연차 사용 문의",
        "다음 주 연차 사용 가능한지 확인 부탁드립니다.",
        status=STATUS_READ, is_read=True, read_at=datetime.utcnow(),
    )
    make_inquiry(
        employee_users["이서연"], admin_users["관리자F"], "비품 신청 문의",
        "모니터 거치대 추가로 신청하고 싶습니다.",
        status=STATUS_READ, is_read=True, read_at=datetime.utcnow(), delete_approved=True,
    )
    park_inquiry = make_inquiry(
        employee_users["박지훈"], admin_users["관리자G"], "출장비 정산 문의",
        "지난달 출장비 정산이 아직 안 된 것 같습니다.",
        is_read=True, read_at=datetime.utcnow(),
    )
    add_message(park_inquiry, admin_users["관리자G"], "확인 후 정산 완료했습니다. 감사합니다.")
    close(park_inquiry, datetime.utcnow())

    # ---- fill the remaining waiting-count targets with synthetic employees,
    # one active (unread, WAITING) inquiry each -- A=1 B=1 C=4 D=2 E=8 F=3 G=7
    target_counts = {"관리자A": 1, "관리자B": 1, "관리자C": 4, "관리자D": 2, "관리자E": 8, "관리자F": 3, "관리자G": 7}
    already_counted = {"관리자A": 1, "관리자B": 1, "관리자D": 1, "관리자F": 1}

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
        print(f"  {name} ({dept}) - {email}")
    print(f"  + {synthetic_index - 1} synthetic staff accounts (staff01@etns.com .. , password: demo1234)")
