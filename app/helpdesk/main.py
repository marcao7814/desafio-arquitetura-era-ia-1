import asyncio
import json

from fastapi import BackgroundTasks, FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse

from . import classification, extraction, report
from .adapters.gateway import LiteLLMGateway
from .schemas import Classification, OrderData, PeriodInput, TicketInput, TopicsReport
from .suggestion import suggest_stream

app = FastAPI(title="Helpdesk")

# Composition root: só aqui o adapter concreto do gateway é construído e
# injetado nas features. Nenhuma feature importa adapters.gateway diretamente.
gateway = LiteLLMGateway()

# Orçamento de latência síncrono (requisito 6): nenhuma feature síncrona pode
# ficar pendurada além disso — responde com sucesso (via fallback do gateway)
# ou erro explícito.
SYNC_TIMEOUT_SECONDS = 15


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/tickets/classification")
async def classify_ticket(ticket: TicketInput) -> Classification:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(classification.classify, ticket, gateway), timeout=SYNC_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Tempo esgotado ao classificar o ticket")


@app.post("/tickets/reply-suggestion")
def suggest_reply(ticket: TicketInput) -> StreamingResponse:
    def event_stream():
        try:
            for chunk in suggest_stream(ticket, gateway):
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"event: end\ndata: {json.dumps({'ticket_id': ticket.ticket_id})}\n\n"
        except Exception:
            message = {"ticket_id": ticket.ticket_id, "message": "A geração foi interrompida"}
            yield f"event: error\ndata: {json.dumps(message)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        # Sem este header, o nginx da borda bufferiza a resposta por padrão e
        # o streaming vira "tudo de uma vez" no fim (edge/nginx.conf não pode
        # ser alterado, mas este header é honrado por padrão pelo nginx).
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.post("/tickets/extraction")
async def extract_order_data(ticket: TicketInput) -> OrderData:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(extraction.extract, ticket, gateway), timeout=SYNC_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Tempo esgotado ao extrair dados do ticket")


@app.post("/reports/topics")
def topics_report(period: PeriodInput, background_tasks: BackgroundTasks) -> Response:
    job_id = report.start_topics_job(period)
    background_tasks.add_task(report.run_topics_job, job_id, period, gateway)
    return Response(
        status_code=202,
        headers={"Location": f"/reports/topics/status/{job_id}", "Retry-After": "5"},
    )


@app.get("/reports/topics/status/{job_id}")
def topics_status(job_id: str):
    job = report.job_status(job_id)
    if job["state"] == "done":
        return Response(status_code=303, headers={"Location": f"/reports/topics/{job_id}"})
    if job["state"] == "failed":
        return {"state": "failed", "reason": job["reason"]}
    return {"state": job["state"], "progress": job["progress"]}


@app.get("/reports/topics/{job_id}")
def topics_result(job_id: str) -> TopicsReport:
    return report.job_result(job_id)
