"""Integridade de ritmo e identificadores de locais repetitivos."""
import pytest
from public_mcp import calcular_linha_balanco, _validar_atividades


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_nao_aceita_duracao_nao_positiva_ou_nao_finita(value):
    with pytest.raises(ValueError, match="tempo_unitario"):
        _validar_atividades([{"nome": "Alvenaria", "tempo_unitario": value}])


def test_rejeita_locais_repetidos_apos_normalizacao():
    with pytest.raises(ValueError, match="Unidades repetidas"):
        calcular_linha_balanco(
            [{"nome": "Alvenaria", "tempo_unitario": 4}],
            ["Pavimento 1", " pavimento 1 "],
        )


def test_preserva_escadinha_com_locais_unicos():
    r = calcular_linha_balanco(
        [{"nome": "Estrutura", "tempo_unitario": 4},
         {"nome": "Alvenaria", "tempo_unitario": 6}],
        ["Pavimento 1 ", " Pavimento 2"],
        "2026-11-02",
    )
    por_nome = {a["nome"]: a for a in r["atividades"]}
    assert [x["unidade"] for x in por_nome["Estrutura"]["unidades"]] == [
        "Pavimento 1", "Pavimento 2"]
    assert [x["inicio_dia"] for x in por_nome["Alvenaria"]["unidades"]] == [4, 10]
    assert r["duracao_total_dias"] == 16
    assert r["persistido"] is False
