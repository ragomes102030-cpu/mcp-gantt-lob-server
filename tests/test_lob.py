"""Testes de models/lob.py — Linha de Balanço (Cap. 20, Aldo Dórea Mattos).

Os valores esperados nos testes de calcular_linha_balanco foram calculados
à mão antes de escrever o código (ver histórico da conversa/commit) —
qualquer mudança no algoritmo deve continuar batendo com eles, ou
justificar por que os valores esperados mudaram.
"""
from __future__ import annotations

from datetime import date

import pytest

from mcp_gantt_lob.models.lob import (
    AtividadeLOB,
    balancear_ritmos,
    calcular_linha_balanco,
    dimensionar_equipes,
)


# ── AtividadeLOB: validação ─────────────────────────────────────────────

def test_atividade_lob_tempo_unitario_invalido():
    with pytest.raises(ValueError, match="tempo_unitario"):
        AtividadeLOB("A", tempo_unitario=0)
    with pytest.raises(ValueError, match="tempo_unitario"):
        AtividadeLOB("A", tempo_unitario=-1)


def test_atividade_lob_numero_equipes_invalido():
    with pytest.raises(ValueError, match="numero_equipes"):
        AtividadeLOB("A", tempo_unitario=5, numero_equipes=0)


def test_atividade_lob_pulmao_negativo_invalido():
    with pytest.raises(ValueError, match="pulmao_dias"):
        AtividadeLOB("A", tempo_unitario=5, pulmao_dias=-1)


def test_ritmo_considera_numero_de_equipes():
    a = AtividadeLOB("A", tempo_unitario=12, numero_equipes=3)
    assert a.ritmo == 4.0


# ── calcular_linha_balanco: casos base ──────────────────────────────────

def test_lista_vazia_falha():
    with pytest.raises(ValueError, match="[Aa]tividades vazia"):
        calcular_linha_balanco([], ["Casa 1"])
    with pytest.raises(ValueError, match="[Uu]nidades .* vazia"):
        calcular_linha_balanco([AtividadeLOB("A", tempo_unitario=1)], [])


def test_unidades_duplicadas_falha():
    with pytest.raises(ValueError, match="repetidas"):
        calcular_linha_balanco(
            [AtividadeLOB("A", tempo_unitario=1)], ["Casa 1", "Casa 1"]
        )


def test_sucessora_mais_lenta_sem_risco():
    """A(tr=4) -> B(tr=6): B nunca alcança A, sem interferência."""
    r = calcular_linha_balanco(
        [AtividadeLOB("A", tempo_unitario=4), AtividadeLOB("B", tempo_unitario=6)],
        unidades=["Casa 1", "Casa 2", "Casa 3"],
    )
    por_nome = {a["nome"]: a for a in r["atividades"]}

    a_unid = por_nome["A"]["unidades"]
    assert [u["inicio_dia"] for u in a_unid] == [0.0, 4.0, 8.0]
    assert [u["fim_dia"] for u in a_unid] == [4.0, 8.0, 12.0]

    b_unid = por_nome["B"]["unidades"]
    assert [u["inicio_dia"] for u in b_unid] == [4.0, 10.0, 16.0]
    assert [u["fim_dia"] for u in b_unid] == [10.0, 16.0, 22.0]

    assert por_nome["B"]["espera_total_dias"] == 0.0
    assert por_nome["B"]["risco_interferencia"] is False
    assert r["duracao_total_dias"] == 22.0


def test_sucessora_mais_rapida_gera_espera_e_risco():
    """A(tr=6) -> B(tr=4): B alcança A e fica esperando (risco)."""
    r = calcular_linha_balanco(
        [AtividadeLOB("A", tempo_unitario=6), AtividadeLOB("B", tempo_unitario=4)],
        unidades=["Casa 1", "Casa 2", "Casa 3"],
    )
    por_nome = {a["nome"]: a for a in r["atividades"]}

    a_unid = por_nome["A"]["unidades"]
    assert [u["fim_dia"] for u in a_unid] == [6.0, 12.0, 18.0]

    b_unid = por_nome["B"]["unidades"]
    assert [u["inicio_dia"] for u in b_unid] == [6.0, 12.0, 18.0]
    assert [u["fim_dia"] for u in b_unid] == [10.0, 16.0, 22.0]
    assert [u["espera_dias"] for u in b_unid] == [0.0, 2.0, 2.0]

    assert por_nome["B"]["espera_total_dias"] == 4.0
    assert por_nome["B"]["risco_interferencia"] is True
    assert por_nome["A"]["risco_interferencia"] is False  # A não tem predecessora


