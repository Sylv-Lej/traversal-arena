#!/usr/bin/env python3
"""Assure l'existence d'un projet Lampion et renvoie sa connection string.

Ne dépend QUE d'une clé API Lampion (LAMPION_API_KEY) + la stdlib Python.
Prévu pour tourner dans un conteneur python jetable (aucun outil requis sur l'hôte).

Comportement (idempotent) :
  1. GET /v1/projects  -> cherche un projet nommé LAMPION_PROJECT_NAME
  2. absent            -> POST /v1/projects {name, region}  (création)
  3. GET /v1/projects/{id}/endpoints -> connection_string de l'endpoint read/write
  4. imprime la `connection_string` (postgresql://...) sur stdout, rien d'autre.

Variables d'environnement :
  LAMPION_API_KEY       (requis)  token Bearer `lmp_live_...`
  LAMPION_PROJECT_NAME  (requis)  nom du projet = nom du site
  LAMPION_REGION        (option.) région Lampion, défaut "fr-par-1"
  LAMPION_API_BASE      (option.) défaut "https://api.lampion.cloud/v1"

Tout ce qui n'est pas la connection string va sur stderr. Exit 1 en cas d'erreur.
"""
import json
import os
import sys
import urllib.error
import urllib.request


def log(*a):
    print(*a, file=sys.stderr)


def api(base, key, method, path, body=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        log(f"Lampion API {method} {path} -> HTTP {e.code}: {detail}")
        sys.exit(1)
    except urllib.error.URLError as e:
        log(f"Lampion API {method} {path} injoignable: {e.reason}")
        sys.exit(1)
    return json.loads(raw) if raw.strip() else {}


def as_list(payload):
    """La liste des projets peut être un tableau nu ou enveloppé (projects/data/items)."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("projects", "data", "items", "results"):
            if isinstance(payload.get(k), list):
                return payload[k]
    return []


def conn_string(obj):
    if not isinstance(obj, dict):
        return None
    for k in ("connection_string", "connectionString", "database_url", "dsn"):
        if obj.get(k):
            return obj[k]
    return None


def endpoint_conn(base, key, project_id):
    """La connection string vit sur l'ENDPOINT du projet, pas sur le projet lui-même.

    On prend l'endpoint read/write (celui de la branche primaire), en préférant un
    endpoint déjà démarré ; à défaut le premier qui expose une connection string.
    """
    eps = as_list(api(base, key, "GET", f"/projects/{project_id}/endpoints"))
    rw = [e for e in eps if e.get("type") == "read_write"] or eps
    for group in ([e for e in rw if e.get("status") == "running"], rw):
        for e in group:
            cs = conn_string(e)
            if cs:
                return cs
    return None


def resolve(base, key, project):
    """connection string du projet : champ direct s'il existe, sinon via les endpoints."""
    return conn_string(project) or endpoint_conn(base, key, project.get("id"))


def main():
    key = os.environ.get("LAMPION_API_KEY", "").strip()
    name = os.environ.get("LAMPION_PROJECT_NAME", "").strip()
    region = os.environ.get("LAMPION_REGION", "fr-par-1").strip()
    base = os.environ.get("LAMPION_API_BASE", "https://api.lampion.cloud/v1").strip()

    if not key:
        log("ERREUR: LAMPION_API_KEY manquant (token 'lmp_live_...').")
        log("        Mets-le dans .env.deploy.")
        sys.exit(1)
    if not name:
        log("ERREUR: LAMPION_PROJECT_NAME manquant (nom du site).")
        sys.exit(1)

    existing = next(
        (p for p in as_list(api(base, key, "GET", "/projects"))
         if p.get("name") == name),
        None,
    )

    if existing:
        log(f"Projet Lampion '{name}' existant.")
        project = existing
    else:
        log(f"Projet Lampion '{name}' absent -> création (region={region}).")
        project = api(base, key, "POST", "/projects",
                      {"name": name, "region": region})

    if not project.get("id"):  # création qui ne renvoie pas le projet -> on relit la liste
        project = next(
            (p for p in as_list(api(base, key, "GET", "/projects"))
             if p.get("name") == name),
            project,
        )

    cs = resolve(base, key, project)

    if not cs:
        log(f"ERREUR: pas de connection_string renvoyée pour '{name}'.")
        sys.exit(1)

    print(cs)  # seule sortie stdout : la connection string


if __name__ == "__main__":
    main()
