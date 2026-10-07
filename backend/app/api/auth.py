from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User
from app.core.security import verify_password, create_access_token
from app.core.deps import get_current_user
from app.schemas.schemas import LoginRequest, TokenResponse, UserResponse

router = APIRouter(prefix='/auth', tags=['Auth'])

@router.post('/login', response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email.lower().strip()).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail='Invalid email or password')
    token = create_access_token({'sub': str(user.id), 'role': user.role})
    return {'access_token': token, 'token_type': 'bearer', 'user': {
        'id': user.id, 'email': user.email, 'name': user.name, 'role': user.role,
        'customer_id': user.customer_id, 'telegram_chat_id': user.telegram_chat_id
    }}

@router.get('/me', response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user
