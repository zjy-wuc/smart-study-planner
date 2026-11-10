from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.response import success, error
from app.core.deps import get_current_user
from app.schemas.user import UserCreate, UserUpdate

from sqlalchemy.exc import IntegrityError
from app.core.security import hash_password


router = APIRouter()


@router.post("/users", status_code=201)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
):
    stored_hash = hash_password(user.password)

    sql = text("""
        INSERT INTO users
        (username, password_hash, nickname, created_at, updated_at)
        VALUES (:username, :password_hash, :nickname, NOW(), NOW())
    """)

    try:
        result = db.execute(sql, {
            "username": user.username,
            "password_hash": stored_hash,
            "nickname": user.nickname,
        })
        db.commit()

        return success({
            "id": result.lastrowid,
            "username": user.username,
            "nickname": user.nickname,
        }, message="User created", code=201)

    except IntegrityError:
        db.rollback()
        return error(409, "用户名已存在")

    except Exception:
        db.rollback()
        raise


@router.get("/users")
def get_users(db: Session = Depends(get_db)):
    sql = text("""
        SELECT id, username, nickname, created_at, updated_at
        FROM users
    """)

    result = db.execute(sql)
    users = [dict(row) for row in result.mappings().all()]

    return success(users)


@router.get("/users/me")
def get_me(current_user=Depends(get_current_user)):
    return success(current_user)


@router.get("/users/{user_id}")
def get_user(
    user_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    sql = text("""
        SELECT id, username, nickname, created_at, updated_at
        FROM users
        WHERE id = :user_id
    """)

    result = db.execute(sql, {"user_id": user_id})
    user = result.mappings().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return success(dict(user))


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    user: UserUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    sql = text("""
        UPDATE users
        SET nickname = :nickname, updated_at = NOW()
        WHERE id = :user_id
    """)

    result = db.execute(sql, {
        "nickname": user.nickname,
        "user_id": user_id,
    })

    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=404, detail="User not found")

    db.commit()
    return success(message="User updated")


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    sql = text("DELETE FROM users WHERE id = :user_id")

    result = db.execute(sql, {"user_id": user_id})

    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=404, detail="User not found")

    db.commit()
    return success(message="User deleted")


