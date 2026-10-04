-- Extensões e tipos fechados do contrato do pipeline.
-- Fonte dos valores: docs/arquiteturas.md (Objetos de dado) e docs/fluxos/ingestao.md.

create extension if not exists vector with schema extensions;

-- Audiência (docs/arquiteturas.md:36)
create type nivel as enum ('iniciante', 'intermediario', 'avancado');

-- Formato de mídia (docs/arquiteturas.md:37)
create type formato as enum ('artigo', 'carrossel', 'roteiro');

-- Fonte de coleta da E0 (argumento da CLI: python -m sunontent <fonte>)
create type fonte as enum ('copom', 'cvm', 'b3');

-- Tipo de documento, 1:1 com a fonte (docs/arquiteturas.md:84, docs/fluxos/ingestao.md:16-20)
create type tipo_documento as enum ('copom_ata', 'cvm_fato_relevante', 'b3_release');

-- Unidade de Numero (docs/arquiteturas.md:53)
-- PENDENTE: como a unidade 'data' é representada em valor Decimal não está definido.
create type unidade_numero as enum ('pct', 'pp', 'BRL', 'BRL_mi', 'x', 'contagem', 'data');

-- Claim.tipo (docs/arquiteturas.md:71)
create type tipo_claim as enum ('decisao', 'projecao', 'condicionante', 'resultado', 'risco');

-- Slide.papel (docs/arquiteturas.md:128)
create type papel_slide as enum ('gancho', 'corpo', 'conclusao');

-- CelulaState.estado (docs/arquiteturas.md:550)
-- PENDENTE: a E8 cita "aprovada com ressalva do juiz" (docs/arquiteturas.md:466), estado que não existe aqui.
create type estado_celula as enum ('PENDENTE', 'GERANDO', 'AVALIANDO', 'APROVADA', 'REPROVADA', 'ERRO_INFRA');

-- Scorecard.veredito (docs/arquiteturas.md:182)
create type veredito as enum ('APROVADA', 'REPROVADA', 'ERRO_INFRA');

-- Modo de execução: normal (com E0) ou --dev (documento de referência).
-- PENDENTE: o modo não é campo do RunManifest na documentação.
create type modo_run as enum ('normal', 'dev');

-- PENDENTE: status do run e persistência de runs abortados na E0 não estão definidos.
create type status_run as enum ('em_andamento', 'concluido', 'abortado');

-- Classe de falha (docs/arquiteturas.md:669, docs/fluxos/ingestao.md:222-234)
create type classe_falha as enum ('retriavel', 'terminal');

-- Decisão humana por célula na E8 (docs/arquiteturas.md:468: "publica ou descarta")
create type decisao_humana as enum ('publicar', 'descartar');

-- Imutabilidade: bloqueia update e delete em tabelas append-only.
create or replace function bloquear_alteracao()
returns trigger
language plpgsql
as $$
begin
  raise exception 'tabela % é imutável: % não permitido', tg_table_name, tg_op;
end;
$$;
