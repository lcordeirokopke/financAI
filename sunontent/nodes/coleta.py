"""E0. Coleta: chama o script da fonte em ingestao/ e coloca o DocumentoFonte no estado.

Dependências vêm de config["configurable"]:
- repositorio: persistencia.Repositorio (Supabase ou, nos testes, em memória);
- raiz_dados: pasta raiz de data/;
- cliente_http (opcional): httpx.Client; sem ele, o nó cria e fecha um.
"""

from pathlib import Path

from sunontent.ingestao import b3, comum, copom, cvm

SCRIPTS = {
    copom.FONTE: copom.coletar,
    cvm.FONTE: cvm.coletar,
    b3.FONTE: b3.coletar,
}


def coleta(state, config) -> dict:
    configuravel = config["configurable"]
    coletar = SCRIPTS[state.manifest.fonte]
    cliente_http = configuravel.get("cliente_http")
    proprio = cliente_http is None
    if proprio:
        cliente_http = comum.novo_cliente_http()
    try:
        documento = coletar(
            run_id=state.run_id,
            repositorio=configuravel["repositorio"],
            raiz_dados=Path(configuravel["raiz_dados"]),
            cliente_http=cliente_http,
        )
    finally:
        if proprio:
            cliente_http.close()
    return {"documento_fonte": documento}
