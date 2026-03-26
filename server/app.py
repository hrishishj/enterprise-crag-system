from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.upload import router as upload_router
from routes.query import router as query_router
from routes.compare import router as compare_router
from routes.clause import router as clause_router

app = FastAPI(title="Enterprise CRAG System", version="1.0.0")

# NOTE: In production, replace "*" with your actual frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router, prefix="/api", tags=["Upload"])
app.include_router(query_router, prefix="/api", tags=["Query"])
app.include_router(compare_router, prefix="/api", tags=["Compare"])
app.include_router(clause_router, prefix="/api", tags=["Clause"])

@app.get("/")
def root():
    return {"message": "Enterprise CRAG System Running"}

@app.get("/health")
def health():
    return {"status": "ok"}
