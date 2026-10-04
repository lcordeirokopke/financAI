"""E0 da CVM: fato relevante mais recente de qualquer companhia aberta.

A lista vem do conjunto de dados aberto IPE da CVM (um ZIP anual com um CSV). O PDF vem do
`Link_Download` (RAD/ENET), que responde com Content-Type text/html: o formato é validado
só pelos primeiros bytes.
"""

import csv
import io
import re
import zipfile
from pathlib import Path

import httpx

from sunontent import persistencia
from sunontent.ingestao import comum
from sunontent.retentativa import FalhaTerminal
from sunontent.schemas import DocumentoFonte

FONTE = "cvm"
TIPO_DOCUMENTO = "cvm_fato_relevante"
URL_IPE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{ano}.zip"
CATEGORIA = "Fato Relevante"
CODIFICACAO_CSV = "latin-1"


def _num_protocolo(link: str) -> int | None:
    achado = re.search(r"[?&]numProtocolo=(\d+)", link)
    return int(achado.group(1)) if achado else None


def doc_id(codigo_cvm: str, num_protocolo: int) -> str:
    return f"{TIPO_DOCUMENTO}_{codigo_cvm}_{num_protocolo}"


def _linhas_ipe(fonte_url: str, conteudo_zip: bytes) -> list[dict[str, str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo_zip)) as arquivo:
            nomes = [n for n in arquivo.namelist() if n.lower().endswith(".csv")]
            if not nomes:
                raise FalhaTerminal(f"{FONTE}: ZIP de {fonte_url} sem CSV")
            texto = arquivo.read(nomes[0]).decode(CODIFICACAO_CSV)
    except zipfile.BadZipFile as erro:
        raise FalhaTerminal(f"{FONTE}: resposta de {fonte_url} não é um ZIP válido") from erro
    return list(csv.DictReader(io.StringIO(texto), delimiter=";"))


def mais_recente(linhas: list[dict[str, str]]) -> tuple[str, int, str] | None:
    """(Codigo_CVM, numProtocolo, Link_Download) do fato relevante entregue por último.

    Desempate no mesmo dia pelo numProtocolo, que é crescente.
    """
    candidatos = []
    for linha in linhas:
        if linha.get("Categoria") != CATEGORIA:
            continue
        link = (linha.get("Link_Download") or "").strip()
        protocolo = _num_protocolo(link)
        codigo = (linha.get("Codigo_CVM") or "").strip()
        entrega = (linha.get("Data_Entrega") or "").strip()
        if not link or protocolo is None or not codigo or not entrega:
            continue
        candidatos.append((entrega, protocolo, codigo, link))
    if not candidatos:
        return None
    _, protocolo, codigo, link = max(candidatos)
    return codigo, protocolo, link


def localizar_ultima(cliente_http: httpx.Client, ano: int) -> tuple[str, int, str]:
    """Procura no ano corrente e, se não houver fato relevante ainda, no anterior."""
    for ano_busca in (ano, ano - 1):
        url = URL_IPE.format(ano=ano_busca)
        try:
            conteudo = comum.baixar_bytes(cliente_http, FONTE, url)
        except comum.NaoEncontrado:
            if ano_busca == ano:
                continue  # arquivo do ano novo ainda não publicado
            raise
        achado = mais_recente(_linhas_ipe(url, conteudo))
        if achado is not None:
            return achado
    raise FalhaTerminal(
        f"{FONTE}: nenhum fato relevante em {URL_IPE.format(ano=ano)} nem em {URL_IPE.format(ano=ano - 1)}"
    )


def coletar(
    *,
    run_id: str,
    repositorio: persistencia.Repositorio,
    raiz_dados: Path,
    cliente_http: httpx.Client,
    relogio=comum.agora_utc,
) -> DocumentoFonte:
    ano = relogio().year
    codigo, protocolo, url_pdf = localizar_ultima(cliente_http, ano)
    return comum.coletar_documento(
        cliente_http=cliente_http,
        repositorio=repositorio,
        raiz_dados=raiz_dados,
        run_id=run_id,
        fonte=FONTE,
        tipo_documento=TIPO_DOCUMENTO,
        doc_id=doc_id(codigo, protocolo),
        url_pdf=url_pdf,
        relogio=relogio,
    )
