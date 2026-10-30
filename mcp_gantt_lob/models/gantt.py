"""
mcp_gantt_lob/models/gantt.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Converte atividades (formato vindo do mcp-cronograma-server) em um
arquivo .xlsx de Gantt profissional, usando a lib xlsx-gantt + pós-
processamento openpyxl (agrupamento colapsável de seções).

Regras de cor por status (validadas em teste manual antes de virar MCP):
    - verde   (70AD47): concluída (progresso == 100) sem atraso
    - azul    (4472C4): planejada, dentro do prazo (padrão do tema)
    - amarelo (FFC000): em risco (perto do prazo, progresso abaixo do
                         esperado, mas ainda não passou da data fim)
    - vermelho(C00000): atrasada (passou da data fim planejada e não
                         concluída) — vira um segundo DateRange (trecho
                         de atraso) somado ao trecho planejado.

Marco (milestone): quando data_inicio == data_fim na atividade de entrada.
"""
from __future__ import annotations

import base64
import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from xlsx_gantt import DateRange, GanttChart, GanttStyle, GanttTheme, Section, Task

COR_CONCLUIDA = "70AD47"
COR_EM_RISCO = "FFC000"
COR_ATRASADA = "C00000"


@dataclass
class AtividadeInput:
    """Formato de entrada esperado por atividade (vindo do orquestrador)."""

    nome: str
    secao: str
    data_inicio: date
    data_fim_planejada: date
    progresso: float  # 0-100
    data_fim_prevista_real: date | None = None  # se None, assume sem atraso
    critico: bool = False  # folga zero no CPM
    hoje: date | None = None  # data de referência p/ calcular status; default = hoje real
    activity_id: str | None = None  # stable, optional; legacy clients remain valid
    eap_uid: str | None = None
    location_id: str | None = None
    baseline_id: str | None = None


def _status_ranges(a: AtividadeInput, cor_planejado: str) -> list[DateRange]:
    """Decide as barras (planejada / atraso / concluída) de uma atividade."""
    hoje = a.hoje or date.today()

    # Marco: início == fim
    if a.data_inicio == a.data_fim_planejada:
        cor = COR_CONCLUIDA if a.progresso >= 100 else cor_planejado
        return [DateRange(start=_dt(a.data_inicio), end=_dt(a.data_fim_planejada), color=cor)]

    # Concluída no prazo ou antes
    if a.progresso >= 100:
        fim_real = a.data_fim_prevista_real or a.data_fim_planejada
        cor = COR_CONCLUIDA if fim_real <= a.data_fim_planejada else COR_ATRASADA
        return [DateRange(start=_dt(a.data_inicio), end=_dt(fim_real), color=cor)]

    # Ainda não concluída: planejado + (opcional) trecho de atraso
    ranges = [DateRange(start=_dt(a.data_inicio), end=_dt(a.data_fim_planejada), color=cor_planejado)]

    if a.data_fim_prevista_real and a.data_fim_prevista_real > a.data_fim_planejada:
        ranges.append(
            DateRange(
                start=_dt(a.data_fim_planejada),
                end=_dt(a.data_fim_prevista_real),
                color=COR_ATRASADA,
            )
        )
    elif hoje > a.data_fim_planejada:
        # passou do prazo planejado e não foi informada nova previsão -> sinaliza risco/atraso simples
        ranges.append(DateRange(start=_dt(a.data_fim_planejada), end=_dt(hoje), color=COR_ATRASADA))

    return ranges


def _dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)


