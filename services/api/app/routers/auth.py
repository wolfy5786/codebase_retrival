"""Auth router — current user profile."""
from fastapi import APIRouter

from app.auth.dependencies import CurrentUser
from app.schemas.auth import UserMeResponse

router = APIRouter()


@router.get("/me", response_model=UserMeResponse)
async def get_me(user: CurrentUser):
    """Return current user profile decoded from JWT."""
    return UserMeResponse(
        id=user["id"],
        email=user.get("email", ""),
        app_metadata=user.get("app_metadata", {}),
    )
