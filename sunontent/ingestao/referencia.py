"""Modo --dev: lê e valida o documento de referência congelado, no lugar da E0.

Ver docs/fluxos/ingestao.md, Modo desenvolvimento. Nunca baixa nada: arquivo ausente ou hash
diferente param o run, e o .json de referência nunca é corrigido.
"""

import json
from datetime import datetime
from pathlib import Path

from sunontent import persistencia
from sunontent.ingestao import b3, comum, copom, cvm
from sunontent.retentativa import FalhaTerminal
from sunontent.schemas import DocumentoFonte

TIPO_DOCUMENTO = {
    copom.FONTE: copom.TIPO_DOCUMENTO,
    cvm.FONTE: cvm.TIPO_DOCUMENTO,
    b3.FONTE: b3.TIPO_DOCUMENTO,
}
CAMPOS = ("doc_id", "doc_sha256", "url_origem", "coletado_em")


def _metadados(arquivo: Path) -> dict:
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except ValueError as erro:
        raise FalhaTerminal(f"referência: {arquivo} não é JSON válido: {erro}") from erro
    ausentes = [campo for campo in CAMPOS if not isinstance(dados, dict) or not dados.get(campo)]
    if ausentes:
        raise FalhaTerminal(f"referência: {arquivo} sem os campos {', '.join(ausentes)}")
    return dados


def carregar(
    *,
    run_id: str,
    fonte: str,
    repositorio: persistencia.Repositorio,
    pasta_referencia: Path,
) -> DocumentoFonte:
    """Valida a referência da fonte, registra o documento no Supabase e devolve o DocumentoFonte."""
    pasta = Path(pasta_referencia)
    pdf = pasta / f"{fonte}.pdf"
    meta = pasta / f"{fonte}.json"
    for arquivo in (pdf, meta):
        if not arquivo.is_file():
            raise FalhaTerminal(
                f"referência: falta o arquivo {arquivo}. O modo --dev não baixa nada: "
                f"congele um documento de {fonte} em {pasta} (docs/fluxos/ingestao.md, Como congelar um documento)."
            )

    dados = _metadados(meta)
    conteudo = pdf.read_bytes()
    encontrado = comum.sha256_hex(conteudo)
    if encontrado != dados["doc_sha256"]:
        raise FalhaTerminal(
            f"referência: {pdf} tem hash {encontrado}, mas {meta} espera {dados['doc_sha256']}. "
            "A referência só muda pelo procedimento de congelamento."
        )

    try:
        documento = DocumentoFonte(
            caminho=pdf,
            doc_id=dados["doc_id"],
            doc_sha256=dados["doc_sha256"],
            url_origem=dados["url_origem"],
            coletado_em=datetime.fromisoformat(dados["coletado_em"]),
        )
    except (ValueError, TypeError) as erro:
        raise FalhaTerminal(f"referência: {meta} com metadados inválidos: {erro}") from erro

    persistencia.enviar_documento(repositorio, fonte, documento.doc_sha256, conteudo)
    persistencia.registrar_documento_referencia(
        repositorio,
        run_id=run_id,
        fonte=fonte,
        tipo_documento=TIPO_DOCUMENTO[fonte],
        doc_sha256=documento.doc_sha256,
        tamanho_bytes=len(conteudo),
        doc_id=documento.doc_id,
        url_origem=documento.url_origem,
        coletado_em=documento.coletado_em,
    )
    return documento
