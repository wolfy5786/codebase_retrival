"""Admin router — CRUD for users (admin only)."""
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.auth.dependencies import AdminUser
from app.db.supabase import get_supabase_admin
from app.schemas.admin import (
    AdminUserCreate,
    AdminUserResponse,
    AdminUserRoleUpdate,
)

router = APIRouter()


def _user_to_response(user) -> AdminUserResponse:
    """Map Supabase User (object or dict) to AdminUserResponse."""
    if hasattr(user, "id"):
        return AdminUserResponse(
            id=user.id,
            email=getattr(user, "email", None),
            app_metadata=getattr(user, "app_metadata", {}) or {},
            created_at=getattr(user, "created_at", None),
            updated_at=getattr(user, "updated_at", None),
        )
    # Dict-like (e.g. from model_dump)
    return AdminUserResponse(
        id=user["id"],
        email=user.get("email"),
        app_metadata=user.get("app_metadata", {}),
        created_at=user.get("created_at"),
        updated_at=user.get("updated_at"),
    )


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(_user: AdminUser):
    """List all users from Supabase Auth."""
    supabase = get_supabase_admin()
    r = supabase.auth.admin.list_users()
    users = getattr(r, "users", []) or []
    if hasattr(r, "model_dump"):
        users = r.model_dump().get("users", users)
    return [_user_to_response(u) for u in users]


@router.get("/users/{id}", response_model=AdminUserResponse)
async def get_user(id: UUID, _user: AdminUser):
    """Get single user by id."""
    supabase = get_supabase_admin()
    r = supabase.auth.admin.get_user_by_id(str(id))
    user = r.user if hasattr(r, "user") else r
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_response(user)


@router.post("/users", response_model=AdminUserResponse)
async def create_user(body: AdminUserCreate, _user: AdminUser):
    """Create a new Supabase auth user and set role in app_metadata."""
    supabase = get_supabase_admin()
    data = {
        "email": body.email,
        "password": body.password,
        "email_confirm": True,
        "app_metadata": {"role": body.role},
    }
    r = supabase.auth.admin.create_user(data)
    user = r.user if hasattr(r, "user") else r
    if not user:
        raise HTTPException(status_code=500, detail="Failed to create user")
    return _user_to_response(user)


@router.patch("/users/{id}/role", response_model=AdminUserResponse)
async def update_user_role(id: UUID, body: AdminUserRoleUpdate, _user: AdminUser):
    """Update app_metadata.role via service role key."""
    supabase = get_supabase_admin()
    r = supabase.auth.admin.update_user_by_id(
        str(id),
        {"app_metadata": {"role": body.role}},
    )
    user = r.user if hasattr(r, "user") else r
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_response(user)


@router.delete("/users/{id}", status_code=204)
async def delete_user(id: UUID, _user: AdminUser):
    """Delete user from Supabase Auth."""
    supabase = get_supabase_admin()
    supabase.auth.admin.delete_user(str(id))
