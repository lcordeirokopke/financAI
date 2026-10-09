"""E1: chunking por seção lógica, não por tamanho fixo.

- Ata do Copom: um chunk por parágrafo numerado, com a seção (A, B, C, D) em `secao`. Os
  parágrafos são numerados em sequência no documento inteiro; só a sequência 1, 2, 3... conta.
- Release da B3: um chunk por seção nomeada (título em maiúsculas, sem dígitos).
- Fato relevante da CVM: sem seções nomeadas, um chunk com o documento todo.

O texto antes da primeira fronteira vira o primeiro chunk, com `secao` vazia. Os chunks cobrem o
texto inteiro, sem sobreposição, e uma tabela nunca é cortada: só se corta em fronteira de seção.
"""

import re
from dataclasses import dataclass

from sunontent.schemas import Chunk, Pagina, TipoDocumento, trecho_das_paginas

_SECAO_COPOM = re.compile(r"^[A-Z]\)\s+\S")
_PARAGRAFO_COPOM = re.compile(r"^(\d{1,3})\.\s+[A-ZÀ-Ý]")
_TITULO_B3 = re.compile(r"^[A-ZÀ-Ý][A-ZÀ-Ý ,.()/&-]{7,}$")


@dataclass
class _Linha:
    texto: str
    pagina: int
    offset: int  # offset do início da linha no texto limpo da página

    @property
    def fim(self) -> int:
        return self.offset + len(self.texto)


def _linhas(paginas: list[Pagina]) -> list[_Linha]:
    linhas = []
    for pagina in paginas:
        offset = 0
        for texto in pagina.texto_limpo.split("\n"):
            if texto:
                linhas.append(_Linha(texto, pagina.pagina, offset))
            offset += len(texto) + 1
    return linhas


def _fronteiras_copom(linhas: list[_Linha]) -> list[tuple[int, str | None]]:
    """(índice da linha onde o chunk começa, seção do chunk)."""
    fronteiras: list[tuple[int, str | None]] = []
    secao: str | None = None
    proximo = 1
    for i, linha in enumerate(linhas):
        if _SECAO_COPOM.match(linha.texto):
            secao = linha.texto
            fronteiras.append((i, secao))
            continue
        achado = _PARAGRAFO_COPOM.match(linha.texto)
        if achado and int(achado.group(1)) == proximo:
            proximo += 1
            if fronteiras and fronteiras[-1][0] == i - 1 and fronteiras[-1][1] == secao:
                continue  # o título da seção e o primeiro parágrafo formam um chunk só
            fronteiras.append((i, secao))
    return fronteiras


def _fronteiras_b3(linhas: list[_Linha]) -> list[tuple[int, str | None]]:
    fronteiras: list[tuple[int, str | None]] = []
    for i, linha in enumerate(linhas):
        if _TITULO_B3.match(linha.texto):
            if fronteiras and fronteiras[-1][0] == i - 1:
                continue  # títulos seguidos formam um só
            fronteiras.append((i, linha.texto))
    return fronteiras


_DETECTORES = {
    "copom_ata": _fronteiras_copom,
    "b3_release": _fronteiras_b3,
    "cvm_fato_relevante": lambda linhas: [],
}


def fatiar(paginas: list[Pagina], tipo: TipoDocumento) -> list[Chunk]:
    linhas = _linhas(paginas)
    if not linhas:
        return []
    fronteiras = _DETECTORES[tipo](linhas)
    if not fronteiras or fronteiras[0][0] != 0:
        fronteiras.insert(0, (0, None))
    limites = [indice for indice, _ in fronteiras] + [len(linhas)]
    chunks = []
    for n, (indice, secao) in enumerate(fronteiras, start=1):
        primeira, ultima = linhas[indice], linhas[limites[n] - 1]
        texto = trecho_das_paginas(paginas, primeira.pagina, primeira.offset, ultima.pagina, ultima.fim)
        chunks.append(
            Chunk(
                chunk_id=f"K{n:02d}",
                secao=secao,
                pagina_inicio=primeira.pagina,
                offset_inicio=primeira.offset,
                pagina_fim=ultima.pagina,
                offset_fim=ultima.fim,
                texto=texto,
            )
        )
    return chunks
