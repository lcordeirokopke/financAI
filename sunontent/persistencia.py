"""Única porta de gravação: Supabase (tabelas e Storage) e cópia local em data/.

Por enquanto só as funções da E0 (docs/fluxos/ingestao.md):
- envio do PDF ao bucket `documentos`, sem upsert;
- transação de `documentos`, `coletas` e vínculo em `runs`, com releitura de `runs.coleta_id`;
- cópia local em data/sources/<fonte>/.

As funções recebem o repositório (Supabase ou, nos testes, em memória) e a pasta raiz de dados
por parâmetro.
"""

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from sunontent.retentativa import FalhaRetriavel, FalhaTerminal, com_retentativa
from sunontent.schemas import DocumentoFonte

BUCKET_DOCUMENTOS = "documentos"


@dataclass(frozen=True)
class Coleta:
    """Linha de `coletas` vinculada ao run."""

    coleta_id: int
    doc_id: str
    doc_sha256: str
    url_origem: str
    coletado_em: datetime


class Repositorio(Protocol):
    """Operações da E0 no Supabase.

    Cada método traduz os erros do cliente para FalhaRetriavel ou FalhaTerminal.
    """

    def documento_existe(self, doc_sha256: str) -> bool: ...

    def enviar_pdf(self, caminho_storage: str, dados: bytes) -> None:
        """Envia sem upsert. Objeto já existente ("Asset Already Exists") não é falha."""
        ...

    def registrar_coleta(
        self,
        *,
        run_id: str,
        fonte: str,
        tipo_documento: str,
        doc_sha256: str,
        tamanho_bytes: int,
        doc_id: str,
        url_origem: str,
        coletado_em: datetime,
    ) -> Coleta:
        """Numa única transação: documentos (sem efeito se o hash existe), coletas e runs."""
        ...

    def coleta_do_run(self, run_id: str) -> Coleta | None:
        """Coleta já vinculada ao run, ou None se `runs.coleta_id` está vazio."""
        ...


def caminho_storage(fonte: str, doc_sha256: str) -> str:
    return f"{fonte}/{doc_sha256}.pdf"


def enviar_documento(repositorio: Repositorio, fonte: str, doc_sha256: str, dados: bytes) -> None:
    """Envia o PDF ao bucket se o hash ainda não está em `documentos`."""
    existe = com_retentativa(
        lambda: repositorio.documento_existe(doc_sha256),
        f"consulta de {doc_sha256} em documentos",
    )
    if existe:
        return
    destino = caminho_storage(fonte, doc_sha256)
    com_retentativa(
        lambda: repositorio.enviar_pdf(destino, dados),
        f"envio de {destino} ao bucket {BUCKET_DOCUMENTOS}",
    )


def registrar_coleta(
    repositorio: Repositorio,
    *,
    run_id: str,
    fonte: str,
    tipo_documento: str,
    doc_sha256: str,
    tamanho_bytes: int,
    doc_id: str,
    url_origem: str,
    coletado_em: datetime,
) -> Coleta:
    """Grava documentos, coletas e o vínculo em runs.

    Se a resposta da transação se perde, relê `runs.coleta_id` e só repete se estiver vazio.
    """

    def reler() -> Coleta | None:
        return com_retentativa(
            lambda: repositorio.coleta_do_run(run_id),
            f"releitura de runs.coleta_id do run {run_id}",
        )

    return com_retentativa(
        lambda: repositorio.registrar_coleta(
            run_id=run_id,
            fonte=fonte,
            tipo_documento=tipo_documento,
            doc_sha256=doc_sha256,
            tamanho_bytes=tamanho_bytes,
            doc_id=doc_id,
            url_origem=url_origem,
            coletado_em=coletado_em,
        ),
        f"transação da coleta do run {run_id}",
        antes_de_repetir=reler,
    )


def _pasta_fonte(raiz_dados: Path, fonte: str) -> Path:
    return Path(raiz_dados) / "sources" / fonte


def _gravar_atomico(destino: Path, dados: bytes) -> None:
    """Grava num temporário da mesma pasta e renomeia no fim."""
    temporario = destino.with_name(f".{destino.name}.{uuid.uuid4().hex}.tmp")
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        with open(temporario, "xb") as arquivo:
            arquivo.write(dados)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, destino)
    except PermissionError as erro:
        temporario.unlink(missing_ok=True)
        raise FalhaTerminal(
            f"não foi possível gravar {destino}: {erro}. Feche o arquivo {destino} "
            "se ele estiver aberto em outro programa."
        ) from erro
    except OSError as erro:
        temporario.unlink(missing_ok=True)
        raise FalhaTerminal(f"não foi possível gravar {destino}: {erro}") from erro


def gravar_pdf_local(raiz_dados: Path, fonte: str, doc_sha256: str, dados: bytes) -> Path:
    """Grava data/sources/<fonte>/<doc_sha256>.pdf só se ainda não existe."""
    destino = _pasta_fonte(raiz_dados, fonte) / f"{doc_sha256}.pdf"
    if not destino.exists():
        _gravar_atomico(destino, dados)
    return destino


def _utc_iso(momento: datetime) -> str:
    return momento.strftime("%Y-%m-%dT%H:%M:%SZ")


