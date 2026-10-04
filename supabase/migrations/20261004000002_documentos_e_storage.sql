-- Documentos fonte e coletas (E0).
-- Regra: todo documento fica armazenado, endereçado por doc_sha256, e nunca é sobrescrito nem apagado.
-- Cada download é uma coleta; várias coletas podem apontar para o mesmo documento.

-- Um documento físico por hash. O PDF fica no bucket 'documentos' em <fonte>/<doc_sha256>.pdf.
create table documentos (
  doc_sha256     char(64) primary key check (doc_sha256 ~ '^[0-9a-f]{64}$'),
  fonte          fonte not null,
  tipo_documento tipo_documento not null,
  storage_path   text not null unique,
  tamanho_bytes  bigint not null check (tamanho_bytes > 0 and tamanho_bytes <= 52428800),
  criado_em      timestamptz not null default now(),
  check (storage_path = fonte::text || '/' || doc_sha256 || '.pdf')
);

comment on table documentos is 'Documento fonte imutável, um por doc_sha256.';
comment on column documentos.doc_sha256 is 'SHA-256 dos bytes baixados, hex minúsculo.';
-- O formato PDF é validado pela E0 só pelos primeiros bytes (%PDF-), antes de qualquer gravação.

create trigger documentos_imutavel
  before update or delete on documentos
  for each row execute function bloquear_alteracao();

create trigger documentos_sem_truncate
  before truncate on documentos
  for each statement execute function bloquear_alteracao();

-- Um download. Guarda os metadados do DocumentoFonte (docs/fluxos/ingestao.md, Arquivo de metadados
-- e Contrato de saída). O vínculo com o run fica em runs.coleta_id (20261004000003_runs.sql).
create table coletas (
  id          bigint generated always as identity primary key,
  doc_sha256  char(64) not null references documentos (doc_sha256),
  doc_id      text not null,
  url_origem  text not null,
  coletado_em timestamptz not null,
  criado_em   timestamptz not null default now(),
  unique (id, doc_id, doc_sha256, url_origem, coletado_em)  -- alvo da FK composta de runs
);

comment on column coletas.doc_id is 'Identificador legível, ex: copom_ata_273. Mesmo doc_id com hash diferente = republicação.';
comment on column coletas.url_origem is 'URL de onde vieram os bytes do PDF, não a da página de listagem.';
-- PENDENTE: doc_id da CVM (cvm_fato_relevante_<Codigo_CVM>_<numProtocolo>) muda a cada versão do
-- documento, porque a CVM gera numProtocolo novo; e doc_id da B3 (b3_release_<ano>_<trimestre>T)
-- não confirmado (docs/fluxos/ingestao.md, Pendências).

create index coletas_doc_sha256_idx on coletas (doc_sha256);
create index coletas_doc_id_idx on coletas (doc_id);
create index coletas_coletado_em_idx on coletas (coletado_em desc);

create trigger coletas_imutavel
  before update or delete on coletas
  for each row execute function bloquear_alteracao();

create trigger coletas_sem_truncate
  before truncate on coletas
  for each statement execute function bloquear_alteracao();

-- Bucket privado dos PDFs. O db reset recria o banco, mas não apaga o bucket: se ele já existe,
-- a configuração é reaplicada. Os arquivos dentro dele não são alterados.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('documentos', 'documentos', false, 52428800, array['application/pdf'])
on conflict (id) do update
  set public             = excluded.public,
      file_size_limit    = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;

-- Bloqueia sobrescrita e exclusão de objetos do bucket 'documentos'.
-- O service role ignora RLS, então a garantia é por trigger e não por policy. O pipeline envia
-- ao bucket sem upsert e nunca apaga objetos; um caminho existente devolve 400 Asset Already Exists.
-- O trigger fica em storage.objects e a função em public, fora do schema gerenciado storage.
-- PENDENTE: testar no Supabase local e no do site: (1) o primeiro upload passa pelo trigger;
-- (2) upload com upsert em caminho existente falha; (3) remove falha e o arquivo continua
-- baixável; (4) a coluna storage.objects.version existe.
create or replace function public.storage_documentos_imutavel()
returns trigger
language plpgsql
as $$
begin
  if old.bucket_id = 'documentos' then
    if tg_op = 'DELETE' then
      raise exception 'objetos do bucket documentos não podem ser apagados';
    end if;
    -- Atualizações de metadado de acesso são permitidas; troca de conteúdo, nome ou bucket não.
    if new.bucket_id is distinct from old.bucket_id
       or new.name is distinct from old.name
       or new.version is distinct from old.version then
      raise exception 'objetos do bucket documentos não podem ser sobrescritos';
    end if;
  end if;
  return case when tg_op = 'DELETE' then old else new end;
end;
$$;

create trigger documentos_bucket_imutavel
  before update or delete on storage.objects
  for each row execute function public.storage_documentos_imutavel();
