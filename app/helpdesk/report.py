import json
import threading
import uuid

from fastapi import HTTPException

from . import config, tickets
from .ports import CompletionGateway
from .schemas import PeriodInput, Topic, TopicsReport

# Estado dos jobs assíncronos de F3, em memória (ver documentacao/specs.md,
# "Fora de escopo": sobreviver a reinício com tarefas em andamento não é
# cobrado). Lock porque o handler HTTP (polling) e a tarefa de fundo rodam em
# threads diferentes do threadpool do Starlette.
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def start_topics_job(period: PeriodInput) -> str:
    if period.start > period.end:
        raise HTTPException(status_code=422, detail="A data inicial é posterior à data final")

    job_id = uuid.uuid4().hex[:8]
    with _jobs_lock:
        _jobs[job_id] = {"state": "pending", "progress": None, "result": None, "reason": None}
    return job_id


def run_topics_job(job_id: str, period: PeriodInput, gateway: CompletionGateway) -> None:
    with _jobs_lock:
        _jobs[job_id]["state"] = "running"
    try:
        selected = tickets.in_period(period.start, period.end)

        # O mês inteiro não cabe numa chamada: processa em lotes, um depois do outro.
        totals: dict[str, dict] = {}
        for first in range(0, len(selected), config.TICKETS_PER_CALL):
            batch = selected[first:first + config.TICKETS_PER_CALL]
            content = "\n".join(f"[{t['id']}] {t['text']}" for t in batch)
            answer = json.loads(gateway.complete(config.REPORT_CAPABILITY, "topics", content))
            for item in answer["topics"]:
                current = totals.setdefault(item["topic"], {"count": 0, "examples": []})
                current["count"] += item["count"]
                current["examples"] = (current["examples"] + item["examples"])[:3]

            done = min(first + config.TICKETS_PER_CALL, len(selected))
            with _jobs_lock:
                _jobs[job_id]["progress"] = f"{done}/{len(selected)}"

        items = [Topic(topic=name, **data) for name, data in totals.items()]
        items.sort(key=lambda t: (-t.count, t.topic))
        report = TopicsReport(start=period.start, end=period.end, total_tickets=len(selected), topics=items)

        with _jobs_lock:
            _jobs[job_id]["state"] = "done"
            _jobs[job_id]["result"] = report
    except Exception as exc:
        with _jobs_lock:
            _jobs[job_id]["state"] = "failed"
            _jobs[job_id]["reason"] = str(exc)


def job_status(job_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return job


def job_result(job_id: str) -> TopicsReport:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None or job["state"] != "done":
        raise HTTPException(status_code=404, detail="Resultado não disponível")
    return job["result"]
