-- E8 (decisão humana), E9 (materialização no Figma) e peças publicadas.

-- Decisão humana por célula (docs/arquiteturas.md:468-472): registrada, nunca descartada.
-- PENDENTE: a documentação não define schema; autor, motivo e vínculo com a tentativa são inferidos.
create table decisoes_humanas (
  id          bigint generated always as identity primary key,
  run_id      text not null,
  celula_id   text not null,
  tentativa   int not null,
  decisao     decisao_humana not null,
  motivo      text,  -- ex: tom, oportunidade editorial, repetição (docs/arquiteturas.md:476)
  autor       text not null,
  decidido_em timestamptz not null default now(),
  foreign key (run_id, celula_id, tentativa) references pecas (run_id, celula_id, tentativa)
);

create index decisoes_humanas_celula_idx on decisoes_humanas (run_id, celula_id);

create trigger decisoes_humanas_imutavel
  before update or delete on decisoes_humanas
  for each row execute function bloquear_alteracao();

-- Materialização de carrossel publicado no Figma (docs/arquiteturas.md:478-500, docs/figma-integracao.md).
-- PENDENTE: a documentação não define schema; colunas inferidas dos dados citados.
create table materializacoes_figma (
  id             bigint generated always as identity primary key,
  run_id         text not null,
  celula_id      text not null,
  tentativa      int not null,
  file_key       text not null,
  frame_node_id  text,
  node_ids       jsonb,  -- node ids devolvidos ao trace (docs/arquiteturas.md:488)
  rota           text,   -- PENDENTE: rota A ou B (docs/figma-integracao.md:72-86)
  texto_relido   jsonb,  -- readback via GET /v1/files/{key}
  diff           jsonb,  -- diferença entre texto relido e CarrosselPayload
  criado_em      timestamptz not null default now(),
  foreign key (run_id, celula_id, tentativa) references pecas (run_id, celula_id, tentativa)
);

-- Peças publicadas, para detecção de repetição por similaridade (pgvector).
-- PENDENTE: mecanismo de detecção de repetição não descrito na documentação; repetição aparece
-- só como motivo de descarte (docs/arquiteturas.md:476).
-- PENDENTE: dimensão do embedding e se o texto publicado é o payload aprovado ou o relido do Figma.
create table pecas_publicadas (
  id            bigint generated always as identity primary key,
  run_id        text not null,
  celula_id     text not null,
  tentativa     int not null,
  decisao_id    bigint not null references decisoes_humanas (id),
  texto         text not null,
  embedding     extensions.vector,
  publicado_em  timestamptz not null default now(),
  unique (run_id, celula_id, tentativa),
  foreign key (run_id, celula_id, tentativa) references pecas (run_id, celula_id, tentativa)
);
