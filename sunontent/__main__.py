"""Ponto de entrada: python -m sunontent <fonte> [--dev].

Lê os parâmetros, confere as credenciais do Supabase, gera o run_id, registra o run e escolhe a
entrada do grafo (E0 no modo normal, nó de referência no --dev). Ver docs/fluxos/ingestao.md.
"""

import argparse
import os
import secrets
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from sunontent import graph, manifesto, persistencia
from sunontent.ingestao import comum
from sunontent.retentativa import Falha
from sunontent.schemas import Fonte, PipelineState, RunManifest

RAIZ = Path(__file__).resolve().parent.parent
FONTES = ("copom", "cvm", "b3")


def gerar_run_id(fonte: str, momento: datetime) -> str:
    """<fonte>_<AAAAMMDDTHHMMSSZ>_<6 hex>"""
    return f"{fonte}_{momento:%Y%m%dT%H%M%SZ}_{secrets.token_hex(3)}"


def _ler_parametros(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m sunontent", description=__doc__.splitlines()[0])
    parser.add_argument("fonte", choices=FONTES, help="fonte do documento")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="usa o documento de referência de tests/fixtures/referencia/ em vez de baixar",
    )
    return parser.parse_args(argv)


def _abortar(
    repositorio: persistencia.Repositorio, raiz_dados: Path, manifest: RunManifest, classe: str, mensagem: str
) -> None:
    """Mostra o erro e registra o aborto. Uma falha ao registrar não esconde o erro original."""
    print(f"abortado ({classe}): {mensagem}", file=sys.stderr)
    try:
        persistencia.abortar_run(repositorio, raiz_dados, manifest, classe, mensagem)
    except Falha as falha:
        print(f"o aborto não foi registrado: {falha.mensagem}", file=sys.stderr)


def executar(
    fonte: Fonte,
    *,
    dev: bool,
    repositorio: persistencia.Repositorio,
    checkpointer,
    raiz: Path = RAIZ,
    cliente_http=None,
    relogio: Callable[[], datetime] = comum.agora_utc,
) -> int:
    """Roda um run. Devolve o código de saída: 0 concluído, 1 abortado."""
    momento = relogio()
    run_id = gerar_run_id(fonte, momento)
    raiz_dados = raiz / "data"
    manifest = manifesto.montar(
        raiz,
        run_id=run_id,
        timestamp=momento,
        modo="dev" if dev else "normal",
        fonte=fonte,
        k=graph.K,
    )
    persistencia.criar_run(repositorio, manifest)
    persistencia.gravar_manifest_local(raiz_dados, manifest, "em_andamento")
    print(f"run {run_id} ({manifest.modo})")

    configuravel = {
        "thread_id": run_id,
        "repositorio": repositorio,
        "raiz_dados": raiz_dados,
        "pasta_referencia": raiz / "tests" / "fixtures" / "referencia",
    }
    if cliente_http is not None:
        configuravel["cliente_http"] = cliente_http

    try:
        resultado = graph.construir_grafo(checkpointer).invoke(
            PipelineState(run_id=run_id, manifest=manifest),
            {"configurable": configuravel},
        )
    except Falha as falha:
        _abortar(repositorio, raiz_dados, manifest, falha.classe, falha.mensagem)
        return 1
    except Exception as erro:
        # Bug fora do contrato de falhas: registra como terminal, com o tipo da exceção, e propaga.
        _abortar(repositorio, raiz_dados, manifest, "terminal", f"{type(erro).__name__}: {erro}")
        raise

    documento = resultado["documento_fonte"]
    manifest = manifest.model_copy(
        update={
            "doc_id": documento.doc_id,
            "doc_sha256": documento.doc_sha256,
            "url_origem": documento.url_origem,
            "coletado_em": documento.coletado_em,
            "coleta_id": documento.coleta_id,
        }
    )
    persistencia.concluir_run(repositorio, raiz_dados, manifest)
    print(f"concluído: {documento.doc_id} ({documento.doc_sha256[:12]})")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parametros = _ler_parametros(argv)
    try:
        from dotenv import load_dotenv

        load_dotenv(RAIZ / ".env")
        repositorio = persistencia.criar_repositorio_supabase(os.environ)
        with persistencia.checkpointer_postgres(os.environ["SUPABASE_DB_URL"]) as checkpointer:
            return executar(
                parametros.fonte, dev=parametros.dev, repositorio=repositorio, checkpointer=checkpointer
            )
    except Falha as falha:
        # Antes de existir a linha em runs: credencial, conexão ou config inválida.
        print(f"erro ({falha.classe}): {falha.mensagem}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
