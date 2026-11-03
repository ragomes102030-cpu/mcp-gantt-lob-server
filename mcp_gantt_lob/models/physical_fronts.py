"""Stateless physical-front capacity constraints using the proven renewable leveler.

Each task occupies a location/front and competes for both labor resources and
physical slots. No project data, global optimization, or automatic productivity.
"""
from __future__ import annotations
from .resource_calendar import nivelar_recursos_com_calendario

_PREFIX = "__frente_fisica__:"


def nivelar_frentes_de_trabalho(
    atividades: list[dict], capacidades_recursos: dict[str, int],
    capacidades_frentes: dict[str, int], dependencias: list[dict] | None = None,
    data_inicio: str | None = None, calendario: dict | None = None,
) -> dict:
    """Tasks require id, duracao_dias, local_id, recursos, optional ocupacao_frente.

    Front capacities are simultaneous activity slots for each physical local.
    No physical geometry, safety distances, or access-route modeling is inferred.
    """
    if not isinstance(capacidades_frentes, dict) or not 1 <= len(capacidades_frentes) <= 100:
        raise ValueError("Informe 1..100 frentes com capacidades")
    if not isinstance(capacidades_recursos, dict) or not capacidades_recursos:
        raise ValueError("Informe capacidades de recursos")
    if any(not isinstance(k, str) or k.startswith(_PREFIX)
           for k in capacidades_recursos):
        raise ValueError("ID de recurso usa prefixo reservado de frente")
    fronts = {}
    for loc, cap in capacidades_frentes.items():
        if not isinstance(loc, str) or not loc.strip() or len(loc) > 100:
            raise ValueError("local_id invalido")
        if type(cap) is not int or not 1 <= cap <= 10000:
            raise ValueError("capacidade de frente invalida")
        fronts[loc] = cap
    if not isinstance(atividades, list):
        raise ValueError("atividades precisam ser lista")
    expanded = []
    locations = {}
    for a in atividades:
        if not isinstance(a, dict):
            raise ValueError("atividade invalida")
        loc = a.get("local_id")
        if loc not in fronts:
            raise ValueError("atividade com local_id sem capacidade de frente")
        occ = a.get("ocupacao_frente", 1)
        if type(occ) is not int or not 1 <= occ <= fronts[loc]:
            raise ValueError("ocupacao_frente invalida ou acima da capacidade")
        labor = a.get("recursos")
        if not isinstance(labor, dict):
            raise ValueError("recursos precisam ser dicionario")
        entry = dict(a)
        entry["recursos"] = {**labor, _PREFIX + loc: occ}
        expanded.append(entry)
        locations[a.get("id")] = (loc, occ)
    caps = {**capacidades_recursos, **{_PREFIX + k: v for k, v in fronts.items()}}
    result = nivelar_recursos_com_calendario(
        expanded, caps, dependencias, data_inicio, calendario)
    tasks = []
    for row in result["tarefas"]:
        loc, occ = locations[row["id"]]
        tasks.append({**row, "local_id": loc, "ocupacao_frente": occ,
                      "recursos": {k: v for k, v in row["recursos"].items()
                                   if not k.startswith(_PREFIX)}})
    return {
        **result, "tarefas": tasks, "capacidades_frentes": fronts,
        "metodo": "nivelamento_recursos_e_capacidade_fisica_frentes",
        "premissa": result["premissa"] +
                    "; slots por local fornecidos pelo cliente; sem geometria ou distancia minima",
    }
