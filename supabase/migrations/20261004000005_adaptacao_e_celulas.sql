-- E4 (ConteudoAdaptado), células e E5 (Peca por tentativa).

-- ConteudoAdaptado (docs/arquiteturas.md:97-112). Um por nível, compartilhado pelas 3 células do
-- nível e nunca regerado no retry (docs/arquiteturas.md:529).
create table conteudos_adaptados (
  run_id             text not null references factsheets (run_id),
  nivel              nivel not null,
  tese               text not null,
  blocos             jsonb not null,  -- list[Bloco]: {texto, claim_ids[], analogias[{termo, explicacao}]}
  claims_usados      text[] not null,
  claims_descartados jsonb not null default '[]',  -- list[[claim_id, motivo]], auditoria na E8
  primary key (run_id, nivel)
);

-- Estado da célula (CelulaState, docs/arquiteturas.md:543-550). Sempre 9 por run.
create table celulas (
  run_id             text not null references runs (run_id),
  celula_id          text not null,
  nivel              nivel not null,
  formato            formato not null,
  estado             estado_celula not null default 'PENDENTE',
  tentativa          int not null default 0 check (tentativa >= 0),
  -- PENDENTE: motivo de REPROVADA (incluindo não convergência, docs/arquiteturas.md:451, 574)
  -- não tem campo na documentação.
  motivo_reprovacao  text,
  -- PENDENTE: contador de retry de parse separado de K (docs/arquiteturas.md:621) sem campo definido.
  tentativas_parse   int not null default 0,
  atualizado_em      timestamptz not null default now(),
  primary key (run_id, celula_id),
  check (celula_id = nivel::text || '__' || formato::text)
);

comment on column celulas.tentativa is
  'Última tentativa gerada. 0 = nenhuma. PENDENTE: CelulaState começa em 0 e Peca é 1-indexada.';

-- Peca, uma linha por tentativa (docs/arquiteturas.md:150-157). O histórico é necessário para o
-- Router comparar violações de tentativas seguidas (docs/arquiteturas.md:452).
create table pecas (
  run_id    text not null,
  celula_id text not null,
  tentativa int not null check (tentativa >= 1),
  nivel     nivel not null,
  formato   formato not null,
  payload   jsonb not null,   -- ArtigoPayload | CarrosselPayload | RoteiroPayload, discriminado por formato
  claim_ids text[] not null,  -- união dos claim_ids internos
  criado_em timestamptz not null default now(),
  primary key (run_id, celula_id, tentativa),
  foreign key (run_id, celula_id) references celulas (run_id, celula_id),
  check (celula_id = nivel::text || '__' || formato::text)
);

-- Rastreabilidade granular: cada unidade estrutural (seção, slide, cena) ligada aos seus claims
-- (docs/arquiteturas.md:367, 468, 661). Permite consulta claim -> peças e claim -> página do PDF.
create table peca_unidade_claims (
  run_id         text not null,
  celula_id      text not null,
  tentativa      int not null,
  unidade_indice int not null check (unidade_indice >= 0),  -- posição da seção, slide ou cena no payload
  claim_id       text not null,
  primary key (run_id, celula_id, tentativa, unidade_indice, claim_id),
  foreign key (run_id, celula_id, tentativa) references pecas (run_id, celula_id, tentativa),
  foreign key (run_id, claim_id) references claims (run_id, claim_id)
);

create index peca_unidade_claims_claim_idx on peca_unidade_claims (run_id, claim_id);
