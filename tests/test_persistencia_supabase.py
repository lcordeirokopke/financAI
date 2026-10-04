"""Integração da E0 com a cópia local do Supabase CLI (supabase start).

Cobre o que o repositório em memória não reproduz: constraints, triggers de imutabilidade e o
bucket `documentos`. Pulado se SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY e SUPABASE_DB_URL não
estiverem no ambiente ou se o Supabase local não estiver no ar. Limpeza: supabase db reset.
"""

import os
import secrets
from datetime import datetime, timezone

import pytest

from sunontent import persistencia
from sunontent.ingestao import comum
from sunontent.retentativa import FalhaTerminal

pytestmark = pytest.mark.supabase


@pytest.fixture(scope="module")
def ambiente():
    faltando = [v for v in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_DB_URL") if not os.environ.get(v)]
    if faltando:
        pytest.skip(f"Supabase local não configurado: faltam {', '.join(faltando)}")
    psycopg = pytest.importorskip("psycopg")
    try:
        psycopg.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=3).close()
    except psycopg.OperationalError as erro:
        pytest.skip(f"Supabase local fora do ar: {erro}")
    return os.environ


@pytest.fixture
def repositorio(ambiente):
    from supabase import create_client

    cliente = create_client(ambiente["SUPABASE_URL"], ambiente["SUPABASE_SERVICE_ROLE_KEY"])
    return persistencia.RepositorioSupabase(cliente, ambiente["SUPABASE_DB_URL"])


def novo_run(db_url: str) -> str:
    import psycopg

    run_id = f"copom_20261004T142205Z_{secrets.token_hex(3)}"
    with psycopg.connect(db_url) as conexao:
        conexao.execute(
            "insert into runs (run_id, \"timestamp\", modo, fonte, modelos, prompts, level_specs,"
            " glossario_versao, arquivos_sha256, \"K\")"
            " values (%s, now(), 'normal', 'copom', '{}', '{}', '{}', 1, '{}', 2)",
            (run_id,),
        )
    return run_id


def test_coleta_completa_e_reaproveitamento(repositorio, ambiente, tmp_path):
    dados = b"%PDF-1.7\n% integracao " + secrets.token_bytes(16) + b"\n%%EOF\n"
    sha = comum.sha256_hex(dados)
    coletado_em = datetime(2026, 10, 4, 14, 22, 5, tzinfo=timezone.utc)

    for numero in (1, 2):
        run_id = novo_run(ambiente["SUPABASE_DB_URL"])
        persistencia.enviar_documento(repositorio, "copom", sha, dados)
        coleta = persistencia.registrar_coleta(
            repositorio, run_id=run_id, fonte="copom", tipo_documento="copom_ata",
            doc_sha256=sha, tamanho_bytes=len(dados), doc_id="copom_ata_999",
            url_origem="https://exemplo/ata.pdf", coletado_em=coletado_em,
        )
        assert repositorio.coleta_do_run(run_id) == coleta
        assert repositorio.documento_existe(sha)

    # Objeto existente: o envio direto é aceito como reaproveitamento, sem sobrescrever.
    repositorio.enviar_pdf(persistencia.caminho_storage("copom", sha), dados)

    # Run já vinculado: a transação é recusada.
    with pytest.raises(FalhaTerminal):
        repositorio.registrar_coleta(
            run_id=run_id, fonte="copom", tipo_documento="copom_ata", doc_sha256=sha,
            tamanho_bytes=len(dados), doc_id="copom_ata_999",
            url_origem="https://exemplo/ata.pdf", coletado_em=coletado_em,
        )

    # documentos e coletas são imutáveis.
    import psycopg

    with psycopg.connect(ambiente["SUPABASE_DB_URL"]) as conexao:
        for sql in (
            "update documentos set tamanho_bytes = tamanho_bytes where doc_sha256 = %s",
            "delete from coletas where doc_sha256 = %s",
        ):
            with pytest.raises(psycopg.Error, match="imutável"):
                with conexao.transaction():
                    conexao.execute(sql, (sha,))
