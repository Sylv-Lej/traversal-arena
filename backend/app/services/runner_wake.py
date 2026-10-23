"""Démarre le runner de l'arène (Serverless Job Scaleway) à la demande.

Le runner passe aussi tout seul toutes les 30 min (cron). Pour un bilan de partie, on
n'attend pas : le backend lance la tâche tout de suite, sauf si un passage est déjà en
cours (il prendra le bilan avant les parties de l'échelle, `arena.claim`).

Clé : `SCW_JOBS_SECRET_KEY`, d'une application IAM qui n'a que `ServerlessJobsFullAccess`
sur le projet `SCW_PROJECT_ID` (Terraform). Les listes doivent nommer ce projet : sans
lui, la requête vise toute l'organisation, où cette clé n'a aucun droit. La tâche est
retrouvée par son nom (`ARENA_JOB_NAME`) : son identifiant dépend de l'URL du backend, le
backend ne peut pas le recevoir de Terraform. Tant qu'un bilan attend le runner, chaque
tour des workers relance cet appel (`analysis_jobs.claim`).
Sans clé (dev local, tests) : rien, le cron ou `make arena-dev` s'en chargent.
"""

import logging
import os
import time

import httpx

log = logging.getLogger("traversal.runner")

API = "https://api.scaleway.com/serverless-jobs/v1alpha2/regions"
ACTIVE = {"initialized", "validated", "queued", "running", "retrying"}
MIN_INTERVAL_S = 20  # entre deux vérifications (plusieurs bilans demandés d'un coup)

_job_id: str | None = None
_last = 0.0


def enabled() -> bool:
    return bool(os.environ.get("SCW_JOBS_SECRET_KEY") and os.environ.get("ARENA_JOB_NAME"))


async def wake() -> None:
    """Lance un passage du runner si aucun n'est en cours. Jamais d'exception : au pire,
    le cron passera (et le bilan retombe sur orque seul après `ARENA_WAIT_S`)."""
    global _job_id, _last
    if not enabled() or time.time() - _last < MIN_INTERVAL_S:
        return
    _last = time.time()
    region = os.environ.get("SCW_REGION", "fr-par")
    headers = {"X-Auth-Token": os.environ["SCW_JOBS_SECRET_KEY"]}
    project = {"project_id": os.environ["SCW_PROJECT_ID"]} if os.environ.get("SCW_PROJECT_ID") else {}
    try:
        async with httpx.AsyncClient(base_url=f"{API}/{region}", headers=headers, timeout=10) as client:
            if _job_id is None:
                r = await client.get("/job-definitions", params={"page_size": 100, **project})
                r.raise_for_status()
                name = os.environ["ARENA_JOB_NAME"]
                _job_id = next((d["id"] for d in r.json()["job_definitions"] if d["name"] == name), None)
                if _job_id is None:
                    log.error("tâche %s introuvable (%d définitions visibles)", name, len(r.json()["job_definitions"]))
                    return
            r = await client.get("/job-runs", params={
                "job_definition_id": _job_id, "order_by": "created_at_desc", "page_size": 5, **project})
            r.raise_for_status()
            if any(run.get("state") in ACTIVE for run in r.json()["job_runs"]):
                return
            r = await client.post(f"/job-definitions/{_job_id}/start", json={})
            r.raise_for_status()
            log.info("runner de l'arène lancé pour un bilan")
    except httpx.HTTPStatusError as exc:
        log.error("runner de l'arène non lancé : %s %s", exc.response.status_code, exc.response.text[:300])
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.error("runner de l'arène non lancé : %s", exc)
