"""Testes de server.py: as tools MCP e o wrapper _seguro. Não testa o
caminho Turso de verdade (mesma ressalva dos outros MCPs — sem
credenciais reais, só o caminho de degradação graciosa é testável aqui)."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _sem_turso(monkeypatch):
    """Garante TURSO_DATABASE_URL ausente — testa o caminho sem persistência
    (degradação graciosa), que é o único testável sem credenciais reais."""
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)


def test_gerar_gantt_sucesso_sem_turso():
    from mcp_gantt_lob import server
    resultado = server.gerar_gantt(
        project_name="Obra Teste",
        atividades=[{
            "nome": "Escavação", "secao": "Fundação",
            "data_inicio": "2026-01-05", "data_fim_planejada": "2026-01-07",
            "progresso": 100, "critico": True,
        }],
    )
    assert "erro" not in resultado
    assert resultado["filename"] == "Obra_Teste_gantt.xlsx"
    assert len(resultado["xlsx_base64"]) > 0


def test_gerar_gantt_erro_vira_dict_com_erro():
    from mcp_gantt_lob import server
    resultado = server.gerar_gantt(project_name="X", atividades=[])
    assert "erro" in resultado
    assert "vazia" in resultado["erro"]


def test_gerar_gantt_atividade_malformada_vira_erro_nao_excecao():
    from mcp_gantt_lob import server
    resultado = server.gerar_gantt(project_name="X", atividades=[{"nome": "Sem os outros campos"}])
    assert "erro" in resultado


def test_listar_exports_sem_turso_vira_dict_com_erro():
    from mcp_gantt_lob import server
    resultado = server.listar_exports()
    assert "erro" in resultado


def test_listar_temas():
    from mcp_gantt_lob import server
    temas = server.listar_temas()
    assert "ocean" in temas
    assert len(temas) == 8


# ── Linha de Balanço ──────────────────────────────────────────────────

def test_calcular_linha_balanco_sucesso():
    from mcp_gantt_lob import server
    r = server.calcular_linha_balanco(
        atividades=[
            {"nome": "Fundação", "tempo_unitario": 3},
            {"nome": "Alvenaria", "tempo_unitario": 5},
        ],
        unidades=["Casa 1", "Casa 2"],
    )
    assert "erro" not in r
    assert r["duracao_total_dias"] == 13.0


def test_calcular_linha_balanco_com_data_inicio():
    from mcp_gantt_lob import server
    r = server.calcular_linha_balanco(
        atividades=[{"nome": "A", "tempo_unitario": 5}],
        unidades=["Casa 1"],
        data_inicio="2026-03-02",
    )
    assert r["atividades"][0]["unidades"][0]["data_inicio"] == "2026-03-02"


def test_calcular_linha_balanco_erro_vira_dict():
    from mcp_gantt_lob import server
    r = server.calcular_linha_balanco(atividades=[], unidades=["Casa 1"])
    assert "erro" in r


def test_calcular_linha_balanco_numero_equipes_e_pulmao():
    from mcp_gantt_lob import server
    r = server.calcular_linha_balanco(
        atividades=[
            {"nome": "A", "tempo_unitario": 12, "numero_equipes": 3},
            {"nome": "B", "tempo_unitario": 4, "pulmao_dias": 1},
        ],
        unidades=["Casa 1"],
    )
    assert r["atividades"][0]["ritmo_dias_por_unidade"] == 4.0  # 12/3


def test_balancear_ritmos_lob_sucesso():
    from mcp_gantt_lob import server
    r = server.balancear_ritmos_lob(atividades=[
        {"nome": "A", "tempo_unitario": 6},
        {"nome": "B", "tempo_unitario": 4},
    ])
    assert r["sugestoes"][1]["risco_interferencia"] is True


def test_balancear_ritmos_lob_erro_vira_dict():
    from mcp_gantt_lob import server
    r = server.balancear_ritmos_lob(atividades=[{"nome": "A", "tempo_unitario": -1}])
    assert "erro" in r


def test_dimensionar_equipes_lob_sucesso():
    from mcp_gantt_lob import server
    r = server.dimensionar_equipes_lob(tempo_unitario=6, ritmo_desejado=4)
    assert r["numero_equipes"] == 2


def test_dimensionar_equipes_lob_erro_vira_dict():
    from mcp_gantt_lob import server
    r = server.dimensionar_equipes_lob(tempo_unitario=0, ritmo_desejado=4)
    assert "erro" in r
