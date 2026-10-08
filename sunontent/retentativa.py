"""Classes de falha e retentativa com backoff exponencial.

Usado por ingestao/ (download das fontes) e por persistencia.py (Supabase).
Classes de falha: docs/fluxos/ingestao.md, Classificação de erros.
"""

import random
import sys
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

TENTATIVAS = 4
ESPERA_BASE_S = 1.0

# Trocado por uma função vazia nos testes, para não dormir.
_dormir = time.sleep


class Falha(Exception):
    """Falha do run inteiro. `classe` segue o enum classe_falha do banco."""

    classe: str = "terminal"

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


class FalhaRetriavel(Falha):
    classe = "retriavel"


class FalhaTerminal(Falha):
    classe = "terminal"


def espera(tentativa: int, base: float = ESPERA_BASE_S) -> float:
    """Espera antes da tentativa seguinte: base * 2^(tentativa-1), com jitter de até 25%."""
    atraso = base * 2 ** (tentativa - 1)
    return atraso + random.uniform(0, atraso * 0.25)


def com_retentativa(
    operacao: Callable[[], T],
    descricao: str,
    tentativas: int = TENTATIVAS,
    antes_de_repetir: Callable[[], T | None] | None = None,
) -> T:
    """Executa `operacao`, repetindo só em FalhaRetriavel.

    `antes_de_repetir`, se informado, roda antes de cada nova tentativa; se devolver
    algo diferente de None, esse valor é o resultado e a operação não é repetida.
    Esgotadas as tentativas, a falha vira terminal.
    """
    for tentativa in range(1, tentativas + 1):
        try:
            return operacao()
        except FalhaRetriavel as falha:
            if tentativa == tentativas:
                raise FalhaTerminal(
                    f"{descricao}: {tentativas} tentativas esgotadas. Última falha: {falha.mensagem}"
                ) from falha
            atraso = espera(tentativa)
            print(
                f"{descricao}: tentativa {tentativa} de {tentativas} falhou ({falha.mensagem});"
                f" nova tentativa em {atraso:.0f}s",
                file=sys.stderr,
                flush=True,
            )
            _dormir(atraso)
            if antes_de_repetir is not None:
                ja_feito = antes_de_repetir()
                if ja_feito is not None:
                    return ja_feito
    raise AssertionError("inalcançável")
