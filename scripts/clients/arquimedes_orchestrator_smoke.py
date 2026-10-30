"""P4 integration gateway: real public MCP calls only; fail-closed on outage.

Default case is a tiny fictitious two-pavement project. Optional JSON
filename accepts a caller-provided, already-authorized payload. No writes.
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mcp import Client
from mcp_gantt_lob.arquimedes_orchestrator import executar_fluxo

URLS = {
    "eap":os.getenv("EAP_PUBLIC_MCP_URL","https://arquimedes-mcp-eap.vercel.app/public-mcp"),
    "cronograma":os.getenv("CRONOGRAMA_PUBLIC_MCP_URL","https://arquimedes-mcp-cronograma.vercel.app/public-mcp"),
    "lob":os.getenv("GANTT_LOB_PUBLIC_MCP_URL","https://arquimedes-mcp-gantt-lob.vercel.app/public-mcp"),
}


def fixture():
    return {
        "project_id":"FICTICIO-P4","schema_version":"1.0",
        "eap_nodes":[
            {"eap_id":"1","eap_uid":"UID-RAIZ","nivel":1,"parent_id":None},
            {"eap_id":"1.1","eap_uid":"UID-F01","nivel":2,"parent_id":"1"},
            {"eap_id":"1.2","eap_uid":"UID-A01","nivel":2,"parent_id":"1"}],
        "locais":["P01","P02"],
        "atividades":[
            {"activity_id":"F01","eap_uid":"UID-F01","nome":"Estrutura","quantidade":20,
             "produtividade":10,"unidade":"m2","unidade_produtividade":"m2",
             "fonte":"parametro ficticio","responsavel":"Equipe A",
             "criterio_aceite":"inspecao ficticia"},
            {"activity_id":"A01","eap_uid":"UID-A01","nome":"Alvenaria","quantidade":30,
             "produtividade":10,"unidade":"m2","unidade_produtividade":"m2",
             "fonte":"parametro ficticio","responsavel":"Equipe B",
             "criterio_aceite":"inspecao ficticia"}],
        "dependencias":[
            {"predecessora_id":"F01","predecessora_local":"P01",
             "sucessora_id":"A01","sucessora_local":"P01","tipo":"TI"},
            {"predecessora_id":"F01","predecessora_local":"P02",
             "sucessora_id":"A01","sucessora_local":"P02","tipo":"TI"}],
        "data_inicio":"2026-11-02",
        "calendario":{"modo":"uteis","calendar_id":"FICTICIO-5D",
                      "dias_semana":[0,1,2,3,4],"feriados":["2026-11-03"]},
    }


def decode(response):
    if response.is_error:
        raise RuntimeError("MCP retornou erro")
    if response.structured_content is not None:
        obj=response.structured_content
    else:
        obj=next((json.loads(x.text) for x in response.content if x.type=="text"),None)
    if not isinstance(obj,dict):
        raise RuntimeError("MCP sem resultado estruturado")
    return obj.get("result",obj)


async def main():
    pedido=fixture()
    if "--json" in sys.argv:
        idx=sys.argv.index("--json")+1
        if idx>=len(sys.argv):
            raise ValueError("--json exige arquivo de entrada")
        with open(sys.argv[idx],encoding="utf-8") as stream:
            pedido=json.load(stream)
    async def call(motor, nome, args):
        if "--simulate-unavailable" in sys.argv and motor=="cronograma":
            raise ConnectionError("indisponibilidade simulada do MCP Cronograma")
        async with Client(URLS[motor],mode="auto") as client:
            return decode(await asyncio.wait_for(client.call_tool(nome,args),timeout=15))
    result=await asyncio.wait_for(executar_fluxo(pedido,call),timeout=120)
    summary={"status":"PASSOU","project_id":result["project_id"],
             "total_tarefas":result["total_tarefas"],
             "duracao_cpm":result["cpm"]["duracao_projeto_dias"],
             "duracao_lob":result["lob"]["duracao_total_dias"],
             "calendar_id":result["calendar_id"],
             "uids":[r["eap_uid"] for r in result["mapa_tarefas"].values()],
             "divergencias":result["divergencias"],"persistido":result["persistido"]}
    if "--json" not in sys.argv:
        assert summary["duracao_cpm"]==8 and summary["duracao_lob"]==8
        assert summary["total_tarefas"]==4 and len(summary["uids"])==4
    return summary


if __name__=="__main__":
    try:
        result=asyncio.run(main())
        print(json.dumps(result,ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"status":"BLOQUEADO","error_type":type(exc).__name__,
            "reason":str(exc)[:250],"no_fabricated_results":True},ensure_ascii=False))
        raise SystemExit(2)
