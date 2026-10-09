"""E1: leitura do PDF. Confere o SHA-256 e devolve as linhas de cada página, com posição.

A camada de texto de PDFs exportados de editores parte números em fragmentos sem caractere de
espaço entre eles (texto justificado, kerning): "R$31" e "5,2" são "R$315,2". O pymupdf, por
padrão, decide onde há espaço pela distância entre os caracteres, o que gera "202 6" e "R $1,3".
Aqui só existe espaço onde o PDF tem um caractere de espaço (TEXT_INHIBIT_SPACES), e os
fragmentos que ficam na mesma linha base, no mesmo bloco, sem espaço na fronteira, são unidos.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from sunontent.retentativa import FalhaTerminal
from sunontent.schemas import DocumentoFonte

FLAGS = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP | pymupdf.TEXT_INHIBIT_SPACES
TOLERANCIA_BASELINE = 0.3  # fração do corpo da fonte


@dataclass
class Linha:
    texto: str
    x0: float
    x1: float
    y0: float
    y1: float
    baseline: float  # linha base do primeiro span
    baseline_fim: float  # linha base do último span
    tamanho: float


@dataclass
class PaginaLida:
    numero: int  # 1-indexado
    altura: float
    linhas: list[Linha]


def ler_documento(documento: DocumentoFonte) -> list[PaginaLida]:
    """Confere o hash dos bytes contra `doc_sha256` e lê as páginas. Erro terminal se algo falhar."""
    caminho = Path(documento.caminho)
    try:
        dados = caminho.read_bytes()
    except OSError as erro:
        raise FalhaTerminal(
            f"E1: não foi possível ler {caminho}: {erro}. O arquivo está ausente; "
            "rode a coleta de novo para gravá-lo."
        ) from erro
    encontrado = hashlib.sha256(dados).hexdigest()
    if encontrado != documento.doc_sha256:
        raise FalhaTerminal(
            f"E1: {caminho} tem SHA-256 {encontrado}, mas o esperado é {documento.doc_sha256}. "
            "Apague o arquivo local; a próxima coleta grava o PDF de novo."
        )
    try:
        pdf = pymupdf.open(stream=dados, filetype="pdf")
    except Exception as erro:  # pymupdf levanta tipos próprios para arquivo corrompido
        raise FalhaTerminal(f"E1: {caminho} não abre como PDF: {erro}") from erro
    with pdf:
        if pdf.needs_pass:
            raise FalhaTerminal(f"E1: {caminho} está protegido por senha")
        paginas = [_ler_pagina(n, pagina) for n, pagina in enumerate(pdf, start=1)]
    sem_texto = [p.numero for p in paginas if not any(l.texto.strip() for l in p.linhas)]
    if sem_texto:
        raise FalhaTerminal(
            f"E1: {caminho} tem páginas sem camada de texto: {sem_texto}. "
            "O OCR ainda não existe, e o run não segue com texto faltando."
        )
    return paginas


def _ler_pagina(numero: int, pagina: pymupdf.Page) -> PaginaLida:
    bruto = []  # (bloco, Linha)
    for bloco in pagina.get_text("dict", flags=FLAGS)["blocks"]:
        if bloco.get("type") != 0:
            continue
        for linha in bloco["lines"]:
            spans = [s for s in linha["spans"] if s["text"]]
            if not spans:
                continue
            texto = "".join(s["text"] for s in spans)
            if not texto.strip():
                continue
            tamanho = max(s["size"] for s in spans)
            x0, y0, x1, y1 = linha["bbox"]
            bruto.append((bloco["number"], Linha(texto, x0, x1, y0, y1, spans[0]["origin"][1], spans[-1]["origin"][1], tamanho)))
    return PaginaLida(numero, pagina.rect.height, _unir_fragmentos(bruto))


def _unir_fragmentos(bruto: list[tuple[int, Linha]]) -> list[Linha]:
    linhas: list[Linha] = []
    bloco_atual = None
    for bloco, linha in bruto:
        if linhas and bloco == bloco_atual:
            anterior = linhas[-1]
            if _mesma_linha_base(anterior, linha) and _sem_espaco_na_fronteira(anterior, linha):
                _anexar(anterior, linha)
                continue
            if _numero_quebrado_na_quebra_de_linha(anterior, linha):
                _anexar(anterior, linha)
                continue
        linhas.append(linha)
        bloco_atual = bloco
    return linhas


def _mesma_linha_base(a: Linha, b: Linha) -> bool:
    return abs(a.baseline_fim - b.baseline) <= TOLERANCIA_BASELINE * min(a.tamanho, b.tamanho) and b.x0 >= a.x1 - 1


def _sem_espaco_na_fronteira(a: Linha, b: Linha) -> bool:
    """Os dois lados da fronteira não têm espaço e juntos formam um mesmo token.

    A distância horizontal não serve de critério: nesses PDFs a posição do texto não acompanha o
    desenho. Rótulo de tabela seguido de valor ("Receita total" e "3.081,4") ou de outra célula
    não se une; número, palavra partida em minúscula e pontuação colada à palavra, sim.
    """
    fim, inicio = a.texto[-1], b.texto[0]
    if fim.isspace() or inicio.isspace():
        return False
    if fim.isdigit():
        return inicio.isdigit() or inicio in ".,%-"
    if fim in ".,$":
        return inicio.isdigit()
    if fim.isalpha():
        return inicio.islower() or inicio in ",.:;-"
    if fim in "%)":
        return inicio in ",.;:"
    return fim == "(" and inicio.isalnum()


def _numero_quebrado_na_quebra_de_linha(a: Linha, b: Linha) -> bool:
    """A linha termina no meio de um número e a seguinte, abaixo, o continua ("R$1" / ".701,2")."""
    if b.baseline <= a.baseline_fim:
        return False
    fim, inicio = a.texto, b.texto
    if fim[-1].isdigit() and len(inicio) > 1 and inicio[0] in ".," and inicio[1].isdigit():
        return True
    return len(fim) > 1 and fim[-1] == "," and fim[-2].isdigit() and inicio[0].isdigit()


def _anexar(base: Linha, outra: Linha) -> None:
    base.texto += outra.texto
    base.baseline_fim = outra.baseline_fim
    base.x1 = max(base.x1, outra.x1)
    base.y0 = min(base.y0, outra.y0)
    base.y1 = max(base.y1, outra.y1)
    base.tamanho = max(base.tamanho, outra.tamanho)