def gerar_gantt_xlsx(
    project_name: str,
    atividades: list[AtividadeInput],
    tema: str = "ocean",
    cor_marca: str | None = None,
) -> bytes:
    """
    Gera o .xlsx do Gantt a partir de uma lista de atividades já
    calculadas (datas do CPM, progresso realizado).

    Parameters
    ----------
    project_name: nome do projeto/obra (título do gráfico)
    atividades: lista de AtividadeInput
    tema: um dos temas prontos da xlsx-gantt (ocean, slate, forest, amber,
        crimson, midnight, royal_purple, teal). Ignorado se cor_marca for informado.
    cor_marca: hex sem '#' (ex: "1F4E78"). Se informado, gera paleta
        automática a partir dessa cor em vez de usar `tema`.

    Returns
    -------
    bytes do arquivo .xlsx pronto (já com agrupamento colapsável por seção).
    """
    if not atividades:
        raise ValueError("Lista de atividades vazia — nada para gerar.")
    for a in atividades:
        try:
            progresso = float(a.progresso)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{a.nome}: progresso invalido") from exc
        if not math.isfinite(progresso) or not 0 <= progresso <= 100:
            raise ValueError(f"{a.nome}: progresso deve estar entre 0 e 100, finito.")
        if a.data_fim_planejada < a.data_inicio:
            raise ValueError(f"{a.nome}: data_fim_planejada anterior ao inicio.")
        if a.data_fim_prevista_real is not None and a.data_fim_prevista_real < a.data_inicio:
            raise ValueError(f"{a.nome}: data_fim_prevista_real anterior ao inicio.")

    style: GanttStyle = GanttTheme.from_color(cor_marca) if cor_marca else GanttTheme.get(tema)
    cor_planejado = style.bar_color

    # Agrupa atividades por seção, preservando ordem de entrada. Mantém
    # também a lista de AtividadeInput por seção (mesma ordem dos Task),
    # para o pós-processamento de célula crítica poder achar a linha certa
    # sem re-percorrer a lista original do zero.
    secoes_ordem: list[str] = []
    secoes_map: dict[str, list[Task]] = {}
    secoes_atividades: dict[str, list[AtividadeInput]] = {}

    for a in atividades:
        if a.secao not in secoes_map:
            secoes_map[a.secao] = []
            secoes_atividades[a.secao] = []
            secoes_ordem.append(a.secao)

        task = Task(
            name=a.nome,
            progress=a.progresso,
            ranges=_status_ranges(a, cor_planejado),
        )
        secoes_map[a.secao].append(task)
        secoes_atividades[a.secao].append(a)

    sections = [Section(name=nome, tasks=secoes_map[nome]) for nome in secoes_ordem]

    data_inicio_geral = min(a.data_inicio for a in atividades)
    data_fim_geral = max(
        (a.data_fim_prevista_real or a.data_fim_planejada) for a in atividades
    )

    chart = GanttChart(
        sections=sections,
        start_date=_dt(data_inicio_geral),
        end_date=_dt(data_fim_geral),
        project_name=project_name,
        style=style,
    )

    xlsx_bytes = chart.generate_excel_bytes()
    xlsx_bytes = _aplicar_agrupamento(xlsx_bytes, secoes_ordem, secoes_map)
    xlsx_bytes = _marcar_criticas(xlsx_bytes, secoes_ordem, secoes_atividades)
    return _incluir_rastreabilidade(xlsx_bytes, atividades)


def _aplicar_agrupamento(
    xlsx_bytes: bytes, secoes_ordem: list[str], secoes_map: dict[str, list[Task]]
) -> bytes:
    """Pós-processa o .xlsx: marca outlineLevel=1 nas linhas de tarefa de
    cada seção, permitindo expandir/recolher (estilo MS Project)."""
    import io

    import openpyxl

    buf_in = io.BytesIO(xlsx_bytes)
    wb = openpyxl.load_workbook(buf_in)
    ws = wb.active

    # Cabeçalho ocupa as 3 primeiras linhas (título/semana, dias, colunas);
    # dados começam na linha 4.
    linha_atual = 4
    for secao in secoes_ordem:
        n_tarefas = len(secoes_map[secao])
        for _ in range(n_tarefas):
            ws.row_dimensions[linha_atual].outlineLevel = 1
            linha_atual += 1

    ws.sheet_properties.outlinePr.summaryBelow = False

    buf_out = io.BytesIO()
    wb.save(buf_out)
    return buf_out.getvalue()


