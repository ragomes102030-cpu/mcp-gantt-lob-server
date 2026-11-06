"""LOB pública: QA de escala e contrato FS da Plataforma Obras sem acessar obras."""
import pytest

from mcp_gantt_lob.models.lob_rede import calcular_lob_com_vinculos
from public_mcp import calcular_linha_balanco


def fixture(qtd_servicos=50, qtd_locais=100):
    locais = [f"P{i:03d}" for i in range(1, qtd_locais + 1)]
    atividades = [
        {"activity_id": f"S{i:02d}", "duracao_dias": 1,
         "numero_equipes": 1, "equipe_id": f"E{i:02d}"}
        for i in range(1, qtd_servicos + 1)
    ]
    dependencias = [
        {"predecessora_id": atividades[j]["activity_id"],
         "predecessora_local": loc,
         "sucessora_id": atividades[j + 1]["activity_id"],
         "sucessora_local": loc,
         "tipo": "FS", "lag_dias": 0}
        for loc in locais for j in range(len(atividades) - 1)
    ]
    return atividades, locais, dependencias


def test_lob_5000_tarefas_e_4900_vinculos_em_memoria():
    a, locais, deps = fixture()
    r = calcular_lob_com_vinculos(a, locais, deps)
    assert r["persistido"] is False
    assert r["total_tarefas"] == 5000
    assert len(r["tarefas"]) == 5000
    assert len({(x["activity_id"], x["location_id"]) for x in r["tarefas"]}) == 5000
    assert all(x["fim_dia"] > x["inicio_dia"] for x in r["tarefas"])


def test_fs_e_ti_equivalentes_na_mesma_frente():
    a = [
        {"activity_id": "A", "duracao_dias": 3, "equipe_id": "E1"},
        {"activity_id": "B", "duracao_dias": 2, "equipe_id": "E2"},
    ]
    d = [{"predecessora_id": "A", "predecessora_local": "P01",
          "sucessora_id": "B", "sucessora_local": "P01",
          "tipo": "FS", "lag_dias": 0}]
    fs = calcular_lob_com_vinculos(a, ["P01"], d)
    ti = calcular_lob_com_vinculos(a, ["P01"], [{**d[0], "tipo": "TI"}])
    assert fs["tarefas"] == ti["tarefas"]
    assert fs["duracao_total_dias"] == ti["duracao_total_dias"] == 5
    assert fs["persistido"] is False


def test_101_locais_rejeitados_sem_escrita():
    a, locais, d = fixture(qtd_servicos=1, qtd_locais=101)
    with pytest.raises(ValueError, match="1 a 100 locais"):
        calcular_lob_com_vinculos(a, locais, d)


def test_lob_simples_5000_combinacoes():
    atividades = [
        {"nome": f"Servico {i}", "tempo_unitario": 1, "numero_equipes": 1, "pulmao_dias": 0}
        for i in range(50)
    ]
    locais = [f"L{i:03d}" for i in range(100)]
    r = calcular_linha_balanco(atividades, locais)
    assert r["persistido"] is False
    assert len(r["atividades"]) == 50
    assert sum(len(x["unidades"]) for x in r["atividades"]) == 5000
