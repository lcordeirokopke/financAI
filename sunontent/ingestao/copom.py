"""E0 do Copom: ata mais recente, pela API JSON do site do Banco Central."""

from pathlib import Path

import httpx

from sunontent import persistencia
from sunontent.ingestao import comum
from sunontent.retentativa import FalhaTerminal
from sunontent.schemas import DocumentoFonte

FONTE = "copom"
TIPO_DOCUMENTO = "copom_ata"
URL_ATAS = "https://www.bcb.gov.br/api/servico/sitebcb/copom/atas"
URL_ATA_DETALHES = "https://www.bcb.gov.br/api/servico/sitebcb/copom/atas_detalhes"


def doc_id(nro_reuniao: int) -> str:
    return f"{TIPO_DOCUMENTO}_{nro_reuniao}"


def localizar_ultima(cliente_http: httpx.Client) -> tuple[int, str]:
    """Número da reunião e URL do PDF da ata mais recente."""
    atas = comum.baixar_json(cliente_http, FONTE, URL_ATAS, params={"quantidade": 1})
    try:
        nro_reuniao = int(atas["conteudo"][0]["nroReuniao"])
    except (KeyError, IndexError, TypeError, ValueError) as erro:
        raise FalhaTerminal(f"{FONTE}: ata mais recente não localizada em {URL_ATAS}") from erro

    detalhes = comum.baixar_json(
        cliente_http, FONTE, URL_ATA_DETALHES, params={"nro_reuniao": nro_reuniao}
    )
    try:
        url_pdf = detalhes["conteudo"][0]["urlPdfAta"]
    except (KeyError, IndexError, TypeError) as erro:
        url_pdf = None
    if not url_pdf:
        raise FalhaTerminal(
            f"{FONTE}: PDF da ata {nro_reuniao} não localizado em {URL_ATA_DETALHES}"
        )
    return nro_reuniao, url_pdf


def coletar(
    *,
    run_id: str,
    repositorio: persistencia.Repositorio,
    raiz_dados: Path,
    cliente_http: httpx.Client,
    relogio=comum.agora_utc,
) -> DocumentoFonte:
    comum.avisar(f"{FONTE}: localizando a ata mais recente")
    nro_reuniao, url_pdf = localizar_ultima(cliente_http)
    return comum.coletar_documento(
        cliente_http=cliente_http,
        repositorio=repositorio,
        raiz_dados=raiz_dados,
        run_id=run_id,
        fonte=FONTE,
        tipo_documento=TIPO_DOCUMENTO,
        doc_id=doc_id(nro_reuniao),
        url_pdf=url_pdf,
        relogio=relogio,
    )
