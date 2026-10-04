"""Partes comuns dos scripts de coleta (E0): HTTP, validação, hash e sequência de gravação.

Ordem obrigatória (docs/fluxos/ingestao.md, Modo normal):
1. baixa o documento inteiro para a memória, com limite de 50 MiB;
2. valida o formato e calcula o doc_sha256; se falhar, nada é gravado;
3. grava no Supabase: bucket e depois a transação de documentos, coletas e runs;
4. grava a cópia local: o PDF e depois o .json da coleta;
5. devolve o DocumentoFonte.
"""

import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from sunontent import persistencia
from sunontent.retentativa import FalhaRetriavel, FalhaTerminal, com_retentativa
from sunontent.schemas import DocumentoFonte

LIMITE_BYTES = 52_428_800  # 50 MiB, limite por arquivo do plano Free do Supabase
ASSINATURA_PDF = b"%PDF-"
USER_AGENT = "sunontent/0.1 (coleta de documentos financeiros publicos)"
TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class NaoEncontrado(FalhaTerminal):
    """HTTP 404: publicação ou arquivo inexistente na fonte."""


def novo_cliente_http() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
        follow_redirects=True,
    )


def _classificar_status(fonte: str, resposta: httpx.Response) -> None:
    status = resposta.status_code
    url = str(resposta.request.url)
    if status == 429 or status >= 500:
        raise FalhaRetriavel(f"{fonte}: HTTP {status} em {url}")
    if status == 404:
        raise NaoEncontrado(f"{fonte}: publicação não encontrada (HTTP 404) em {url}")
    if status >= 400:
        raise FalhaTerminal(f"{fonte}: HTTP {status} em {url}")


def _requisitar(
    cliente: httpx.Client,
    fonte: str,
    metodo: str,
    url: str,
    leitor: Callable[[httpx.Response], Any],
    **kwargs: Any,
) -> Any:
    """Uma requisição com retentativa. `leitor` consome a resposta ainda aberta."""

    def tentativa():
        try:
            with cliente.stream(metodo, url, **kwargs) as resposta:
                _classificar_status(fonte, resposta)
                return leitor(resposta)
        except httpx.TimeoutException as erro:
            raise FalhaRetriavel(f"{fonte}: tempo esgotado em {url}: {erro!r}") from erro
        except httpx.TransportError as erro:
            raise FalhaRetriavel(f"{fonte}: erro de conexão em {url}: {erro!r}") from erro

    return com_retentativa(tentativa, f"{fonte}: requisição a {url}")


def _ler_com_limite(fonte: str, resposta: httpx.Response) -> bytes:
    url = str(resposta.request.url)
    declarado = resposta.headers.get("Content-Length")
    if declarado is not None and declarado.isdigit() and int(declarado) > LIMITE_BYTES:
        raise FalhaTerminal(
            f"{fonte}: documento de {int(declarado)} bytes em {url} excede o limite de {LIMITE_BYTES} bytes"
        )
    partes = []
    total = 0
    for parte in resposta.iter_bytes():
        total += len(parte)
        if total > LIMITE_BYTES:
            raise FalhaTerminal(
                f"{fonte}: documento em {url} excede o limite de {LIMITE_BYTES} bytes"
                f" (lidos {total} bytes até a interrupção)"
            )
        partes.append(parte)
    return b"".join(partes)


def baixar_bytes(cliente: httpx.Client, fonte: str, url: str, metodo: str = "GET", **kwargs: Any) -> bytes:
    """Baixa a resposta inteira para a memória, com o limite de 50 MiB."""
    return _requisitar(cliente, fonte, metodo, url, lambda r: _ler_com_limite(fonte, r), **kwargs)


def baixar_json(cliente: httpx.Client, fonte: str, url: str, metodo: str = "GET", **kwargs: Any) -> Any:
    import json

    dados = baixar_bytes(cliente, fonte, url, metodo, **kwargs)
    try:
        return json.loads(dados)
    except ValueError as erro:
        raise FalhaTerminal(f"{fonte}: resposta de {url} não é JSON válido: {erro}") from erro


def validar_pdf(fonte: str, url: str, dados: bytes) -> None:
    """O formato é decidido só pelos primeiros bytes; o Content-Type é ignorado."""
    if not dados.startswith(ASSINATURA_PDF):
        inicio = dados[:40]
        raise FalhaTerminal(
            f"{fonte}: conteúdo baixado de {url} não é PDF (início: {inicio!r})"
        )


def sha256_hex(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def agora_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def coletar_documento(
    *,
    cliente_http: httpx.Client,
    repositorio: persistencia.Repositorio,
    raiz_dados: Path,
    run_id: str,
    fonte: str,
    tipo_documento: str,
    doc_id: str,
    url_pdf: str,
    relogio: Callable[[], datetime] = agora_utc,
) -> DocumentoFonte:
    """Baixa o PDF, valida, grava no Supabase e na cópia local e devolve o DocumentoFonte."""
    dados = baixar_bytes(cliente_http, fonte, url_pdf)
    coletado_em = relogio()
    validar_pdf(fonte, url_pdf, dados)
    doc_sha256 = sha256_hex(dados)

    persistencia.enviar_documento(repositorio, fonte, doc_sha256, dados)
    coleta = persistencia.registrar_coleta(
        repositorio,
        run_id=run_id,
        fonte=fonte,
        tipo_documento=tipo_documento,
        doc_sha256=doc_sha256,
        tamanho_bytes=len(dados),
        doc_id=doc_id,
        url_origem=url_pdf,
        coletado_em=coletado_em,
    )

    caminho = persistencia.gravar_pdf_local(raiz_dados, fonte, doc_sha256, dados)
    documento = DocumentoFonte(
        caminho=caminho,
        doc_id=coleta.doc_id,
        doc_sha256=coleta.doc_sha256,
        url_origem=coleta.url_origem,
        coletado_em=coleta.coletado_em,
        coleta_id=coleta.coleta_id,
    )
    persistencia.gravar_metadados_coleta(raiz_dados, fonte, documento)
    return documento
