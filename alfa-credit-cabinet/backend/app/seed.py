"""Синтетические данные для демонстрации: тестовые учётные записи."""
from sqlalchemy.orm import Session

from .models import User
from .security import hash_password

DEMO_USERS = [
    ("client@demo.test", "client123", "Анна Клиентова", "client"),
    ("client2@demo.test", "client123", "Пётр Предпринимателев", "client"),
    ("operator@demo.test", "operator123", "Ольга Операторова", "operator"),
    ("analyst@demo.test", "analyst123", "Алексей Аналитиков", "analyst"),
    ("admin@demo.test", "admin123", "Админ Системов", "admin"),
]


def seed(db: Session) -> None:
    for email, password, name, role in DEMO_USERS:
        if not db.query(User).filter_by(email=email).first():
            db.add(User(email=email, password_hash=hash_password(password), name=name, role=role))
    db.commit()
