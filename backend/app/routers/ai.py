from fastapi import APIRouter, Depends
from pydantic import BaseModel
from ..auth_utils import get_current_user
from ..ai import generate

router = APIRouter()

class ChatIn(BaseModel):
  prompt: str

@router.post("/chat")
async def chat(body: ChatIn, user = Depends(get_current_user)):
  text = await generate(body.prompt)
  return {"ok": True, "response": text}
