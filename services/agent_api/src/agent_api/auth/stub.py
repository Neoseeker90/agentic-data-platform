from fastapi import Header, HTTPException, status
from pydantic import BaseModel


class AuthenticatedUser(BaseModel):
    user_id: str
    role: str = "business_user"


async def get_current_user(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_user_role: str = Header(default="business_user", alias="X-User-Role"),
) -> AuthenticatedUser:
    if x_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-Id header",
        )
    return AuthenticatedUser(user_id=x_user_id, role=x_user_role)
