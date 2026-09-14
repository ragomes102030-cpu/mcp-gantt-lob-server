"""Testes de server.py: as tools MCP e o wrapper _seguro. Não testa o
caminho Turso de verdade (mesma ressalva dos outros MCPs — sem
credenciais reais, só o caminho de degradação graciosa é testável aqui)."""
from __future__ import annotations

import os

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
