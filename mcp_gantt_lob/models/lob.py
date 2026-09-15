"""Linha de Balanço (LOB) — Cap. 20 do livro de Aldo Dórea Mattos
("Planejamento e Controle de Obras").

Modelo: uma atividade se repete numa sequência ORDENADA de "unidades de
repetição" (andar, casa, trecho de rodovia...). Cada atividade tem um
"tempo de ritmo" (tr) — quanto tempo leva pra executar UMA unidade — que
pode vir direto ou ser derivado de `tempo_unitario / numero_equipes`
(mais equipes trabalhando a mesma unidade em paralelo reduzem o tr; é a
simplificação padrão do método, documentada no Cap. 20.4 "Balanceamento
das operações").

Regra de traçado (Fig. 20.17 do livro): pra cada unidade `n` de uma
atividade que depende de outra (mesma unidade) e da unidade anterior da
MESMA atividade (mesma equipe não pode estar em dois lugares):

    inicio(atividade, n) = max(
        fim(predecessora, n) + pulmão,     # a unidade already ficou pronta
        fim(atividade, n-1),               # a equipe está livre
    )
    fim(atividade, n) = inicio(atividade, n) + tr(atividade)

Quando quem manda no `max` é sempre a predecessora (não a própria
atividade), a equipe fica esperando — ritmo desbalanceado, risco de
interferência. É exatamente o alerta que a seção 20.4 do livro descreve:
sinal de que vale balancear (mudar nº de equipes) ou dimensionar de novo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any


@dataclass
class AtividadeLOB:
    """Uma atividade que se repete por todas as unidades, na ordem dada."""

    nome: str
    tempo_unitario: float  # dias para 1 equipe completar 1 unidade
    numero_equipes: int = 1
    pulmao_dias: float = 0.0  # espera mínima extra além da predecessora (buffer)

    def __post_init__(self) -> None:
        if self.tempo_unitario <= 0:
            raise ValueError(f"'{self.nome}': tempo_unitario deve ser > 0.")
        if self.numero_equipes <= 0:
            raise ValueError(f"'{self.nome}': numero_equipes deve ser >= 1.")
        if self.pulmao_dias < 0:
            raise ValueError(f"'{self.nome}': pulmao_dias não pode ser negativo.")

    @property
    def ritmo(self) -> float:
        """Tempo de ritmo (tr): dias para executar 1 unidade, já considerando
        o nº de equipes trabalhando em paralelo na mesma unidade."""
        return self.tempo_unitario / self.numero_equipes


@dataclass
class ResultadoUnidade:
    unidade: str
    inicio_dia: float  # dias corridos desde o marco zero (0 = data_inicio)
    fim_dia: float
    limitado_por_predecessora: bool  # True = a equipe esperou a atividade anterior
    espera_dias: float  # quanto a equipe ficou parada esperando (0 se não esperou)


@dataclass
class ResultadoAtividadeLOB:
    nome: str
    ritmo: float
    resultados: list[ResultadoUnidade] = field(default_factory=list)

    @property
    def espera_total_dias(self) -> float:
        return round(sum(r.espera_dias for r in self.resultados), 6)

    @property
    def risco_interferencia(self) -> bool:
        """True se a equipe ficou parada esperando a predecessora em
        ALGUMA unidade — sinal de ritmo mais rápido que a atividade
        anterior, desperdiçando produtividade da equipe (Cap. 20.4)."""
        return self.espera_total_dias > 1e-9


def calcular_linha_balanco(
    atividades: list[AtividadeLOB],
    unidades: list[str],
    data_inicio: date | None = None,
) -> dict[str, Any]:
    """Calcula início/fim de cada atividade em cada unidade de repetição.

    ``atividades`` deve estar na ORDEM de execução (a atividade [i] é
    predecessora da [i+1] na mesma unidade — sequência construtiva real,
    ex.: Fundação -> Alvenaria -> Cobertura). ``unidades`` é a lista
    ordenada de unidades de repetição (ex.: ["Casa 1", "Casa 2", "Casa 3"]
    ou ["Pav. 1", ..., "Pav. 10"]).

    Retorna, por atividade: ritmo, resultado por unidade (início/fim em
    dias e em data real se ``data_inicio`` for informado), espera total
    (dias que a equipe ficou parada esperando a predecessora) e
    ``risco_interferencia`` (True = ritmo mais rápido que a predecessora
    em algum ponto — vale balancear).
    """
    if not atividades:
        raise ValueError("Lista de atividades vazia — nada para calcular.")
    if not unidades:
        raise ValueError("Lista de unidades de repetição vazia — nada para calcular.")
    if len(set(unidades)) != len(unidades):
        raise ValueError("Unidades de repetição repetidas na lista — cada uma deve ser única.")

    resultados: dict[str, ResultadoAtividadeLOB] = {
        a.nome: ResultadoAtividadeLOB(nome=a.nome, ritmo=a.ritmo) for a in atividades
    }

    fim_anterior_mesma_atividade: dict[str, float] = {}  # nome -> fim(atividade, n-1)

    for i, atividade in enumerate(atividades):
        tr = atividade.ritmo
        for n, unidade in enumerate(unidades):
            fim_predecessora = None
            if i > 0:
                predecessora = atividades[i - 1]
                fim_predecessora = resultados[predecessora.nome].resultados[n].fim_dia

            candidato_predecessora = (
                fim_predecessora + atividade.pulmao_dias if fim_predecessora is not None else 0.0
            )
            candidato_propria_equipe = fim_anterior_mesma_atividade.get(atividade.nome, 0.0)

            inicio = max(candidato_predecessora, candidato_propria_equipe)
            fim = inicio + tr

            limitado_por_predecessora = (
                fim_predecessora is not None and candidato_predecessora >= candidato_propria_equipe
                and candidato_predecessora > 0.0
            )
            # Espera só é medida a partir da 2a unidade (n >= 1): na 1a
            # unidade de qualquer atividade não existe "a equipe já estava
            # livre antes" pra comparar contra — contar isso como espera
            # dispararia risco_interferencia falso-positivo pra toda
            # atividade que tem predecessora, mesmo com ritmos compatíveis.
            espera = (
                max(0.0, candidato_predecessora - candidato_propria_equipe)
                if (fim_predecessora is not None and n > 0)
                else 0.0
            )

            resultados[atividade.nome].resultados.append(
                ResultadoUnidade(
                    unidade=unidade, inicio_dia=round(inicio, 6), fim_dia=round(fim, 6),
                    limitado_por_predecessora=limitado_por_predecessora,
                    espera_dias=round(espera, 6),
                )
            )
            fim_anterior_mesma_atividade[atividade.nome] = fim

    duracao_total_dias = max(
        r.fim_dia for res in resultados.values() for r in res.resultados
    )

    saida_atividades = []
    for atividade in atividades:
        r = resultados[atividade.nome]
        unidades_saida = []
        for u in r.resultados:
            item: dict[str, Any] = {
                "unidade": u.unidade, "inicio_dia": u.inicio_dia, "fim_dia": u.fim_dia,
                "limitado_por_predecessora": u.limitado_por_predecessora,
                "espera_dias": u.espera_dias,
            }
            if data_inicio is not None:
                item["data_inicio"] = (data_inicio + timedelta(days=u.inicio_dia)).isoformat()
                item["data_fim"] = (data_inicio + timedelta(days=u.fim_dia)).isoformat()
            unidades_saida.append(item)
        saida_atividades.append({
            "nome": atividade.nome,
            "ritmo_dias_por_unidade": round(atividade.ritmo, 6),
            "numero_equipes": atividade.numero_equipes,
            "espera_total_dias": r.espera_total_dias,
            "risco_interferencia": r.risco_interferencia,
            "unidades": unidades_saida,
        })

    return {
        "duracao_total_dias": round(duracao_total_dias, 6),
        "total_unidades": len(unidades),
        "atividades": saida_atividades,
    }


def dimensionar_equipes(tempo_unitario: float, ritmo_desejado: float) -> int:
    """Cap. 20.5 (Dimensionamento): quantas equipes uma atividade precisa
    pra atingir um ritmo desejado (dias por unidade), dado o tempo que 1
    equipe leva pra fazer 1 unidade sozinha.

    ``numero_equipes = ceil(tempo_unitario / ritmo_desejado)`` — arredonda
    pra cima porque equipe é indivisível (não dá pra ter 1,3 equipe).
    """
    if tempo_unitario <= 0:
        raise ValueError("tempo_unitario deve ser > 0.")
    if ritmo_desejado <= 0:
        raise ValueError("ritmo_desejado deve ser > 0.")
    return math.ceil(tempo_unitario / ritmo_desejado)


def balancear_ritmos(atividades: list[AtividadeLOB]) -> dict[str, Any]:
    """Cap. 20.4 (Balanceamento das operações): compara o ritmo de cada
    atividade com o da atividade imediatamente anterior na sequência e
    sugere como igualar os ritmos — evitando tanto uma equipe rápida
    parada esperando a de trás (risco de interferência) quanto uma
    equipe lenta demais que faz a fila atrás dela crescer sem controle.

    Duas direções possíveis pra resolver quando HÁ risco (sucessora mais
    rápida que a predecessora) — as duas são reportadas juntas; quem
    decide qual aplicar (mudar a equipe da frente ou a de trás) é o
    planejador, não o cálculo:
      - Reduzir a SUCESSORA até ela não ser mais rápida que a predecessora
        (``equipes_sucessora_para_deixar_de_ser_mais_rapida``, pode ser
        ``None`` se nem 1 equipe resolver).
      - Acelerar a PREDECESSORA até ela alcançar o ritmo da sucessora
        (``equipes_predecessora_para_acelerar``).

    Quando NÃO há risco (sucessora igual ou mais lenta — configuração
    segura segundo o método), nenhuma sugestão de equipe é feita — só o
    ritmo atual fica registrado pra referência.

    Sugestão sempre em relação à atividade IMEDIATAMENTE anterior — não
    tenta um ótimo global da rede inteira (otimização mais ampla, fora
    do escopo desta v1).
    """
    sugestoes = []
    for i, atividade in enumerate(atividades):
        sugestao: dict[str, Any] = {
            "nome": atividade.nome,
            "ritmo_atual": round(atividade.ritmo, 6),
            "numero_equipes_atual": atividade.numero_equipes,
        }
        if i > 0:
            predecessora = atividades[i - 1]
            ritmo_predecessora = predecessora.ritmo
            ritmo_sucessora = atividade.ritmo
            risco = ritmo_sucessora < ritmo_predecessora

            sugestao["ritmo_da_predecessora"] = round(ritmo_predecessora, 6)
            sugestao["risco_interferencia"] = risco

            if risco:
                # Duas formas de resolver o risco (reportadas as duas — quem
                # decide qual aplicar é o planejador):
                # 1) Reduzir a equipe da sucessora até ela deixar de ser
                #    mais rápida que a predecessora (só faz sentido se o
                #    resultado for >= 1 equipe — não dá pra ter menos que isso).
                equipes_sucessora_bruto = math.floor(atividade.tempo_unitario / ritmo_predecessora)
                if equipes_sucessora_bruto >= 1:
                    sugestao["equipes_sucessora_para_deixar_de_ser_mais_rapida"] = equipes_sucessora_bruto
                else:
                    sugestao["equipes_sucessora_para_deixar_de_ser_mais_rapida"] = None
                    sugestao["nota_sucessora"] = (
                        "Mesmo com 1 equipe (mínimo) a sucessora já é mais rápida "
                        "que a predecessora — reduzir equipe não resolve; use "
                        "equipes_predecessora_para_acelerar."
                    )
                # 2) Acelerar a predecessora até ela alcançar o ritmo da sucessora.
                sugestao["equipes_predecessora_para_acelerar"] = dimensionar_equipes(
                    predecessora.tempo_unitario, ritmo_sucessora
                )
            # Sem risco (sucessora igual ou mais lenta que a predecessora):
            # já é a configuração segura descrita pelo método — nenhuma
            # mudança de equipe é necessária, só fica registrado o ritmo
            # atual pra referência (acima).
        sugestoes.append(sugestao)
    return {"sugestoes": sugestoes}