def test_primeira_unidade_nunca_conta_como_espera():
    """Regressão: a 1a unidade de qualquer atividade com predecessora não
    pode contar como 'espera' — não existe estado anterior pra comparar."""
    r = calcular_linha_balanco(
        [AtividadeLOB("A", tempo_unitario=100), AtividadeLOB("B", tempo_unitario=1)],
        unidades=["Casa 1"],  # só 1 unidade — sem 2a unidade não há como comparar ritmo de verdade
    )
    por_nome = {a["nome"]: a for a in r["atividades"]}
    assert por_nome["B"]["unidades"][0]["espera_dias"] == 0.0
    assert por_nome["B"]["espera_total_dias"] == 0.0


def test_pulmao_desloca_inicio_da_sucessora():
    r = calcular_linha_balanco(
        [AtividadeLOB("A", tempo_unitario=4),
         AtividadeLOB("B", tempo_unitario=4, pulmao_dias=2)],
        unidades=["Casa 1", "Casa 2"],
    )
    por_nome = {a["nome"]: a for a in r["atividades"]}
    # sem pulmão, B começaria em 4 (fim de A); com pulmão de 2, começa em 6.
    assert por_nome["B"]["unidades"][0]["inicio_dia"] == 6.0


def test_com_data_inicio_gera_datas_reais():
    r = calcular_linha_balanco(
        [AtividadeLOB("A", tempo_unitario=5)],
        unidades=["Casa 1"],
        data_inicio=date(2026, 3, 2),
    )
    u = r["atividades"][0]["unidades"][0]
    assert u["data_inicio"] == "2026-03-02"
    assert u["data_fim"] == "2026-03-07"


def test_tres_atividades_em_sequencia_valores_exatos():
    r = calcular_linha_balanco(
        [
            AtividadeLOB("Fundação", tempo_unitario=3),
            AtividadeLOB("Alvenaria", tempo_unitario=5),
            AtividadeLOB("Cobertura", tempo_unitario=2),
        ],
        unidades=["Casa 1", "Casa 2"],
    )
    por_nome = {a["nome"]: a for a in r["atividades"]}
    alvenaria = por_nome["Alvenaria"]["unidades"]
    assert alvenaria[0]["inicio_dia"] == 3.0 and alvenaria[0]["fim_dia"] == 8.0
    assert alvenaria[1]["inicio_dia"] == 8.0 and alvenaria[1]["fim_dia"] == 13.0

    cobertura = por_nome["Cobertura"]["unidades"]
    assert cobertura[0]["inicio_dia"] == 8.0 and cobertura[0]["fim_dia"] == 10.0
    assert cobertura[1]["inicio_dia"] == 13.0 and cobertura[1]["fim_dia"] == 15.0
    assert r["duracao_total_dias"] == 15.0


# ── dimensionar_equipes ──────────────────────────────────────────────────

def test_dimensionar_equipes_arredonda_pra_cima():
    assert dimensionar_equipes(6, 4) == 2  # ceil(1.5)
    assert dimensionar_equipes(6, 3) == 2  # ceil(2.0)
    assert dimensionar_equipes(6, 2) == 3  # ceil(3.0)


def test_dimensionar_equipes_validacao():
    with pytest.raises(ValueError):
        dimensionar_equipes(0, 5)
    with pytest.raises(ValueError):
        dimensionar_equipes(5, 0)


# ── balancear_ritmos ─────────────────────────────────────────────────────

def test_balancear_sem_risco_nao_sugere_equipe():
    r = balancear_ritmos([AtividadeLOB("A", tempo_unitario=4), AtividadeLOB("B", tempo_unitario=9)])
    sugestao_b = r["sugestoes"][1]
    assert sugestao_b["risco_interferencia"] is False
    assert "equipes_predecessora_para_acelerar" not in sugestao_b


def test_balancear_com_risco_sugere_as_duas_direcoes():
    r = balancear_ritmos([
        AtividadeLOB("A", tempo_unitario=3),
        AtividadeLOB("B", tempo_unitario=10, numero_equipes=4),
    ])
    sugestao_b = r["sugestoes"][1]
    assert sugestao_b["risco_interferencia"] is True
    assert sugestao_b["equipes_sucessora_para_deixar_de_ser_mais_rapida"] == 3
    assert sugestao_b["equipes_predecessora_para_acelerar"] == 2


def test_balancear_risco_extremo_sucessora_nao_pode_desacelerar():
    r = balancear_ritmos([AtividadeLOB("A", tempo_unitario=20), AtividadeLOB("B", tempo_unitario=2)])
    sugestao_b = r["sugestoes"][1]
    assert sugestao_b["equipes_sucessora_para_deixar_de_ser_mais_rapida"] is None
    assert "nota_sucessora" in sugestao_b
    assert sugestao_b["equipes_predecessora_para_acelerar"] == 10


def test_balancear_primeira_atividade_sem_sugestao():
    r = balancear_ritmos([AtividadeLOB("A", tempo_unitario=5)])
    assert "risco_interferencia" not in r["sugestoes"][0]