def _marcar_criticas(
    xlsx_bytes: bytes,
    secoes_ordem: list[str],
    secoes_atividades: dict[str, list["AtividadeInput"]],
) -> bytes:
    """Pós-processa o .xlsx: nome de atividade crítica (folga zero no CPM)
    vira negrito + borda vermelha na célula — sem isso, `critico` era
    recebido pela tool e simplesmente descartado (bug achado em auditoria:
    a informação mais importante do CPM pro leitor do Gantt não aparecia
    em lugar nenhum do arquivo gerado)."""
    import io

    import openpyxl
    from openpyxl.styles import Border, Font, Side

    buf_in = io.BytesIO(xlsx_bytes)
    wb = openpyxl.load_workbook(buf_in)
    ws = wb.active

    borda_vermelha = Border(
        left=Side(style="thin", color="C00000"), right=Side(style="thin", color="C00000"),
        top=Side(style="thin", color="C00000"), bottom=Side(style="thin", color="C00000"),
    )

    linha_atual = 4  # mesmo offset de cabeçalho usado em _aplicar_agrupamento
    for secao in secoes_ordem:
        for atividade in secoes_atividades[secao]:
            if atividade.critico:
                celula = ws.cell(row=linha_atual, column=2)  # coluna "Task" (nome da atividade)
                celula.font = Font(bold=True, color="C00000")
                celula.border = borda_vermelha
            linha_atual += 1

    buf_out = io.BytesIO()
    wb.save(buf_out)
    return buf_out.getvalue()


def _incluir_rastreabilidade(xlsx_bytes: bytes, atividades: list[AtividadeInput]) -> bytes:
    """Add a neutral, editable data sheet with stable IDs without altering
    the visual Gantt or re-running CPM. Existing positional API is preserved.
    """
    import io
    import openpyxl

    def cell_text(value):
        if value is None:
            return ""
        text = str(value)
        # Prevent untrusted labels/IDs from turning into Excel formulas.
        return "'" + text if text.startswith(("=", "+", "-", "@")) else text

    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.create_sheet("Rastreabilidade")
    ws.append(["activity_id", "eap_uid", "location_id", "baseline_id",
               "nome", "secao", "data_inicio", "data_fim_planejada", "progresso"])
    for a in atividades:
        ws.append([cell_text(a.activity_id), cell_text(a.eap_uid),
                   cell_text(a.location_id), cell_text(a.baseline_id),
                   cell_text(a.nome), cell_text(a.secao),
                   a.data_inicio, a.data_fim_planejada, a.progresso])
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def gerar_gantt_base64(
    project_name: str,
    atividades: list[AtividadeInput],
    tema: str = "ocean",
    cor_marca: str | None = None,
) -> str:
    """Mesma coisa que gerar_gantt_xlsx, mas devolve base64 (formato de
    retorno de tool MCP — não dá pra devolver bytes crus)."""
    xlsx_bytes = gerar_gantt_xlsx(project_name, atividades, tema, cor_marca)
    return base64.b64encode(xlsx_bytes).decode("ascii")


def atividade_from_dict(d: dict[str, Any]) -> AtividadeInput:
    """Constrói AtividadeInput a partir do dict que a tool MCP recebe
    (datas como string ISO 'YYYY-MM-DD').

    Campos obrigatórios: nome, secao, data_inicio, data_fim_planejada.
    """
    CAMPOS_OBRIGATORIOS = ["nome", "secao", "data_inicio", "data_fim_planejada"]
    for campo in CAMPOS_OBRIGATORIOS:
        valor = d.get(campo)
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            raise ValueError(
                f"Atividade em 'atividades' está incompleta: falta o campo "
                f"'{campo}'. Formato esperado: {{nome, secao, data_inicio, "
                f"data_fim_planejada, progresso, data_fim_prevista_real, critico}}"
            )

    def _parse_data(v: str | None) -> date | None:
        return datetime.strptime(v, "%Y-%m-%d").date() if v else None

    try:
        progresso = float(d.get("progresso", 0))
    except (ValueError, TypeError) as exc:
        raise ValueError("progresso invalido") from exc
    if not math.isfinite(progresso) or not 0 <= progresso <= 100:
        raise ValueError("progresso deve estar entre 0 e 100, finito.")
    inicio = _parse_data(d["data_inicio"])
    planejado = _parse_data(d["data_fim_planejada"])
    previsto = _parse_data(d.get("data_fim_prevista_real"))
    if planejado < inicio or (previsto is not None and previsto < inicio):
        raise ValueError("data final anterior a data_inicio")
    return AtividadeInput(
        nome=d["nome"], secao=d["secao"],
        data_inicio=inicio, data_fim_planejada=planejado,
        progresso=progresso, data_fim_prevista_real=previsto,
        critico=bool(d.get("critico", False)),
        activity_id=d.get("activity_id"),
        eap_uid=d.get("eap_uid"),
        location_id=d.get("location_id"),
        baseline_id=d.get("baseline_id"),
    )
