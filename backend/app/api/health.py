from fastapi import APIRouter

router=APIRouter(
    prefix="/health",
    tags=["Health"]
)

@router.get("/")

def health():
    return {"Status":"Healthy"}