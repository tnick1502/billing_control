from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.api import devices, parts, orders, bom, monthly_plans, invoices, files
from app.database import Base, async_session_maker, engine
from app.seeds.init_data import seed_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Ensure S3 bucket exists
    try:
        from app.services.s3_service import ensure_bucket_exists
        await ensure_bucket_exists()
    except Exception as e:
        print(f"S3 bucket init warning: {e}")

    # Seed if enabled
    if settings.seed_on_startup:
        async with async_session_maker() as session:
            try:
                seeded = await seed_database(session)
                await session.commit()
                if seeded:
                    print("Database seeded with test data")
            except Exception as e:
                await session.rollback()
                print(f"Seed warning: {e}")

    yield
    # shutdown


app = FastAPI(
    title="MRP BOM Orders API",
    description="API for managing orders, devices, BOMs, monthly plans and invoices",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    msg = str(exc.orig) if exc.orig else str(exc)
    if "unique" in msg.lower() or "duplicate" in msg.lower():
        return JSONResponse(status_code=409, content={"detail": "Запись с такими данными уже существует"})
    if "foreign key" in msg.lower() or "violates" in msg.lower():
        return JSONResponse(status_code=400, content={"detail": "Некорректная ссылка (план, деталь и т.д.)"})
    return JSONResponse(status_code=400, content={"detail": msg})



app.include_router(devices.router)
app.include_router(parts.router)
app.include_router(orders.router)
app.include_router(bom.router)
app.include_router(monthly_plans.router)
app.include_router(invoices.router)
app.include_router(files.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