def gravar_metadados_coleta(raiz_dados: Path, fonte: str, documento: DocumentoFonte) -> Path:
    """Grava data/sources/<fonte>/<doc_sha256>.<AAAAMMDDTHHMMSSZ>.json a partir do DocumentoFonte."""
    carimbo = documento.coletado_em.strftime("%Y%m%dT%H%M%SZ")
    destino = _pasta_fonte(raiz_dados, fonte) / f"{documento.doc_sha256}.{carimbo}.json"
    conteudo = {
        "doc_id": documento.doc_id,
        "doc_sha256": documento.doc_sha256,
        "url_origem": documento.url_origem,
        "coletado_em": _utc_iso(documento.coletado_em),
    }
    texto = json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n"
    _gravar_atomico(destino, texto.encode("utf-8"))
    return destino


class RepositorioSupabase:
    """Repositório real: Storage pela API do Supabase e tabelas pela conexão Postgres.

    Abre uma conexão nova por operação, para que uma conexão perdida não contamine a
    tentativa seguinte.
    """

    def __init__(self, cliente, db_url: str, connect_timeout_s: int = 10):
        self._cliente = cliente
        self._db_url = db_url
        self._connect_timeout_s = connect_timeout_s

    def _conectar(self):
        import psycopg

        try:
            return psycopg.connect(self._db_url, connect_timeout=self._connect_timeout_s)
        except psycopg.OperationalError as erro:
            raise FalhaRetriavel(f"conexão com o banco recusada: {erro}") from erro

    def _executar(self, operacao):
        import psycopg

        try:
            with self._conectar() as conexao:
                return operacao(conexao)
        except (FalhaRetriavel, FalhaTerminal):
            raise
        except (psycopg.OperationalError, psycopg.errors.QueryCanceled) as erro:
            raise FalhaRetriavel(f"banco: {erro}") from erro
        except psycopg.Error as erro:
            raise FalhaTerminal(f"banco recusou a gravação: {erro}") from erro

    def documento_existe(self, doc_sha256: str) -> bool:
        def consulta(conexao):
            linha = conexao.execute(
                "select 1 from documentos where doc_sha256 = %s", (doc_sha256,)
            ).fetchone()
            return linha is not None

        return self._executar(consulta)

    def enviar_pdf(self, caminho_storage: str, dados: bytes) -> None:
        import httpx

        try:
            # Sem a opção upsert: o Storage recusa caminho existente.
            self._cliente.storage.from_(BUCKET_DOCUMENTOS).upload(
                caminho_storage, dados, {"content-type": "application/pdf"}
            )
        except (httpx.TimeoutException, httpx.TransportError) as erro:
            raise FalhaRetriavel(f"bucket {BUCKET_DOCUMENTOS}: {erro}") from erro
        except Exception as erro:
            status, mensagem = _status_storage(erro)
            if _objeto_ja_existe(status, mensagem):
                return
            if status is not None and status >= 500:
                raise FalhaRetriavel(f"bucket {BUCKET_DOCUMENTOS}: HTTP {status} {mensagem}") from erro
            raise FalhaTerminal(
                f"bucket {BUCKET_DOCUMENTOS} recusou {caminho_storage}: HTTP {status} {mensagem}"
            ) from erro

    def registrar_coleta(
        self,
        *,
        run_id: str,
        fonte: str,
        tipo_documento: str,
        doc_sha256: str,
        tamanho_bytes: int,
        doc_id: str,
        url_origem: str,
        coletado_em: datetime,
    ) -> Coleta:
        def transacao(conexao):
            with conexao.transaction():
                conexao.execute(
                    "insert into documentos (doc_sha256, fonte, tipo_documento, storage_path, tamanho_bytes)"
                    " values (%s, %s, %s, %s, %s) on conflict (doc_sha256) do nothing",
                    (doc_sha256, fonte, tipo_documento, caminho_storage(fonte, doc_sha256), tamanho_bytes),
                )
                coleta_id, coletado_em_banco = conexao.execute(
                    "insert into coletas (doc_sha256, doc_id, url_origem, coletado_em)"
                    " values (%s, %s, %s, %s) returning id, coletado_em",
                    (doc_sha256, doc_id, url_origem, coletado_em),
                ).fetchone()
                vinculo = conexao.execute(
                    "update runs set doc_id = %s, doc_sha256 = %s, coleta_id = %s, url_origem = %s,"
                    " coletado_em = %s where run_id = %s and coleta_id is null",
                    (doc_id, doc_sha256, coleta_id, url_origem, coletado_em_banco, run_id),
                )
                if vinculo.rowcount != 1:
                    raise FalhaTerminal(
                        f"run {run_id} não existe em runs ou já tem coleta vinculada"
                    )
            return Coleta(coleta_id, doc_id, doc_sha256, url_origem, coletado_em_banco)

        return self._executar(transacao)

    def coleta_do_run(self, run_id: str) -> Coleta | None:
        def consulta(conexao):
            linha = conexao.execute(
                "select coleta_id, doc_id, doc_sha256, url_origem, coletado_em"
                " from runs where run_id = %s and coleta_id is not null",
                (run_id,),
            ).fetchone()
            return Coleta(*linha) if linha else None

        return self._executar(consulta)


def _status_storage(erro: Exception) -> tuple[int | None, str]:
    """Extrai status HTTP e mensagem de uma exceção do cliente de Storage."""
    dados = erro.args[0] if erro.args and isinstance(erro.args[0], dict) else {}
    status = getattr(erro, "status", None) or dados.get("statusCode") or dados.get("status")
    mensagem = getattr(erro, "message", None) or dados.get("message") or dados.get("error") or str(erro)
    try:
        status = int(status) if status is not None else None
    except (TypeError, ValueError):
        status = None
    return status, str(mensagem)


def _objeto_ja_existe(status: int | None, mensagem: str) -> bool:
    texto = mensagem.lower()
    return status == 409 or "already exists" in texto or "duplicate" in texto
