from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import User

Base.metadata.create_all(bind=engine)

app = FastAPI()


@app.get("/")
def root():
    return {
        "message": "Welcome to Code Clan API"
    }


@app.post("/users")
def create_user(
    name: str,
    email: str,
    role: str = "student",
    db: Session = Depends(get_db)
):
    new_user = User(
        name=name,
        email=email,
        role=role
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "id": new_user.id,
        "name": new_user.name,
        "email": new_user.email,
        "role": new_user.role
    }