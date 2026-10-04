"""E0 da B3: release de resultados trimestral mais recente da própria B3 S.A. (B3SA3).

O site de RI (ri.b3.com.br) monta a lista no navegador a partir da API de arquivos da MZIQ;
o script chama a mesma API direto.
"""

from pathlib import Path

import httpx

from sunontent import persistencia
from sunontent.ingestao import comum
from sunontent.retentativa import FalhaTerminal
from sunontent.schemas import DocumentoFonte

FONTE = "b3"
TIPO_DOCUMENTO = "b3_release"
ID_EMPRESA_MZIQ = "5fd7b7d8-54a1-472d-8426-eb896ad8a3c4"
URL_ARQUIVOS = (
    f"https://apicatalog.mziq.com/filemanager/company/{ID_EMPRESA_MZIQ}/filter/categories/meta"
)
CATEGORIA = "central_de_resultados_release_de_resultados"
IDIOMA = "pt_BR"


def doc_id(ano: int, trimestre: int) -> str:
    return f"{TIPO_DOCUMENTO}_{ano}_{trimestre}T"


def mais_recente(documentos: list[dict]) -> dict | None:
    """Release publicado por último; desempate por ano e trimestre."""
    candidatos = [
        d
        for d in documentos
        if d.get("file_published_date")
        and d.get("file_year")
        and d.get("file_quarter")
        and (d.get("link_url") or d.get("permalink"))
        and d.get("is_published", True)
        and d.get("language_code", IDIOMA) == IDIOMA
        and d.get("category_internal_name", CATEGORIA) == CATEGORIA
    ]
    if not candidatos:
        return None
    return max(
        candidatos,
        key=lambda d: (d["file_published_date"], int(d["file_year"]), int(d["file_quarter"])),
    )


def localizar_ultima(cliente_http: httpx.Client) -> tuple[int, int, str]:
    """Ano, trimestre e URL do PDF do release mais recente."""
    resposta = comum.baixar_json(
        cliente_http,
        FONTE,
        URL_ARQUIVOS,
        metodo="POST",
        json={"categoryInternalNames": [CATEGORIA], "language": IDIOMA, "published": True},
    )
    try:
        documentos = resposta["data"]["document_metas"] if resposta.get("success") else []
    except (KeyError, TypeError, AttributeError):
        documentos = []
    escolhido = mais_recente(documentos or [])
    if escolhido is None:
        raise FalhaTerminal(f"{FONTE}: release de resultados não localizado em {URL_ARQUIVOS}")
    url_pdf = escolhido.get("link_url") or escolhido["permalink"]
    return int(escolhido["file_year"]), int(escolhido["file_quarter"]), url_pdf


def coletar(
    *,
    run_id: str,
    repositorio: persistencia.Repositorio,
    raiz_dados: Path,
    cliente_http: httpx.Client,
    relogio=comum.agora_utc,
) -> DocumentoFonte:
    ano, trimestre, url_pdf = localizar_ultima(cliente_http)
    return comum.coletar_documento(
        cliente_http=cliente_http,
        repositorio=repositorio,
        raiz_dados=raiz_dados,
        run_id=run_id,
        fonte=FONTE,
        tipo_documento=TIPO_DOCUMENTO,
        doc_id=doc_id(ano, trimestre),
        url_pdf=url_pdf,
        relogio=relogio,
    )
