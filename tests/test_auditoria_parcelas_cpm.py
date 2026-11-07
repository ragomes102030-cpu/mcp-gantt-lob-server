"""Regressao: Escola e Aurora (apenas fixtures anonimas, sem acesso ao banco)."""
from mcp_gantt_lob.models.auditoria_parcelas import auditar_parcelas_lob_cpm


def test_escola_detecta_parcela_no_dia_zero_e_local_didatico():
    r = auditar_parcelas_lob_cpm(
        [{"id": "1029", "inicio_cpm": "2027-03-01", "fim_cpm": "2027-03-19"}],
        [{"id": "52", "nome": "Terreo Bloco A (didatico)", "didatico": True}],
        [{"activity_id": "1029", "location_id": "52",
          "start_date": "2026-10-29", "finish_date": "2026-11-12"}],
    )
    assert not r["valido"]
    assert {"ANTES_DO_CPM", "LOCAL_DIDATICO"} <= {a["codigo"] for a in r["achados"]}
    assert r["persistido"] is False


def test_cadencia_igual_e_alerta_nao_falsifica_dependencias():
    r = auditar_parcelas_lob_cpm(
        [{"id": "a", "inicio_cpm": "2026-11-02", "fim_cpm": "2026-11-10"}],
        [{"id": "P1", "nome": "Pav 1"}, {"id": "P2", "nome": "Pav 2"}],
        [{"activity_id": "a", "location_id": "P1", "start_date": "2026-11-03", "finish_date": "2026-11-06"},
         {"activity_id": "a", "location_id": "P2", "start_date": "2026-11-03", "finish_date": "2026-11-06"}],
    )
    assert r["valido"] is True
    assert r["alertas"][0]["codigo"] == "REVISAR_CADENCIA"


def test_detecta_referencia_orfa_e_fim_posterior():
    r = auditar_parcelas_lob_cpm(
        [{"id": 1, "inicio_cpm": "2026-11-02", "fim_cpm": "2026-11-10"}],
        [{"id": 2, "nome": "P01"}],
        [{"activity_id": 1, "location_id": 2, "start_date": "2026-11-03", "finish_date": "2026-11-13"},
         {"activity_id": 404, "location_id": 2, "start_date": "2026-11-03", "finish_date": "2026-11-04"}],
    )
    assert {"DEPOIS_DO_CPM", "ATIVIDADE_ORFA"} <= {a["codigo"] for a in r["achados"]}


def test_regressao_escola_30_atividades_90_parcelas():
    # Fixture de contagem baseada na auditoria real: 3 atividades com ES=0,
    # 27 atividades posteriores, cada uma alocada nos 3 locais didaticos.
    # Datas oficiais neste teste sao artificiais: NAO substituem o calendario da obra.
    acts = [{"id": i, "inicio_cpm": "2026-10-29" if i < 3 else "2026-11-03",
             "fim_cpm": "2026-12-31"} for i in range(30)]
    units = [{"id": u, "nome": f"Setor {u} (didatico)", "didatico": True}
             for u in (52, 53, 54)]
    parcels = [{"activity_id": i, "location_id": u,
                "start_date": "2026-10-29", "finish_date": "2026-11-02"}
               for i in range(30) for u in (52, 53, 54)]
    r = auditar_parcelas_lob_cpm(acts, units, parcels)
    assert r["total_parcelas"] == 90
    assert sum(x["codigo"] == "ANTES_DO_CPM" for x in r["achados"]) == 81
    assert sum(x["codigo"] == "LOCAL_DIDATICO" for x in r["achados"]) == 90
    assert len(r["alertas"]) == 30
    assert r["valido"] is False
    assert r["persistido"] is False
